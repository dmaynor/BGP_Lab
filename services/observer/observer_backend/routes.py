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
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

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

    response_data = resp.json()
    scenario_payload = response_data.get("scenarios", [])
    active_scenario = response_data.get("active_scenario", "normal")
    routers = [router["name"] for router in settings.lab_config.get("routers", [])]

    return LabStatus(
        scenarios=[Scenario(**scenario) for scenario in scenario_payload],
        routers=routers,
        active_scenario=active_scenario,
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


def _parse_bgp_routes(router_name: str) -> Dict[str, Any]:
    """Parse BGP routes from a router using vtysh."""
    try:
        result = subprocess.run(
            ["docker", "exec", router_name, "vtysh", "-c", "show ip bgp"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {"error": f"Failed to get BGP routes from {router_name}"}

        routes = {}
        lines = result.stdout.split("\n")
        current_prefix = None

        for i, line in enumerate(lines):
            # Match lines like: "*> 10.10.1.0/24     10.0.0.2                 0             0 65001 i"
            match = re.match(r'\s*([*>= ]+)\s+(\d+\.\d+\.\d+\.\d+/\d+)\s+(\S+)', line)
            if match:
                status, prefix, nexthop = match.groups()
                current_prefix = prefix
            else:
                # Match continuation lines like: "*>                  10.0.0.2  ..."
                cont_match = re.match(r'\s*([*>= ]+)\s+(\S+)', line)
                if cont_match and current_prefix:
                    status, nexthop = cont_match.groups()
                    prefix = current_prefix
                else:
                    continue

            # Extract AS path and origin from the rest of the line
            if match:
                rest_of_line = line[match.end():].strip()
            else:
                rest_of_line = line[cont_match.end():].strip()

            parts = rest_of_line.split()

            # AS path is usually after metric/localpref/weight (numbers) and before origin (i/e/?)
            as_path = []
            origin = 'i'

            # Find origin code at the end
            if parts and parts[-1] in ['i', 'e', '?']:
                origin = parts[-1]
                # AS path numbers are before origin
                for part in reversed(parts[:-1]):
                    if part.isdigit():
                        as_path.insert(0, part)
                    elif not part.isdigit() and as_path:
                        break

            if prefix not in routes:
                routes[prefix] = []

            is_best = '>' in status

            routes[prefix].append({
                "nexthop": nexthop,
                "as_path": as_path,
                "best": is_best,
                "origin": origin,
            })

        return {"router": router_name, "routes": routes}
    except Exception as e:
        return {"error": str(e)}


@router.get("/bgp_routes")
def bgp_routes() -> dict:
    """Get BGP routes from all routers for visualization."""
    routers_config = settings.lab_config.get("routers", [])
    router_names = [r["name"] for r in routers_config]

    all_routes = {}
    topology_nodes = []
    topology_edges = set()

    # Collect routes from each router
    for router_name in router_names:
        router_data = _parse_bgp_routes(router_name)
        if "error" not in router_data:
            all_routes[router_name] = router_data

    # Build name-to-ASN mapping
    router_asn_map = {r.get("name"): r.get("asn") for r in routers_config}

    # Build topology from lab config
    for router in routers_config:
        router_asn = router.get("asn")
        router_name = router.get("name")
        router_role = router.get("role", "")

        topology_nodes.append({
            "id": router_asn,
            "label": f"AS {router_asn}\n({router_name})",
            "role": router_role,
            "name": router_name,
        })

    # Get peering from lab config (not topology-metadata.json)
    for router in routers_config:
        from_asn = router.get("asn")
        for peer_info in router.get("peers", []):
            # peer_info is a dict like {"neighbor": "r2", "link": "fabric-a"}
            if isinstance(peer_info, dict):
                peer_name = peer_info.get("neighbor")
            else:
                peer_name = peer_info  # fallback if it's just a string

            to_asn = router_asn_map.get(peer_name)
            if to_asn:
                edge = tuple(sorted([from_asn, to_asn]))
                topology_edges.add(edge)

    return {
        "routes": all_routes,
        "topology": {
            "nodes": topology_nodes,
            "edges": [{"from": e[0], "to": e[1]} for e in topology_edges],
        },
    }
