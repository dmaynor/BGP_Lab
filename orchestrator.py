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
BGP attack lab orchestrator.

This module controls a three-AS FRR BGP lab running in Docker.

Topology (current legacy baseline):

* R1 (container ``r1``): Victim, AS 65001, prefix ``10.10.1.0/24``.
* R2 (container ``r2``): Transit/Provider, AS 65002.
* R3 (container ``r3``): Attacker, AS 65003, prefix ``10.20.3.0/24``.

Scenarios are intentionally simple and deterministic so they can be
triggered safely from the Attack Controller and visualised by the
Observer UI. All traffic stays on private Docker networks.

Supported scenario entrypoints (matched by ``lab_config.yaml``):

* ``normal``: Baseline – no hijack, attacker only advertises its own
  prefix.
* ``hijack``: Attacker re-originates the victim's prefix
  (classic origin hijack).
* ``more-specific``: Attacker advertises a more specific subprefix of
  the victim's space to win via longest-prefix match.
* ``leak``: Transit AS incorrectly re-originates both edge prefixes
  (simple route leak demonstration).
* ``aspath``: Attacker hijacks the victim prefix and prepends a forged
  AS_PATH to appear more legitimate.
* ``blackhole``: Remotely triggered blackhole for the victim prefix:
  traffic is steered to a Null0 route at the attacker.

Usage examples::

    python3 orchestrator.py status
    python3 orchestrator.py scenario normal
    python3 orchestrator.py scenario hijack
    python3 orchestrator.py scenario more-specific
    python3 orchestrator.py scenario leak
    python3 orchestrator.py scenario aspath
    python3 orchestrator.py scenario blackhole
