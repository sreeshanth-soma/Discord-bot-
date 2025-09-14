import discord
from utils.database import add_warning, get_warnings, log_server_event
from utils.permissions import has_mod_permissions, get_user_from_mention

async def handle_warn_command(message):
    """Handle !warn command"""
    if not has_mod_permissions(message.author):
        await message.channel.send("❌ You don't have permission to use this command!")
        return True
    
    # Parse command: !warn @user reason
    parts = message.content.split(' ', 2)
    if len(parts) < 3:
        await message.channel.send("❌ Usage: `!warn @user <reason>`")
        return True
    
    user_mention = parts[1]
    reason = parts[2]
    
    # Get user from mention
    user = get_user_from_mention(message, user_mention)
    if not user:
        await message.channel.send("❌ User not found!")
        return True
    
    # Add warning to database
    warning_count = add_warning(user.id, message.guild.id, message.author.id, reason)
    
    if warning_count is not None:
        embed = discord.Embed(
            title="⚠️ Warning Issued",
            color=0xffa500,
            timestamp=message.created_at
        )
        embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=True)
        embed.add_field(name="Moderator", value=f"{message.author.mention}", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Total Warnings", value=f"{warning_count}", inline=True)
        embed.set_footer(text=f"Warning #{warning_count}")
        
        await message.channel.send(embed=embed)
        
        # Log the warning
        log_server_event(message.guild.id, "warning_issued", user.id, message.channel.id,
                        f"Warning issued by {message.author.display_name}: {reason}")
        
        # Try to DM the user
        try:
            dm_embed = discord.Embed(
                title="⚠️ You have been warned",
                description=f"You received a warning in **{message.guild.name}**",
                color=0xffa500
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Total Warnings", value=f"{warning_count}", inline=True)
            dm_embed.set_footer(text="Please follow the server rules to avoid further action.")
            
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass  # User has DMs disabled
    else:
        await message.channel.send("❌ Failed to add warning to database!")
    
    return True

async def handle_kick_command(message):
    """Handle !kick command"""
    if not has_mod_permissions(message.author):
        await message.channel.send("❌ You don't have permission to use this command!")
        return True
    
    # Parse command: !kick @user reason
    parts = message.content.split(' ', 2)
    if len(parts) < 3:
        await message.channel.send("❌ Usage: `!kick @user <reason>`")
        return True
    
    user_mention = parts[1]
    reason = parts[2]
    
    # Get user from mention
    user = get_user_from_mention(message, user_mention)
    if not user:
        await message.channel.send("❌ User not found!")
        return True
    
    # Check if user can be kicked
    if user.top_role >= message.author.top_role and message.author != message.guild.owner:
        await message.channel.send("❌ You cannot kick someone with equal or higher role!")
        return True
    
    try:
        # DM the user before kicking
        try:
            dm_embed = discord.Embed(
                title="👢 You have been kicked",
                description=f"You were kicked from **{message.guild.name}**",
                color=0xff0000
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.set_footer(text="You can rejoin if you have an invite link.")
            
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass  # User has DMs disabled
        
        # Kick the user
        await user.kick(reason=f"Kicked by {message.author.display_name}: {reason}")
        
        embed = discord.Embed(
            title="👢 User Kicked",
            color=0xff0000,
            timestamp=message.created_at
        )
        embed.add_field(name="User", value=f"{user.display_name} ({user.id})", inline=True)
        embed.add_field(name="Moderator", value=f"{message.author.mention}", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await message.channel.send(embed=embed)
        
        # Log the kick
        log_server_event(message.guild.id, "user_kicked", user.id, message.channel.id,
                        f"Kicked by {message.author.display_name}: {reason}")
        
    except discord.Forbidden:
        await message.channel.send("❌ I don't have permission to kick this user!")
    except Exception as e:
        await message.channel.send(f"❌ Error kicking user: {str(e)}")
    
    return True

async def handle_ban_command(message):
    """Handle !ban command"""
    if not has_mod_permissions(message.author):
        await message.channel.send("❌ You don't have permission to use this command!")
        return True
    
    # Parse command: !ban @user reason
    parts = message.content.split(' ', 2)
    if len(parts) < 3:
        await message.channel.send("❌ Usage: `!ban @user <reason>`")
        return True
    
    user_mention = parts[1]
    reason = parts[2]
    
    # Get user from mention
    user = get_user_from_mention(message, user_mention)
    if not user:
        await message.channel.send("❌ User not found!")
        return True
    
    # Check if user can be banned
    if user.top_role >= message.author.top_role and message.author != message.guild.owner:
        await message.channel.send("❌ You cannot ban someone with equal or higher role!")
        return True
    
    try:
        # DM the user before banning
        try:
            dm_embed = discord.Embed(
                title="🔨 You have been banned",
                description=f"You were banned from **{message.guild.name}**",
                color=0x8b0000
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.set_footer(text="This ban is permanent unless appealed.")
            
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass  # User has DMs disabled
        
        # Ban the user
        await user.ban(reason=f"Banned by {message.author.display_name}: {reason}")
        
        embed = discord.Embed(
            title="🔨 User Banned",
            color=0x8b0000,
            timestamp=message.created_at
        )
        embed.add_field(name="User", value=f"{user.display_name} ({user.id})", inline=True)
        embed.add_field(name="Moderator", value=f"{message.author.mention}", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await message.channel.send(embed=embed)
        
        # Log the ban
        log_server_event(message.guild.id, "user_banned", user.id, message.channel.id,
                        f"Banned by {message.author.display_name}: {reason}")
        
    except discord.Forbidden:
        await message.channel.send("❌ I don't have permission to ban this user!")
    except Exception as e:
        await message.channel.send(f"❌ Error banning user: {str(e)}")
    
    return True

async def handle_warnings_command(message):
    """Handle !warnings command"""
    if not has_mod_permissions(message.author):
        await message.channel.send("❌ You don't have permission to use this command!")
        return True
    
    # Parse command: !warnings @user
    parts = message.content.split(' ', 1)
    if len(parts) < 2:
        await message.channel.send("❌ Usage: `!warnings @user`")
        return True
    
    user_mention = parts[1]
    
    # Get user from mention
    user = get_user_from_mention(message, user_mention)
    if not user:
        await message.channel.send("❌ User not found!")
        return True
    
    # Get warnings from database
    warnings = get_warnings(user.id, message.guild.id)
    
    if not warnings:
        await message.channel.send(f"✅ {user.mention} has no warnings!")
        return True
    
    embed = discord.Embed(
        title=f"⚠️ Warnings for {user.display_name}",
        color=0xffa500,
        timestamp=message.created_at
    )
    
    for i, (reason, timestamp) in enumerate(warnings[:10], 1):  # Show last 10 warnings
        embed.add_field(
            name=f"Warning #{i}",
            value=f"**Reason:** {reason}\n**Date:** {timestamp}",
            inline=False
        )
    
    if len(warnings) > 10:
        embed.set_footer(text=f"Showing last 10 of {len(warnings)} warnings")
    else:
        embed.set_footer(text=f"Total: {len(warnings)} warnings")
    
    await message.channel.send(embed=embed)
    return True

async def handle_poll_command(message):
    """Handle !poll command"""
    if not has_mod_permissions(message.author):
        await message.channel.send("❌ You don't have permission to use this command!")
        return True
    
    # Parse command: !poll question
    poll_question = message.content[6:].strip()  # Remove "!poll "
    
    if not poll_question:
        await message.channel.send("❌ Usage: `!poll <question>`")
        return True
    
    embed = discord.Embed(
        title="📊 Poll",
        description=poll_question,
        color=0x3498db,
        timestamp=message.created_at
    )
    embed.set_footer(text=f"Poll created by {message.author.display_name}")
    
    poll_message = await message.channel.send(embed=embed)
    
    # Add reaction options
    await poll_message.add_reaction("✅")  # Yes/Agree
    await poll_message.add_reaction("❌")  # No/Disagree
    await poll_message.add_reaction("🤷")  # Neutral/Unsure
    
    # Log the poll creation
    log_server_event(message.guild.id, "poll_created", message.author.id, message.channel.id,
                    f"Poll created: {poll_question}")
    
    return True

async def handle_announce_command(message):
    """Handle !announce command"""
    if not has_mod_permissions(message.author):
        await message.channel.send("❌ You don't have permission to use this command!")
        return True
    
    # Parse command: !announce message
    announcement = message.content[10:].strip()  # Remove "!announce "
    
    if not announcement:
        await message.channel.send("❌ Usage: `!announce <message>`")
        return True
    
    embed = discord.Embed(
        title="📢 Server Announcement",
        description=announcement,
        color=0xff6b6b,
        timestamp=message.created_at
    )
    embed.set_footer(text=f"Announced by {message.author.display_name}")
    
    await message.channel.send("@everyone", embed=embed)
    
    # Log the announcement
    log_server_event(message.guild.id, "announcement_made", message.author.id, message.channel.id,
                    f"Announcement: {announcement}")
    
    return True

async def handle_logs_command(message):
    """Handle !logs command"""
    if not has_mod_permissions(message.author):
        await message.channel.send("❌ You don't have permission to use this command!")
        return True
    
    # This would typically show recent server logs
    # For now, we'll show a placeholder
    embed = discord.Embed(
        title="📋 Server Logs",
        description="Recent server activity logs would be displayed here.",
        color=0x9b59b6
    )
    embed.add_field(
        name="Available Logs",
        value="• Member joins/leaves\n• Message edits/deletes\n• Moderation actions\n• Auto-moderation triggers",
        inline=False
    )
    embed.set_footer(text="Logs are stored in the database for security purposes")
    
    await message.channel.send(embed=embed)
    return True

async def process_moderation_commands(message):
    """Process all moderation commands"""
    content = message.content.lower()
    
    if content.startswith('!warn '):
        return await handle_warn_command(message)
    elif content.startswith('!kick '):
        return await handle_kick_command(message)
    elif content.startswith('!ban '):
        return await handle_ban_command(message)
    elif content.startswith('!warnings '):
        return await handle_warnings_command(message)
    elif content.startswith('!poll '):
        return await handle_poll_command(message)
    elif content.startswith('!announce '):
        return await handle_announce_command(message)
    elif content == '!logs':
        return await handle_logs_command(message)
    
    return False
