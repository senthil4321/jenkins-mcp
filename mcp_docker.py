from mcp.server import FastMCP
import paramiko
import json
import os
import logging

# Load Docker/SSH config
config_path = os.path.join(os.path.dirname(__file__), "docker_config.json")
try:
    with open(config_path, "r") as f:
        config = json.load(f)
        DOCKER_HOST = config.get("host")
        DOCKER_PORT = config.get("port", 22)
        DOCKER_USER = config.get("username")
        DOCKER_PASS = config.get("password")
        DOCKER_KEY  = config.get("key_path")
except Exception as e:
    logging.error(f"Could not load docker config: {e}")
    DOCKER_HOST = None
    DOCKER_PORT = 22
    DOCKER_USER = None
    DOCKER_PASS = None
    DOCKER_KEY  = None

mcp = FastMCP(name="mcp_docker")


def _ssh_run(command: str) -> dict:
    """Open an SSH connection, run command, return stdout/stderr/exit_code."""
    if not DOCKER_HOST or not DOCKER_USER:
        return {"error": "DOCKER_HOST or DOCKER_USER not configured"}
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if DOCKER_KEY:
            client.connect(hostname=DOCKER_HOST, port=DOCKER_PORT,
                           username=DOCKER_USER, key_filename=DOCKER_KEY)
        else:
            client.connect(hostname=DOCKER_HOST, port=DOCKER_PORT,
                           username=DOCKER_USER, password=DOCKER_PASS)
        _, stdout, stderr = client.exec_command(command)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        exit_code = stdout.channel.recv_exit_status()
        client.close()
        return {"stdout": out, "stderr": err, "exit_code": exit_code}
    except Exception as e:
        logging.error(f"SSH command failed: {e}")
        return {"error": str(e)}


def _parse_table(raw: str) -> list[dict]:
    """Parse docker ps / docker images tab-separated output into list of dicts."""
    lines = raw.splitlines()
    if not lines:
        return []
    headers = [h.strip() for h in lines[0].split('\t')]
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        cols = line.split('\t')
        rows.append({headers[i]: cols[i].strip() if i < len(cols) else "" for i in range(len(headers))})
    return rows


# ─── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
def getDockerInfo() -> dict:
    """Returns Docker engine info (version, OS, total containers, images) from the remote host."""
    result = _ssh_run("docker info --format '{{json .}}'")
    if "error" in result:
        return result
    try:
        info = json.loads(result["stdout"])
        return {
            "server_version": info.get("ServerVersion"),
            "os": info.get("OperatingSystem"),
            "kernel": info.get("KernelVersion"),
            "containers_total": info.get("Containers"),
            "containers_running": info.get("ContainersRunning"),
            "containers_stopped": info.get("ContainersStopped"),
            "images": info.get("Images"),
            "docker_root": info.get("DockerRootDir"),
        }
    except Exception:
        return result


@mcp.tool()
def listContainers(all: bool = True) -> dict:
    """
    Lists Docker containers on the remote host.

    Set all=False to show only running containers. Default shows all containers.
    """
    flag = "-a" if all else ""
    fmt = "table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
    result = _ssh_run(f"docker ps {flag} --format '{fmt}'")
    if "error" in result:
        return result
    containers = _parse_table(result["stdout"])
    return {"containers": containers, "count": len(containers)}


@mcp.tool()
def listImages() -> dict:
    """Lists all Docker images on the remote host."""
    fmt = "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.CreatedSince}}"
    result = _ssh_run(f"docker images --format '{fmt}'")
    if "error" in result:
        return result
    images = _parse_table(result["stdout"])
    return {"images": images, "count": len(images)}


@mcp.tool()
def startContainer(container: str) -> dict:
    """Starts a stopped Docker container by name or ID."""
    result = _ssh_run(f"docker start {container}")
    if "error" in result:
        return result
    return {"message": f"Container '{container}' started.", "output": result["stdout"], "exit_code": result["exit_code"]}


@mcp.tool()
def stopContainer(container: str, timeout: int = 10) -> dict:
    """Stops a running Docker container by name or ID. Waits `timeout` seconds before killing (default 10)."""
    result = _ssh_run(f"docker stop -t {timeout} {container}")
    if "error" in result:
        return result
    return {"message": f"Container '{container}' stopped.", "output": result["stdout"], "exit_code": result["exit_code"]}


@mcp.tool()
def restartContainer(container: str) -> dict:
    """Restarts a Docker container by name or ID."""
    result = _ssh_run(f"docker restart {container}")
    if "error" in result:
        return result
    return {"message": f"Container '{container}' restarted.", "output": result["stdout"], "exit_code": result["exit_code"]}


