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

"""API routes for the observer backend."""

import json
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException

from .config import ObserverSettings
from .models import LabStatus, Scenario, TopologyModel
from .pcap import list_pcaps

router = APIRouter()
settings = ObserverSettings()


@router.get("/healthz")
def healthcheck() -> dict:
    return {"status": "ok"}


@router.get("/status", response_model=LabStatus)
def status() -> LabStatus:
    try:
        resp = httpx.get(f"{settings.attack_controller_url}/scenarios", timeout=5)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    scenario_payload = resp.json().get("scenarios", [])
    routers = [router["name"] for router in settings.lab_config.get("routers", [])]
    return LabStatus(
        scenarios=[Scenario(**scenario) for scenario in scenario_payload],
        routers=routers,
    )


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text or "Scenario activation failed"
    for key in ("detail", "message", "error"):
        if isinstance(payload.get(key), str):
            return str(payload[key])
    return json.dumps(payload)


@router.post("/scenario/{name}")
def activate_scenario(name: str) -> dict:
    try:
        resp = httpx.post(
            f"{settings.attack_controller_url}/scenario/{name}",
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _extract_error_message(exc.response)
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        payload = resp.json()
    except json.JSONDecodeError:
        payload = {}
    message = (
        payload.get("detail")
        or payload.get("message")
        or f"Scenario '{name}' activated"
    )
    return {"detail": message}


@router.get("/pcaps")
def pcaps() -> dict:
    base_path = Path("/captures")
    files = [path.name for path in list_pcaps(base_path)]
    return {"files": files}


@router.get("/topology", response_model=TopologyModel)
def topology() -> TopologyModel:
    metadata_path = Path(settings.topology_metadata_path)
    try:
        payload = metadata_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Topology metadata not found. Run lab_gen.py to generate it.",
        ) from exc
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid topology metadata. Regenerate lab artifacts.",
        ) from exc
    return TopologyModel(**data)
