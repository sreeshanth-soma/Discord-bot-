import sqlite3
import json
from datetime import datetime, timedelta

def init_database():
    """Initialize the database with all required tables"""
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

def log_server_event(guild_id, event_type, user_id=None, channel_id=None, description=None):
    """Log server events to database"""
    try:
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO server_logs (guild_id, event_type, user_id, channel_id, description)
                         VALUES (?, ?, ?, ?, ?)''', (guild_id, event_type, user_id, channel_id, description))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging event: {e}")

def add_warning(user_id, guild_id, moderator_id, reason):
    """Add a warning to the database"""
    try:
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO warnings (user_id, guild_id, moderator_id, reason)
                         VALUES (?, ?, ?, ?)''', (user_id, guild_id, moderator_id, reason))
        conn.commit()
        
        # Get warning count
        cursor.execute('SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?', (user_id, guild_id))
        warning_count = cursor.fetchone()[0]
        conn.close()
        return warning_count
    except Exception as e:
        print(f"Error adding warning: {e}")
        return 0

def get_warnings(user_id, guild_id, limit=10):
    """Get warnings for a user"""
    try:
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('''SELECT reason, timestamp FROM warnings 
                         WHERE user_id = ? AND guild_id = ? 
                         ORDER BY timestamp DESC LIMIT ?''', (user_id, guild_id, limit))
        warnings = cursor.fetchall()
        conn.close()
        return warnings
    except Exception as e:
        print(f"Error getting warnings: {e}")
        return []

def get_server_logs(guild_id, limit=20):
    """Get server logs"""
    try:
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('''SELECT event_type, user_id, description, timestamp 
                         FROM server_logs 
                         WHERE guild_id = ? 
                         ORDER BY timestamp DESC LIMIT ?''', (guild_id, limit))
        logs = cursor.fetchall()
        conn.close()
        return logs
    except Exception as e:
        print(f"Error retrieving logs: {e}")
        return []

def create_poll_db(message_id, channel_id, guild_id, creator_id, question, options, end_time):
    """Create a poll in the database"""
    try:
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO polls (message_id, channel_id, guild_id, creator_id, question, options, end_time)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                      (message_id, channel_id, guild_id, creator_id, question, json.dumps(options), end_time))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error creating poll: {e}")
        return False

def end_poll_db(message_id):
    """End a poll in the database"""
    try:
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE polls SET active = 0 WHERE message_id = ?', (message_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error ending poll: {e}")
        return False
