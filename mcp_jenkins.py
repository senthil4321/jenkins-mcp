from mcp.server import FastMCP
import logging
import requests
import os
import json

# Jenkins configuration (global variables)
JENKINS_JOB_NAME = None
JENKINS_URL = None
JENKINS_USERNAME = None
JENKINS_API_TOKEN = None

# Load Jenkins config from local config file
config_path = os.path.join(os.path.dirname(__file__), "jenkins_config.json")
try:
    with open(config_path, "r") as f:
        config = json.load(f)
        JENKINS_JOB_NAME = config.get("job_name")
        JENKINS_URL = config.get("url")
        JENKINS_USERNAME = config.get("username")
        JENKINS_API_TOKEN = config.get("token")
except Exception as e:
    logging.error(f"Could not load Jenkins config from {config_path}: {e}")
    JENKINS_JOB_NAME = None
    JENKINS_URL = None
    JENKINS_USERNAME = None
    JENKINS_API_TOKEN = None

# Create MCP server
mcp = FastMCP(name="mcp_jenkins")


def _auth():
    return (JENKINS_USERNAME, JENKINS_API_TOKEN) if JENKINS_USERNAME and JENKINS_API_TOKEN else None


def _require_config():
    if not JENKINS_URL or not JENKINS_JOB_NAME:
        return {"error": "JENKINS_URL or JENKINS_JOB_NAME not set"}
    return None


# ─── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
def getJenkinsStatus() -> dict:
    """Fetches the latest Jenkins build status for the configured job."""
    err = _require_config()
    if err:
        return err
    api_url = JENKINS_URL.rstrip('/') + f'/job/{JENKINS_JOB_NAME}/lastBuild/api/json'
    try:
        response = requests.get(api_url, timeout=10, auth=_auth())
        response.raise_for_status()
        data = response.json()
        return {
            "build_number": data.get('number', 'N/A'),
            "status": data.get('result', 'UNKNOWN'),
            "duration_ms": data.get('duration'),
            "url": data.get('url'),
        }
    except Exception as e:
        logging.error(f"Failed to fetch Jenkins status: {e}")
        return {"error": str(e)}


@mcp.tool()
def getPassedJenkinsStatus() -> dict:
    """Fetches the status of the last successful Jenkins build."""
    err = _require_config()
    if err:
        return err
    api_url = JENKINS_URL.rstrip('/') + f'/job/{JENKINS_JOB_NAME}/lastSuccessfulBuild/api/json'
    try:
        response = requests.get(api_url, timeout=10, auth=_auth())
        response.raise_for_status()
        data = response.json()
        return {
            "build_number": data.get('number', 'N/A'),
            "status": data.get('result', 'UNKNOWN'),
            "url": data.get('url'),
        }
    except Exception as e:
        logging.error(f"Failed to fetch last successful Jenkins build status: {e}")
        return {"error": str(e)}


@mcp.tool()
def getBuildDetails(build_number: int) -> dict:
    """Fetches details for a specific Jenkins build number."""
    err = _require_config()
    if err:
        return err
    api_url = JENKINS_URL.rstrip('/') + f'/job/{JENKINS_JOB_NAME}/{build_number}/api/json'
    try:
        response = requests.get(api_url, timeout=10, auth=_auth())
        response.raise_for_status()
        data = response.json()
        return {
            "build_number": data.get('number'),
            "status": data.get('result', 'UNKNOWN'),
            "duration_ms": data.get('duration'),
            "timestamp": data.get('timestamp'),
            "building": data.get('building', False),
            "url": data.get('url'),
            "causes": [
                c.get('shortDescription', '')
                for c in (data.get('actions') or [])
                if isinstance(c, dict) and c.get('_class', '').endswith('CauseAction')
                for c in c.get('causes', [])
            ],
        }
    except Exception as e:
        logging.error(f"Failed to fetch build details for #{build_number}: {e}")
        return {"error": str(e)}


@mcp.tool()
def getBuildLog(build_number: int, max_lines: int = 100) -> dict:
    """
    Fetches the console log for a specific Jenkins build.

    Returns the last `max_lines` lines (default 100). Use a larger value for
    deeper debugging. For in-progress builds the log may be incomplete.
    """
    err = _require_config()
    if err:
        return err
    url = JENKINS_URL.rstrip('/') + f'/job/{JENKINS_JOB_NAME}/{build_number}/consoleText'
    try:
        response = requests.get(url, timeout=30, auth=_auth())
        response.raise_for_status()
        lines = response.text.splitlines()
        tail = lines[-max_lines:] if len(lines) > max_lines else lines
        return {
            "build_number": build_number,
            "total_lines": len(lines),
            "returned_lines": len(tail),
            "log": "\n".join(tail),
        }
    except Exception as e:
        logging.error(f"Failed to fetch build log for #{build_number}: {e}")
        return {"error": str(e)}


