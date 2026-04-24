"""
BANE MCP - Deployment & Git Tools
=====================================
Tools for managing git repositories, npm packages, and deployment workflows.
"""

import subprocess
import os
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event, log_error

@mcp_custom_tool(
    name="deployment_tools.git_status",
    description="Check the git status of a repository. Args: {'path': 'path_to_repo'}"
)
def git_status(path: str = "D:\\Project_Workspace") -> str:
    """Check git status."""
    log_event("DEPLOYMENT", f"Checking git status at {path}")
    try:
        result = subprocess.run(
            ["git", "status"],
            cwd=path, capture_output=True, text=True, check=True
        )
        return result.stdout
    except Exception as e:
        return f"❌ Error: {e}"

@mcp_custom_tool(
    name="deployment_tools.git_clone",
    description="Clone a git repository. Args: {'url': 'repo_url', 'path': 'dest_path'}"
)
def git_clone(url: str, path: str = "D:\\Project_Workspace") -> str:
    """Clone a repository."""
    log_event("DEPLOYMENT", f"Cloning {url} to {path}")
    try:
        result = subprocess.run(
            ["git", "clone", url],
            cwd=path, capture_output=True, text=True, check=True
        )
        return f"✅ Successfully cloned {url}\n{result.stdout}"
    except Exception as e:
        return f"❌ Error: {e}"

@mcp_custom_tool(
    name="deployment_tools.npm_install",
    description="Install npm dependencies. Args: {'path': 'path_to_package_json'}"
)
def npm_install(path: str = "D:\\Project_Workspace") -> str:
    """Run npm install."""
    log_event("DEPLOYMENT", f"Running npm install at {path}")
    try:
        result = subprocess.run(
            ["npm", "install"],
            cwd=path, capture_output=True, text=True, check=True, shell=True
        )
        return f"✅ npm install complete\n{result.stdout}"
    except Exception as e:
        return f"❌ Error: {e}"
