from typing import Final
import discord
from discord.ext import commands, tasks
import os
import requests
from dotenv import load_dotenv
import json
import google.generativeai as genai
from datetime import datetime, timedelta
import asyncio
import re
import sqlite3
from collections import defaultdict, deque
import time
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp
import functools
from discord.ui import View, Button, Select, Modal, TextInput
from discord import ButtonStyle, SelectOption

load_dotenv()
TOKEN: Final[str] = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY: Final[str] = os.getenv('GEMINI_API_KEY')
SPOTIFY_CLIENT_ID: Final[str] = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET: Final[str] = os.getenv('SPOTIFY_CLIENT_SECRET')

# Configure Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash-lite')
else:
    gemini_model = None

# Configure Spotify API
spotify = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        client_credentials_manager = SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        )
        spotify = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
    except Exception as e:
        print(f"Spotify API setup failed: {e}")
        spotify = None

# Database setup
def init_database():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    # Warnings table
    cursor.execute('''CREATE TABLE IF NOT EXISTS warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,
        moderator_id INTEGER NOT NULL,
        reason TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Server logs table
    cursor.execute('''CREATE TABLE IF NOT EXISTS server_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        user_id INTEGER,
        channel_id INTEGER,
        description TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Polls table
    cursor.execute('''CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER UNIQUE NOT NULL,
        channel_id INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,
        creator_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        options TEXT NOT NULL,
        end_time DATETIME,
        active BOOLEAN DEFAULT 1
    )''')
    
    # Scheduled announcements table
    cursor.execute('''CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        schedule_time DATETIME NOT NULL,
        repeat_interval INTEGER DEFAULT 0,
        active BOOLEAN DEFAULT 1
    )''')
    
    conn.commit()
    conn.close()

# Initialize database
init_database()

# Auto-moderation settings
spam_tracker = defaultdict(lambda: deque(maxlen=5))  # Track last 5 messages per user
bad_words = [
    'spam', 'scam', 'hack', 'cheat', 'bot', 'fake', 'virus', 
    # Add more as needed - keeping it mild for demonstration
]

# Active polls storage
active_polls = {}

# Music player configuration for audio playback
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

    @classmethod
    async def search_youtube_for_audio(cls, search_query, *, loop=None):
        """Search YouTube specifically for audio playback"""
        loop = loop or asyncio.get_event_loop()
        
        def search():
            try:
                search_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'default_search': 'ytsearch1:',
                    'extract_flat': False,
                    'skip_download': True,
                    'format': 'bestaudio/best',
                }
                
                with yt_dlp.YoutubeDL(search_opts) as ydl:
                    search_results = ydl.extract_info(f"ytsearch1:{search_query}", download=False)
                    
                if search_results and 'entries' in search_results and search_results['entries']:
                    video = search_results['entries'][0]
                    return video.get('webpage_url', f"https://www.youtube.com/watch?v={video.get('id')}")
                    
                return None
            except Exception as e:
                print(f"YouTube search error: {e}")
                return None
        
        return await loop.run_in_executor(None, search)

# Spotify Music System (for metadata only)
class SpotifyMusicSource:
    @classmethod
    async def search_spotify(cls, search_query, *, loop=None):
        """Fast Spotify search - returns first result immediately"""
        if not spotify:
            return None, None, None, None, None, None
        
        loop = loop or asyncio.get_event_loop()
        
        def search():
            try:
                # Search Spotify for tracks
                results = spotify.search(q=search_query, type='track', limit=1)
                
                if results['tracks']['items']:
                    track = results['tracks']['items'][0]
                    
                    # Get track info
                    title = track['name']
                    artist = ', '.join([artist['name'] for artist in track['artists']])
                    duration_ms = track['duration_ms']
                    duration = duration_ms // 1000 if duration_ms else 0
                    
                    # Get album art
                    thumbnail = ''
                    if track['album']['images']:
                        thumbnail = track['album']['images'][0]['url']
                    
                    # Create a simple preview URL (Spotify preview or placeholder)
                    preview_url = track.get('preview_url', '')
                    spotify_url = track['external_urls']['spotify']
                    
                    return {
                        'title': title,
                        'artist': artist,
                        'duration': duration,
                        'thumbnail': thumbnail,
                        'preview_url': preview_url,
                        'spotify_url': spotify_url,
                        'popularity': track.get('popularity', 0)
                    }
                    
                return None
            except Exception as e:
                print(f"Spotify search error: {e}")
                return None
        
        result = await loop.run_in_executor(None, search)
        if result:
            return (
                result['spotify_url'], 
                result['title'], 
                result['duration'], 
                result['thumbnail'], 
                result['artist'], 
                result['popularity']
            )
        return None, None, None, None, None, None

    @classmethod
    def create_audio_source(cls, track_info):
        """Create a simple audio source for Discord"""
        # For now, we'll create a placeholder audio source
        # In a real implementation, you'd need to use the preview_url or integrate with a music service
        return None  # Placeholder for audio source

class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.queues = defaultdict(list)
        self.current_songs = {}
        self.volumes = defaultdict(lambda: 0.5)
        self.loop_modes = defaultdict(lambda: False)  # False: no loop, True: loop current song
        self.music_cards = {}  # Store music card references

    async def join_voice_channel(self, ctx):
        if ctx.author.voice is None:
            return None
        
        channel = ctx.author.voice.channel
        
        if ctx.guild.id in self.voice_clients:
            if self.voice_clients[ctx.guild.id].channel != channel:
                await self.voice_clients[ctx.guild.id].move_to(channel)
        else:
            try:
                voice_client = await channel.connect()
                self.voice_clients[ctx.guild.id] = voice_client
            except Exception as e:
                print(f"Failed to connect to voice channel: {str(e)}")
                return None
        
        return self.voice_clients[ctx.guild.id]

    async def play_next(self, guild_id):
        """Play next song with audio"""
        if guild_id not in self.voice_clients:
            return
        
        voice_client = self.voice_clients[guild_id]
        
        if self.loop_modes[guild_id] and guild_id in self.current_songs:
            # Replay current song if loop is enabled
            song_info = self.current_songs[guild_id]
            try:
                # Search YouTube for audio using Spotify metadata
                search_query = f"{song_info['title']} {song_info['uploader']}"
                youtube_url = await YTDLSource.search_youtube_for_audio(search_query)
                if youtube_url:
                    player = await YTDLSource.from_url(youtube_url, stream=True)
                    player.volume = self.volumes[guild_id]
                    voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(guild_id), self.bot.loop))
                    return
            except Exception as e:
                print(f"Error replaying song: {e}")
        
        if not self.queues[guild_id]:
            # Queue is empty
            if guild_id in self.current_songs:
                del self.current_songs[guild_id]
            # Update any active music cards
            if guild_id in self.music_cards:
                await self.music_cards[guild_id].update_card()
            return
        
        # Play next song in queue
        song_info = self.queues[guild_id].pop(0)
        self.current_songs[guild_id] = song_info
        
        try:
            # Search YouTube for audio using Spotify metadata
            search_query = f"{song_info['title']} {song_info['uploader']}"
            youtube_url = await YTDLSource.search_youtube_for_audio(search_query)
            if youtube_url:
                player = await YTDLSource.from_url(youtube_url, stream=True)
                player.volume = self.volumes[guild_id]
                voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(guild_id), self.bot.loop))
            else:
                # If YouTube search fails, try next song
                await self.play_next(guild_id)
        except Exception as e:
            print(f"Error playing next song: {e}")
            # Try next song
            await self.play_next(guild_id)
        
        # Update any active music cards
        if guild_id in self.music_cards:
            await self.music_cards[guild_id].update_card()

