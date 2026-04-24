from mcp.mcp_registry import mcp_tool
import sys
import os
import re

# Add root project path to allow importing database
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import core.database as database

@mcp_tool(name="memory_tools.query_recent_conversations", description="Queries the database for a user's recent conversations. IMPORTANT: You MUST provide your current chrome_profile (e.g. 'Profile 4', 'Profile 7') to only fetch memories relevant to your specific academic/professional persona. Otherwise, memories will leak across subjects. Provide days_back (default 1) to look back.")
def query_recent_conversations(user_id: str = "5662168844", days_back: int = 1, chrome_profile: str = "ALL"):
    """Fetch previous interactions and messages for context awareness."""
    try:
        conn = database._get_connection()
        try:
            # Add dynamic profile filtering
            profile_query = "AND c.chrome_profile = ?" if chrome_profile and chrome_profile != "ALL" else ""
            params = [str(user_id), f'-{days_back} days']
            if profile_query:
                params.append(chrome_profile)

            # Fetch recent conversations for the user
            convos = conn.execute(
                f"SELECT c.conversation_id, c.source_platform, c.started_at, c.chrome_profile FROM conversations c "
                f"JOIN users u ON c.user_id = u.user_id "
                f"WHERE u.platform_user_id = ? AND c.started_at >= datetime('now', ?) {profile_query} "
                f"ORDER BY c.started_at DESC LIMIT 5",
                tuple(params)
            ).fetchall()
            
            if not convos:
                return f"No conversations found for user {user_id} in the last {days_back} days."
            
            result = []
            for c in convos:
                cid = c["conversation_id"]
                plat = c["source_platform"]
                started = c["started_at"]
                
                msgs = conn.execute(
                    "SELECT sender_type, message_content, timestamp FROM messages "
                    "WHERE conversation_id = ? ORDER BY timestamp ASC LIMIT 20",
                    (cid,)
                ).fetchall()
                
                prof_str = c["chrome_profile"] if c["chrome_profile"] else "Unknown Profile"
                convo_data = f"--- Session on {plat} [{prof_str}] at {started} ---\n"
                for m in msgs:
                    content = m['message_content']
                    if len(content) > 300:
                        content = content[:300] + "... [TRUNCATED]"
                    convo_data += f"[{m['timestamp']}] {m['sender_type']}: {content}\n"
                result.append(convo_data)
                
            return "\n\n".join(result)
        finally:
            conn.close()
    except Exception as e:
        return f"Error querying conversations: {str(e)}"

@mcp_tool(name="memory_tools.search_past_topics", description="Searches a user's database conversations for specific keywords. IMPORTANT: Provide your current chrome_profile (e.g. 'Profile 4') to isolate the search to your specific academic/professional persona, preventing topic hallucination across profiles.")
def search_past_topics(user_id: str = "5662168844", keyword: str = "", chrome_profile: str = "ALL"):
    """Search previous conversations for a specific topic."""
    if not keyword:
        return "Keyword is required."
    try:
        conn = database._get_connection()
        try:
            # Add dynamic profile filtering
            profile_query = "AND c.chrome_profile = ?" if chrome_profile and chrome_profile != "ALL" else ""
            params = [str(user_id), f'%{keyword}%', f'%{keyword}%']
            if profile_query:
                params.append(chrome_profile)

            # Match conversations that have messages containing the keyword
            convos = conn.execute(
                f"SELECT DISTINCT c.conversation_id, c.source_platform, c.started_at, c.chrome_profile FROM conversations c "
                f"JOIN users u ON c.user_id = u.user_id "
                f"JOIN messages m ON c.conversation_id = m.conversation_id "
                f"WHERE u.platform_user_id = ? AND (m.message_content LIKE ? OR c.conversation_id LIKE ?) {profile_query} "
                f"ORDER BY c.started_at DESC LIMIT 5",
                tuple(params)
            ).fetchall()
            
            if not convos:
                return f"No memories found for user {user_id} regarding '{keyword}'."
            
            result = [f"Memories regarding '{keyword}':"]
            for c in convos:
                cid = c["conversation_id"]
                plat = c["source_platform"]
                started = c["started_at"]
                
                msgs = conn.execute(
                    "SELECT sender_type, message_content, timestamp FROM messages "
                    "WHERE conversation_id = ? ORDER BY timestamp ASC LIMIT 20",
                    (cid,)
                ).fetchall()
                
                prof_str = c["chrome_profile"] if c["chrome_profile"] else "Unknown Profile"
                convo_data = f"--- Session on {plat} [{prof_str}] at {started} ---"
                for m in msgs:
                    content = m['message_content']
                    if len(content) > 300:
                        content = content[:300] + "... [TRUNCATED]"
                    # Only show the time portion for brevity if feasible, but let's keep full timestamp
                    convo_data += f"\n[{m['timestamp']}] {m['sender_type']}: {content}"
                result.append(convo_data)
                
            return "\n\n".join(result)
        finally:
            conn.close()
    except Exception as e:
        return f"Error searching memory: {str(e)}"

