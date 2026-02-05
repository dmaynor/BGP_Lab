# MIT License
#
# Copyright (c) 2024 BGP Lab contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""FastAPI attack controller skeleton."""

from fastapi import FastAPI, HTTPException

from .config import LabSettings
from .scenarios import ScenarioRegistry
from .scenarios_executor import ScenariosExecutor
from .state_manager import StateManager

app = FastAPI(title="BGP Attack Controller", version="0.1.0")
settings = LabSettings()
registry = ScenarioRegistry(settings.scenarios)
executor = ScenariosExecutor()
state_manager = StateManager()


@app.get("/healthz")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/scenarios")
def list_scenarios() -> dict:
    return {
        "scenarios": [
            {"name": scenario.name, "description": scenario.description}
            for scenario in registry.list()
        ],
        "active_scenario": state_manager.get_active_scenario(),
    }


@app.post("/scenario/{scenario_name}")
def trigger_scenario(scenario_name: str) -> dict:
    scenario = registry.get(scenario_name)
    if not scenario:
        raise HTTPException(status_code=404, detail="scenario not found")

    try:
        executor.run_scenario(scenario.orchestrator_entrypoint)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )

    # Update active scenario on success
    state_manager.set_active_scenario(scenario_name)

    return {"detail": f"Scenario '{scenario_name}' activated"}