# Music Player UI Components
class MusicSearchModal(Modal, title='🎵 Search for Music'):
    def __init__(self, music_player, ctx):
        super().__init__()
        self.music_player = music_player
        self.ctx = ctx

    search_query = TextInput(
        label='Song Name or YouTube URL',
        placeholder='Enter song name or paste YouTube URL...',
        required=True,
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        query = self.search_query.value
        
        # Join voice channel
        voice_client = await self.music_player.join_voice_channel(self.ctx)
        if not voice_client:
            if self.ctx.author.voice is None:
                await interaction.followup.send("❌ You need to join a voice channel first!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to connect to your voice channel!", ephemeral=True)
            return

        # Search for the song
        loading_embed = discord.Embed(title="🔍 Searching...", description=f"Looking for: `{query}`", color=0x3498db)
        await interaction.followup.send(embed=loading_embed)

        if query.startswith(('http://', 'https://')):
            # Direct URL
            url = query
            try:
                data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                if 'entries' in data:
                    data = data['entries'][0]
                title = data.get('title', 'Unknown Title')
                duration = data.get('duration', 0)
                thumbnail = data.get('thumbnail', '')
            except Exception as e:
                error_embed = discord.Embed(title="❌ Error", description=f"Error loading URL: {str(e)}", color=0xff0000)
                await interaction.edit_original_response(embed=error_embed)
                return
        else:
            # Search YouTube
            url, title, duration, thumbnail, uploader, view_count = await YTDLSource.search_youtube(query)
            if not url:
                error_embed = discord.Embed(title="❌ No Results", description="No results found for your search.", color=0xff0000)
                await interaction.edit_original_response(embed=error_embed)
                return

        # Format duration
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Unknown"

        song_info = {
            'url': url,
            'title': title,
            'duration': duration_str,
            'thumbnail': thumbnail,
            'requester': interaction.user.display_name
        }

        # If nothing is playing, start playing immediately
        if not voice_client.is_playing():
            self.music_player.current_songs[interaction.guild.id] = song_info
            try:
                player = await YTDLSource.from_url(url, stream=True)
                player.volume = self.music_player.volumes[interaction.guild.id]
                voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(self.music_player.play_next(interaction.guild.id), self.music_player.bot.loop))
                
                # Create music player embed with controls
                view = MusicPlayerView(self.music_player, interaction.guild.id)
                embed = await view.create_now_playing_embed(song_info)
                await interaction.edit_original_response(embed=embed, view=view)
            except Exception as e:
                error_embed = discord.Embed(title="❌ Error", description=f"Error playing song: {str(e)}", color=0xff0000)
                await interaction.edit_original_response(embed=error_embed)
        else:
            # Add to queue
            self.music_player.queues[interaction.guild.id].append(song_info)
            
            embed = discord.Embed(title="📋 Added to Queue", color=0x3498db)
            embed.add_field(name="Title", value=title, inline=False)
            embed.add_field(name="Position in Queue", value=str(len(self.music_player.queues[interaction.guild.id])), inline=True)
            embed.add_field(name="Requested by", value=interaction.user.display_name, inline=True)
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
            
            view = MusicPlayerView(self.music_player, interaction.guild.id)
            await interaction.edit_original_response(embed=embed, view=view)

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

