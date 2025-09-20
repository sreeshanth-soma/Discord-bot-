import discord
from discord.ui import View, Button, Modal, TextInput
from discord import ButtonStyle
from discord.errors import HTTPException
import asyncio
import time
from utils.music_sources import MusicPlayer, YTDLSource
from ui.music_views import SpotifyMusicCard, FastMusicSearchModal, MusicPlayerView

# Global music player instance
music_player = None

# Rate limiting cooldown tracking
_last_error_message = {}
_error_cooldown = 2.0  # seconds

async def safe_send_message(channel_or_interaction, message, ephemeral=True, max_retries=3):
    """Safely send a message with rate limit handling and cooldown"""
    global _last_error_message
    
    # Check cooldown for error messages
    current_time = time.time()
    
    # Get user ID from channel or interaction
    if hasattr(channel_or_interaction, 'user'):
        user_id = channel_or_interaction.user.id
    elif hasattr(channel_or_interaction, 'author'):
        user_id = channel_or_interaction.author.id
    else:
        user_id = 0  # Unknown user
    
    if message.startswith("❌") and user_id in _last_error_message:
        if current_time - _last_error_message[user_id] < _error_cooldown:
            print(f"Rate limiting error message for user {user_id}")
            return False
    
    # Update cooldown for error messages
    if message.startswith("❌"):
        _last_error_message[user_id] = current_time
    
    # Try to send with retries
    for attempt in range(max_retries):
        try:
            if hasattr(channel_or_interaction, 'send'):  # Channel
                await channel_or_interaction.send(message)
            else:  # Interaction
                await channel_or_interaction.response.send_message(message, ephemeral=ephemeral)
            return True
        except HTTPException as e:
            if e.status == 429:  # Rate limited
                retry_after = e.retry_after if hasattr(e, 'retry_after') else 1.0
                print(f"Rate limited, waiting {retry_after}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(retry_after)
            else:
                print(f"HTTP error {e.status}: {e}")
                break
        except Exception as e:
            print(f"Error sending message: {e}")
            break
    
    print(f"Failed to send message after {max_retries} attempts")
    return False

def initialize_music_player(bot):
    """Initialize the global music player"""
    global music_player
    print("🎵 Initializing music player...")
    music_player = MusicPlayer(bot)
    print(f"✅ Music player initialized: {music_player}")
    return music_player

async def handle_music_command(message):
    """Handle !music and !player commands"""
    global music_player
    
    # Check if music player is initialized
    if music_player is None:
        await safe_send_message(message.channel, "❌ Music player is not initialized yet. Please wait a moment and try again.")
        return True

    if not message.author.voice:
        await safe_send_message(message.channel, "❌ You need to be in a voice channel to use the music player!")
        return True
    
    # Create the Spotify-like music card
    music_card = SpotifyMusicCard(music_player, message.guild.id)
    embed = await music_card.create_spotify_card()
    
    # Send the card and store the message reference
    sent_message = await message.channel.send(embed=embed, view=music_card)
    music_card.message = sent_message
    return True

async def handle_search_command(message):
    """Handle !search command"""
    parts = message.content.split(' ', 1)
    if len(parts) < 2:
        await safe_send_message(message.channel, "❌ Usage: `!search <song name>`")
        return True
    
    query = parts[1]
    
    # Create a mock context object
    class MockContext:
        def __init__(self, message):
            self.message = message
            self.author = message.author
            self.guild = message.guild
            self.channel = message.channel
    
    ctx = MockContext(message)
    
    # Since we can't send modal directly, we'll simulate the search
    if not message.author.voice:
        await safe_send_message(message.channel, "❌ You need to be in a voice channel!")
        return True
    
    # Search for the song
    loading_msg = await message.channel.send(f"🔍 Searching for: `{query}`...")
    
    url, title, duration, thumbnail, uploader, view_count = await YTDLSource.search_youtube(query)
    if not url:
        await loading_msg.edit(content="❌ No results found for your search.")
        return True
    
    # Show search result with option to play
    embed = discord.Embed(title="🔍 Search Result", color=0x3498db)
    embed.add_field(name="Title", value=title, inline=False)
    duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Unknown"
    embed.add_field(name="Duration", value=duration_str, inline=True)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    
    # Create simple play button
    class QuickPlayView(View):
        def __init__(self, url, title, duration_str, thumbnail, requester):
            super().__init__(timeout=30)
            self.url = url
            self.title = title
            self.duration_str = duration_str
            self.thumbnail = thumbnail
            self.requester = requester
        
        @discord.ui.button(label='▶️ Play Now', style=ButtonStyle.success)
        async def play_button(self, interaction: discord.Interaction, button: Button):
            voice_client = await music_player.join_voice_channel(ctx)
            if not voice_client:
                await safe_send_message(interaction, "❌ You need to be in a voice channel!", ephemeral=True)
                return
            
            song_info = {
                'url': self.url,
                'title': self.title,
                'duration': self.duration_str,
                'thumbnail': self.thumbnail,
                'requester': self.requester,
                'uploader': uploader
            }
            
            if not voice_client.is_playing():
                music_player.current_songs[interaction.guild.id] = song_info
                try:
                    player = await YTDLSource.from_url(self.url, stream=True)
                    player.volume = music_player.volumes[interaction.guild.id]
                    voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(music_player.play_next(interaction.guild.id), music_player.bot.loop))
                    
                    # Create music player embed with controls
                    view = MusicPlayerView(music_player, interaction.guild.id)
                    embed = await view.create_now_playing_embed(song_info)
                    await interaction.response.edit_message(embed=embed, view=view)
                except Exception as e:
                    error_msg = f"❌ Error playing song: {type(e).__name__}: {str(e)}"
                    print(f"Music playback error: {error_msg}")
                    import traceback
                    traceback.print_exc()
                    await interaction.response.send_message(error_msg, ephemeral=True)
            else:
                music_player.queues[interaction.guild.id].append(song_info)
                embed = discord.Embed(title="📋 Added to Queue", color=0x3498db)
                embed.add_field(name="Title", value=self.title, inline=False)
                embed.add_field(name="Position", value=str(len(music_player.queues[interaction.guild.id])), inline=True)
                await interaction.response.edit_message(embed=embed, view=None)
    
    view = QuickPlayView(url, title, duration_str, thumbnail, message.author.display_name)
    await loading_msg.edit(content="", embed=embed, view=view)
    return True

