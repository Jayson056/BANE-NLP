from mcp.decorators import mcp_tool
import sqlite3

@mcp_tool
def execute_query(db_path: str, query: str):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [description for description in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()
        return results
    except Exception as e:
        return f'Error: {str(e)}'