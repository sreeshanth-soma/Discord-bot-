import discord
from utils.permissions import is_admin

async def handle_myid(message):
    """Handle !myid command"""
    await message.channel.send(f"Your Discord User ID: `{message.author.id}`")

async def handle_getid(message, client):
    """Handle !getid command - admin only"""
    if not is_admin(message.author):
        await message.channel.send("❌ You don't have permission to use this command")
        return
    
    try:
        parts = message.content.split(' ', 1)
        if len(parts) >= 2:
            user_mention = parts[1]
            if user_mention.startswith('<@') and user_mention.endswith('>'):
                user_id = int(user_mention[2:-1].replace('!', ''))
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

async def handle_dm_commands(message, client):
    """Handle DM commands - admin only"""
    if not is_admin(message.author):
        await message.channel.send("❌ You don't have permission to use this command")
        return
    
    if message.content.startswith('!dmid'):
        await handle_dmid(message, client)
    elif message.content.startswith('!dm'):
        await handle_dm(message, client)

async def handle_dmid(message, client):
    """Handle !dmid command"""
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

async def handle_dm(message, client):
    """Handle !dm command"""
    try:
        parts = message.content.split(' ', 2)
        if len(parts) >= 3:
            user_mention = parts[1]
            dm_message = parts[2]
            
            # Check if it's a user mention (@username)
            if user_mention.startswith('<@') and user_mention.endswith('>'):
                user_id = int(user_mention[2:-1].replace('!', ''))
                
                # Try multiple methods to find the user
                user = message.guild.get_member(user_id)
                if not user:
                    # Try fetching the user directly
                    try:
                        user = await client.fetch_user(user_id)
                    except:
                        user = None
                
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

async def handle_stats(message):
    """Handle !stats command"""
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

async def process_utility_commands(message, client):
    """Process utility commands"""
    content = message.content.lower()
    
    if message.content.startswith('!myid'):
        await handle_myid(message)
        return True
    elif message.content.startswith('!getid'):
        await handle_getid(message, client)
        return True
    elif message.content.startswith('!dmid'):
        await handle_dm_commands(message, client)
        return True
    elif message.content.startswith('!dm'):
        await handle_dm_commands(message, client)
        return True
    elif message.content.startswith('!stats'):
        await handle_stats(message)
        return True
    
    return False
