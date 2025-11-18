"""API routes for the observer backend."""

from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException

from .config import ObserverSettings
from .models import LabStatus, Scenario
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


@router.get("/pcaps")
def pcaps() -> dict:
    base_path = Path("/captures")
    files = [path.name for path in list_pcaps(base_path)]
    return {"files": files}