async def handle_play_command(message):
    """Handle !play command (legacy support)"""
    try:
        parts = message.content.split(' ', 1)
        if len(parts) < 2:
            await safe_send_message(message.channel, "❌ Usage: `!play <song name or YouTube URL>`")
            return True
        
        query = parts[1]
        
        # Create a mock context object for the music player
        class MockContext:
            def __init__(self, message):
                self.message = message
                self.author = message.author
                self.guild = message.guild
                self.channel = message.channel
                
            async def send(self, content=None, *, embed=None):
                if embed:
                    return await self.channel.send(embed=embed)
                return await self.channel.send(content)
        
        ctx = MockContext(message)
        
        # Join voice channel
        voice_client = await music_player.join_voice_channel(ctx)
        if not voice_client:
            return True
        
        # Search for the song
        loading_msg = await message.channel.send("🔍 Searching for song...")
        
        if query.startswith(('http://', 'https://')):
            # Direct URL
            url = query
            try:
                import yt_dlp
                ytdl = yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True})
                data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                if 'entries' in data:
                    data = data['entries'][0]
                title = data.get('title', 'Unknown Title')
                duration = data.get('duration', 0)
                thumbnail = data.get('thumbnail', '')
                uploader = data.get('uploader', 'Unknown')
            except Exception as e:
                await loading_msg.edit(content=f"❌ Error loading URL: {str(e)}")
                return True
        else:
            # Search YouTube
            url, title, duration, thumbnail, uploader, view_count = await YTDLSource.search_youtube(query)
            if not url:
                await loading_msg.edit(content="❌ No results found for your search.")
                return True
        
        # Format duration
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Unknown"
        
        song_info = {
            'url': url,
            'title': title,
            'duration': duration_str,
            'thumbnail': thumbnail,
            'requester': message.author.display_name,
            'uploader': uploader
        }
        
        # If nothing is playing, start playing immediately
        if not voice_client.is_playing():
            music_player.current_songs[message.guild.id] = song_info
            try:
                player = await YTDLSource.from_url(url, stream=True)
                player.volume = music_player.volumes[message.guild.id]
                voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(music_player.play_next(message.guild.id), music_player.bot.loop))
                
                embed = discord.Embed(title="🎵 Now Playing", color=0x00ff00)
                embed.add_field(name="Title", value=title, inline=False)
                embed.add_field(name="Duration", value=duration_str, inline=True)
                embed.add_field(name="Requested by", value=message.author.display_name, inline=True)
                if thumbnail:
                    embed.set_thumbnail(url=thumbnail)
                
                await loading_msg.edit(content="", embed=embed)
            except Exception as e:
                await loading_msg.edit(content=f"❌ Error playing song: {str(e)}")
        else:
            # Add to queue
            music_player.queues[message.guild.id].append(song_info)
            
            embed = discord.Embed(title="📋 Added to Queue", color=0x3498db)
            embed.add_field(name="Title", value=title, inline=False)
            embed.add_field(name="Position in Queue", value=str(len(music_player.queues[message.guild.id])), inline=True)
            embed.add_field(name="Requested by", value=message.author.display_name, inline=True)
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
            
            await loading_msg.edit(content="", embed=embed)
            
    except Exception as e:
        await safe_send_message(message.channel, f"❌ Error with play command: {str(e)}")
    return True

