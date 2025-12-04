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

"""
Network linter and fixer for the BGP lab project.

This script inspects and optionally rewrites:

    - docker-compose.yml
    - frr/r1/frr.conf
    - frr/r2/frr.conf
    - frr/r3/frr.conf

Capabilities:

1) Lint mode (--lint)
   - Discover subnets in docker-compose.yml (net_ab, net_bc).
   - Check static ipv4_address entries:
       * Inside a known lab subnet?
       * Equal to Docker's gateway IP (subnet.network + 1)?
   - Check FRR neighbor IPs:
       * Inside any lab subnet?

2) Rewrite mode (--set-networks NET_AB NET_BC)
   - If subnets already exist:
       * Replace all IPs in old subnets with equivalent IPs in new ones.
       * Optionally fix gateway IP misuse (with --fix-gateways).
   - If no subnets exist:
       * Insert a networks: block with net_ab/net_bc using the new subnets.
       * FRR configs are left unchanged (no mapping info).

3) Auto-network mode (--auto-networks)
   - Query Docker for existing network subnets.
   - Choose two unused /24 subnets from a candidate pool (10.200.0.0/16).
   - Apply them as in (2).

4) Topology fix (--fix-topology)
   - Deduplicate networks: section (keep first net_ab/net_bc definition).
   - Assign deterministic IPs:
        r1@net_ab = subnet_ab + 10
        r2@net_ab = subnet_ab + 11
        r2@net_bc = subnet_bc + 10
        r3@net_bc = subnet_bc + 11
   - Rewrite service networks blocks to use ipv4_address for those IPs.
   - Rewrite FRR neighbor IPs to match those addresses.
"""

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file_atomic(path: str, data: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Docker utilities for auto-networking
# ---------------------------------------------------------------------------

def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(f"Failed to execute command: {cmd}") from exc
    return proc.returncode, proc.stdout, proc.stderr


def get_docker_network_subnets() -> List[ipaddress.IPv4Network]:
    code, out, err = run_cmd(["docker", "network", "ls", "-q"])
    if code != 0:
        raise RuntimeError(
            f"Failed to list Docker networks (exit {code}). stderr:\n{err}"
        )
    ids = [line.strip() for line in out.splitlines() if line.strip()]
    if not ids:
        return []
    code, out, err = run_cmd(["docker", "network", "inspect"] + ids)
    if code != 0:
        raise RuntimeError(
            f"Failed to inspect Docker networks (exit {code}). stderr:\n{err}"
        )
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Failed to parse 'docker network inspect' JSON") from exc

    subnets: List[ipaddress.IPv4Network] = []
    for net in data:
        ipam = net.get("IPAM") or {}
        configs = ipam.get("Config") or []
        for cfg in configs:
            subnet_str = cfg.get("Subnet")
            if not subnet_str:
                continue
            try:
                subnets.append(ipaddress.ip_network(subnet_str))
            except ValueError:
                continue
    return subnets


def pick_unused_subnets(
    used: List[ipaddress.IPv4Network],
    count: int = 2,
    candidate_cidr: str = "10.200.0.0/16",
    new_prefix: int = 24,
) -> List[ipaddress.IPv4Network]:
    candidate = ipaddress.ip_network(candidate_cidr)
    candidates = list(candidate.subnets(new_prefix=new_prefix))

    free: List[ipaddress.IPv4Network] = []
    for cand in candidates:
        if any(cand.overlaps(u) for u in used):
            continue
        free.append(cand)
        if len(free) >= count:
            break

    if len(free) < count:
        raise RuntimeError(
            f"Could not find {count} free /{new_prefix} subnets inside "
            f"{candidate_cidr} that do not overlap existing Docker networks."
        )

    return free


# ---------------------------------------------------------------------------
# Docker compose parsing / linting
# ---------------------------------------------------------------------------

def discover_subnets(compose_text: str) -> List[ipaddress.IPv4Network]:
    nets = re.findall(r"subnet:\s*([\d\.]+/\d+)", compose_text)
    if not nets:
        raise RuntimeError("No 'subnet:' entries found in docker-compose.yml.")
    return [ipaddress.ip_network(n) for n in nets]


def lint_compose_ips(
    compose_text: str,
    subnets: List[ipaddress.IPv4Network],
) -> List[str]:
    messages: List[str] = []
    lines = compose_text.splitlines()

    current_service: Optional[str] = None
    in_services = False

    for line in lines:
        stripped = line.strip()

        if re.match(r"^services:\s*$", stripped):
            in_services = True
            current_service = None
            continue

        if re.match(r"^[a-zA-Z0-9_]+:\s*$", stripped) and not line.startswith(" "):
            key = stripped.split(":", 1)[0]
            if key != "services":
                in_services = False
                current_service = None
            continue

        if in_services and re.match(r"^\s{2}[a-zA-Z0-9_]+:\s*$", line):
            key = stripped.split(":", 1)[0]
            current_service = key
            continue

        match = re.search(r"ipv4_address:\s*([\d\.]+)", stripped)
        if not match:
            continue

        ip_str = match.group(1)
        try:
            ip_addr = ipaddress.ip_address(ip_str)
        except ValueError:
            messages.append(
                f"[compose] {current_service or '?'}: invalid ipv4_address "
                f"'{ip_str}'"
            )
            continue

        if not isinstance(ip_addr, ipaddress.IPv4Address):
            messages.append(
                f"[compose] {current_service or '?'}: ipv4_address {ip_str} "
                "is not an IPv4 address"
            )
            continue

        in_any = False
        gw_hit = False
        gw_for: List[str] = []

        for net in subnets:
            if ip_addr in net:
                in_any = True
                gateway = net.network_address + 1
                if ip_addr == gateway:
                    gw_hit = True
                    gw_for.append(str(net))

        if not in_any:
            messages.append(
                f"[compose] {current_service or '?'}: ipv4_address {ip_addr} "
                f"is not in any known subnet {subnets}"
            )

        if gw_hit:
            nets_str = ", ".join(gw_for)
            messages.append(
                f"[compose] {current_service or '?'}: ipv4_address {ip_addr} "
                f"matches Docker gateway for subnet(s) {nets_str} "
                "(this will cause 'address already in use' errors)"
            )

    return messages


def fix_gateway_ips_in_compose(
    compose_text: str,
    subnets: List[ipaddress.IPv4Network],
) -> Tuple[str, List[str]]:
    messages: List[str] = []
    new_text = compose_text

    for net in subnets:
        gateway = net.network_address + 1
        offset = 10 if net.num_addresses > 16 else 2
        safe_ip = net.network_address + offset

        pattern = (
            r"(ipv4_address:\s*)"
            + re.escape(str(gateway))
            + r"(\b)"
        )

        def repl(match: re.Match) -> str:
            messages.append(
                f"[fix] Rewriting ipv4_address {gateway} to {safe_ip} "
                f"in subnet {net}"
            )
            return f"{match.group(1)}{safe_ip}{match.group(2)}"

        new_text, _ = re.subn(pattern, repl, new_text)

    return new_text, messages


# ---------------------------------------------------------------------------
# FRR parsing / linting
# ---------------------------------------------------------------------------

def lint_frr_neighbors(
    repo: str,
    subnets: List[ipaddress.IPv4Network],
) -> List[str]:
    messages: List[str] = []

    for router in ("r1", "r2", "r3"):
        frr_path = os.path.join(repo, "frr", router, "frr.conf")
        if not os.path.exists(frr_path):
            continue

        text = read_file(frr_path)
        neighbors = re.findall(
            r"neighbor\s+([\d\.]+)\s+remote-as",
            text,
        )

        for ip_str in neighbors:
            try:
                ip_addr = ipaddress.ip_address(ip_str)
            except ValueError:
                messages.append(
                    f"[frr] {router}: invalid neighbor address '{ip_str}'"
                )
                continue

            if not isinstance(ip_addr, ipaddress.IPv4Address):
                messages.append(
                    f"[frr] {router}: neighbor {ip_str} is not IPv4"
                )
                continue

            if not any(ip_addr in net for net in subnets):
                messages.append(
                    f"[frr] {router}: neighbor {ip_addr} is not in any lab "
                    f"subnet {subnets} (verify if this is intentional)"
                )

    return messages


# ---------------------------------------------------------------------------
# Network rewriting / injection logic
# ---------------------------------------------------------------------------

def replace_ips(
    text: str,
    old_subnet: ipaddress.IPv4Network,
    new_subnet: ipaddress.IPv4Network,
) -> Tuple[str, bool]:
    changed = False

    def repl(match: re.Match) -> str:
        nonlocal changed
        ip = ipaddress.ip_address(match.group(0))
        if isinstance(ip, ipaddress.IPv4Address) and ip in old_subnet:
            offset = int(ip) - int(old_subnet.network_address)
            new_ip = new_subnet.network_address + offset
            changed = True
            return str(new_ip)
        return match.group(0)

    new_text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", repl, text)
    return new_text, changed


def inject_lab_networks_block(
    compose_text: str,
    net_ab: ipaddress.IPv4Network,
    net_bc: ipaddress.IPv4Network,
) -> str:
    block = [
        "networks:",
        "  net_ab:",
        "    driver: bridge",
        "    ipam:",
        "      config:",
        f"        - subnet: {net_ab}",
        "  net_bc:",
        "    driver: bridge",
        "    ipam:",
        "      config:",
        f"        - subnet: {net_bc}",
    ]

    lines = compose_text.splitlines()
    new_lines: List[str] = []
    inserted = False

    for line in lines:
        new_lines.append(line)
        if not inserted and re.match(r"^networks:\s*$", line):
            for bline in block[1:]:
                new_lines.append(bline)
            inserted = True

    if not inserted:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.extend(block)

    return "\n".join(new_lines) + "\n"


def dedupe_networks_section(compose_text: str) -> str:
    lines = compose_text.splitlines()
    new_lines: List[str] = []
    in_networks = False
    seen_keys: Dict[str, bool] = {}

    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^networks:\s*$", line):
            in_networks = True
            new_lines.append(line)
            i += 1
            continue

        if in_networks:
            m = re.match(r"^(\s{2})([a-zA-Z0-9_]+):\s*$", line)
            if m:
                indent, key = m.groups()
                if key in seen_keys:
                    # skip this block
                    i += 1
                    while i < len(lines):
                        nxt = lines[i]
                        if re.match(r"^\s{2}[a-zA-Z0-9_]+:\s*$", nxt):
                            break
                        if re.match(r"^[^ \t]", nxt):
                            break
                        i += 1
                    continue
                seen_keys[key] = True
                new_lines.append(line)
                i += 1
                continue
        new_lines.append(line)
        i += 1

    return "\n".join(new_lines) + "\n"


def rewrite_networks(
    repo: str,
    new_ab: ipaddress.IPv4Network,
    new_bc: ipaddress.IPv4Network,
    fix_gateways: bool,
) -> None:
    compose_file = os.path.join(repo, "docker-compose.yml")
    compose_text = read_file(compose_file)

    try:
        old_subnets = discover_subnets(compose_text)
    except RuntimeError:
        print(
            "[!] No existing 'subnet:' entries found. "
            "Injecting new net_ab/net_bc networks and leaving FRR configs untouched."
        )
        updated_compose = inject_lab_networks_block(
            compose_text, new_ab, new_bc
        )
        updated_compose = dedupe_networks_section(updated_compose)
        write_file_atomic(compose_file, updated_compose)
        print(f"[+] docker-compose.yml: added networks net_ab={new_ab}, net_bc={new_bc}")
        return

    if len(old_subnets) < 2:
        raise RuntimeError(
            "Expected at least two subnets in docker-compose.yml "
            "(net_ab, net_bc)."
        )

    old_ab = old_subnets[0]
    old_bc = old_subnets[1]

    print("[*] Old networks:")
    print(f"    net_ab: {old_ab}")
    print(f"    net_bc: {old_bc}")
    print("[*] New networks:")
    print(f"    net_ab: {new_ab}")
    print(f"    net_bc: {new_bc}")

    updated_compose, changed1 = replace_ips(compose_text, old_ab, new_ab)
    updated_compose, changed2 = replace_ips(updated_compose, old_bc, new_bc)

    gateway_fix_msgs: List[str] = []
    if fix_gateways:
        updated_compose, gateway_fix_msgs = fix_gateway_ips_in_compose(
            updated_compose, [new_ab, new_bc]
        )

    updated_compose = dedupe_networks_section(updated_compose)

    if changed1 or changed2 or gateway_fix_msgs:
        write_file_atomic(compose_file, updated_compose)
        print("[+] docker-compose.yml updated.")
        for msg in gateway_fix_msgs:
            print(msg)
    else:
        print("[!] No changes were needed for docker-compose.yml.")

    for router in ("r1", "r2", "r3"):
        frr_path = os.path.join(repo, "frr", router, "frr.conf")
        if not os.path.exists(frr_path):
            continue

        text = read_file(frr_path)
        new_text, ch1 = replace_ips(text, old_ab, new_ab)
        new_text, ch2 = replace_ips(new_text, old_bc, new_bc)

        if ch1 or ch2:
            write_file_atomic(frr_path, new_text)
            print(f"[+] Updated {router}/frr.conf")
        else:
            print(f"[!] No IPs needed replacing in {router}/frr.conf")

    print("[✓] Network rewrite completed.")


# ---------------------------------------------------------------------------
# Topology fixer: assign IPs + fix FRR
# ---------------------------------------------------------------------------

def patch_service_networks(
    compose_text: str,
    subnets: List[ipaddress.IPv4Network],
) -> Tuple[str, Dict[str, Dict[str, ipaddress.IPv4Address]]]:
    """
    Ensure r1/r2/r3 have deterministic IPs on net_ab/net_bc.

    Returns:
        (updated_compose_text, mapping)
    mapping format:
        {
          "r1": {"net_ab": IPv4Address},
          "r2": {"net_ab": IPv4Address, "net_bc": IPv4Address},
          "r3": {"net_bc": IPv4Address},
        }
    """
    if len(subnets) < 2:
        raise RuntimeError("Need at least two subnets for topology fix.")

    net_ab = subnets[0]
    net_bc = subnets[1]

    mapping: Dict[str, Dict[str, ipaddress.IPv4Address]] = {
        "r1": {"net_ab": net_ab.network_address + 10},
        "r2": {
            "net_ab": net_ab.network_address + 11,
            "net_bc": net_bc.network_address + 10,
        },
        "r3": {"net_bc": net_bc.network_address + 11},
    }

    lines = compose_text.splitlines()
    new_lines: List[str] = []

    current_service: Optional[str] = None
    i = 0
    while i < len(lines):
        line = lines[i]

        m_service = re.match(r"^  (r1|r2|r3):\s*$", line)
        if m_service:
            current_service = m_service.group(1)
            new_lines.append(line)
            i += 1
            continue

        if current_service and re.match(r"^  [a-zA-Z0-9_]+:\s*$", line):
            # starting a new top-level service; reset
            current_service = None
            new_lines.append(line)
            i += 1
            continue

        if current_service and re.match(r"^\s{4}networks:\s*$", line):
            # Replace this networks block
            new_lines.append(line)
            i += 1
            # skip old networks block
            while i < len(lines):
                nxt = lines[i]
                if re.match(r"^\s{4}[a-zA-Z0-9_]+:\s*$", nxt):
                    break
                if re.match(r"^  [a-zA-Z0-9_]+:\s*$", nxt):
                    break
                if re.match(r"^[^ ]", nxt):
                    break
                if re.match(r"^\s{6}-\s+net_(ab|bc)\s*$", nxt):
                    i += 1
                    continue
                new_lines.append(nxt)
                i += 1

            # insert our deterministic mapping
            if current_service == "r1":
                ip_ab = mapping["r1"]["net_ab"]
                new_lines.append("      net_ab:")
                new_lines.append(f"        ipv4_address: {ip_ab}")
            elif current_service == "r2":
                ip_ab = mapping["r2"]["net_ab"]
                ip_bc = mapping["r2"]["net_bc"]
                new_lines.append("      net_ab:")
                new_lines.append(f"        ipv4_address: {ip_ab}")
                new_lines.append("      net_bc:")
                new_lines.append(f"        ipv4_address: {ip_bc}")
            elif current_service == "r3":
                ip_bc = mapping["r3"]["net_bc"]
                new_lines.append("      net_bc:")
                new_lines.append(f"        ipv4_address: {ip_bc}")

            continue

        new_lines.append(line)
        i += 1

    return "\n".join(new_lines) + "\n", mapping


def align_frr_to_mapping(
    repo: str,
    mapping: Dict[str, Dict[str, ipaddress.IPv4Address]],
    subnets: List[ipaddress.IPv4Network],
) -> None:
    """
    Rewrite FRR neighbor IPs to match docker IP mapping.

    We assume:
        r1 ASN = 65001
        r2 ASN = 65002
        r3 ASN = 65003

    Topology:
        r1 <-> r2 on net_ab
        r2 <-> r3 on net_bc
    """
    # r1 neighbors r2
    r1_frr = os.path.join(repo, "frr", "r1", "frr.conf")
    if os.path.exists(r1_frr):
        txt = read_file(r1_frr)
        old_ips = re.findall(r"neighbor\s+([\d\.]+)\s+remote-as\s+65002", txt)
        new_ip = str(mapping["r2"]["net_ab"])
        for old in set(old_ips):
            pattern = r"\b" + re.escape(old) + r"\b"
            txt = re.sub(pattern, new_ip, txt)
        write_file_atomic(r1_frr, txt)
        print(f"[+] r1: neighbors now point to {new_ip} for AS 65002")

    # r2 neighbors r1 (AS 65001) and r3 (AS 65003)
    r2_frr = os.path.join(repo, "frr", "r2", "frr.conf")
    if os.path.exists(r2_frr):
        txt = read_file(r2_frr)
        old_ips_65001 = re.findall(r"neighbor\s+([\d\.]+)\s+remote-as\s+65001", txt)
        new_ip_65001 = str(mapping["r1"]["net_ab"])
        for old in set(old_ips_65001):
            pattern = r"\b" + re.escape(old) + r"\b"
            txt = re.sub(pattern, new_ip_65001, txt)

        old_ips_65003 = re.findall(r"neighbor\s+([\d\.]+)\s+remote-as\s+65003", txt)
        new_ip_65003 = str(mapping["r3"]["net_bc"])
        for old in set(old_ips_65003):
            pattern = r"\b" + re.escape(old) + r"\b"
            txt = re.sub(pattern, new_ip_65003, txt)

        write_file_atomic(r2_frr, txt)
        print(f"[+] r2: neighbors now point to {new_ip_65001} (AS 65001) and {new_ip_65003} (AS 65003)")

    # r3 neighbors r2
    r3_frr = os.path.join(repo, "frr", "r3", "frr.conf")
    if os.path.exists(r3_frr):
        txt = read_file(r3_frr)
        old_ips = re.findall(r"neighbor\s+([\d\.]+)\s+remote-as\s+65002", txt)
        new_ip = str(mapping["r2"]["net_bc"])
        for old in set(old_ips):
            pattern = r"\b" + re.escape(old) + r"\b"
            txt = re.sub(pattern, new_ip, txt)
        write_file_atomic(r3_frr, txt)
        print(f"[+] r3: neighbors now point to {new_ip} for AS 65002")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint and fix network-related settings in the BGP lab."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to BGP lab repo (default: current directory).",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help="Run network linting checks and report issues.",
    )
    parser.add_argument(
        "--fix-gateways",
        action="store_true",
        help="Fix ipv4_address entries that equal Docker's gateway IP.",
    )
    parser.add_argument(
        "--set-networks",
        nargs=2,
        metavar=("NET_AB", "NET_BC"),
        help="Rewrite lab to use new subnets NET_AB and NET_BC.",
    )
    parser.add_argument(
        "--auto-networks",
        action="store_true",
        help=(
            "Automatically pick two unused /24 subnets (from 10.200.0.0/16) "
            "that do not overlap existing Docker networks, and apply them."
        ),
    )
    parser.add_argument(
        "--fix-topology",
        action="store_true",
        help=(
            "Align docker service IPs and FRR neighbor IPs to the lab "
            "subnets (assign deterministic IPs to r1/r2/r3)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = os.path.abspath(args.repo)

    compose_file = os.path.join(repo, "docker-compose.yml")
    if not os.path.exists(compose_file):
        print(
            f"[-] docker-compose.yml not found at {compose_file}",
            file=sys.stderr,
        )
        sys.exit(1)

    compose_text = read_file(compose_file)

    # 1. Auto-network mode
    if args.auto_networks:
        print("[*] Auto-network mode: discovering used Docker subnets...")
        used = get_docker_network_subnets()
        print(f"    Docker currently uses: {used or '[]'}")
        new_subnets = pick_unused_subnets(used, count=2)
        new_ab, new_bc = new_subnets[0], new_subnets[1]
        print(
            f"[*] Selected free subnets for lab:\n"
            f"    net_ab: {new_ab}\n"
            f"    net_bc: {new_bc}"
        )
        rewrite_networks(repo, new_ab, new_bc, fix_gateways=args.fix_gateways)
        compose_text = read_file(compose_file)

    # 2. Explicit set-networks
    if args.set_networks:
        net_ab_str, net_bc_str = args.set_networks
        new_ab = ipaddress.ip_network(net_ab_str)
        new_bc = ipaddress.ip_network(net_bc_str)
        rewrite_networks(repo, new_ab, new_bc, fix_gateways=args.fix_gateways)
        compose_text = read_file(compose_file)

    # 3. Topology fix (assign IPs + fix FRR)
    if args.fix_topology:
        try:
            subnets = discover_subnets(compose_text)
        except RuntimeError as exc:
            print(f"[!] Cannot fix topology: {exc}", file=sys.stderr)
            subnets = []

        if subnets:
            updated_compose, mapping = patch_service_networks(compose_text, subnets)
            updated_compose = dedupe_networks_section(updated_compose)
            write_file_atomic(compose_file, updated_compose)
            compose_text = updated_compose
            align_frr_to_mapping(repo, mapping, subnets)
        else:
            print("[!] Skipping topology fix; no lab subnets found.", file=sys.stderr)

    # 4. Lint (explicit or default)
    do_lint = args.lint or (not args.auto_networks and not args.set_networks and not args.fix_topology)

    if do_lint:
        print("[*] Linting docker-compose.yml and FRR configs...")
        try:
            subnets = discover_subnets(compose_text)
        except RuntimeError as exc:
            print(f"[!] Lint warning: {exc}", file=sys.stderr)
            subnets = []

        lint_msgs: List[str] = []
        if subnets:
            lint_msgs.extend(lint_compose_ips(compose_text, subnets))
            lint_msgs.extend(lint_frr_neighbors(repo, subnets))
        else:
            lint_msgs.append(
                "[lint] No explicit subnets found; cannot validate IPs "
                "against lab ranges."
            )

        if not lint_msgs:
            print("[✓] No network issues detected.")
        else:
            print("[!] Network lint findings:")
            for msg in lint_msgs:
                print("    " + msg)


if __name__ == "__main__":
    main()

