import sqlite3
from datetime import datetime
import os

class CapstoneDAO:
    def __init__(self, db_name="capstone_workspace.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._migrate()

    def _migrate(self):
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS capstone_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_title TEXT NOT NULL,
            proposal_type TEXT DEFAULT 'Proposal 2',
            status TEXT DEFAULT 'Draft'
        )""")
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            description TEXT,
            upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES capstone_projects(id)
        )""")
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_performed TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        self.conn.commit()

    def add_project(self, title: str):
        self.cursor.execute("INSERT INTO capstone_projects (project_title) VALUES (?)", (title,))
        self.conn.commit()
        return self.cursor.lastrowid

    def log_action(self, action: str):
        self.cursor.execute("INSERT INTO user_tracking (action_performed) VALUES (?)", (action,))
        self.conn.commit()


# ==========================================
# MCP TOOLS EXPORT
# ==========================================

def get_mcp_actions():
    return [
        {
            "name": "capstone_initialize",
            "description": "Initialize a new capstone project in the tracking database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the project"}
                },
                "required": ["title"]
            },
        },
        {
            "name": "capstone_log_action",
            "description": "Log an action related to the capstone tracking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action taken"}
                },
                "required": ["action"]
            },
        }
    ]

def execute_capstone_initialize(title: str):
    dao = CapstoneDAO()
    pid = dao.add_project(title)
    dao.log_action(f"Initialized new project '{title}' (ID: {pid})")
    return f"Success: Capstone project '{title}' initialized with ID {pid}."

def execute_capstone_log_action(action: str):
    dao = CapstoneDAO()
    dao.log_action(action)
    return "Success: Action logged."
