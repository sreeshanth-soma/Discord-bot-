import discord
import asyncio
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from config.settings import YTDL_FORMAT_OPTIONS, FFMPEG_OPTIONS, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
from collections import defaultdict

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

ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)

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
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

    @classmethod
    async def search_youtube(cls, search_query, *, loop=None):
        """Search YouTube and return video info"""
        loop = loop or asyncio.get_event_loop()
        
        def search():
            try:
                search_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'default_search': 'ytsearch1:',
                    'extract_flat': False,
                    'skip_download': True,
                }
                
                with yt_dlp.YoutubeDL(search_opts) as ydl:
                    search_results = ydl.extract_info(f"ytsearch1:{search_query}", download=False)
                    
                if search_results and 'entries' in search_results and search_results['entries']:
                    video = search_results['entries'][0]
                    return (
                        video.get('webpage_url', f"https://www.youtube.com/watch?v={video.get('id')}"),
                        video.get('title', 'Unknown Title'),
                        video.get('duration', 0),
                        video.get('thumbnail', ''),
                        video.get('uploader', 'Unknown'),
                        video.get('view_count', 0)
                    )
                    
                return None, None, None, None, None, None
            except Exception as e:
                print(f"YouTube search error: {e}")
                return None, None, None, None, None, None
        
        return await loop.run_in_executor(None, search)

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
                search_query = f"{song_info['title']} {song_info.get('uploader', '')}"
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
            search_query = f"{song_info['title']} {song_info.get('uploader', '')}"
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
