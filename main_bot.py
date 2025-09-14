import discord
from discord.ext import commands
import asyncio
import time
from collections import defaultdict, deque

# Import configuration
from config.settings import TOKEN

# Railway database setup
try:
    from railway_db_setup import setup_railway_database
    setup_railway_database()
except ImportError:
    pass  # Local development

# Import utilities
from utils.database import init_database, log_server_event
from utils.permissions import has_mod_permissions

# Import command handlers
from commands.fun import process_fun_command, handle_entertainment_commands
from commands.search import handle_search_command, handle_private_search_command
from commands.utility import process_utility_commands
from commands.music import process_music_commands, initialize_music_player
from commands.moderation import process_moderation_commands

# Auto-moderation settings
spam_tracker = defaultdict(lambda: deque(maxlen=5))
from config.settings import BAD_WORDS as bad_words

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

class MyClient(discord.Client):
    async def on_ready(self):
        print(f'Logged on as {self.user}!')
        # Initialize music player
        initialize_music_player(self)

    async def on_member_join(self, member):
        channel = member.guild.system_channel
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
        
        # Update activity for auto-stop functionality
        try:
            import requests
            requests.post('http://localhost:8080/activity', timeout=1)
        except:
            pass  # Health server might not be running
        
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
                    pass
                except discord.errors.Forbidden:
                    pass
            
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
                    pass
                except discord.errors.Forbidden:
                    pass
        
        # Process search commands
        if await handle_search_command(message, is_private=False):
            return
        
        # Process private commands
        if message.content.startswith('?'):
            # Handle private search commands
            if await handle_private_search_command(message):
                return
            
            # Handle other private commands
            private_command = message.content[1:].strip()
            if await process_fun_command_private(message, private_command):
                return
            else:
                # Default private response for unknown commands
                await message.author.send('This is a private message response to your question.')
            return
        
        # Process fun commands
        if await process_fun_command(message, is_private=False):
            return
        
        # Process entertainment commands
        if await handle_entertainment_commands(message):
            return
        
        # Process utility commands
        if await process_utility_commands(message, self):
            return
        
        # Process moderation commands
        if await process_moderation_commands(message):
            return
        
        # Process music commands
        if await process_music_commands(message):
            return
        
        # Help commands
        if message.content.startswith('/help') or message.content.startswith('!help'):
            await send_help_message(message)
            return
        elif message.content.startswith('/ahelp') or message.content.startswith('!ahelp'):
            await send_admin_help_message(message)
            return

async def process_fun_command_private(message, private_command):
    """Process private fun commands"""
    if private_command == 'meme' or private_command == '$meme':
        from utils.helpers import get_meme
        await message.author.send(get_meme())
        return True
    elif private_command == 'myid':
        await message.author.send(f"Your Discord User ID: `{message.author.id}`")
        return True
    elif private_command == 'hello' or private_command == '$hello':
        await message.author.send('Hello World! (Private)')
        return True
    elif private_command == 'game?':
        await message.author.send('whatsapp come')
        return True
    elif private_command == 'mic':
        await message.author.send('hey mike, mic on chey ra')
        return True
    
    return False

async def send_help_message(message):
    """Send help message for all users"""
    # General Commands
    embed1 = discord.Embed(title="🤖 Bot Commands Help", color=0x3498db)
    embed1.add_field(name="🔍 Search", value="`--topic` - Search for information", inline=False)
    embed1.add_field(name="📅 Date & Time", value="`--what is todays date` - Get current date", inline=False)
    embed1.add_field(name="🎉 Fun Commands", value="`hello`, `$hello`, `$meme`, `game?`, `mic`", inline=False)
    embed1.add_field(name="🛠️ Utility Commands", value="`!myid` - Get your Discord ID\n`!stats` - Server statistics", inline=False)
    embed1.add_field(name="❓ Private Commands", value="Start with `?` for private responses\n`?--topic`, `?meme`, `?myid`, etc.", inline=False)
    embed1.add_field(name="🤖 Auto-Moderation", value="**Spam Detection** - Auto-deletes spam messages\n**Content Filter** - Removes inappropriate content", inline=False)
    embed1.set_footer(text="Use any command to get started! 🚀")
    
    # Music Commands (Separate Message)
    embed2 = discord.Embed(title="🎵 Music Commands", color=0x1DB954)
    embed2.add_field(name="⚠️ Important Note", value="**You must be in a voice channel to use music commands!**", inline=False)
    embed2.add_field(name="🎵 Music Player", value="`!music` - Interactive music player\n`!play <song>` - Play music\n`!search <song>` - Quick search", inline=True)
    embed2.add_field(name="🎵 Music Controls", value="`!pause` - Pause music\n`!resume` - Resume music\n`!skip` - Skip song\n`!stop` - Stop music\n`!queue` - Show queue\n`!volume <0-100>` - Set volume\n`!loop` - Toggle loop\n`!leave` - Leave voice channel\n`!nowplaying` - Current song", inline=True)
    embed2.set_footer(text="Join a voice channel to start using music commands! 🎧")
    
    await message.channel.send(embed=embed1)
    await message.channel.send(embed=embed2)

async def send_admin_help_message(message):
    """Send admin help message"""
    # Check if user has admin permissions
    if not has_mod_permissions(message.author):
        await message.channel.send("❌ You don't have permission to use admin commands!")
        return
    
    embed1 = discord.Embed(title="🔒 Admin Commands Help - Part 1", color=0xe74c3c)
    embed1.add_field(name="👥 User Management", value="`!getid @user` - Get user ID\n`!warn @user <reason>` - Issue warning\n`!kick @user <reason>` - Kick user\n`!ban @user <reason>` - Ban user\n`!warnings @user` - Check warnings", inline=False)
    embed1.add_field(name="💬 DM Commands", value="`!dm @user message` - Send DM\n`!dmid 123456789 message` - DM by ID", inline=False)
    embed1.add_field(name="📊 Server Management", value="`!poll <question>` - Create poll\n`!announce <message>` - Server announcement\n`!logs` - View server logs", inline=False)
    
    embed2 = discord.Embed(title="🔒 Admin Commands Help - Part 2", color=0x8e44ad)
    embed2.add_field(name="🔧 Bot Management", value="`!ahelp` - Show this admin help\n`!stats` - Detailed server statistics", inline=False)
    embed2.add_field(name="📈 Monitoring", value="**Activity Logging** - Tracks all server events\n**Auto-Moderation** - Spam and content filtering\n**Member Tracking** - Join/leave events", inline=False)
    embed2.add_field(name="⚠️ Important Notes", value="• Admin commands require proper permissions\n• All actions are logged for security\n• Use moderation commands responsibly", inline=False)
    embed2.set_footer(text="Admin commands - Use responsibly! 🛡️")
    
    await message.channel.send(embed=embed1)
    await message.channel.send(embed=embed2)

# Initialize database
init_database()

# Setup Discord intents
intents = discord.Intents.default()
intents.message_content = True

# Create and run client
client = MyClient(intents=intents)

if __name__ == "__main__":
    client.run(token=TOKEN)