@mcp_tool(name="memory_tools.query_ai_sessions", description="Queries database for recent AI operational sessions and average latency.")
def query_ai_sessions(limit: int = 10):
    try:
        conn = database._get_connection()
        try:
            rows = conn.execute(
                "SELECT session_id, ai_model, request_time, latency_ms FROM ai_sessions "
                "ORDER BY request_time DESC LIMIT ?",
                (limit,)
            ).fetchall()
            if not rows:
                return "No sessions found."
            
            res = ["Recent AI Sessions:"]
            for r in rows:
                res.append(f"- {r['request_time']} | Model: {r['ai_model']} | Latency: {r['latency_ms']}ms")
            return "\n".join(res)
        finally:
            conn.close()
    except Exception as e:
        return f"Error querying sessions: {str(e)}"

@mcp_tool(name="memory_tools.search_logs", description="Search the engine logs for specific errors or keywords (e.g., 'error', 'failed').")
def search_logs(keyword: str, lines_before: int = 2, lines_after: int = 2):
    import glob
    log_dir = os.path.join(root_dir, "logs")
    log_file = os.path.join(log_dir, "bnp_system.log")
    if not os.path.exists(log_file):
        return "Log file logs/bnp_system.log not found."
    
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            
        results = []
        # Search backwards so we find the most recent errors first
        for i in range(len(lines) - 1, -1, -1):
            if keyword.lower() in lines[i].lower():
                start = max(0, i - lines_before)
                end = min(len(lines), i + lines_after + 1)
                snippet = "".join(lines[start:end])
                results.append(f"--- Match near line {i} ---\n{snippet}")
                if len(results) >= 5: # Limit to 5 matches
                    break
                    
        if not results:
            return f"No matches found for '{keyword}' in logs/bnp_system.log."
        
        # Reverse results back to chronological order
        return "\n".join(reversed(results))
    except Exception as e:
        return f"Error reading logs: {str(e)}"

@mcp_tool(name="memory_tools.list_unique_keywords", description="Lists the most frequent words/topics used in previous conversations to help the AI know what topics are available for recall.")
def list_unique_keywords(user_id: str = "5662168844", limit: int = 15):
    """Identify common topics for easier memory retrieval."""
    try:
        conn = database._get_connection()
        try:
            # Simple word frequency from messages (filtering out tiny words)
            rows = conn.execute(
                "SELECT message_content FROM messages m "
                "JOIN conversations c ON m.conversation_id = c.conversation_id "
                "JOIN users u ON c.user_id = u.user_id "
                "WHERE u.platform_user_id = ? AND m.sender_type = 'USER' "
                "ORDER BY m.timestamp DESC LIMIT 50",
                (str(user_id),)
            ).fetchall()
            
            if not rows:
                return "No conversation history found to analyze topics."
                
            words = []
            stop_words = {'the', 'and', 'my', 'that', 'this', 'for', 'with', 'your', 'from', 'what', 'who', 'how'}
            for r in rows:
                content = r['message_content'].lower()
                for word in re.findall(r'\b\w{4,}\b', content): # Words at least 4 chars
                    if word not in stop_words:
                        words.append(word)
            
            from collections import Counter
            counts = Counter(words).most_common(limit)
            
            if not counts:
                return "No significant keywords found."
                
            topics = [f"{w} ({c})" for w, c in counts]
            return "Frequent Topics in Previous Sessions:\n• " + "\n• ".join(topics)
        finally:
            conn.close()
    except Exception as e:
        import traceback
        return f"Error listing keywords: {str(e)}\n{traceback.format_exc()}"