@mcp.tool()
def removeContainer(container: str, force: bool = False) -> dict:
    """
    Removes a Docker container by name or ID.

    Set force=True to remove a running container (equivalent to docker rm -f).
    """
    flag = "-f" if force else ""
    result = _ssh_run(f"docker rm {flag} {container}")
    if "error" in result:
        return result
    return {"message": f"Container '{container}' removed.", "exit_code": result["exit_code"]}


@mcp.tool()
def getContainerLogs(container: str, tail: int = 100) -> dict:
    """
    Fetches the last `tail` lines of logs from a Docker container (default 100).

    Works for both running and stopped containers.
    """
    result = _ssh_run(f"docker logs --tail {tail} {container} 2>&1")
    if "error" in result:
        return result
    lines = result["stdout"].splitlines()
    return {"container": container, "lines_returned": len(lines), "logs": result["stdout"]}


@mcp.tool()
def getContainerStats(container: str) -> dict:
    """Returns live resource usage stats (CPU, memory, network I/O) for a running container."""
    fmt = "{{json .}}"
    result = _ssh_run(f"docker stats --no-stream --format '{fmt}' {container}")
    if "error" in result:
        return result
    try:
        stats = json.loads(result["stdout"])
        return {
            "container": stats.get("Name"),
            "cpu_percent": stats.get("CPUPerc"),
            "mem_usage": stats.get("MemUsage"),
            "mem_percent": stats.get("MemPerc"),
            "net_io": stats.get("NetIO"),
            "block_io": stats.get("BlockIO"),
            "pids": stats.get("PIDs"),
        }
    except Exception:
        return result


@mcp.tool()
def inspectContainer(container: str) -> dict:
    """Returns detailed configuration and state for a Docker container (docker inspect)."""
    result = _ssh_run(f"docker inspect {container}")
    if "error" in result:
        return result
    try:
        data = json.loads(result["stdout"])
        if data:
            c = data[0]
            state = c.get("State", {})
            network = c.get("NetworkSettings", {}).get("Networks", {})
            return {
                "id": c.get("Id", "")[:12],
                "name": c.get("Name", "").lstrip("/"),
                "image": c.get("Config", {}).get("Image"),
                "status": state.get("Status"),
                "started_at": state.get("StartedAt"),
                "restart_count": c.get("RestartCount"),
                "ports": c.get("NetworkSettings", {}).get("Ports"),
                "networks": {k: v.get("IPAddress") for k, v in network.items()},
                "mounts": [{"src": m.get("Source"), "dst": m.get("Destination")} for m in c.get("Mounts", [])],
                "env": c.get("Config", {}).get("Env"),
            }
        return {"error": "No data returned"}
    except Exception:
        return result


@mcp.tool()
def pullImage(image: str) -> dict:
    """
    Pulls a Docker image from a registry on the remote host.

    Example: pullImage("nginx:latest") or pullImage("myrepo/myapp:v2")
    """
    result = _ssh_run(f"docker pull {image}")
    if "error" in result:
        return result
    return {"message": f"Image '{image}' pulled.", "output": result["stdout"], "exit_code": result["exit_code"]}


@mcp.tool()
def runContainer(image: str, name: str = "", ports: str = "", env: str = "", detach: bool = True) -> dict:
    """
    Runs a new Docker container from an image on the remote host.

    Args:
        image:  Image name, e.g. "nginx:latest"
        name:   Optional container name (--name)
        ports:  Port mapping string, e.g. "8080:80" or "8080:80,443:443"
        env:    Env vars as comma-separated KEY=VALUE, e.g. "DEBUG=true,PORT=3000"
        detach: Run in background (default True). Set False to run in foreground.
    """
    cmd = "docker run"
    if detach:
        cmd += " -d"
    if name:
        cmd += f" --name {name}"
    for p in ports.split(","):
        p = p.strip()
        if p:
            cmd += f" -p {p}"
    for e in env.split(","):
        e = e.strip()
        if e:
            cmd += f" -e {e}"
    cmd += f" {image}"

    result = _ssh_run(cmd)
    if "error" in result:
        return result
    return {
        "message": f"Container started from '{image}'.",
        "container_id": result["stdout"][:12] if result["exit_code"] == 0 else None,
        "output": result["stdout"],
        "exit_code": result["exit_code"],
    }


@mcp.tool()
def pruneDocker(volumes: bool = False) -> dict:
    """
    Removes stopped containers, dangling images, unused networks, and optionally volumes.

    Set volumes=True to also prune unused volumes (use with caution).
    """
    cmds = ["docker container prune -f", "docker image prune -f", "docker network prune -f"]
    if volumes:
        cmds.append("docker volume prune -f")
    result = _ssh_run(" && ".join(cmds))
    if "error" in result:
        return result
    return {"message": "Docker prune completed.", "output": result["stdout"], "exit_code": result["exit_code"]}


# Run the MCP server
mcp.run()