async def handle_music_control_commands(message):
    """Handle music control commands like pause, resume, stop, skip, etc."""
    content = message.content.lower()
    
    # Pause command
    if content.startswith('!pause'):
        if message.guild.id in music_player.voice_clients:
            voice_client = music_player.voice_clients[message.guild.id]
            if voice_client.is_playing():
                voice_client.pause()
                await message.channel.send("⏸️ Music paused.")
            else:
                await safe_send_message(message.channel, "❌ Nothing is currently playing.")
        else:
            await safe_send_message(message.channel, "❌ Bot is not connected to a voice channel.")
        return True
    
    # Resume command
    if content.startswith('!resume'):
        if message.guild.id in music_player.voice_clients:
            voice_client = music_player.voice_clients[message.guild.id]
            if voice_client.is_paused():
                voice_client.resume()
                await message.channel.send("▶️ Music resumed.")
            else:
                await safe_send_message(message.channel, "❌ Music is not paused.")
        else:
            await safe_send_message(message.channel, "❌ Bot is not connected to a voice channel.")
        return True
    
    # Stop command
    if content.startswith('!stop'):
        if message.guild.id in music_player.voice_clients:
            voice_client = music_player.voice_clients[message.guild.id]
            voice_client.stop()
            music_player.queues[message.guild.id].clear()
            if message.guild.id in music_player.current_songs:
                del music_player.current_songs[message.guild.id]
            await message.channel.send("⏹️ Music stopped and queue cleared.")
        else:
            await safe_send_message(message.channel, "❌ Bot is not connected to a voice channel.")
        return True
    
    # Skip command
    if content.startswith('!skip'):
        if message.guild.id in music_player.voice_clients:
            voice_client = music_player.voice_clients[message.guild.id]
            if voice_client.is_playing():
                voice_client.stop()  # This will trigger play_next
                await message.channel.send("⏭️ Skipped current song.")
            else:
                await safe_send_message(message.channel, "❌ Nothing is currently playing.")
        else:
            await safe_send_message(message.channel, "❌ Bot is not connected to a voice channel.")
        return True
    
    # Queue command
    if content.startswith('!queue'):
        if message.guild.id not in music_player.queues or not music_player.queues[message.guild.id]:
            if message.guild.id in music_player.current_songs:
                # Show only current song
                current = music_player.current_songs[message.guild.id]
                embed = discord.Embed(title="🎵 Current Song", color=0x00ff00)
                embed.add_field(name="Now Playing", value=f"**{current['title']}**\nRequested by: {current['requester']}", inline=False)
                await message.channel.send(embed=embed)
            else:
                await message.channel.send("📋 Queue is empty.")
            return True
        
        embed = discord.Embed(title="📋 Music Queue", color=0x3498db)
        
        # Current song
        if message.guild.id in music_player.current_songs:
            current = music_player.current_songs[message.guild.id]
            embed.add_field(name="🎵 Now Playing", value=f"**{current['title']}**\nRequested by: {current['requester']}", inline=False)
        
        # Queue
        queue_text = ""
        for i, song in enumerate(music_player.queues[message.guild.id][:10], 1):
            queue_text += f"{i}. **{song['title']}** - {song['requester']}\n"
        
        if queue_text:
            embed.add_field(name="📋 Up Next", value=queue_text, inline=False)
        
        if len(music_player.queues[message.guild.id]) > 10:
            embed.add_field(name="📝 Note", value=f"... and {len(music_player.queues[message.guild.id]) - 10} more songs", inline=False)
        
        await message.channel.send(embed=embed)
        return True
    
    # Volume command
    if content.startswith('!volume'):
        try:
            parts = message.content.split(' ', 1)
            if len(parts) < 2:
                current_vol = int(music_player.volumes[message.guild.id] * 100)
                await message.channel.send(f"🔊 Current volume: {current_vol}%")
                return True
            
            volume = int(parts[1])
            if volume < 0 or volume > 100:
                await safe_send_message(message.channel, "❌ Volume must be between 0 and 100.")
                return True
            
            music_player.volumes[message.guild.id] = volume / 100
            
            # Update current player volume if playing
            if message.guild.id in music_player.voice_clients:
                voice_client = music_player.voice_clients[message.guild.id]
                if voice_client.source:
                    voice_client.source.volume = volume / 100
            
            await message.channel.send(f"🔊 Volume set to {volume}%")
        except ValueError:
            await safe_send_message(message.channel, "❌ Please provide a valid number (0-100).")
        except Exception as e:
            await safe_send_message(message.channel, f"❌ Error setting volume: {str(e)}")
        return True
    
    # Loop command
    if content.startswith('!loop'):
        music_player.loop_modes[message.guild.id] = not music_player.loop_modes[message.guild.id]
        status = "enabled" if music_player.loop_modes[message.guild.id] else "disabled"
        emoji = "🔁" if music_player.loop_modes[message.guild.id] else "➡️"
        await message.channel.send(f"{emoji} Loop {status}.")
        return True
    
    # Leave voice channel command
    if content.startswith('!leave'):
        if message.guild.id in music_player.voice_clients:
            await music_player.voice_clients[message.guild.id].disconnect()
            del music_player.voice_clients[message.guild.id]
            music_player.queues[message.guild.id].clear()
            if message.guild.id in music_player.current_songs:
                del music_player.current_songs[message.guild.id]
            await message.channel.send("👋 Left the voice channel.")
        else:
            await safe_send_message(message.channel, "❌ Bot is not connected to a voice channel.")
        return True
    
    # Now Playing command
    if content.startswith('!nowplaying') or content.startswith('!np'):
        if message.guild.id in music_player.current_songs:
            current = music_player.current_songs[message.guild.id]
            embed = discord.Embed(title="🎵 Now Playing", color=0x00ff00)
            embed.add_field(name="Title", value=current['title'], inline=False)
            embed.add_field(name="Duration", value=current['duration'], inline=True)
            embed.add_field(name="Requested by", value=current['requester'], inline=True)
            
            # Add loop status
            loop_status = "🔁 Loop: ON" if music_player.loop_modes[message.guild.id] else "➡️ Loop: OFF"
            embed.add_field(name="Status", value=loop_status, inline=True)
            
            if current.get('thumbnail'):
                embed.set_thumbnail(url=current['thumbnail'])
            
            await message.channel.send(embed=embed)
        else:
            await safe_send_message(message.channel, "❌ Nothing is currently playing.")
        return True
    
    return False

async def process_music_commands(message):
    """Process all music-related commands"""
    global music_player
    
    content = message.content.lower()
    
    # Check if music player is initialized for any music command
    if music_player is None:
        if any(content.startswith(cmd) for cmd in ['!music', '!play', '!pause', '!resume', '!skip', '!stop', '!queue', '!volume', '!loop', '!leave', '!nowplaying']):
            await safe_send_message(message.channel, "❌ Music player is not initialized yet. Please wait for the bot to fully start up.")
            return True
        return False
    
    # Main music commands
    if content.startswith('!music') or content.startswith('!player'):
        return await handle_music_command(message)
    elif content.startswith('!search'):
        return await handle_search_command(message)
    elif content.startswith('!play'):
        return await handle_play_command(message)
    else:
        # Music control commands
        return await handle_music_control_commands(message)