@mcp.tool()
def startJenkinsBuild() -> dict:
    """Triggers a new Jenkins build for the configured job (no parameters)."""
    err = _require_config()
    if err:
        return err
    url = JENKINS_URL.rstrip('/') + f'/job/{JENKINS_JOB_NAME}/build'
    try:
        response = requests.post(url, timeout=10, auth=_auth())
        response.raise_for_status()
        return {"message": "Build triggered successfully.", "url": url, "status_code": response.status_code}
    except Exception as e:
        logging.error(f"Failed to start Jenkins build: {e}")
        return {"error": str(e)}


@mcp.tool()
def startBuildWithParams(params: dict) -> dict:
    """
    Triggers a parameterized Jenkins build.

    Pass a flat dict of parameter name → value, e.g.
    {"BRANCH": "main", "ENV": "staging"}.
    """
    err = _require_config()
    if err:
        return err
    url = JENKINS_URL.rstrip('/') + f'/job/{JENKINS_JOB_NAME}/buildWithParameters'
    try:
        response = requests.post(url, params=params, timeout=10, auth=_auth())
        response.raise_for_status()
        return {"message": "Parameterized build triggered successfully.", "params": params, "status_code": response.status_code}
    except Exception as e:
        logging.error(f"Failed to start parameterized Jenkins build: {e}")
        return {"error": str(e)}


@mcp.tool()
def stopBuild(build_number: int) -> dict:
    """Aborts a running Jenkins build by build number."""
    err = _require_config()
    if err:
        return err
    url = JENKINS_URL.rstrip('/') + f'/job/{JENKINS_JOB_NAME}/{build_number}/stop'
    try:
        response = requests.post(url, timeout=10, auth=_auth())
        response.raise_for_status()
        return {"message": f"Build #{build_number} stop signal sent.", "status_code": response.status_code}
    except Exception as e:
        logging.error(f"Failed to stop build #{build_number}: {e}")
        return {"error": str(e)}


@mcp.tool()
def listJobs() -> dict:
    """Lists all Jenkins jobs on the configured server with their name and status color."""
    if not JENKINS_URL:
        return {"error": "JENKINS_URL not set"}
    api_url = JENKINS_URL.rstrip('/') + '/api/json?tree=jobs[name,url,color]'
    try:
        response = requests.get(api_url, timeout=10, auth=_auth())
        response.raise_for_status()
        data = response.json()
        return {"jobs": data.get('jobs', []), "url": api_url}
    except Exception as e:
        logging.error(f"Failed to fetch Jenkins jobs: {e}")
        return {"error": str(e)}


@mcp.tool()
def getQueueStatus() -> dict:
    """Returns the current Jenkins build queue (pending/waiting builds)."""
    if not JENKINS_URL:
        return {"error": "JENKINS_URL not set"}
    api_url = JENKINS_URL.rstrip('/') + '/queue/api/json?tree=items[id,task[name],why,stuck,blocked]'
    try:
        response = requests.get(api_url, timeout=10, auth=_auth())
        response.raise_for_status()
        data = response.json()
        items = data.get('items', [])
        return {"queued_count": len(items), "items": items}
    except Exception as e:
        logging.error(f"Failed to fetch Jenkins queue: {e}")
        return {"error": str(e)}


# ─── Prompts ──────────────────────────────────────────────────────────────────

@mcp.prompt("commitAndPush")
def commitAndPush(name: str = "World") -> str:
    """Commit and push the changes."""
    return "commit and push the changes"


# ─── Resources ────────────────────────────────────────────────────────────────

@mcp.resource("jenkins://world")
def hello_world_resource() -> str:
    return "Hello World from MCP resource!"


@mcp.resource("jenkins://builds")
def get_jenkins_builds() -> dict:
    """Returns a list of recent builds for the configured Jenkins job."""
    err = _require_config()
    if err:
        return err
    api_url = JENKINS_URL.rstrip('/') + f'/job/{JENKINS_JOB_NAME}/api/json?tree=builds[number,result,timestamp,duration]'
    try:
        response = requests.get(api_url, timeout=10, auth=_auth())
        response.raise_for_status()
        data = response.json()
        return {"builds": data.get('builds', []), "url": api_url}
    except Exception as e:
        logging.error(f"Failed to fetch Jenkins builds: {e}")
        return {"error": str(e)}


@mcp.resource("jenkins://jobs")
def get_jenkins_jobs() -> dict:
    """Returns a list of all Jenkins jobs from the configured server."""
    if not JENKINS_URL:
        return {"error": "JENKINS_URL not set"}
    api_url = JENKINS_URL.rstrip('/') + '/api/json?tree=jobs[name,url,color]'
    try:
        response = requests.get(api_url, timeout=10, auth=_auth())
        response.raise_for_status()
        data = response.json()
        return {"jobs": data.get('jobs', []), "url": api_url}
    except Exception as e:
        logging.error(f"Failed to fetch Jenkins jobs: {e}")
        return {"error": str(e)}


# Run the MCP server
mcp.run()
