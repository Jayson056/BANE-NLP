"""
BANE V4 — Network Tools
========================
Network diagnostics, connectivity checks, and port scanning.
"""

import subprocess
import socket
import sys
from mcp.mcp_registry import mcp_tool
from core.logger import log_event


@mcp_tool(
    name="network_tools.ping",
    description="Ping a host to check connectivity. Args: {'host': 'google.com', 'count': 4}"
)
def ping(host: str = "google.com", count: int = 4) -> str:
    """Ping a host and return the results."""
    log_event("MCP", f"Pinging {host} ({count} packets)")
    try:
        flag = "-n" if sys.platform == "win32" else "-c"
        result = subprocess.run(
            ["ping", flag, str(count), host],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            output += f"\n{result.stderr.strip()}" if result.stderr else ""
        return output or "No output from ping."
    except subprocess.TimeoutExpired:
        return f"⚠️ Ping to {host} timed out after 15 seconds."
    except Exception as e:
        return f"❌ Ping failed: {e}"


@mcp_tool(
    name="network_tools.check_port",
    description="Check if a specific port is open on a host. Args: {'host': 'localhost', 'port': 8080}"
)
def check_port(host: str = "localhost", port: int = 80) -> str:
    """Check if a TCP port is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        if result == 0:
            return f"✅ Port {port} on {host} is OPEN."
        else:
            return f"❌ Port {port} on {host} is CLOSED (code: {result})."
    except Exception as e:
        return f"❌ Port check failed: {e}"


@mcp_tool(
    name="network_tools.get_ip",
    description="Get the machine's local and public IP addresses. Args: {}"
)
def get_ip() -> str:
    """Get local and public IP."""
    import urllib.request
    lines = []
    
    # Local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        lines.append(f"Local IP: {local_ip}")
    except:
        lines.append("Local IP: Unable to determine")
    
    # Public IP
    try:
        public_ip = urllib.request.urlopen("https://api.ipify.org", timeout=5).read().decode()
        lines.append(f"Public IP: {public_ip}")
    except:
        lines.append("Public IP: Unable to determine")
    
    # Hostname
    lines.append(f"Hostname: {socket.gethostname()}")
    
    return "\n".join(lines)


@mcp_tool(
    name="network_tools.dns_lookup",
    description="Perform DNS lookup for a domain. Args: {'domain': 'google.com'}"
)
def dns_lookup(domain: str = "") -> str:
    """Resolve a domain name to IP addresses."""
    if not domain:
        return "❌ Error: 'domain' is required."
    try:
        results = socket.getaddrinfo(domain, None)
        ips = list(set([r[4][0] for r in results]))
        return f"DNS lookup for {domain}:\n" + "\n".join(f"  → {ip}" for ip in ips)
    except socket.gaierror as e:
        return f"❌ DNS lookup failed for {domain}: {e}"
