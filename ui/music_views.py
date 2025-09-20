import discord
from discord.ui import View, Button, Modal, TextInput
from discord import ButtonStyle
from discord.errors import HTTPException
import asyncio
import time
from utils.music_sources import YTDLSource, SpotifyMusicSource

# Rate limiting cooldown tracking
_last_error_message = {}
_error_cooldown = 2.0  # seconds

async def safe_send_message(interaction, message, ephemeral=True, max_retries=3):
    """Safely send a message with rate limit handling and cooldown"""
    global _last_error_message
    
    # Check cooldown for error messages
    current_time = time.time()
    user_id = interaction.user.id
    
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
            await interaction.followup.send(message, ephemeral=ephemeral)
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

class SpotifyMusicCard(View):
    def __init__(self, music_player, guild_id):
        super().__init__(timeout=None)
        self.music_player = music_player
        self.guild_id = guild_id
        self.message = None  # Will store the message to edit

    async def create_spotify_card(self, song_info=None):
        """Create a Spotify-like music card"""
        if song_info is None and self.guild_id in self.music_player.current_songs:
            song_info = self.music_player.current_songs[self.guild_id]
        
        if song_info:
            # Playing state
            embed = discord.Embed(color=0x1DB954)  # Spotify green
            
            # Main song info - compact like Spotify
            title = song_info.get('title', 'Unknown Title')
            if len(title) > 50:
                title = title[:47] + "..."
            
            uploader = song_info.get('uploader', 'Unknown Artist')
            if len(uploader) > 30:
                uploader = uploader[:27] + "..."
            
            embed.description = f"**{title}**\n{uploader}"
            
            # Status bar
            volume = int(self.music_player.volumes[self.guild_id] * 100)
            is_paused = False
            if self.guild_id in self.music_player.voice_clients:
                voice_client = self.music_player.voice_clients[self.guild_id]
                is_paused = voice_client.is_paused()
            
            status_icon = "⏸️" if is_paused else "▶️"
            loop_icon = " 🔁" if self.music_player.loop_modes[self.guild_id] else ""
            queue_count = len(self.music_player.queues[self.guild_id])
            
            status_line = f"{status_icon} **{song_info.get('duration', 'Live')}** • 🔊 {volume}%{loop_icon}"
            if queue_count > 0:
                status_line += f" • 📋 {queue_count} in queue"
            
            embed.add_field(name="", value=status_line, inline=False)
            
            # Thumbnail
            if song_info.get('thumbnail'):
                embed.set_thumbnail(url=song_info['thumbnail'])
            
        else:
            # Idle state
            embed = discord.Embed(
                title="🎵 Music Player",
                description="**Ready to play music**\nClick 🎵 to search for songs",
                color=0x36393F  # Discord dark theme color
            )
            embed.add_field(name="", value="🎧 Join a voice channel and start listening", inline=False)
        
        return embed

    async def update_card(self):
        """Update the music card with current info"""
        if self.message:
            try:
                embed = await self.create_spotify_card()
                await self.message.edit(embed=embed, view=self)
            except:
                pass  # Ignore errors if message was deleted

    @discord.ui.button(label='⏯️', style=ButtonStyle.secondary, custom_id='pause_resume')
    async def pause_resume_button(self, interaction: discord.Interaction, button: Button):
        if self.guild_id in self.music_player.voice_clients:
            voice_client = self.music_player.voice_clients[self.guild_id]
            if voice_client.is_playing():
                voice_client.pause()
            elif voice_client.is_paused():
                voice_client.resume()
            else:
                await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
                return
            
            await interaction.response.defer()
            await self.update_card()
        else:
            await interaction.response.send_message("❌ Bot is not connected to a voice channel.", ephemeral=True)

    @discord.ui.button(label='⏭️', style=ButtonStyle.secondary, custom_id='skip')
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        if self.guild_id in self.music_player.voice_clients:
            voice_client = self.music_player.voice_clients[self.guild_id]
            if voice_client.is_playing():
                voice_client.stop()  # This will trigger play_next
                await interaction.response.defer()
                # Card will update automatically when next song starts
            else:
                await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot is not connected to a voice channel.", ephemeral=True)

    @discord.ui.button(label='⏹️', style=ButtonStyle.danger, custom_id='stop')
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        if self.guild_id in self.music_player.voice_clients:
            voice_client = self.music_player.voice_clients[self.guild_id]
            voice_client.stop()
            self.music_player.queues[self.guild_id].clear()
            if self.guild_id in self.music_player.current_songs:
                del self.music_player.current_songs[self.guild_id]
            
            await interaction.response.defer()
            await self.update_card()
        else:
            await interaction.response.send_message("❌ Bot is not connected to a voice channel.", ephemeral=True)

    @discord.ui.button(label='🔁', style=ButtonStyle.secondary, custom_id='loop')
    async def loop_button(self, interaction: discord.Interaction, button: Button):
        self.music_player.loop_modes[self.guild_id] = not self.music_player.loop_modes[self.guild_id]
        await interaction.response.defer()
        await self.update_card()

    @discord.ui.button(label='📋', style=ButtonStyle.primary, custom_id='queue')
    async def queue_button(self, interaction: discord.Interaction, button: Button):
        # Create a clean queue display
        embed = discord.Embed(title="📋 Queue", color=0x1DB954)
        
        queue = self.music_player.queues[self.guild_id]
        current = self.music_player.current_songs.get(self.guild_id)
        
        if current:
            title = current['title'][:40] + "..." if len(current['title']) > 40 else current['title']
            embed.add_field(name="▶️ Now Playing", value=f"**{title}**", inline=False)
        
        if queue:
            queue_text = ""
            for i, song in enumerate(queue[:8], 1):  # Show max 8 songs
                title = song['title'][:35] + "..." if len(song['title']) > 35 else song['title']
                queue_text += f"`{i}.` {title}\n"
            
            embed.add_field(name="⏭️ Up Next", value=queue_text, inline=False)
            
            if len(queue) > 8:
                embed.add_field(name="", value=f"*...and {len(queue) - 8} more songs*", inline=False)
        else:
            embed.add_field(name="⏭️ Up Next", value="*Queue is empty*", inline=False)
        
        view = QueueManagementView(self.music_player, self.guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label='🔊', style=ButtonStyle.secondary, custom_id='volume')
    async def volume_button(self, interaction: discord.Interaction, button: Button):
        current_vol = int(self.music_player.volumes[self.guild_id] * 100)
        view = VolumeControlView(self.music_player, self.guild_id, current_vol, self)
        embed = discord.Embed(title="🔊 Volume", description=f"Current: **{current_vol}%**", color=0x1DB954)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label='🎵', style=ButtonStyle.success, custom_id='add_song')
    async def add_song_button(self, interaction: discord.Interaction, button: Button):
        # Create a mock context object
        class MockContext:
            def __init__(self, interaction):
                self.interaction = interaction
                self.author = interaction.user
                self.guild = interaction.guild
                self.channel = interaction.channel
        
        ctx = MockContext(interaction)
        modal = FastMusicSearchModal(self.music_player, ctx, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label='👋', style=ButtonStyle.danger, custom_id='disconnect')
    async def disconnect_button(self, interaction: discord.Interaction, button: Button):
        # Clear everything and disconnect
        self.music_player.queues[self.guild_id].clear()
        if self.guild_id in self.music_player.current_songs:
            del self.music_player.current_songs[self.guild_id]
        
        # Disconnect from voice channel
        if self.guild_id in self.music_player.voice_clients:
            await self.music_player.voice_clients[self.guild_id].disconnect()
            del self.music_player.voice_clients[self.guild_id]
        
        await interaction.response.defer()
        await self.update_card()