"""

from __future__ import annotations

import argparse
import itertools
import subprocess
from typing import Callable, Dict, Iterable, List, Tuple


def run_command(command: List[str]) -> Tuple[int, str, str]:
    """Run a shell command and capture its output.

    Parameters
    ----------
    command:
        The full command line to execute, including arguments.

    Returns
    -------
    tuple[int, str, str]
        A tuple of ``(exit_code, stdout, stderr)``.
    """
    result = subprocess.run(  # type: ignore[call-arg]
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def _build_vtysh_command(container: str, commands: Iterable[str]) -> List[str]:
    """Construct a ``vtysh`` invocation for a set of configuration commands.

    The commands are passed using repeated ``-c`` flags so that the
    resulting call is easy to trace and replay.

    Parameters
    ----------
    container:
        Name of the Docker service/container (e.g. ``"r3"``).
    commands:
        Iterable of configuration commands to feed into ``vtysh``.

    Returns
    -------
    list[str]
        The full command line suitable for :func:`subprocess.run`.
    """
    base_cmd: List[str] = [
        "docker",
        "compose",
        "exec",
        "-T",
        container,
        "vtysh",
    ]
    vty_args: List[str] = list(
        itertools.chain.from_iterable(("-c", cmd) for cmd in commands)
    )
    return base_cmd + vty_args


def vtysh_bgp_config(container: str, bgp_asn: int, commands: List[str]) -> None:
    """Apply BGP configuration commands to a router using ``vtysh``.

    This helper drops into BGP IPv4 unicast configuration mode and runs
    the given commands. It then writes the FRR configuration to disk.

    Parameters
    ----------
    container:
        Docker service/container name (for example, ``"r3"``).
    bgp_asn:
        The BGP ASN of the router being configured.
    commands:
        A list of commands to execute inside
        ``router bgp <asn> -> address-family ipv4 unicast``.

    Raises
    ------
    RuntimeError
        If the underlying ``vtysh`` invocation fails.
    """
    vty_commands: List[str] = [
        "configure terminal",
        f"router bgp {bgp_asn}",
        "address-family ipv4 unicast",
        *commands,
        "exit-address-family",
        "end",
        "write memory",
    ]
    full_cmd = _build_vtysh_command(container, vty_commands)
    exit_code, stdout, stderr = run_command(full_cmd)
    # Ignore benign errors from cleanup commands (removing non-existent config)
    benign_errors = [
        "Can't find",
        "Refusing to remove",
        "Can't open configuration file /etc/frr/vtysh.conf",
    ]
    if exit_code != 0 and not any(err in stdout for err in benign_errors):
        raise RuntimeError(
            f"Failed to apply BGP configuration on {container}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )


def vtysh_global_config(container: str, commands: List[str]) -> None:
    """Apply global FRR configuration commands using ``vtysh``.

    This helper runs the provided commands from ``configure terminal``
    mode without entering any protocol-specific submodes. It is used for
    features such as static routes and route-maps that are not specific
    to a single BGP address-family configuration block.

    Parameters
    ----------
    container:
        Docker service/container name.
    commands:
        A list of configuration-mode commands (no ``end`` or
        ``write memory`` required).

    Raises
    ------
    RuntimeError
        If ``vtysh`` returns a non-zero exit code.
    """
    if not commands:
        return

    vty_commands: List[str] = ["configure terminal", *commands, "end", "write memory"]
    full_cmd = _build_vtysh_command(container, vty_commands)
    exit_code, stdout, stderr = run_command(full_cmd)
    # Ignore benign errors from cleanup commands (removing non-existent config)
    benign_errors = [
        "Can't find static route",
        "Refusing to remove a non-existent",
        "Can't open configuration file /etc/frr/vtysh.conf",
    ]
    if exit_code != 0 and not any(err in stdout for err in benign_errors):
        raise RuntimeError(
            f"Failed to apply global configuration on {container}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )


def scenario_normal() -> None:
    """Configure the lab in the baseline "normal" state.

    * Attacker (``r3``) advertises only its own prefix ``10.20.3.0/24``.
    * Any stray hijack/leak/blackhole artefacts from previous scenarios
      are cleaned up as best-effort.
    """
    print("[*] Setting scenario: normal (no hijack)")
    # Best-effort cleanup of advanced scenarios (safe even if not set).
    vtysh_global_config(
        container="r3",
        commands=[
            "no route-map ASPATH-FORGE permit 10",
            "no ip route 10.10.1.0/24 Null0",
            "no ip route 0.0.0.0/0 10.0.0.10",
        ],
    )
    vtysh_global_config(
        container="r2",
        commands=[
            "no ip route 10.10.1.0/24 10.0.0.2",
            "no ip route 10.20.3.0/24 10.0.0.11",
        ],
    )
    vtysh_bgp_config(
        container="r3",
        bgp_asn=65003,
        commands=[
            "no neighbor 10.0.0.10 route-map ASPATH-FORGE out",
            "no network 10.10.1.0/24",
            "no network 10.10.1.128/25",
            "network 10.20.3.0/24",
        ],
    )
    vtysh_bgp_config(
        container="r2",
        bgp_asn=65002,
        commands=[
            "no network 10.10.1.0/24",
            "no network 10.20.3.0/24",
        ],
    )
    print("[+] Scenario 'normal' applied.")


def scenario_hijack() -> None:
    """Configure a classic prefix-hijack scenario.

    The attacker (``r3``) originates the victim's prefix
    ``10.10.1.0/24`` in addition to its own prefix. This matches the
    behaviour described in ``lab_config.yaml`` under the
    ``hijack`` scenario.
    """
    print("[*] Setting scenario: hijack (attacker announces 10.10.1.0/24)")
    # Add static route for the hijacked prefix so BGP can originate it
    vtysh_global_config(
        container="r3",
        commands=["ip route 10.10.1.0/24 Null0"],
    )
    # Cleanup previous scenario configs (separate call to avoid abort on error)
    vtysh_bgp_config(
        container="r3",
        bgp_asn=65003,
        commands=[
            "no neighbor 10.0.0.10 route-map ASPATH-FORGE out",
            "no network 10.10.1.128/25",
        ],
    )
    # Apply the hijack configuration
    vtysh_bgp_config(
        container="r3",
        bgp_asn=65003,
        commands=[
            "network 10.20.3.0/24",
            "network 10.10.1.0/24",
        ],
    )
    print("[+] Scenario 'hijack' applied.")


def scenario_more_specific() -> None:
    """Configure a more-specific prefix-hijack scenario.

    The attacker (``r3``) advertises a subprefix ``10.10.1.128/25`` of
    the victim's ``10.10.1.0/24`` block. Longest-prefix match causes
    traffic destined for the subprefix to favour the attacker.
    """
    print(
        "[*] Setting scenario: more-specific hijack "
        "(attacker announces 10.10.1.128/25)"
    )
    # Add static route for the more-specific hijacked prefix
    vtysh_global_config(
        container="r3",
        commands=["ip route 10.10.1.128/25 Null0"],
    )
    vtysh_bgp_config(
        container="r3",
        bgp_asn=65003,
        commands=[
            "no neighbor 10.0.0.10 route-map ASPATH-FORGE out",
            "network 10.20.3.0/24",
            "network 10.10.1.128/25",
            "no network 10.10.1.0/24",
        ],
    )
    print("[+] Scenario 'more-specific' applied.")


def scenario_leak() -> None:
    """Configure a simple route-leak style scenario.

    In this demonstration:

    * The transit AS (``r2``, ASN 65002) re-originates both edge
      prefixes (victim and attacker) using static routes plus
      ``network`` statements.
    * This is a stylised, contained example to show how a transit AS
      leaking prefixes can create alternative origins for the same
      address space.

    The exact semantics are tuned for a 3-router educational lab and do
    not model a specific real-world incident.
    """
    print("[*] Setting scenario: route leak (transit re-originates both edges)")
    # Ensure attacker is honest in this scenario.
    vtysh_bgp_config(
        container="r3",
        bgp_asn=65003,
        commands=[
            "no neighbor 10.0.0.10 route-map ASPATH-FORGE out",
            "no network 10.10.1.0/24",
            "no network 10.10.1.128/25",
            "network 10.20.3.0/24",
        ],
    )
    # Static routes on the transit so it can legitimately originate both
    # prefixes via BGP.
    vtysh_global_config(
        container="r2",
        commands=[
            "ip route 10.10.1.0/24 10.0.0.2",
            "ip route 10.20.3.0/24 10.0.0.11",
        ],
    )
    vtysh_bgp_config(
        container="r2",
        bgp_asn=65002,
        commands=[
            "network 10.10.1.0/24",
            "network 10.20.3.0/24",
        ],
    )
    print("[+] Scenario 'leak' applied.")


def scenario_aspath() -> None:
    """Configure an AS-PATH forgery style hijack scenario.

    This scenario builds on the basic origin hijack but also attaches a
    forged AS-PATH so that, from the outside, the attacker can appear
    more legitimate (for example, by prepending the victim ASN).

    Implementation notes
    --------------------
    * A simple route-map ``ASPATH-FORGE`` is installed on ``r3``.
    * The route-map prepends ``65001 65001`` to outbound announcements.
    * The victim prefix ``10.10.1.0/24`` is originated from ``r3``.
    """
    print("[*] Setting scenario: AS-PATH forgery hijack")
    # Add static route for the hijacked prefix
    vtysh_global_config(
        container="r3",
        commands=["ip route 10.10.1.0/24 Null0"],
    )
    # Install / refresh the route-map.
    vtysh_global_config(
        container="r3",
        commands=[
            "no route-map ASPATH-FORGE permit 10",
            "route-map ASPATH-FORGE permit 10",
            " set as-path prepend 65001 65001",
        ],
    )
    vtysh_bgp_config(
        container="r3",
        bgp_asn=65003,
        commands=[
            "network 10.20.3.0/24",
            "network 10.10.1.0/24",
            "no network 10.10.1.128/25",
            "neighbor 10.0.0.10 route-map ASPATH-FORGE out",
        ],
    )
    print("[+] Scenario 'aspath' applied.")


def scenario_blackhole() -> None:
    """Configure a remotely triggered blackhole (RTBH) style scenario.

    The attacker advertises the victim prefix ``10.10.1.0/24`` but
    installs a static route to ``Null0`` so that traffic sent towards the
    hijacked prefix is discarded once it reaches the attacker.

    This models the *effect* of RTBH in a minimal way suitable for this
    3-router lab.
    """
    print("[*] Setting scenario: blackhole (RTBH-style for 10.10.1.0/24)")
    # Ensure the static blackhole route exists on the attacker.
    vtysh_global_config(
        container="r3",
        commands=["ip route 10.10.1.0/24 Null0"],
    )
    vtysh_bgp_config(
        container="r3",
        bgp_asn=65003,
        commands=[
            "no neighbor 10.0.0.10 route-map ASPATH-FORGE out",
            "network 10.20.3.0/24",
            "network 10.10.1.0/24",
            "no network 10.10.1.128/25",
        ],
    )
    print("[+] Scenario 'blackhole' applied.")


def show_bgp_table(container: str) -> None:
    """Print the IPv4 BGP table from a given router.

    Parameters
    ----------
    container:
        Docker service/container name (for example, ``"r1"``).
    """
    print(f"[*] BGP table on {container}:")
    commands = [
        "vtysh",
        "-c",
        "show ip bgp",
    ]
    base_cmd: List[str] = [
        "docker",
        "compose",
        "exec",
        "-T",
        container,
        *commands,
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


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the orchestrator.

    Returns
    -------
    argparse.Namespace
        Parsed arguments with ``command`` and any sub-command options.
    """
    parser = argparse.ArgumentParser(
        description="BGP attack lab orchestrator (3-router baseline)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser(
        "status", help="Show BGP tables on key routers"
    )
    status_parser.set_defaults(command="status")

    scenario_parser = subparsers.add_parser(
        "scenario", help="Apply a named BGP scenario"
    )
    scenario_parser.add_argument(
        "name",
        help=(
            "Scenario name (normal, hijack, more-specific, leak, aspath, "
            "blackhole)"
        ),
    )
    scenario_parser.set_defaults(command="scenario")

    return parser.parse_args()


SCENARIO_HANDLERS: Dict[str, Callable[[], None]] = {
    "normal": scenario_normal,
    "hijack": scenario_hijack,
    "more-specific": scenario_more_specific,
    "leak": scenario_leak,
    "aspath": scenario_aspath,
    "blackhole": scenario_blackhole,
}


def main() -> None:
    """Entry point for the orchestrator CLI.

    This function dispatches the requested command to the appropriate
    helper function. Scenario names are aligned with the
    ``orchestrator_entrypoint`` values defined in ``lab_config.yaml`` so
    the Attack Controller can safely invoke them.
    """
    args = _parse_args()

    if args.command == "status":
        show_status()
        return

    if args.command == "scenario":
        scenario_name: str = args.name
        try:
            handler = SCENARIO_HANDLERS[scenario_name]
        except KeyError as exc:  # pragma: no cover - defensive guardrail
            valid = ", ".join(sorted(SCENARIO_HANDLERS))
            raise ValueError(
                f"Unhandled scenario name: {scenario_name!r}. "
                f"Valid scenarios: {valid}"
            ) from exc
        handler()
        return

    raise ValueError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    main()
