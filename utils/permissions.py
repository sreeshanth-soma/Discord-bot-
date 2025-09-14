from config.settings import ADMIN_USER_ID

def has_mod_permissions(member):
    """Check if user has moderation permissions"""
    return (member.guild_permissions.kick_members or 
            member.guild_permissions.ban_members or 
            member.guild_permissions.manage_messages or
            member.id == ADMIN_USER_ID)

def is_admin(member):
    """Check if user is the bot admin"""
    return member.id == ADMIN_USER_ID

def can_kick(member):
    """Check if user can kick members"""
    return member.guild_permissions.kick_members or member.id == ADMIN_USER_ID

def can_ban(member):
    """Check if user can ban members"""
    return member.guild_permissions.ban_members or member.id == ADMIN_USER_ID

def can_manage_roles(member):
    """Check if user can manage roles"""
    return member.guild_permissions.manage_roles or member.id == ADMIN_USER_ID

def can_manage_messages(member):
    """Check if user can manage messages"""
    return member.guild_permissions.manage_messages or member.id == ADMIN_USER_ID

def get_user_from_mention(message, mention):
    """Get user from mention string"""
    if not mention:
        return None
    
    # Check if it's a user mention
    if mention.startswith('<@') and mention.endswith('>'):
        # Remove <@ and > and check if it's a user ID
        user_id = mention[2:-1]
        if user_id.startswith('!'):
            user_id = user_id[1:]  # Remove ! for nickname mentions
        
        try:
            return message.guild.get_member(int(user_id))
        except ValueError:
            return None
    
    # Check if it's a raw user ID
    try:
        user_id = int(mention)
        return message.guild.get_member(user_id)
    except ValueError:
        pass
    
    # Check if it's a username#discriminator or display name
    for member in message.guild.members:
        if (member.name.lower() == mention.lower() or 
            member.display_name.lower() == mention.lower() or
            str(member).lower() == mention.lower()):
            return member
    
    return None