class FastMusicSearchModal(Modal, title='🎵 Add Music'):
    def __init__(self, music_player, ctx, music_card):
        super().__init__()
        self.music_player = music_player
        self.ctx = ctx
        self.music_card = music_card

    search_query = TextInput(
        label='Song or Artist',
        placeholder='Enter song name, artist, or YouTube URL...',
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        query = self.search_query.value
        
        # Join voice channel
        voice_client = await self.music_player.join_voice_channel(self.ctx)
        if not voice_client:
            if self.ctx.author.voice is None:
                await safe_send_message(interaction, "❌ You need to join a voice channel first!", ephemeral=True)
            else:
                await safe_send_message(interaction, "❌ Failed to connect to your voice channel!", ephemeral=True)
            return

        # Check if it's a direct YouTube URL
        if query.startswith(('http://', 'https://')) and ('youtube.com' in query or 'youtu.be' in query):
            # Handle direct YouTube URL
            try:
                import yt_dlp
                ytdl = yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True})
                data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
                if 'entries' in data:
                    data = data['entries'][0]
                
                title = data.get('title', 'Unknown Title')
                duration = data.get('duration', 0)
                thumbnail = data.get('thumbnail', '')
                uploader = data.get('uploader', 'Unknown')
                
                # Format duration
                duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Live"
                
                song_info = {
                    'url': query,
                    'title': title,
                    'duration': duration_str,
                    'thumbnail': thumbnail,
                    'requester': interaction.user.display_name,
                    'uploader': uploader
                }
                
                # Play the YouTube URL directly
                if not voice_client.is_playing():
                    # Start playing immediately
                    self.music_player.current_songs[interaction.guild.id] = song_info
                    try:
                        player = await YTDLSource.from_url(query, stream=True)
                        player.volume = self.music_player.volumes[interaction.guild.id]
                        voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(self.music_player.play_next(interaction.guild.id), self.music_player.bot.loop))
                        
                        await self.music_card.update_card()
                        await interaction.followup.send(f"▶️ **Now playing:** {title} by {uploader}", ephemeral=True)
                    except Exception as e:
                        error_msg = f"❌ Error playing song: {type(e).__name__}: {str(e)}"
                        print(f"Music search playback error: {error_msg}")
                        import traceback
                        traceback.print_exc()
                        await interaction.followup.send(error_msg, ephemeral=True)
                else:
                    # Add to queue
                    self.music_player.queues[interaction.guild.id].append(song_info)
                    position = len(self.music_player.queues[interaction.guild.id])
                    
                    await interaction.followup.send(f"📋 **Added to queue #{position}:** {title} by {uploader}", ephemeral=True)
                    await self.music_card.update_card()
                    
            except Exception as e:
                await safe_send_message(interaction, f"❌ Error loading YouTube URL: {str(e)}", ephemeral=True)
            return

        # Fast Spotify search - always use first result
        url, title, duration, thumbnail, artist, popularity = await SpotifyMusicSource.search_spotify(query)
        if not url:
            await safe_send_message(interaction, "❌ No results found on Spotify.", ephemeral=True)
            return

        # Format duration
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Live"

        song_info = {
            'url': url,
            'title': title,
            'duration': duration_str,
            'thumbnail': thumbnail,
            'requester': interaction.user.display_name,
            'uploader': artist,
            'spotify_url': url,
            'popularity': popularity
        }

        # Play audio using YouTube with Spotify metadata
        if not voice_client.is_playing():
            # Start playing immediately
            self.music_player.current_songs[interaction.guild.id] = song_info
            try:
                # Search YouTube for audio using Spotify metadata
                search_query = f"{title} {artist}"
                youtube_url = await YTDLSource.search_youtube_for_audio(search_query)
                if youtube_url:
                    player = await YTDLSource.from_url(youtube_url, stream=True)
                    player.volume = self.music_player.volumes[interaction.guild.id]
                    voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(self.music_player.play_next(interaction.guild.id), self.music_player.bot.loop))
                    
                    await self.music_card.update_card()
                    await safe_send_message(interaction, f"▶️ **Now playing:** {title} by {artist}", ephemeral=True)
                else:
                    await safe_send_message(interaction, f"❌ Couldn't find audio for: {title}", ephemeral=True)
            except Exception as e:
                error_msg = f"❌ Error playing song: {type(e).__name__}: {str(e)}"
                print(f"Music modal playback error: {error_msg}")
                import traceback
                traceback.print_exc()
                await safe_send_message(interaction, error_msg, ephemeral=True)
        else:
            # Add to queue
            self.music_player.queues[interaction.guild.id].append(song_info)
            position = len(self.music_player.queues[interaction.guild.id])
            
            # Only show queue addition message
            await safe_send_message(interaction, f"📋 **Added to queue #{position}:** {title} by {artist}", ephemeral=True)
            
            # Update the music card to show new queue count
            await self.music_card.update_card()

