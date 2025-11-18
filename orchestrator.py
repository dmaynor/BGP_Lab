#!/usr/bin/env python3
"""
BGP attack lab orchestrator.

This script controls a three-AS FRR BGP lab running in Docker:

- R1 (bgp_r1): Victim, AS 65001, prefix 10.10.1.0/24.
- R2 (bgp_r2): Transit/Provider, AS 65002.
- R3 (bgp_r3): Attacker, AS 65003, prefix 10.20.3.0/24.

Scenarios:
    - normal: attacker is honest, no hijack.
    - hijack: attacker announces victim's 10.10.1.0/24.
    - more-specific: attacker announces 10.10.1.128/25 to win via
      longest-prefix match.

The lab is intentionally self-contained; all BGP traffic stays on
private Docker networks.

Usage examples:
    python3 orchestrator.py status
    python3 orchestrator.py scenario normal
    python3 orchestrator.py scenario hijack
    python3 orchestrator.py scenario more-specific
"""

import argparse
import subprocess
from typing import List, Tuple


def run_command(command: List[str]) -> Tuple[int, str, str]:
    """Run a shell command and capture its output."""
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"Failed to execute command: {command}") from exc

    return result.returncode, result.stdout, result.stderr


def vtysh_bgp_config(
    container: str,
    bgp_asn: int,
    commands: List[str],
) -> None:
    """Apply BGP configuration commands to a router using vtysh."""
    base_cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        container,
        "vtysh",
    ]

    vty_commands = [
        "configure terminal",
        f"router bgp {bgp_asn}",
        *commands,
        "end",
        "write",
    ]

    for cmd in vty_commands:
        exit_code, stdout, stderr = run_command(base_cmd + ["-c", cmd])
        if exit_code != 0:
            raise RuntimeError(
                f"vtysh command failed on {container}: {cmd}\n"
                f"stdout:\n{stdout}\n"
                f"stderr:\n{stderr}"
            )


def scenario_normal() -> None:
    """Configure the lab in the 'normal' baseline state."""
    print("[*] Setting scenario: normal (no hijack)")
    vtysh_bgp_config(
        container="r3",
        bgp_asn=65003,
        commands=[
            "no network 10.10.1.0/24",
            "no network 10.10.1.128/25",
        ],
    )
    vtysh_bgp_config(
        container="r3",
        bgp_asn=65003,
        commands=[
            "network 10.20.3.0/24",
        ],
    )
    print("[+] Scenario 'normal' applied.")


def scenario_hijack() -> None:
    """Configure a classic prefix hijack scenario."""
    print("[*] Setting scenario: hijack (attacker announces 10.10.1.0/24)")
    vtysh_bgp_config(
        container="r3",
        bgp_asn=65003,
        commands=[
            "network 10.20.3.0/24",
            "network 10.10.1.0/24",
            "no network 10.10.1.128/25",
        ],
    )
    print("[+] Scenario 'hijack' applied.")


def scenario_more_specific() -> None:
    """Configure a more-specific prefix hijack scenario."""
    print(
        "[*] Setting scenario: more-specific hijack "
        "(attacker announces 10.10.1.128/25)"
    )
    vtysh_bgp_config(
        container="r3",
        bgp_asn=65003,
        commands=[
            "network 10.20.3.0/24",
            "network 10.10.1.128/25",
            "no network 10.10.1.0/24",
        ],
    )
    print("[+] Scenario 'more-specific' applied.")


def show_bgp_table(container: str) -> None:
    """Print the IPv4 BGP table from a given router."""
    print(f"[*] BGP table on {container}:")
    base_cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        container,
        "vtysh",
        "-c",
        "show ip bgp",
    ]
    exit_code, stdout, stderr = run_command(base_cmd)
    if exit_code != 0:
        raise RuntimeError(
            f"Failed to show BGP table on {container}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )

    print(stdout)


def show_status() -> None:
    """Show the current BGP tables on the victim and transit routers."""
    for container in ("r1", "r2"):
        show_bgp_table(container)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the orchestrator."""
    parser = argparse.ArgumentParser(
        description="BGP attack lab orchestrator.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        help="Sub-command to execute.",
    )

    subparsers.add_parser(
        "status",
        help="Show BGP tables on victim (r1) and transit (r2).",
    )

    scenario_parser = subparsers.add_parser(
        "scenario",
        help="Set a BGP attack scenario.",
    )
    scenario_parser.add_argument(
        "name",
        choices=["normal", "hijack", "more-specific"],
        help="Scenario name to activate.",
    )

    return parser.parse_args()


def main() -> None:
    """Entry point for the orchestrator script."""
    args = parse_args()

    if args.command == "status":
        show_status()
    elif args.command == "scenario":
        if args.name == "normal":
            scenario_normal()
        elif args.name == "hijack":
            scenario_hijack()
        elif args.name == "more-specific":
            scenario_more_specific()
        else:
            raise ValueError(f"Unhandled scenario name: {args.name}")
    else:
        raise ValueError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    main()
