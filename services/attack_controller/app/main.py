"""FastAPI attack controller skeleton."""

from fastapi import FastAPI, HTTPException

from .config import LabSettings
from .orchestrator_client import OrchestratorClient
from .scenarios import ScenarioRegistry

app = FastAPI(title="BGP Attack Controller", version="0.1.0")
settings = LabSettings()
registry = ScenarioRegistry(settings.scenarios)
orchestrator = OrchestratorClient()


@app.get("/healthz")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/scenarios")
def list_scenarios() -> dict:
    return {
        "scenarios": [
            {"name": scenario.name, "description": scenario.description}
            for scenario in registry.list()
        ]
    }


@app.post("/scenario/{scenario_name}")
def trigger_scenario(scenario_name: str) -> dict:
    scenario = registry.get(scenario_name)
    if not scenario:
        raise HTTPException(status_code=404, detail="scenario not found")
    completed = orchestrator.run_scenario(scenario.orchestrator_entrypoint)
    if completed.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )
    return {"stdout": completed.stdout}