class VolumeControlView(View):
    def __init__(self, music_player, guild_id, current_volume, music_card):
        super().__init__(timeout=60)
        self.music_player = music_player
        self.guild_id = guild_id
        self.current_volume = current_volume
        self.music_card = music_card

    @discord.ui.button(label='🔇', style=ButtonStyle.secondary, custom_id='mute')
    async def mute_button(self, interaction: discord.Interaction, button: Button):
        self.music_player.volumes[self.guild_id] = 0.0
        if self.guild_id in self.music_player.voice_clients:
            voice_client = self.music_player.voice_clients[self.guild_id]
            if voice_client.source:
                voice_client.source.volume = 0.0
        
        embed = discord.Embed(title="🔇 Muted", description="Volume: **0%**", color=0x95a5a6)
        await interaction.response.edit_message(embed=embed)
        await self.music_card.update_card()

    @discord.ui.button(label='25%', style=ButtonStyle.secondary, custom_id='low')
    async def low_volume_button(self, interaction: discord.Interaction, button: Button):
        await self._set_volume(interaction, 0.25, "25%")

    @discord.ui.button(label='50%', style=ButtonStyle.secondary, custom_id='medium')
    async def medium_volume_button(self, interaction: discord.Interaction, button: Button):
        await self._set_volume(interaction, 0.5, "50%")

    @discord.ui.button(label='75%', style=ButtonStyle.secondary, custom_id='high')
    async def high_volume_button(self, interaction: discord.Interaction, button: Button):
        await self._set_volume(interaction, 0.75, "75%")

    @discord.ui.button(label='100%', style=ButtonStyle.secondary, custom_id='max')
    async def max_volume_button(self, interaction: discord.Interaction, button: Button):
        await self._set_volume(interaction, 1.0, "100%")
    
    async def _set_volume(self, interaction, volume, display):
        self.music_player.volumes[self.guild_id] = volume
        if self.guild_id in self.music_player.voice_clients:
            voice_client = self.music_player.voice_clients[self.guild_id]
            if voice_client.source:
                voice_client.source.volume = volume
        
        embed = discord.Embed(title="🔊 Volume", description=f"Volume: **{display}**", color=0x1DB954)
        await interaction.response.edit_message(embed=embed)
        await self.music_card.update_card()

