---
appliesTo:
  - services/attack_controller/**
  - services/observer/**
---

# FastAPI Services

## Overview

The lab includes two FastAPI services:
1. **Attack Controller** (`services/attack_controller/`): Internal API for triggering scenarios
2. **Observer** (`services/observer/`): Student-facing dashboard with HTMX frontend

## Architecture Patterns

### Attack Controller

**Purpose**: Expose orchestrator functionality via REST API without giving direct container access.

**Key Files**:
- `app/main.py`: FastAPI application and routing
- `app/scenarios.py`: Scenario definitions and validation
- `app/orchestrator_client.py`: Wrapper around orchestrator.py subprocess calls
- `app/config.py`: Configuration management

**API Design**:
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class ScenarioRequest(BaseModel):
    name: str
    # Additional parameters as needed

@app.post("/scenario/{scenario_name}")
async def trigger_scenario(scenario_name: str):
    """Trigger a BGP attack scenario."""
    # Validate scenario exists
    if scenario_name not in VALID_SCENARIOS:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    # Execute via orchestrator
    # Return status and description
    return {"status": "success", "scenario": scenario_name}

@app.get("/healthz")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
```

### Observer Service

**Purpose**: Provide a safe, read-only view of lab state for students.

**Key Files**:
- `observer_backend/main.py`: FastAPI backend
- `observer_backend/routes.py`: API endpoints
- `observer_backend/pcap.py`: PCAP file management
- `observer_backend/models.py`: Pydantic models
- `frontend/`: HTMX templates and static files

**Security Principles**:
- **READ-ONLY**: Never allow modifications through Observer
- **NO DIRECT ACCESS**: Don't expose docker/container APIs
- **SANITIZE PATHS**: Validate file paths to prevent directory traversal
- **LIMIT SCOPE**: Only show data from mounted volumes

Example secure PCAP listing:
```python
from pathlib import Path
from fastapi import HTTPException

PCAP_DIR = Path("/captures")  # Mounted volume

@app.get("/api/pcaps")
async def list_pcaps():
    """List available packet captures."""
    if not PCAP_DIR.exists():
        return {"pcaps": []}
    
    pcaps = []
    try:
        # Only read from allowed directory
        for pcap_file in PCAP_DIR.glob("*.pcap"):
            # Validate it's actually under PCAP_DIR (prevent symlink attacks)
            if not pcap_file.resolve().is_relative_to(PCAP_DIR.resolve()):
                continue
            
            pcaps.append({
                "name": pcap_file.name,
                "size": pcap_file.stat().st_size,
                "modified": pcap_file.stat().st_mtime
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error reading captures")
    
    return {"pcaps": sorted(pcaps, key=lambda x: x["modified"], reverse=True)}
```

## FastAPI Best Practices

### Dependency Injection

```python
from fastapi import Depends

def get_config():
    """Dependency that provides configuration."""
    return load_config_from_yaml("lab_config.yaml")

@app.get("/scenarios")
async def list_scenarios(config: dict = Depends(get_config)):
    """List available scenarios from config."""
    return {"scenarios": config.get("scenarios", {})}
```

### Error Handling

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle validation errors gracefully."""
    return JSONResponse(
        status_code=400,
        content={"error": str(exc)}
    )
```

### CORS (if needed)

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # Be specific!
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### Async Best Practices

```python
import asyncio

# Good: Use async for I/O-bound operations
@app.get("/status")
async def get_status():
    # If calling subprocess, use asyncio.create_subprocess_exec
    proc = await asyncio.create_subprocess_exec(
        "docker", "ps",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return {"output": stdout.decode()}

# OK: Sync function for CPU-bound work (FastAPI handles it)
@app.get("/compute")
def compute_something():
    return {"result": expensive_calculation()}
```

## HTMX Frontend (Observer)

### Template Structure

```html
<!-- Good: Declarative, leverages HTMX attributes -->
<div id="scenario-status">
  <button hx-post="/api/scenario/normal" 
          hx-target="#scenario-status"
          hx-swap="innerHTML">
    Reset to Normal
  </button>
</div>

<!-- Response from server -->
<div id="scenario-status">
  <p class="success">Scenario 'normal' activated</p>
  <span hx-get="/api/status" 
        hx-trigger="every 5s"
        hx-swap="outerHTML">
    Loading status...
  </span>
</div>
```

### Serving Static Files

```python
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
```

## Testing Services

### Unit Tests

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_invalid_scenario():
    response = client.post("/scenario/invalid_scenario_name")
    assert response.status_code == 404
```

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 9000

# Test endpoints
curl http://localhost:9000/healthz
curl http://localhost:9000/scenarios
```

### Docker Build

```bash
# Build the image
docker build -t bgp-lab/attack-ctl:dev services/attack_controller/

# Run it
docker run -p 9000:9000 \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  bgp-lab/attack-ctl:dev
```

## Common Tasks

### Adding a New Endpoint

1. Define Pydantic model for request/response
2. Implement handler function with proper type hints
3. Add appropriate HTTP status codes
4. Document with OpenAPI docstring
5. Add test cases

### Integrating New Scenario

1. Add scenario to `lab_config.yaml`
2. Update Attack Controller to recognize it
3. Add UI elements in Observer frontend
4. Test end-to-end flow

### Updating Dependencies

```bash
# Update requirements.txt
pip freeze > requirements.txt

# Or use pip-tools
pip-compile requirements.in
```

## DO NOT

- Don't expose docker socket in production Observer (Attack Controller needs it, Observer does not)
- Don't execute user input directly - always validate and sanitize
- Don't log sensitive information (even in debug mode)
- Don't use synchronous blocking calls in async endpoints
- Don't serve user-uploaded files without validation
- Don't trust client-side validation - always validate server-side
- Don't hardcode URLs/ports - use configuration
- Don't forget to set proper CORS policies for production

## Monitoring & Logging

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.post("/scenario/{name}")
async def trigger_scenario(name: str):
    logger.info(f"Triggering scenario: {name}")
    # ... implementation ...
    logger.info(f"Scenario {name} completed successfully")
```

Use FastAPI's built-in request logging or integrate with structured logging libraries.
