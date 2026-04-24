import sqlite3
import json
import sys
import os

def get_schedule():
    """Retrieves all events from the local BANE calendar database."""
    # Ensure we use an absolute path for the DB to avoid CWD issues
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bane_data.db')
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table exists first
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='calendar_schedule';")
        if not cursor.fetchone():
            return json.dumps({'error': 'Table calendar_schedule not found in database.'})

        cursor.execute('SELECT event_name, start_time, end_time FROM calendar_schedule ORDER BY start_time ASC')
        rows = cursor.fetchall()
        events = []
        for row in rows:
            events.append({
                'event': row[0],
                'start': row[1],
                'end': row[2]
            })
        conn.close()
        return json.dumps(events, indent=2)
    except Exception as e:
        return json.dumps({'error': str(e)})

if __name__ == '__main__':
    # MCP-compatible output
    print(get_schedule())