class QueueManagementView(View):
    def __init__(self, music_player, guild_id):
        super().__init__(timeout=60)
        self.music_player = music_player
        self.guild_id = guild_id

    @discord.ui.button(label='🗑️ Clear Queue', style=ButtonStyle.danger, custom_id='clear_queue')
    async def clear_queue_button(self, interaction: discord.Interaction, button: Button):
        self.music_player.queues[self.guild_id].clear()
        embed = discord.Embed(title="🗑️ Queue Cleared", description="All songs removed from queue.", color=0xe74c3c)
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label='🔀 Shuffle', style=ButtonStyle.secondary, custom_id='shuffle_queue')
    async def shuffle_queue_button(self, interaction: discord.Interaction, button: Button):
        if len(self.music_player.queues[self.guild_id]) > 1:
            import random
            random.shuffle(self.music_player.queues[self.guild_id])
            embed = discord.Embed(title="🔀 Queue Shuffled", description="Queue has been randomized.", color=0x9b59b6)
            await interaction.response.edit_message(embed=embed)
        else:
            await interaction.response.send_message("❌ Need at least 2 songs in queue to shuffle.", ephemeral=True)

class MusicPlayerView(View):
    def __init__(self, music_player, guild_id):
        super().__init__(timeout=None)
        self.music_player = music_player
        self.guild_id = guild_id

    async def create_now_playing_embed(self, song_info=None):
        """Create now playing embed"""
        if song_info is None and self.guild_id in self.music_player.current_songs:
            song_info = self.music_player.current_songs[self.guild_id]
        
        if song_info:
            embed = discord.Embed(title="🎵 Now Playing", color=0x00ff00)
            embed.add_field(name="Title", value=song_info['title'], inline=False)
            embed.add_field(name="Duration", value=song_info['duration'], inline=True)
            embed.add_field(name="Requested by", value=song_info['requester'], inline=True)
            
            # Add loop status
            loop_status = "🔁 Loop: ON" if self.music_player.loop_modes[self.guild_id] else "➡️ Loop: OFF"
            embed.add_field(name="Status", value=loop_status, inline=True)
            
            if song_info.get('thumbnail'):
                embed.set_thumbnail(url=song_info['thumbnail'])
            
            return embed
        else:
            embed = discord.Embed(
                title="🎵 Music Player",
                description="**Ready to play music**\nClick 🎵 to search for songs",
                color=0x36393F
            )
            return embed

    @discord.ui.button(label='⏯️', style=ButtonStyle.secondary, custom_id='pause_resume')
    async def pause_resume_button(self, interaction: discord.Interaction, button: Button):
        if self.guild_id in self.music_player.voice_clients:
            voice_client = self.music_player.voice_clients[self.guild_id]
            if voice_client.is_playing():
                voice_client.pause()
                await interaction.response.send_message("⏸️ Music paused.", ephemeral=True)
            elif voice_client.is_paused():
                voice_client.resume()
                await interaction.response.send_message("▶️ Music resumed.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot is not connected to a voice channel.", ephemeral=True)

    @discord.ui.button(label='⏭️', style=ButtonStyle.secondary, custom_id='skip')
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        if self.guild_id in self.music_player.voice_clients:
            voice_client = self.music_player.voice_clients[self.guild_id]
            if voice_client.is_playing():
                voice_client.stop()  # This will trigger play_next
                await interaction.response.send_message("⏭️ Skipped current song.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot is not connected to a voice channel.", ephemeral=True)

    @discord.ui.button(label='⏹️', style=ButtonStyle.danger, custom_id='stop')
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        if self.guild_id in self.music_player.voice_clients:
            voice_client = self.music_player.voice_clients[self.guild_id]
            voice_client.stop()
            self.music_player.queues[self.guild_id].clear()
            if self.guild_id in self.music_player.current_songs:
                del self.music_player.current_songs[self.guild_id]
            
            await interaction.response.send_message("⏹️ Music stopped and queue cleared.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot is not connected to a voice channel.", ephemeral=True)

    @discord.ui.button(label='🔁', style=ButtonStyle.secondary, custom_id='loop')
    async def loop_button(self, interaction: discord.Interaction, button: Button):
        self.music_player.loop_modes[self.guild_id] = not self.music_player.loop_modes[self.guild_id]
        status = "enabled" if self.music_player.loop_modes[self.guild_id] else "disabled"
        emoji = "🔁" if self.music_player.loop_modes[self.guild_id] else "➡️"
        await interaction.response.send_message(f"{emoji} Loop {status}.", ephemeral=True)

    @discord.ui.button(label='📋', style=ButtonStyle.primary, custom_id='queue')
    async def queue_button(self, interaction: discord.Interaction, button: Button):
        # Create a clean queue display
        embed = discord.Embed(title="📋 Queue", color=0x1DB954)
        
        queue = self.music_player.queues[self.guild_id]
        current = self.music_player.current_songs.get(self.guild_id)
        
        if current:
            title = current['title'][:40] + "..." if len(current['title']) > 40 else current['title']
            embed.add_field(name="▶️ Now Playing", value=f"**{title}**", inline=False)
        
        if queue:
            queue_text = ""
            for i, song in enumerate(queue[:8], 1):  # Show max 8 songs
                title = song['title'][:35] + "..." if len(song['title']) > 35 else song['title']
                queue_text += f"`{i}.` {title}\n"
            
            embed.add_field(name="⏭️ Up Next", value=queue_text, inline=False)
            
            if len(queue) > 8:
                embed.add_field(name="", value=f"*...and {len(queue) - 8} more songs*", inline=False)
        else:
            embed.add_field(name="⏭️ Up Next", value="*Queue is empty*", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
