import discord
import asyncio
import yt_dlp
import os
import base64
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

def _prepare_cookiefile() -> str | None:
    """Resolve a cookies file for yt-dlp.

    Priority:
      1) YT_DLP_COOKIES_PATH env (existing file)
      2) utils/cookies.txt in repo (if present)
      3) YT_DLP_COOKIES_B64 (base64 content)
      4) YT_DLP_COOKIES (raw Netscape content)
    Returns path or None.
    """
    try:
        # 1) Explicit path via env
        path_env = os.getenv('YT_DLP_COOKIES_PATH')
        if path_env and os.path.isfile(path_env):
            return path_env

        # 2) Project file fallback
        for candidate in (
            'utils/cookies.txt',           # local dev
            '/app/utils/cookies.txt',      # Railway container path
        ):
            if os.path.isfile(candidate):
                return candidate

        # 3/4) Inline content via env → write to /tmp
        cookies_raw = os.getenv('YT_DLP_COOKIES')
        cookies_b64 = os.getenv('YT_DLP_COOKIES_B64')
        if cookies_b64 and not cookies_raw:
            try:
                cookies_raw = base64.b64decode(cookies_b64).decode('utf-8', errors='ignore')
            except Exception as e:
                print(f"Failed to decode YT_DLP_COOKIES_B64: {e}")
        if cookies_raw:
            cookiefile = '/tmp/youtube_cookies.txt'
            with open(cookiefile, 'w', encoding='utf-8') as f:
                f.write(cookies_raw)
            return cookiefile
    except Exception as e:
        print(f"Error preparing cookies file: {e}")
    return None


def _build_ytdl(opts: dict | None = None) -> yt_dlp.YoutubeDL:
    """Build a YoutubeDL instance with hardened options (android client, cookies)."""
    final_opts = dict(YTDL_FORMAT_OPTIONS)
    final_opts.update({
        'format': 'bestaudio[ext=m4a]/bestaudio/best',  # Prefer M4A, then any best audio
        'noprogress': True,
        'quiet': True,
        'geo_bypass': True,
        'extractor_args': {
            'youtube': {'player_client': ['android']},
        },
    })
    cookiefile = _prepare_cookiefile()
    if cookiefile:
        final_opts['cookiefile'] = cookiefile
    if opts:
        final_opts.update(opts)
    return yt_dlp.YoutubeDL(final_opts)


ytdl = _build_ytdl()

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
        try:
            def _extract():
                try:
                    return ytdl.extract_info(url, download=not stream)
                except Exception as e1:
                    err = str(e1)
                    print(f"yt-dlp extract failed, retrying (fresh client): {err}")
                    # Retry 1: fresh client with same options
                    try:
                        fresh = _build_ytdl()
                        return fresh.extract_info(url, download=not stream)
                    except Exception as e2:
                        err2 = str(e2)
                        # Retry 2: adjust format to a more permissive selector
                        try:
                            print(f"yt-dlp second attempt failed, retry with permissive format: {err2}")
                            permissive = _build_ytdl({
                                'format': 'bestaudio[ext=webm]/bestaudio/best'
                            })
                            return permissive.extract_info(url, download=not stream)
                        except Exception as e3:
                            # Final attempt: remove format constraint entirely
                            print(f"yt-dlp third attempt failed, retry without format: {e3}")
                            nofmt = _build_ytdl({})
                            # remove any inherited format by rebuilding without override
                            return nofmt.extract_info(url, download=not stream)

            data = await loop.run_in_executor(None, _extract)
            
            if 'entries' in data:
                data = data['entries'][0]

            filename = data['url'] if stream else ytdl.prepare_filename(data)
            
            # Test FFmpeg availability before creating audio source
            try:
                import subprocess
                subprocess.run(['ffmpeg', '-version'], check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                raise Exception(f"FFmpeg not available: {e}")
            
            print(f"🎵 Creating FFmpeg audio source for: {filename}")
            print(f"🎵 FFMPEG_OPTIONS: {FFMPEG_OPTIONS}")
            audio_source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
            print(f"✅ FFmpeg audio source created successfully")
            return cls(audio_source, data=data)
        except Exception as e:
            print(f"❌ Error in YTDLSource.from_url: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise

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
                ydl = _build_ytdl(search_opts)
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
                }
                ydl = _build_ytdl(search_opts)
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
