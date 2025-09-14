"""
Railway startup script - handles database setup and starts the bot
"""
import os
import sys
import shutil
from pathlib import Path

def setup_railway_environment():
    """Setup Railway environment for the Discord bot"""
    
    print("🚀 Setting up Railway environment...")
    
    # Install FFmpeg if not available
    try:
        import subprocess
        # Check if ffmpeg is available
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("🎵 FFmpeg is already available")
            print(f"🎵 FFmpeg version: {result.stdout.split()[2] if len(result.stdout.split()) > 2 else 'Unknown'}")
        else:
            raise FileNotFoundError("FFmpeg not found")
    except FileNotFoundError:
        print("📦 Installing FFmpeg...")
        try:
            # Try to install ffmpeg using apt (Railway uses Ubuntu-based containers)
            print("📦 Updating package lists...")
            subprocess.run(['apt-get', 'update'], check=True, capture_output=True)
            print("📦 Installing FFmpeg and audio libraries...")
            subprocess.run(['apt-get', 'install', '-y', 'ffmpeg', 'libopus0', 'libopus-dev', 'libffi-dev', 'pkg-config'], check=True, capture_output=True)
            
            # Verify installation
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ FFmpeg installed successfully")
                print(f"✅ FFmpeg version: {result.stdout.split()[2] if len(result.stdout.split()) > 2 else 'Unknown'}")
            else:
                raise Exception("FFmpeg installation verification failed")
                
            # Verify Opus library
            try:
                result = subprocess.run(['pkg-config', '--exists', 'opus'], capture_output=True)
                if result.returncode == 0:
                    print("✅ Opus library is available")
                else:
                    print("⚠️ Opus library verification failed")
            except FileNotFoundError:
                print("⚠️ pkg-config not available for Opus verification")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"⚠️ Could not install FFmpeg: {e}")
            print("⚠️ Music features may not work properly")
    
    # Create data directory
    data_dir = Path("/tmp/bot_data")
    data_dir.mkdir(exist_ok=True)
    
    # Copy existing database if it exists
    if Path("bot_data.db").exists():
        shutil.copy("bot_data.db", "/tmp/bot_data/bot_data.db")
        print("📊 Copied existing database")
    
    # Set environment variables for Railway
    os.environ['DATABASE_PATH'] = '/tmp/bot_data/bot_data.db'
    
    print(f"✅ Database path: {os.environ['DATABASE_PATH']}")
    print("🤖 Starting Discord bot...")

def setup_opus_library():
    """Setup Opus library for Discord voice functionality"""
    print("🎵 Setting up Opus library...")
    
    # Add library path to environment
    import os
    current_path = os.environ.get('LD_LIBRARY_PATH', '')
    if '/usr/lib/x86_64-linux-gnu' not in current_path:
        os.environ['LD_LIBRARY_PATH'] = f"/usr/lib/x86_64-linux-gnu:{current_path}"
        print(f"✅ Added library path: {os.environ['LD_LIBRARY_PATH']}")
    
    try:
        import discord
        # Try loading Opus library with different methods
        opus_loaded = False
        
        # Method 1: Try full path to libopus.so.0
        try:
            discord.opus.load_opus('/usr/lib/x86_64-linux-gnu/libopus.so.0')
            print("✅ Opus loaded successfully (/usr/lib/x86_64-linux-gnu/libopus.so.0)")
            opus_loaded = True
        except Exception as e:
            print(f"⚠️ Method 1 failed: {e}")
        
        # Method 2: Try full path to libopus.so
        if not opus_loaded:
            try:
                discord.opus.load_opus('/usr/lib/x86_64-linux-gnu/libopus.so')
                print("✅ Opus loaded successfully (/usr/lib/x86_64-linux-gnu/libopus.so)")
                opus_loaded = True
            except Exception as e:
                print(f"⚠️ Method 2 failed: {e}")
        
        # Method 3: Try libopus.so.0 (simple name)
        if not opus_loaded:
            try:
                discord.opus.load_opus('libopus.so.0')
                print("✅ Opus loaded successfully (libopus.so.0)")
                opus_loaded = True
            except Exception as e:
                print(f"⚠️ Method 3 failed: {e}")
        
        # Method 4: Try libopus.so (simple name)
        if not opus_loaded:
            try:
                discord.opus.load_opus('libopus.so')
                print("✅ Opus loaded successfully (libopus.so)")
                opus_loaded = True
            except Exception as e:
                print(f"⚠️ Method 4 failed: {e}")
        
        # Method 5: Check if already loaded
        if not opus_loaded:
            try:
                if discord.opus.is_loaded():
                    print("✅ Opus is already loaded")
                    opus_loaded = True
            except Exception as e:
                print(f"⚠️ Opus check failed: {e}")
        
        if not opus_loaded:
            print("❌ Could not load Opus library - voice features will not work")
            print("📋 Available libraries:")
            import subprocess
            try:
                result = subprocess.run(['find', '/usr/lib', '-name', '*opus*'], capture_output=True, text=True)
                print(result.stdout)
            except:
                pass
        
        return opus_loaded
    except Exception as e:
        print(f"❌ Error setting up Opus: {e}")
        return False

if __name__ == "__main__":
    # Setup environment
    setup_railway_environment()
    
    # Setup Opus before importing Discord bot
    setup_opus_library()
    
    # Import and run the main bot
    try:
        print("📡 Connecting to Discord...")
        # Import the bot components
        import main_bot
        
        # Run the bot directly
        main_bot.client.run(token=main_bot.TOKEN)
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
