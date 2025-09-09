from mcp.server import FastMCP
import paramiko
import json
import os

# Load Linux SSH config from local config file
config_path = os.path.join(os.path.dirname(__file__), "linux_config.json")
try:
    with open(config_path, "r") as f:
        config = json.load(f)
        SSH_HOST = config.get("ip") or config.get("host")
        SSH_USERNAME = config.get("username")
        SSH_PASSWORD = config.get("password")
        SSH_KEY_PATH = config.get("key_path")
except Exception as e:
    SSH_HOST = None
    SSH_USERNAME = None
    SSH_PASSWORD = None
    SSH_KEY_PATH = None

# Create MCP server for SSH
ssh_mcp = FastMCP(name="ssh-mcp")

@ssh_mcp.tool()
def connectSSH(ip: str = None, username: str = None, password: str = None) -> dict:
    """Connects to a remote Linux host using SSH (username & password). Uses config file if parameters are not provided."""
    h = ip or SSH_HOST
    u = username or SSH_USERNAME
    p = password or SSH_PASSWORD
    if not h or not u or not p:
        return {"error": "IP, username, or password not set."}
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=h, username=u, password=p)
        stdin, stdout, stderr = client.exec_command('uname -a')
        output = stdout.read().decode()
        client.close()
        return {"message": "Connected successfully.", "output": output}
    except Exception as e:
        return {"error": str(e)}

@ssh_mcp.tool()
def runCommand(command: str = "date", ip: str = None, username: str = None, password: str = None) -> dict:
    """Runs a command on the remote Linux host using SSH (username & password). Uses config file if parameters are not provided."""
    h = ip or SSH_HOST
    u = username or SSH_USERNAME
    p = password or SSH_PASSWORD
    if not h or not u or not p:
        return {"error": "IP, username, or password not set."}
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=h, username=u, password=p)
        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()
        client.close()
        return {"output": output, "error": error}
    except Exception as e:
        return {"error": str(e)}

@ssh_mcp.tool()
def getFirewallStatus(ip: str = None, username: str = None, password: str = None) -> dict:
    """Gets the UFW firewall status on the remote Linux host using SSH (username & password). Uses config file if parameters are not provided. Uses sudo with password for root access."""
    h = ip or SSH_HOST
    u = username or SSH_USERNAME
    p = password or SSH_PASSWORD
    if not h or not u or not p:
        return {"error": "IP, username, or password not set."}
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=h, username=u, password=p)
        # Only run ufw status with sudo -S
        cmd_actual = f"echo '{p}' | sudo -S ufw status"
        stdin, stdout, stderr = client.exec_command(cmd_actual)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        client.close()
        return {"ufw_status": {"output": output, "error": error}}
    except Exception as e:
        return {"error": str(e)}

# Run the SSH MCP server
ssh_mcp.run()
