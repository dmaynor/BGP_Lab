#!/usr/bin/env python3
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

"""Topology generator scaffolding for the BGP Attack Lab."""

from __future__ import annotations

import argparse
import ipaddress
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence

import yaml
from jinja2 import Environment, FileSystemLoader


@dataclass
class RouterPeer:
    neighbor: str
    link: str


@dataclass
class RouterDefinition:
    name: str
    asn: int
    role: str
    router_id: str
    mgmt_ip: str
    loopback: str
    networks: List[str] = field(default_factory=list)
    peers: List[RouterPeer] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> "RouterDefinition":
        peers = [RouterPeer(**peer) for peer in data.get("peers", [])]
        return cls(
            name=data["name"],
            asn=data["asn"],
            role=data["role"],
            router_id=data["router_id"],
            mgmt_ip=data["mgmt_ip"],
            loopback=data.get("loopback", "0.0.0.0/32"),
            networks=list(data.get("networks", [])),
            peers=peers,
        )


@dataclass
class LabConfig:
    metadata: Dict
    routers: List[RouterDefinition]
    links: Dict[str, Dict]
    scenarios: Dict[str, Dict]
    pcap_pipeline: Dict

    @classmethod
    def from_dict(cls, data: Dict) -> "LabConfig":
        routers = [RouterDefinition.from_dict(entry) for entry in data.get("routers", [])]
        return cls(
            metadata=data.get("metadata", {}),
            routers=routers,
            links=data.get("links", {}),
            scenarios=data.get("scenarios", {}),
            pcap_pipeline=data.get("pcap_pipeline", {}),
        )


def load_config(path: Path) -> LabConfig:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return LabConfig.from_dict(data)


def validate_config(config: LabConfig) -> Sequence[str]:
    errors: List[str] = []
    if not config.routers:
        errors.append("at least one router must be defined")
    unique_names = {router.name for router in config.routers}
    if len(unique_names) != len(config.routers):
        errors.append("router names must be unique")
    declared_links = set(config.links.keys())
    for router in config.routers:
        for peer in router.peers:
            if peer.link not in declared_links:
                errors.append(
                    f"router {router.name} references undefined link '{peer.link}'"
                )
    return errors


def build_link_ip_assignments(config: LabConfig) -> Dict[str, Dict[str, str]]:
    assignments: Dict[str, Dict[str, str]] = {router.name: {} for router in config.routers}
    participants: Dict[str, List[str]] = {name: [] for name in config.links}
    for router in config.routers:
        for peer in router.peers:
            participants.setdefault(peer.link, []).append(router.name)
    for link_name, routers_on_link in participants.items():
        if not routers_on_link:
            continue
        subnet = config.links.get(link_name, {}).get("ipv4_subnet")
        if not subnet:
            raise ValueError(f"link {link_name} missing ipv4_subnet in lab_config.yaml")
        hosts = ipaddress.IPv4Network(subnet).hosts()
        next(hosts) # Skip the first usable IP (Docker bridge gateway)
        for router_name in dict.fromkeys(routers_on_link):
            try:
                assignments[router_name][link_name] = str(next(hosts))
            except StopIteration as exc:
                raise ValueError(
                    f"link {link_name} does not have enough usable addresses"
                ) from exc
    return assignments


def build_router_template_contexts(config: LabConfig) -> List[Dict]:
    router_lookup = {router.name: router for router in config.routers}
    link_ips = build_link_ip_assignments(config)
    contexts = []
    for router in config.routers:
        interfaces = [
            {"bridge": "lab_mgmt", "ipv4_address": router.mgmt_ip},
        ]
        for link_name, ipv4 in link_ips.get(router.name, {}).items():
            interfaces.append({"bridge": link_name, "ipv4_address": ipv4})
        peer_entries = []
        for peer in router.peers:
            remote_router = router_lookup[peer.neighbor]
            neighbor_ip = link_ips[remote_router.name][peer.link]
            peer_entries.append(
                {
                    "neighbor_name": remote_router.name,
                    "neighbor_ip": neighbor_ip,
                    "remote_asn": remote_router.asn,
                }
            )
        contexts.append(
            {
                "name": router.name,
                "asn": router.asn,
                "role": router.role,
                "router_id": router.router_id,
                "interfaces": interfaces,
                "env": {"ASN": router.asn},
                "prefixes": router.networks,
                "networks": router.networks,
                "peers": peer_entries,
            }
        )
    return contexts


def render_templates(
    config: LabConfig,
    output_dir: Path,
    metadata_targets: Sequence[Path] | None = None,
) -> None:
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), trim_blocks=True, lstrip_blocks=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    router_contexts = build_router_template_contexts(config)
    compose_template = env.get_template("docker-compose.j2")
    compose_payload = compose_template.render(
        routers=router_contexts,
        links=config.links,
        metadata=config.metadata,
        pcap_pipeline={
            "enabled": bool(config.pcap_pipeline.get("enabled", False)),
            "shared_volume": config.pcap_pipeline.get("shared_volume", "lab_state"),
        },
    )
    compose_path = output_dir / "docker-compose.yml"
    compose_path.write_text(compose_payload, encoding="utf-8")
    frr_template = env.get_template("frr.conf.j2")
    for router in router_contexts:
        router_dir = output_dir / "frr" / router["name"]
        router_dir.mkdir(parents=True, exist_ok=True)
        (router_dir / "daemons").write_text("bgpd=yes\nzebra=yes\n", encoding="utf-8")
        frr_payload = frr_template.render(router=router)
        (router_dir / "frr.conf").write_text(frr_payload, encoding="utf-8")
    metadata_template = env.get_template("topology-metadata.json.j2")
    metadata_payload = metadata_template.render(
        routers=router_contexts,
        links=config.links,
        metadata=config.metadata,
    )
    metadata_path = output_dir / "topology-metadata.json"
    metadata_path.write_text(metadata_payload, encoding="utf-8")
    seen_paths = {metadata_path.resolve()}
    for target in metadata_targets or []:
        target_path = target.resolve()
        if target_path in seen_paths:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(metadata_payload, encoding="utf-8")
        seen_paths.add(target_path)


def summarize(config: LabConfig) -> str:
    routers = [
        {
            "name": router.name,
            "asn": router.asn,
            "role": router.role,
            "prefixes": router.networks,
        }
        for router in config.routers
    ]
    return json.dumps({"metadata": config.metadata, "routers": routers}, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate multi-AS lab artifacts from lab_config.yaml")
    parser.add_argument("config", type=Path, nargs="?", default=Path("lab_config.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("generated_lab"))
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    errors = validate_config(config)
    if errors:
        for error in errors:
            print(f"[lab-gen] validation error: {error}")
        raise SystemExit(1)
    print("[lab-gen] loaded configuration:")
    print(summarize(config))
    if args.validate_only:
        return
    config_path = args.config.resolve()
    metadata_targets = [config_path.parent / "topology-metadata.json"]
    render_templates(config, args.output_dir, metadata_targets)
    print(f"[lab-gen] wrote artifacts to {args.output_dir}")


if __name__ == "__main__":
    main()