# Fast search modal that only shows queue additions
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
                await interaction.followup.send("❌ You need to join a voice channel first!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to connect to your voice channel!", ephemeral=True)
            return

        # Fast Spotify search - always use first result
        url, title, duration, thumbnail, artist, popularity = await SpotifyMusicSource.search_spotify(query)
        if not url:
            await interaction.followup.send("❌ No results found on Spotify.", ephemeral=True)
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
                    await interaction.followup.send(f"▶️ **Now playing:** {title} by {artist}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Couldn't find audio for: {title}", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Error playing song: {str(e)}", ephemeral=True)
        else:
            # Add to queue
            self.music_player.queues[interaction.guild.id].append(song_info)
            position = len(self.music_player.queues[interaction.guild.id])
            
            # Only show queue addition message
            await interaction.followup.send(f"📋 **Added to queue #{position}:** {title} by {artist}", ephemeral=True)
            
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

# Global music player instance
music_player = None

# Moderation permissions check
def has_mod_permissions(member):
    return (member.guild_permissions.kick_members or 
            member.guild_permissions.ban_members or 
            member.guild_permissions.manage_messages or
            member.id == 1187080447709171743)  # Your ID as fallback admin

# Logging function
def log_server_event(guild_id, event_type, user_id=None, channel_id=None, description=None):
    try:
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO server_logs (guild_id, event_type, user_id, channel_id, description)
                         VALUES (?, ?, ?, ?, ?)''', (guild_id, event_type, user_id, channel_id, description))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging event: {e}")

# Poll System Functions
async def create_poll(channel, question, options, duration_minutes=60):
    if len(options) < 2 or len(options) > 10:
        return None, "Poll must have between 2-10 options."
    
    # Create embed
    embed = discord.Embed(
        title="📊 Poll",
        description=f"**{question}**",
        color=0x3498db,
        timestamp=datetime.utcnow()
    )
    
    # Add options with emoji reactions
    reactions = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    option_text = ""
    for i, option in enumerate(options):
        option_text += f"{reactions[i]} {option}\n"
    
    embed.add_field(name="Options:", value=option_text, inline=False)
    
    end_time = datetime.utcnow() + timedelta(minutes=duration_minutes)
    embed.add_field(name="Ends:", value=f"<t:{int(end_time.timestamp())}:R>", inline=True)
    embed.set_footer(text="React to vote!")
    
    # Send poll message
    poll_message = await channel.send(embed=embed)
    
    # Add reactions
    for i in range(len(options)):
        await poll_message.add_reaction(reactions[i])
    
    # Store in database
    try:
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO polls (message_id, channel_id, guild_id, creator_id, question, options, end_time)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                      (poll_message.id, channel.id, channel.guild.id, poll_message.author.id if hasattr(poll_message, 'author') else 0, 
                       question, json.dumps(options), end_time))
        conn.commit()
        conn.close()
        
        # Store in memory for quick access
        active_polls[poll_message.id] = {
            'question': question,
            'options': options,
            'end_time': end_time,
            'channel_id': channel.id
        }
        
        return poll_message, None
    except Exception as e:
        return None, f"Error creating poll: {e}"

async def end_poll(message_id):
    try:
        # Get poll from database
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM polls WHERE message_id = ? AND active = 1', (message_id,))
        poll_data = cursor.fetchone()
        
        if not poll_data:
            return
        
        # Mark as inactive
        cursor.execute('UPDATE polls SET active = 0 WHERE message_id = ?', (message_id,))
        conn.commit()
        conn.close()
        
        # Remove from active polls
        if message_id in active_polls:
            del active_polls[message_id]
            
    except Exception as e:
        print(f"Error ending poll: {e}")

# Auto-moderation functions
def is_spam(user_id, message_content):
    now = time.time()
    user_messages = spam_tracker[user_id]
    
    # Add current message
    user_messages.append((now, message_content))
    
    # Check for spam patterns
    if len(user_messages) >= 4:
        # Check if 4+ messages in 10 seconds
        recent_messages = [msg for msg in user_messages if now - msg[0] <= 10]
        if len(recent_messages) >= 4:
            return True
        
        # Check for repeated content
        contents = [msg[1] for msg in user_messages]
        if len(set(contents)) == 1 and len(contents) >= 3:  # Same message 3+ times
            return True
    
    return False

def contains_bad_words(message_content):
    content_lower = message_content.lower()
    return any(word in content_lower for word in bad_words)

def get_meme():
  response = requests.get('https://meme-api.com/gimme')
  json_data = json.loads(response.text)
  return json_data['url']

async def process_command(message, is_private=False):
    """Process a command and send response to channel or DM based on is_private flag."""
    content = message.content.lower()
    
    # Search commands
    if content.startswith('--'):
        topic = content[2:].strip()
        
        # Handle date-related queries with real-time information
        if any(word in topic.lower() for word in ['date', 'today', 'time', 'day', 'what day', 'current date']):
            current_date = datetime.now()
            formatted_date = current_date.strftime("%A, %B %d, %Y")
            day_of_year = current_date.timetuple().tm_yday
            days_remaining = 365 - day_of_year if not current_date.year % 4 == 0 else 366 - day_of_year
            
            response_text = f"**Today's Date: {formatted_date}**\n\n"
            response_text += f"📅 **Day of Year:** {day_of_year}\n"
            response_text += f"📅 **Days Remaining:** {days_remaining}\n"
            response_text += f"📅 **Weekday:** {current_date.strftime('%A')}\n"
            response_text += f"📅 **Month:** {current_date.strftime('%B')}\n"
            response_text += f"📅 **Year:** {current_date.year}"
            
            if is_private:
                await message.author.send(response_text)
            else:
                await message.channel.send(response_text)
            return True

        # Search for information about the topic
        result = search_topic(topic)
        if result:
            response_text = f"**{result['title']}**\n{result['extract']}"
            if result.get('url'):
                response_text += f"\n\n🔗 [Learn more]({result['url']})"
        else:
            response_text = "Sorry, I couldn't find information about that topic. Try something more specific like '--python' or '--discord'."
        
        if is_private:
            await message.author.send(response_text)
        else:
            await message.channel.send(response_text)
        return True
    
    # Fun commands
    elif content.startswith('hello'):
        response_text = 'Hello World!'
        if is_private:
            response_text += ' (Private)'
        if is_private:
            await message.author.send(response_text)
        else:
            await message.channel.send(response_text)
        return True
        
    elif content.startswith('$hello'):
        response_text = 'Hello World!'
        if is_private:
            response_text += ' (Private)'
        if is_private:
            await message.author.send(response_text)
        else:
            await message.channel.send(response_text)
        return True
        
    elif content.startswith('$meme') or content == 'meme':
        if is_private:
            await message.author.send(get_meme())
        else:
            await message.channel.send(get_meme())
        return True
        
    elif content.startswith('game?'):
        response_text = 'whatsapp come'
        if is_private:
            await message.author.send(response_text)
        else:
            await message.channel.send(response_text)
        return True
        
    elif content.startswith('mic'):
        response_text = 'hey mike, mic on chey ra'
        if is_private:
            await message.author.send(response_text)
        else:
            await message.channel.send(response_text)
        return True
        
    elif content == 'myid':
        response_text = f"Your Discord User ID: `{message.author.id}`"
        if is_private:
            await message.author.send(response_text)
        else:
            await message.channel.send(response_text)
        return True
    
    return False

# Gemini-powered search function
def search_topic(topic):
    try:
        # Handle very generic terms
        generic_terms = ['what', 'who', 'where', 'when', 'why', 'how', 'the', 'a', 'an']
        if topic.lower() in generic_terms:
            return None
        
        # Try Gemini API first (best quality responses)
        if gemini_model:
            try:
                prompt = f"""Provide a concise, informative summary about "{topic}". 
                Include key facts and important details. 
                Keep it under 300 words and make it engaging and educational.
                Format your response as: Title: [Title] | Summary: [Summary]"""
                
                response = gemini_model.generate_content(prompt)
                if response and response.text:
                    # Parse the response
                    text = response.text.strip()
                    if "Title:" in text and "Summary:" in text:
                        parts = text.split("|")
                        title_part = parts[0].replace("Title:", "").strip()
                        summary_part = parts[1].replace("Summary:", "").strip()
                        
                        # Limit summary to 1500 characters to stay under Discord's 2000 limit
                        if len(summary_part) > 1500:
                            summary_part = summary_part[:1500] + "..."
                        
                        return {
                            'title': title_part,
                            'extract': summary_part,
                            'url': f"https://www.google.com/search?q={topic.replace(' ', '+')}"
                        }
                    else:
                        # If format is different, use the whole response but limit length
                        if len(text) > 1500:
                            text = text[:1500] + "..."
                        return {
                            'title': topic.title(),
                            'extract': text,
                            'url': f"https://www.google.com/search?q={topic.replace(' ', '+')}"
                        }
            except Exception as e:
                print(f"Gemini API error: {e}")
        
        # Fallback to Wikipedia API if Gemini fails
        try:
            import urllib.parse
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            encoded_topic = urllib.parse.quote(topic.replace(' ', '_'))
            wiki_response = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_topic}", headers=headers)
            if wiki_response.status_code == 200:
                wiki_data = wiki_response.json()
                if wiki_data.get('extract') and len(wiki_data['extract']) > 50 and not wiki_data['extract'].startswith('may refer to'):
                    return {
                        'title': wiki_data.get('title', topic.title()),
                        'extract': wiki_data['extract'],
                        'url': wiki_data.get('content_urls', {}).get('desktop', {}).get('page', '')
                    }
        except Exception:
            pass
        
        # Final fallback
        return {
            'title': topic.title(),
            'extract': f"I couldn't find detailed information about '{topic.title()}'. Please try a more specific search term or check if the topic name is spelled correctly.",
            'url': f"https://www.google.com/search?q={topic.replace(' ', '+')}"
        }
                
    except Exception as e:
        print(f"Error searching for topic: {e}")
        return None
    
class MyClient(discord.Client):
  async def on_ready(self):
    print('Logged on as {0}!'.format(self.user))
    global music_player
    music_player = MusicPlayer(self)

  async def on_member_join(self, member):
          channel = member.guild.system_channel  # Get the system channel of the guild (default welcome channel)
          if channel is not None:
              await channel.send(f'{member.display_name} has joined the server!')
          
          # Log the join event
          log_server_event(member.guild.id, "member_joined", member.id, 
                          channel.id if channel else None, 
                          f"{member.display_name} ({member.id}) joined the server")

  async def on_member_remove(self, member):
          # Log the leave event
          log_server_event(member.guild.id, "member_left", member.id, None, 
                          f"{member.display_name} ({member.id}) left the server")

  async def on_message_edit(self, before, after):
          if before.author.bot:
              return
          
          # Log message edits
          if before.content != after.content:
              log_server_event(after.guild.id, "message_edited", after.author.id, after.channel.id,
                              f"Message edited in #{after.channel.name}")

  async def on_message_delete(self, message):
          if message.author.bot:
              return
          
          # Log message deletions
          log_server_event(message.guild.id, "message_deleted", message.author.id, message.channel.id,
                          f"Message deleted in #{message.channel.name}: {message.content[:100]}...")

  async def on_message(self, message):
    if message.author == self.user:
      return
    
    # Auto-moderation checks
    if not message.author.bot and message.guild:
        # Check for spam
        if is_spam(message.author.id, message.content):
            try:
                await message.delete()
                embed = discord.Embed(
                    title="🚫 Auto-Moderation: Spam Detected", 
                    description=f"{message.author.mention} was detected sending spam messages.",
                    color=0xff0000
                )
                embed.add_field(name="Action", value="Message deleted", inline=False)
                warning_msg = await message.channel.send(embed=embed)
                
                # Auto-delete the warning after 5 seconds
                await asyncio.sleep(5)
                await warning_msg.delete()
                
                log_server_event(message.guild.id, "spam_detected", message.author.id, message.channel.id, 
                               "Spam message auto-deleted")
                return
            except discord.errors.NotFound:
                pass  # Message already deleted
            except discord.errors.Forbidden:
                pass  # No permission to delete
        
        # Check for bad words
        if contains_bad_words(message.content):
            try:
                await message.delete()
                embed = discord.Embed(
                    title="🚫 Auto-Moderation: Inappropriate Content", 
                    description=f"{message.author.mention}, your message contained inappropriate content.",
                    color=0xff0000
                )
                embed.add_field(name="Action", value="Message deleted", inline=False)
                warning_msg = await message.channel.send(embed=embed)
                
                # Auto-delete the warning after 5 seconds
                await asyncio.sleep(5)
                await warning_msg.delete()
                
                log_server_event(message.guild.id, "inappropriate_content", message.author.id, message.channel.id, 
                               "Inappropriate content auto-deleted")
                return
            except discord.errors.NotFound:
                pass  # Message already deleted
            except discord.errors.Forbidden:
                pass  # No permission to delete
    
    content = message.content.lower()  # Convert message content to lowercase for case-insensitive matching

    # Process search commands
    if content.startswith('--'):
        await process_command(message, is_private=False)
        return
        
    # Process private commands
    if message.content.startswith('?'):
        # Extract the command after the '?' and process it privately
        private_command = message.content[1:].strip()  # Remove the '?' and get the command
        
        # Handle private search commands
        if private_command.startswith('--'):
            topic = private_command[2:].strip()
            
            # Handle date-related queries with real-time information
            if any(word in topic.lower() for word in ['date', 'today', 'time', 'day', 'what day', 'current date']):
                current_date = datetime.now()
                formatted_date = current_date.strftime("%A, %B %d, %Y")
                day_of_year = current_date.timetuple().tm_yday
                days_remaining = 365 - day_of_year if not current_date.year % 4 == 0 else 366 - day_of_year
                
                response_text = f"**Today's Date: {formatted_date}**\n\n"
                response_text += f"📅 **Day of Year:** {day_of_year}\n"
                response_text += f"📅 **Days Remaining:** {days_remaining}\n"
                response_text += f"📅 **Weekday:** {current_date.strftime('%A')}\n"
                response_text += f"📅 **Month:** {current_date.strftime('%B')}\n"
                response_text += f"📅 **Year:** {current_date.year}"
                
                await message.author.send(response_text)
                return

            # Search for information about the topic
            result = search_topic(topic)
            if result:
                response_text = f"**{result['title']}**\n{result['extract']}"
                if result.get('url'):
                    response_text += f"\n\n🔗 [Learn more]({result['url']})"
                await message.author.send(response_text)
            else:
                await message.author.send("Sorry, I couldn't find information about that topic. Try something more specific like '--python' or '--discord'.")
            return
            
        # Handle other private commands
        elif private_command == 'meme' or private_command == '$meme':
            await message.author.send(get_meme())
            return
        elif private_command == 'myid':
            await message.author.send(f"Your Discord User ID: `{message.author.id}`")
            return
        elif private_command == 'hello':
            await message.author.send('Hello World! (Private)')
            return
        elif private_command == '$hello':
            await message.author.send('Hello World! (Private)')
            return
        elif private_command == 'game?':
            await message.author.send('whatsapp come')
            return
        elif private_command == 'mic':
            await message.author.send('hey mike, mic on chey ra')
            return
        else:
            # Default private response for unknown commands
            await message.author.send('This is a private message response to your question.')
        return
    
    # Music Player Commands
    
    # Interactive Music Player Command
    if message.content.startswith('!music') or message.content.startswith('!player'):
        # Check if user is in voice channel
        if not message.author.voice:
            await message.channel.send("❌ You need to be in a voice channel to use the music player!")
            return
        
        # Create the Spotify-like music card
        music_card = SpotifyMusicCard(music_player, message.guild.id)
        embed = await music_card.create_spotify_card()
        
        # Send the card and store the message reference
        sent_message = await message.channel.send(embed=embed, view=music_card)
        music_card.message = sent_message
        return
    
    # Quick search command (still available)
    if message.content.startswith('!search'):
        parts = message.content.split(' ', 1)
        if len(parts) < 2:
            await message.channel.send("❌ Usage: `!search <song name>`")
            return
        
        query = parts[1]
        class MockContext:
            def __init__(self, message):
                self.message = message
                self.author = message.author
                self.guild = message.guild
                self.channel = message.channel
        
        ctx = MockContext(message)
        modal = MusicSearchModal(music_player, ctx)
        
        # Since we can't send modal directly, we'll simulate the search
        if not message.author.voice:
            await message.channel.send("❌ You need to be in a voice channel!")
            return
        
        # Search for the song
        loading_msg = await message.channel.send(f"🔍 Searching for: `{query}`...")
        
        url, title, duration, thumbnail = await YTDLSource.search_youtube(query)
        if not url:
            await loading_msg.edit(content="❌ No results found for your search.")
            return
        
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
                    await interaction.response.send_message("❌ You need to be in a voice channel!", ephemeral=True)
                    return
                
                song_info = {
                    'url': self.url,
                    'title': self.title,
                    'duration': self.duration_str,
                    'thumbnail': self.thumbnail,
                    'requester': self.requester
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
                        await interaction.response.send_message(f"❌ Error playing song: {str(e)}", ephemeral=True)
                else:
                    music_player.queues[interaction.guild.id].append(song_info)
                    embed = discord.Embed(title="📋 Added to Queue", color=0x3498db)
                    embed.add_field(name="Title", value=self.title, inline=False)
                    embed.add_field(name="Position", value=str(len(music_player.queues[interaction.guild.id])), inline=True)
                    await interaction.response.edit_message(embed=embed, view=None)
        
        view = QuickPlayView(url, title, duration_str, thumbnail, message.author.display_name)
        await loading_msg.edit(content="", embed=embed, view=view)
        return
    
    # Play music command (legacy support)
    if message.content.startswith('!play'):
        try:
            parts = message.content.split(' ', 1)
            if len(parts) < 2:
                await message.channel.send("❌ Usage: `!play <song name or YouTube URL>`")
                return
            
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
                return
            
            # Search for the song
            loading_msg = await message.channel.send("🔍 Searching for song...")
            
            if query.startswith(('http://', 'https://')):
                # Direct URL
                url = query
                try:
                    data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                    if 'entries' in data:
                        data = data['entries'][0]
                    title = data.get('title', 'Unknown Title')
                    duration = data.get('duration', 0)
                    thumbnail = data.get('thumbnail', '')
                except Exception as e:
                    await loading_msg.edit(content=f"❌ Error loading URL: {str(e)}")
                    return
            else:
                # Search YouTube
                url, title, duration, thumbnail, uploader, view_count = await YTDLSource.search_youtube(query)
                if not url:
                    await loading_msg.edit(content="❌ No results found for your search.")
                    return
            
            # Format duration
            duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Unknown"
            
            song_info = {
                'url': url,
                'title': title,
                'duration': duration_str,
                'thumbnail': thumbnail,
                'requester': message.author.display_name
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
            await message.channel.send(f"❌ Error with play command: {str(e)}")
        return
    
    # Pause command
    if message.content.startswith('!pause'):
        if message.guild.id in music_player.voice_clients:
            voice_client = music_player.voice_clients[message.guild.id]
            if voice_client.is_playing():
                voice_client.pause()
                await message.channel.send("⏸️ Music paused.")
            else:
                await message.channel.send("❌ Nothing is currently playing.")
        else:
            await message.channel.send("❌ Bot is not connected to a voice channel.")
        return
    
    # Resume command
    if message.content.startswith('!resume'):
        if message.guild.id in music_player.voice_clients:
            voice_client = music_player.voice_clients[message.guild.id]
            if voice_client.is_paused():
                voice_client.resume()
                await message.channel.send("▶️ Music resumed.")
            else:
                await message.channel.send("❌ Music is not paused.")
        else:
            await message.channel.send("❌ Bot is not connected to a voice channel.")
        return
    
    # Stop command
    if message.content.startswith('!stop'):
        if message.guild.id in music_player.voice_clients:
            voice_client = music_player.voice_clients[message.guild.id]
            voice_client.stop()
            music_player.queues[message.guild.id].clear()
            if message.guild.id in music_player.current_songs:
                del music_player.current_songs[message.guild.id]
            await message.channel.send("⏹️ Music stopped and queue cleared.")
        else:
            await message.channel.send("❌ Bot is not connected to a voice channel.")
        return
    
    # Skip command
    if message.content.startswith('!skip'):
        if message.guild.id in music_player.voice_clients:
            voice_client = music_player.voice_clients[message.guild.id]
            if voice_client.is_playing():
                voice_client.stop()  # This will trigger play_next
                await message.channel.send("⏭️ Skipped current song.")
            else:
                await message.channel.send("❌ Nothing is currently playing.")
        else:
            await message.channel.send("❌ Bot is not connected to a voice channel.")
        return
    
    # Queue command
    if message.content.startswith('!queue'):
        if message.guild.id not in music_player.queues or not music_player.queues[message.guild.id]:
            if message.guild.id in music_player.current_songs:
                # Show only current song
                current = music_player.current_songs[message.guild.id]
                embed = discord.Embed(title="🎵 Current Song", color=0x00ff00)
                embed.add_field(name="Now Playing", value=f"**{current['title']}**\nRequested by: {current['requester']}", inline=False)
                await message.channel.send(embed=embed)
            else:
                await message.channel.send("📋 Queue is empty.")
            return
        
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
        return
    
    # Volume command
    if message.content.startswith('!volume'):
        try:
            parts = message.content.split(' ', 1)
            if len(parts) < 2:
                current_vol = int(music_player.volumes[message.guild.id] * 100)
                await message.channel.send(f"🔊 Current volume: {current_vol}%")
                return
            
            volume = int(parts[1])
            if volume < 0 or volume > 100:
                await message.channel.send("❌ Volume must be between 0 and 100.")
                return
            
            music_player.volumes[message.guild.id] = volume / 100
            
            # Update current player volume if playing
            if message.guild.id in music_player.voice_clients:
                voice_client = music_player.voice_clients[message.guild.id]
                if voice_client.source:
                    voice_client.source.volume = volume / 100
            
            await message.channel.send(f"🔊 Volume set to {volume}%")
        except ValueError:
            await message.channel.send("❌ Please provide a valid number (0-100).")
        except Exception as e:
            await message.channel.send(f"❌ Error setting volume: {str(e)}")
        return
    
    # Loop command
    if message.content.startswith('!loop'):
        music_player.loop_modes[message.guild.id] = not music_player.loop_modes[message.guild.id]
        status = "enabled" if music_player.loop_modes[message.guild.id] else "disabled"
        emoji = "🔁" if music_player.loop_modes[message.guild.id] else "➡️"
        await message.channel.send(f"{emoji} Loop {status}.")
        return
    
    # Leave voice channel command
    if message.content.startswith('!leave'):
        if message.guild.id in music_player.voice_clients:
            await music_player.voice_clients[message.guild.id].disconnect()
            del music_player.voice_clients[message.guild.id]
            music_player.queues[message.guild.id].clear()
            if message.guild.id in music_player.current_songs:
                del music_player.current_songs[message.guild.id]
            await message.channel.send("👋 Left the voice channel.")
        else:
            await message.channel.send("❌ Bot is not connected to a voice channel.")
        return
    
    # Now Playing command
    if message.content.startswith('!nowplaying') or message.content.startswith('!np'):
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
            await message.channel.send("❌ Nothing is currently playing.")
        return
    
    # Server Management Commands
    
    # Poll System
    if message.content.startswith('!poll'):
        if not has_mod_permissions(message.author):
            await message.channel.send("❌ You don't have permission to create polls.")
            return
        
        try:
            # Parse poll command: !poll "Question?" "Option 1" "Option 2" [duration]
            parts = re.findall(r'"([^"]*)"', message.content)
            if len(parts) < 3:
                await message.channel.send("❌ Usage: `!poll \"Question?\" \"Option 1\" \"Option 2\" [\"Option 3\"...]`")
                return
            
            question = parts[0]
            options = parts[1:]
            
            # Check for duration (optional)
            duration = 60  # default 60 minutes
            duration_match = re.search(r'(\d+)m', message.content)
            if duration_match:
                duration = int(duration_match.group(1))
                if duration > 1440:  # Max 24 hours
                    duration = 1440
            
            poll_message, error = await create_poll(message.channel, question, options, duration)
            if error:
                await message.channel.send(f"❌ {error}")
            else:
                log_server_event(message.guild.id, "poll_created", message.author.id, message.channel.id, f"Poll: {question}")
                
        except Exception as e:
            await message.channel.send(f"❌ Error creating poll: {str(e)}")
        return
    
    # Moderation Commands
    if message.content.startswith('!warn'):
        if not has_mod_permissions(message.author):
            await message.channel.send("❌ You don't have permission to warn users.")
            return
        
        try:
            parts = message.content.split(' ', 2)
            if len(parts) < 2:
                await message.channel.send("❌ Usage: `!warn @user [reason]`")
                return
            
            user_mention = parts[1]
            reason = parts[2] if len(parts) > 2 else "No reason provided"
            
            if user_mention.startswith('<@') and user_mention.endswith('>'):
                user_id = int(user_mention[2:-1].replace('!', ''))
                user = message.guild.get_member(user_id)
                
                if user:
                    # Store warning in database
                    conn = sqlite3.connect('bot_data.db')
                    cursor = conn.cursor()
                    cursor.execute('''INSERT INTO warnings (user_id, guild_id, moderator_id, reason)
                                     VALUES (?, ?, ?, ?)''', (user_id, message.guild.id, message.author.id, reason))
                    conn.commit()
                    
                    # Get warning count
                    cursor.execute('SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?', (user_id, message.guild.id))
                    warning_count = cursor.fetchone()[0]
                    conn.close()
                    
                    embed = discord.Embed(title="⚠️ User Warned", color=0xff9900)
                    embed.add_field(name="User", value=user.mention, inline=True)
                    embed.add_field(name="Moderator", value=message.author.mention, inline=True)
                    embed.add_field(name="Reason", value=reason, inline=False)
                    embed.add_field(name="Total Warnings", value=str(warning_count), inline=True)
                    
                    await message.channel.send(embed=embed)
                    
                    # DM the user
                    try:
                        await user.send(f"⚠️ You have been warned in **{message.guild.name}**\nReason: {reason}\nTotal warnings: {warning_count}")
                    except:
                        pass
                    
                    log_server_event(message.guild.id, "user_warned", user_id, message.channel.id, f"Reason: {reason}")
                else:
                    await message.channel.send("❌ User not found in this server.")
            else:
                await message.channel.send("❌ Please mention a valid user.")
        except Exception as e:
            await message.channel.send(f"❌ Error warning user: {str(e)}")
        return
    
    if message.content.startswith('!kick'):
        if not message.author.guild_permissions.kick_members:
            await message.channel.send("❌ You don't have permission to kick users.")
            return
        
        try:
            parts = message.content.split(' ', 2)
            if len(parts) < 2:
                await message.channel.send("❌ Usage: `!kick @user [reason]`")
                return
            
            user_mention = parts[1]
            reason = parts[2] if len(parts) > 2 else "No reason provided"
            
            if user_mention.startswith('<@') and user_mention.endswith('>'):
                user_id = int(user_mention[2:-1].replace('!', ''))
                user = message.guild.get_member(user_id)
                
                if user:
                    if user.top_role >= message.author.top_role and message.author.id != message.guild.owner_id:
                        await message.channel.send("❌ You cannot kick users with equal or higher roles.")
                        return
                    
                    await user.kick(reason=reason)
                    
                    embed = discord.Embed(title="👢 User Kicked", color=0xff6600)
                    embed.add_field(name="User", value=f"{user.display_name} ({user.id})", inline=True)
                    embed.add_field(name="Moderator", value=message.author.mention, inline=True)
                    embed.add_field(name="Reason", value=reason, inline=False)
                    
                    await message.channel.send(embed=embed)
                    log_server_event(message.guild.id, "user_kicked", user_id, message.channel.id, f"Reason: {reason}")
                else:
                    await message.channel.send("❌ User not found in this server.")
            else:
                await message.channel.send("❌ Please mention a valid user.")
        except Exception as e:
            await message.channel.send(f"❌ Error kicking user: {str(e)}")
        return
    
    if message.content.startswith('!ban'):
        if not message.author.guild_permissions.ban_members:
            await message.channel.send("❌ You don't have permission to ban users.")
            return
        
        try:
            parts = message.content.split(' ', 2)
            if len(parts) < 2:
                await message.channel.send("❌ Usage: `!ban @user [reason]`")
                return
            
            user_mention = parts[1]
            reason = parts[2] if len(parts) > 2 else "No reason provided"
            
            if user_mention.startswith('<@') and user_mention.endswith('>'):
                user_id = int(user_mention[2:-1].replace('!', ''))
                user = message.guild.get_member(user_id)
                
                if user:
                    if user.top_role >= message.author.top_role and message.author.id != message.guild.owner_id:
                        await message.channel.send("❌ You cannot ban users with equal or higher roles.")
                        return
                    
                    await user.ban(reason=reason, delete_message_days=1)
                    
                    embed = discord.Embed(title="🔨 User Banned", color=0xff0000)
                    embed.add_field(name="User", value=f"{user.display_name} ({user.id})", inline=True)
                    embed.add_field(name="Moderator", value=message.author.mention, inline=True)
                    embed.add_field(name="Reason", value=reason, inline=False)
                    
                    await message.channel.send(embed=embed)
                    log_server_event(message.guild.id, "user_banned", user_id, message.channel.id, f"Reason: {reason}")
                else:
                    await message.channel.send("❌ User not found in this server.")
            else:
                await message.channel.send("❌ Please mention a valid user.")
        except Exception as e:
            await message.channel.send(f"❌ Error banning user: {str(e)}")
        return
    
    # Role Management
    if message.content.startswith('!addrole'):
        if not message.author.guild_permissions.manage_roles:
            await message.channel.send("❌ You don't have permission to manage roles.")
            return
        
        try:
            parts = message.content.split(' ', 2)
            if len(parts) < 3:
                await message.channel.send("❌ Usage: `!addrole @user RoleName`")
                return
            
            user_mention = parts[1]
            role_name = parts[2]
            
            if user_mention.startswith('<@') and user_mention.endswith('>'):
                user_id = int(user_mention[2:-1].replace('!', ''))
                user = message.guild.get_member(user_id)
                role = discord.utils.get(message.guild.roles, name=role_name)
                
                if user and role:
                    if role >= message.author.top_role and message.author.id != message.guild.owner_id:
                        await message.channel.send("❌ You cannot assign roles equal to or higher than your own.")
                        return
                    
                    await user.add_roles(role)
                    await message.channel.send(f"✅ Added role **{role.name}** to {user.display_name}")
                    log_server_event(message.guild.id, "role_added", user_id, message.channel.id, f"Role: {role.name}")
                else:
                    await message.channel.send("❌ User or role not found.")
            else:
                await message.channel.send("❌ Please mention a valid user.")
        except Exception as e:
            await message.channel.send(f"❌ Error adding role: {str(e)}")
        return
    
    if message.content.startswith('!removerole'):
        if not message.author.guild_permissions.manage_roles:
            await message.channel.send("❌ You don't have permission to manage roles.")
            return
        
        try:
            parts = message.content.split(' ', 2)
            if len(parts) < 3:
                await message.channel.send("❌ Usage: `!removerole @user RoleName`")
                return
            
            user_mention = parts[1]
            role_name = parts[2]
            
            if user_mention.startswith('<@') and user_mention.endswith('>'):
                user_id = int(user_mention[2:-1].replace('!', ''))
                user = message.guild.get_member(user_id)
                role = discord.utils.get(message.guild.roles, name=role_name)
                
                if user and role:
                    if role >= message.author.top_role and message.author.id != message.guild.owner_id:
                        await message.channel.send("❌ You cannot remove roles equal to or higher than your own.")
                        return
                    
                    await user.remove_roles(role)
                    await message.channel.send(f"✅ Removed role **{role.name}** from {user.display_name}")
                    log_server_event(message.guild.id, "role_removed", user_id, message.channel.id, f"Role: {role.name}")
                else:
                    await message.channel.send("❌ User or role not found.")
            else:
                await message.channel.send("❌ Please mention a valid user.")
        except Exception as e:
            await message.channel.send(f"❌ Error removing role: {str(e)}")
        return
    
    # Server Stats
    if message.content.startswith('!stats'):
        try:
            embed = discord.Embed(title=f"📊 Server Stats - {message.guild.name}", color=0x00ff00)
            
            # Basic stats
            embed.add_field(name="👥 Total Members", value=str(message.guild.member_count), inline=True)
            embed.add_field(name="📅 Created", value=message.guild.created_at.strftime("%B %d, %Y"), inline=True)
            embed.add_field(name="👑 Owner", value=message.guild.owner.display_name if message.guild.owner else "Unknown", inline=True)
            
            # Channel counts
            text_channels = len(message.guild.text_channels)
            voice_channels = len(message.guild.voice_channels)
            embed.add_field(name="💬 Text Channels", value=str(text_channels), inline=True)
            embed.add_field(name="🔊 Voice Channels", value=str(voice_channels), inline=True)
            embed.add_field(name="🎭 Roles", value=str(len(message.guild.roles)), inline=True)
            
            # Member status
            online = sum(1 for member in message.guild.members if member.status != discord.Status.offline)
            embed.add_field(name="🟢 Online", value=str(online), inline=True)
            embed.add_field(name="🔴 Offline", value=str(message.guild.member_count - online), inline=True)
            
            # Bot stats
            bots = sum(1 for member in message.guild.members if member.bot)
            embed.add_field(name="🤖 Bots", value=str(bots), inline=True)
            
            await message.channel.send(embed=embed)
        except Exception as e:
            await message.channel.send(f"❌ Error getting stats: {str(e)}")
        return
    
    # Warning check
    if message.content.startswith('!warnings'):
        try:
            parts = message.content.split(' ', 1)
            if len(parts) < 2:
                await message.channel.send("❌ Usage: `!warnings @user`")
                return
            
            user_mention = parts[1]
            if user_mention.startswith('<@') and user_mention.endswith('>'):
                user_id = int(user_mention[2:-1].replace('!', ''))
                user = message.guild.get_member(user_id)
                
                if user:
                    conn = sqlite3.connect('bot_data.db')
                    cursor = conn.cursor()
                    cursor.execute('''SELECT reason, timestamp FROM warnings 
                                     WHERE user_id = ? AND guild_id = ? 
                                     ORDER BY timestamp DESC LIMIT 10''', (user_id, message.guild.id))
                    warnings = cursor.fetchall()
                    conn.close()
                    
                    embed = discord.Embed(title=f"⚠️ Warnings for {user.display_name}", color=0xff9900)
                    
                    if warnings:
                        for i, (reason, timestamp) in enumerate(warnings, 1):
                            embed.add_field(
                                name=f"Warning #{i}",
                                value=f"**Reason:** {reason}\n**Date:** {timestamp}",
                                inline=False
                            )
                    else:
                        embed.add_field(name="No Warnings", value="This user has no warnings.", inline=False)
                    
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send("❌ User not found in this server.")
            else:
                await message.channel.send("❌ Please mention a valid user.")
        except Exception as e:
            await message.channel.send(f"❌ Error checking warnings: {str(e)}")
        return
    
    # Server logs viewing
    if message.content.startswith('!logs'):
        if not has_mod_permissions(message.author):
            await message.channel.send("❌ You don't have permission to view server logs.")
            return
        
        try:
            conn = sqlite3.connect('bot_data.db')
            cursor = conn.cursor()
            cursor.execute('''SELECT event_type, user_id, description, timestamp 
                             FROM server_logs 
                             WHERE guild_id = ? 
                             ORDER BY timestamp DESC LIMIT 20''', (message.guild.id,))
            logs = cursor.fetchall()
            conn.close()
            
            embed = discord.Embed(title="📋 Server Activity Logs", color=0x3498db)
            
            if logs:
                log_text = ""
                for event_type, user_id, description, timestamp in logs:
                    user_mention = f"<@{user_id}>" if user_id else "System"
                    log_text += f"**{event_type.upper()}** | {user_mention} | {description} | {timestamp}\n"
                
                # Split into chunks if too long
                if len(log_text) > 1024:
                    chunks = [log_text[i:i+1024] for i in range(0, len(log_text), 1024)]
                    for i, chunk in enumerate(chunks[:3]):  # Limit to 3 chunks
                        embed.add_field(name=f"Recent Activity {i+1}", value=chunk, inline=False)
                else:
                    embed.add_field(name="Recent Activity", value=log_text, inline=False)
            else:
                embed.add_field(name="No Logs", value="No recent activity logged.", inline=False)
            
            await message.channel.send(embed=embed)
        except Exception as e:
            await message.channel.send(f"❌ Error retrieving logs: {str(e)}")
        return
    
    # Announcement system
    if message.content.startswith('!announce'):
        if not has_mod_permissions(message.author):
            await message.channel.send("❌ You don't have permission to make announcements.")
            return
        
        try:
            parts = message.content.split(' ', 1)
            if len(parts) < 2:
                await message.channel.send("❌ Usage: `!announce Your announcement message here`")
                return
            
            announcement = parts[1]
            
            embed = discord.Embed(
                title="📢 Server Announcement",
                description=announcement,
                color=0x00ff00,
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=f"Announced by {message.author.display_name}")
            
            await message.channel.send(embed=embed)
            log_server_event(message.guild.id, "announcement_made", message.author.id, message.channel.id, 
                           f"Announcement: {announcement[:100]}...")
        except Exception as e:
            await message.channel.send(f"❌ Error making announcement: {str(e)}")
        return
    
    # Help command
    if message.content.startswith('/help') or message.content.startswith('!help'):
        # Split help into multiple embeds to avoid length limit
        embed1 = discord.Embed(title="🤖 Bot Commands Help - Part 1", color=0x3498db)
        embed1.add_field(name="🎵 Music Player", value="`!music` - Interactive music player\n`!search <song>` - Quick search", inline=False)
        embed1.add_field(name="🔍 Search", value="`--topic` - Search for information", inline=False)
        embed1.add_field(name="📅 Date & Time", value="`--what is todays date` - Get current date", inline=False)
        embed1.add_field(name="👤 User Commands", value="`!myid` - Get your Discord ID\n`!getid @user` - Get user ID (admin)", inline=False)
        
        embed2 = discord.Embed(title="🤖 Bot Commands Help - Part 2", color=0x9b59b6)
        embed2.add_field(name="🛡️ Moderation (Mods only)", value="`!warn @user [reason]` - Warn user\n`!kick @user [reason]` - Kick user\n`!ban @user [reason]` - Ban user\n`!warnings @user` - Check warnings", inline=False)
        embed2.add_field(name="🎭 Role Management", value="`!addrole @user RoleName` - Add role\n`!removerole @user RoleName` - Remove role", inline=False)
        embed2.add_field(name="📊 Server Management", value="`!poll \"Question?\" \"Option 1\" \"Option 2\"`\n`!stats` - Server statistics\n`!logs` - Activity logs\n`!announce message`", inline=False)
        
        embed3 = discord.Embed(title="🤖 Bot Commands Help - Part 3", color=0xe74c3c)
        embed3.add_field(name="🎉 Fun Commands", value="`hello`, `$hello`, `$meme`, `game?`, `mic`", inline=False)
        embed3.add_field(name="💬 DM Commands (Admin)", value="`!dm @user message` - Send DM\n`!dmid 123456789 message` - DM by ID", inline=False)
        embed3.add_field(name="❓ Private Commands", value="Start with `?` for private responses\n`?--topic`, `?meme`, `?myid`, etc.", inline=False)
        embed3.set_footer(text="Use any command to get started! 🚀")
        
        await message.channel.send(embed=embed1)
        await message.channel.send(embed=embed2)
        await message.channel.send(embed=embed3)
        return
    
    # Command to get your user ID
    if message.content.startswith('!myid'):
        await process_command(message, is_private=False)
        return
    
    # Command to get someone's user ID: !getid @user
    if message.content.startswith('!getid'):
        if message.author.id == 1187080447709171743:  # Your Discord user ID
            try:
                parts = message.content.split(' ', 1)
                if len(parts) >= 2:
                    user_mention = parts[1]
                    if user_mention.startswith('<@') and user_mention.endswith('>'):
                        user_id = int(user_mention[2:-1])
                        user = message.guild.get_member(user_id)
                        if user:
                            await message.channel.send(f"User ID for {user.display_name}: `{user_id}`")
                        else:
                            await message.channel.send("❌ User not found in this server")
                    else:
                        await message.channel.send("❌ Please mention a user with @username")
                else:
                    await message.channel.send("❌ Usage: !getid @user")
            except Exception as e:
                await message.channel.send(f"❌ Error: {str(e)}")
        else:
            await message.channel.send("❌ You don't have permission to use this command")
        return
    
    # Command to send DM to any user by ID: !dmid 123456789 message
    if message.content.startswith('!dmid'):
        if message.author.id == 1187080447709171743:  # Your Discord user ID
            try:
                parts = message.content.split(' ', 2)
                if len(parts) >= 3:
                    user_id_str = parts[1]
                    dm_message = parts[2]
                    
                    # Check if it's a valid user ID (numbers only)
                    if user_id_str.isdigit():
                        user_id = int(user_id_str)
                        try:
                            # Get user by ID (works for any Discord user)
                            user = await client.fetch_user(user_id)
                            await user.send(f"Message from {message.author.display_name}: {dm_message}")
                            await message.channel.send(f"✅ DM sent to {user.display_name} (ID: {user_id})")
                        except discord.NotFound:
                            await message.channel.send("❌ User not found with that ID")
                        except discord.Forbidden:
                            await message.channel.send("❌ Cannot send DM to this user (they may have DMs disabled)")
                        except Exception as e:
                            await message.channel.send(f"❌ Error: {str(e)}")
                    else:
                        await message.channel.send("❌ Please provide a valid User ID (numbers only)")
                else:
                    await message.channel.send("❌ Usage: !dmid 123456789012345678 your message here")
            except Exception as e:
                await message.channel.send(f"❌ Error sending DM: {str(e)}")
        else:
            await message.channel.send("❌ You don't have permission to use this command")
        return
    
    # Command to send DM to a server member: !dm @user message
    if message.content.startswith('!dm'):
        if message.author.id == 1187080447709171743:  # Your Discord user ID
            try:
                parts = message.content.split(' ', 2)
                if len(parts) >= 3:
                    user_mention = parts[1]
                    dm_message = parts[2]
                    
                    # Check if it's a user mention (@username)
                    if user_mention.startswith('<@') and user_mention.endswith('>'):
                        user_id = int(user_mention[2:-1])
                        
                        # Try multiple methods to find the user
                        user = message.guild.get_member(user_id)
                        if not user:
                            # Try fetching the user directly
                            try:
                                user = await client.fetch_user(user_id)
                            except:
                                user = None
                        
                        # Debug info
                        await message.channel.send(f"🔍 Debug: Looking for user ID {user_id} in server")
                        await message.channel.send(f"🔍 Debug: Found user: {user}")
                        await message.channel.send(f"🔍 Debug: Server members count: {len(message.guild.members)}")
                        
                        if user:
                            try:
                                await user.send(f"Message from {message.author.display_name}: {dm_message}")
                                await message.channel.send(f"✅ DM sent to {user.display_name}")
                            except discord.Forbidden:
                                await message.channel.send("❌ Cannot send DM to this user (they may have DMs disabled)")
                            except Exception as e:
                                await message.channel.send(f"❌ Error sending DM: {str(e)}")
                        else:
                            await message.channel.send("❌ User not found in this server")
                    else:
                        await message.channel.send("❌ Please mention a user with @username")
                else:
                    await message.channel.send("❌ Usage: !dm @user your message here")
            except Exception as e:
                await message.channel.send(f"❌ Error sending DM: {str(e)}")
        else:
            await message.channel.send("❌ You don't have permission to use this command")
        return
    # Process fun commands
    if (message.content.startswith('hello') or 
        message.content.startswith('$hello') or 
        message.content.startswith('$meme') or 
        message.content.startswith('game?') or 
        message.content.startswith('mic')):
        await process_command(message, is_private=False)
        return
    
    # Process entertainment commands
    if (message.content.startswith('ep') or 
        message.content.startswith('pp') or 
        message.content.startswith('bkl') or 
        message.content.startswith('lode') or 
        message.content.startswith('lawde') or 
        message.content.startswith('gandu')):
        entertainment_responses = {
            'ep': 'nuvvu ra ep',
            'pp': 'nuvvu pp',
            'bkl': 'em matladuthunav ra maidapindi',
            'lode': 'tuh lode',
            'lawde': 'tuh bk-lawde',
            'gandu': 'tuh gandu dalla'
        }
        for cmd, response in entertainment_responses.items():
            if message.content.startswith(cmd):
                await message.channel.send(response)
                return

intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
client.run(token=TOKEN)