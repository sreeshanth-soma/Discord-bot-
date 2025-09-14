"""
Railway Database Setup - Ensures proper database handling on Railway
"""
import os
import sqlite3
from pathlib import Path

def setup_railway_database():
    """Setup database for Railway deployment"""
    
    # Create data directory if it doesn't exist
    data_dir = Path("/app/data")
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
    
    # Set database path to persistent volume (if available) or local
    if os.getenv('RAILWAY_VOLUME_MOUNT_PATH'):
        # Railway volume is available
        db_path = os.path.join(os.getenv('RAILWAY_VOLUME_MOUNT_PATH'), 'bot_data.db')
    else:
        # Fallback to local path
        db_path = '/app/data/bot_data.db'
    
    # Update database path in environment
    os.environ['DATABASE_PATH'] = db_path
    
    print(f"Database will be stored at: {db_path}")
    return db_path

def get_database_connection():
    """Get database connection with Railway-compatible path"""
    db_path = os.getenv('DATABASE_PATH', 'bot_data.db')
    return sqlite3.connect(db_path)

if __name__ == "__main__":
    setup_railway_database()
