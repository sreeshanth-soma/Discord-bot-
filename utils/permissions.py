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
