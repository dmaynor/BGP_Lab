#!/usr/bin/env python3
"""
Network replacement utility for the BGP lab.

This tool allows you to change the subnets used in:
    - docker-compose.yml
    - frr/r1/frr.conf
    - frr/r2/frr.conf
    - frr/r3/frr.conf

Usage:

    python3 network_repair.py --show
        Shows which networks are currently in use.

    python3 network_repair.py --set-networks 172.30.12.0/24 172.30.23.0/24
        Rewrites docker-compose.yml and FRR configs so the lab uses:
            net_ab -> 172.30.12.0/24
            net_bc -> 172.30.23.0/24
"""

import argparse
import ipaddress
import os
import re
import sys
from typing import Tuple, List


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_file(path: str) -> str:
    """Read a file and return its contents."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file_atomic(path: str, data: str) -> None:
    """Write a file atomically."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)


def find_ips(text: str) -> List[str]:
    """
    Extract all IPv4 addresses from a block of text.

    Returns:
        A list of strings in dotted-quad format.
    """
    return re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)


def replace_ips(text: str, old_subnet: ipaddress.IPv4Network,
                new_subnet: ipaddress.IPv4Network) -> Tuple[str, bool]:
    """
    Replace all IPs in 'old_subnet' with their equivalents in 'new_subnet'.

    Mapping is position-based:
        old_subnet.network_address + offset -> new_subnet.network_address + offset

    Returns:
        (new_text, changed_flag)
    """
    changed = False

    def repl(match):
        nonlocal changed
        ip = ipaddress.IPv4Address(match.group(0))
        if ip in old_subnet:
            offset = int(ip) - int(old_subnet.network_address)
            new_ip = new_subnet.network_address + offset
            changed = True
            return str(new_ip)
        return match.group(0)

    new_text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", repl, text)
    return new_text, changed


def discover_current_networks(compose_text: str) -> Tuple[ipaddress.IPv4Network, ipaddress.IPv4Network]:
    """
    Extract the net_ab and net_bc subnets from docker-compose.yml.

    Raises:
        RuntimeError if networks cannot be found.
    """
    nets = re.findall(r"subnet:\s*([\d\.]+/\d+)", compose_text)
    if len(nets) < 2:
        raise RuntimeError("Could not detect at least two subnets in docker-compose.yml")

    net_ab = ipaddress.ip_network(nets[0])
    net_bc = ipaddress.ip_network(nets[1])
    return net_ab, net_bc


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def show_networks(repo: str) -> None:
    """Print the networks currently defined in docker-compose.yml."""
    compose_file = os.path.join(repo, "docker-compose.yml")
    compose_text = read_file(compose_file)
    net_ab, net_bc = discover_current_networks(compose_text)

    print("[*] Current lab networks:")
    print(f"    net_ab: {net_ab}")
    print(f"    net_bc: {net_bc}")


def rewrite_networks(repo: str, new_ab: str, new_bc: str) -> None:
    """
    Rewrite docker-compose.yml and FRR configs so the lab uses new subnets.
    """
    new_ab_net = ipaddress.ip_network(new_ab)
    new_bc_net = ipaddress.ip_network(new_bc)

    compose_file = os.path.join(repo, "docker-compose.yml")
    compose_text = read_file(compose_file)
    old_ab, old_bc = discover_current_networks(compose_text)

    print("[*] Old networks:")
    print(f"    net_ab: {old_ab}")
    print(f"    net_bc: {old_bc}")
    print("[*] New networks:")
    print(f"    net_ab: {new_ab_net}")
    print(f"    net_bc: {new_bc_net}")

    # Replace in docker-compose.yml
    updated_compose, changed_c = replace_ips(
        compose_text, old_ab, new_ab_net
    )
    updated_compose, changed_c2 = replace_ips(
        updated_compose, old_bc, new_bc_net
    )
    if changed_c or changed_c2:
        write_file_atomic(compose_file, updated_compose)
        print("[+] docker-compose.yml updated.")
    else:
        print("[!] No changes were needed for docker-compose.yml.")

    # Replace in FRR configs
    for router in ["r1", "r2", "r3"]:
        frr_path = os.path.join(repo, "frr", router, "frr.conf")
        text = read_file(frr_path)
        new_text, changed = replace_ips(text, old_ab, new_ab_net)
        new_text, changed2 = replace_ips(new_text, old_bc, new_bc_net)
        if changed or changed2:
            write_file_atomic(frr_path, new_text)
            print(f"[+] Updated {router}/frr.conf")
        else:
            print(f"[!] No IPs needed replacing in {router}/frr.conf")

    print("[✓] Network replacement completed.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find and replace BGP lab network subnets."
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Show current lab networks and exit."
    )
    parser.add_argument(
        "--set-networks", nargs=2, metavar=("NET_AB", "NET_BC"),
        help="Replace lab networks with the given subnets."
    )
    parser.add_argument(
        "--repo", default=".",
        help="Path to BGP lab repo (default: current directory)."
    )
    return parser.parse_args()


def main():
    args = parse_args()

    repo = os.path.abspath(args.repo)

    if args.show:
        show_networks(repo)
        return

    if args.set_networks:
        new_ab, new_bc = args.set_networks
        rewrite_networks(repo, new_ab, new_bc)
        return

    print("No action specified. Use --show or --set-networks.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

