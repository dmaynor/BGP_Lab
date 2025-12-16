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
BGP scenario executor using Docker SDK.

This module controls a multi-AS FRR BGP lab running in Docker.
Scenarios are intentionally simple and deterministic so they can be
triggered safely from the Attack Controller and visualised by the
Observer UI.
"""

from __future__ import annotations

import itertools
from typing import Callable, Dict, Iterable, List

from app.docker_client import DockerClient


class ScenariosExecutor:
    """Execute BGP attack scenarios using the Docker SDK."""

    def __init__(self, docker_client: DockerClient | None = None) -> None:
        """Initialize the scenarios executor.

        Parameters
        ----------
        docker_client:
            Optional DockerClient instance. If not provided, creates a new one.
        """
        self.docker = docker_client or DockerClient()

    def _build_vtysh_command(self, commands: Iterable[str]) -> List[str]:
        """Construct a vtysh invocation for a set of configuration commands.

        The commands are passed using repeated -c flags.

        Parameters
        ----------
        commands:
            Iterable of configuration commands to feed into vtysh.

        Returns
        -------
        list[str]
            The full command line suitable for container.exec_run().
        """
        base_cmd: List[str] = ["vtysh"]
        vty_args: List[str] = list(
            itertools.chain.from_iterable(("-c", cmd) for cmd in commands)
        )
        return base_cmd + vty_args

    def vtysh_bgp_config(
        self, container: str, bgp_asn: int, commands: List[str]
    ) -> None:
        """Apply BGP configuration commands to a router using vtysh.

        This helper drops into BGP IPv4 unicast configuration mode and runs
        the given commands. It then writes the FRR configuration to disk.

        Parameters
        ----------
        container:
            Docker container name (for example, "r3").
        bgp_asn:
            The BGP ASN of the router being configured.
        commands:
            A list of commands to execute inside
            router bgp <asn> -> address-family ipv4 unicast.

        Raises
        ------
        RuntimeError
            If the underlying vtysh invocation fails.
        """
        vty_commands: List[str] = [
            "configure terminal",
            f"router bgp {bgp_asn}",
            "address-family ipv4 unicast",
            *commands,
            "exit-address-family",
            "end",
        ]
        full_cmd = self._build_vtysh_command(vty_commands)
        exit_code, output = self.docker.exec_in_container(container, full_cmd)

        # Ignore benign errors from cleanup commands (removing non-existent config)
        benign_errors = [
            "Can't find",
            "Refusing to remove",
            "Can't open configuration file /etc/frr/vtysh.conf",
        ]
        if exit_code != 0 and not any(err in output for err in benign_errors):
            raise RuntimeError(
                f"Failed to apply BGP configuration on {container}\n"
                f"output:\n{output}"
            )

    def vtysh_global_config(self, container: str, commands: List[str]) -> None:
        """Apply global FRR configuration commands using vtysh.

        This helper runs the provided commands from configure terminal
        mode without entering any protocol-specific submodes.

        Parameters
        ----------
        container:
            Docker container name.
        commands:
            A list of configuration-mode commands (no end or
            write memory required).

        Raises
        ------
        RuntimeError
            If vtysh returns a non-zero exit code.
        """
        if not commands:
            return

        vty_commands: List[str] = [
            "configure terminal",
            *commands,
            "end",
        ]
        full_cmd = self._build_vtysh_command(vty_commands)
        exit_code, output = self.docker.exec_in_container(container, full_cmd)

        # Ignore benign errors from cleanup commands (removing non-existent config)
        benign_errors = [
            "Can't find static route",
            "Refusing to remove a non-existent",
            "Can't open configuration file /etc/frr/vtysh.conf",
        ]
        if exit_code != 0 and not any(err in output for err in benign_errors):
            raise RuntimeError(
                f"Failed to apply global configuration on {container}\n"
                f"output:\n{output}"
            )

    def scenario_normal(self) -> None:
        """Configure the lab in the baseline "normal" state.

        * Attacker (r3) advertises only its own prefix 10.20.3.0/24.
        * Any stray hijack/leak/blackhole artefacts from previous scenarios
          are cleaned up as best-effort.
        """
        print("[*] Setting scenario: normal (no hijack)")
        # Best-effort cleanup of advanced scenarios (safe even if not set).
        self.vtysh_global_config(
            container="r3",
            commands=[
                "no route-map ASPATH-FORGE permit 10",
                "no ip route 10.10.1.0/24 Null0",
                "no ip route 0.0.0.0/0 10.0.0.10",
            ],
        )
        self.vtysh_global_config(
            container="r2",
            commands=[
                "no ip route 10.10.1.0/24 10.0.0.2",
                "no ip route 10.20.3.0/24 10.0.0.11",
            ],
        )
        self.vtysh_bgp_config(
            container="r3",
            bgp_asn=65003,
            commands=[
                "no neighbor 10.0.0.10 route-map ASPATH-FORGE out",
                "no network 10.10.1.0/24",
                "no network 10.10.1.128/25",
                "network 10.20.3.0/24",
            ],
        )
        self.vtysh_bgp_config(
            container="r2",
            bgp_asn=65002,
            commands=[
                "no network 10.10.1.0/24",
                "no network 10.20.3.0/24",
            ],
        )
        print("[+] Scenario 'normal' applied.")

    def scenario_hijack(self) -> None:
        """Configure a classic prefix-hijack scenario.

        The attacker (r3) originates the victim's prefix
        10.10.1.0/24 in addition to its own prefix.
        """
        print("[*] Setting scenario: hijack (attacker announces 10.10.1.0/24)")
        # Cleanup previous scenario configs by resetting to normal
        self.scenario_normal()
        # Add static route for the hijacked prefix so BGP can originate it
        self.vtysh_global_config(
            container="r3",
            commands=["ip route 10.10.1.0/24 Null0"],
        )
        # Apply the hijack configuration
        self.vtysh_bgp_config(
            container="r3",
            bgp_asn=65003,
            commands=[
                "network 10.20.3.0/24",
                "network 10.10.1.0/24",
            ],
        )
        print("[+] Scenario 'hijack' applied.")

    def scenario_more_specific(self) -> None:
        """Configure a more-specific prefix-hijack scenario.

        The attacker (r3) advertises a subprefix 10.10.1.128/25 of
        the victim's 10.10.1.0/24 block. Longest-prefix match causes
        traffic destined for the subprefix to favour the attacker.
        """
        print(
            "[*] Setting scenario: more-specific hijack "
            "(attacker announces 10.10.1.128/25)"
        )
        # Cleanup previous scenario configs by resetting to normal
        self.scenario_normal()
        # Add static route for the more-specific hijacked prefix
        self.vtysh_global_config(
            container="r3",
            commands=["ip route 10.10.1.128/25 Null0"],
        )
        self.vtysh_bgp_config(
            container="r3",
            bgp_asn=65003,
            commands=[
                "network 10.20.3.0/24",
                "network 10.10.1.128/25",
            ],
        )
        print("[+] Scenario 'more-specific' applied.")

    def scenario_leak(self) -> None:
        """Configure a simple route-leak style scenario.

        In this demonstration:

        * The transit AS (r2, ASN 65002) re-originates both edge
          prefixes (victim and attacker) using static routes plus
          network statements.
        * This is a stylised, contained example to show how a transit AS
          leaking prefixes can create alternative origins for the same
          address space.
        """
        print("[*] Setting scenario: route leak (transit re-originates both edges)")
        # Cleanup previous scenario configs by resetting to normal
        self.scenario_normal()
        # Static routes on the transit so it can legitimately originate both
        # prefixes via BGP.
        self.vtysh_global_config(
            container="r2",
            commands=[
                "ip route 10.10.1.0/24 10.0.0.2",
                "ip route 10.20.3.0/24 10.0.0.11",
            ],
        )
        self.vtysh_bgp_config(
            container="r2",
            bgp_asn=65002,
            commands=[
                "network 10.10.1.0/24",
                "network 10.20.3.0/24",
            ],
        )
        print("[+] Scenario 'leak' applied.")

    def scenario_aspath(self) -> None:
        """Configure an AS-PATH forgery style hijack scenario.

        This scenario builds on the basic origin hijack but also attaches a
        forged AS-PATH so that, from the outside, the attacker can appear
        more legitimate (for example, by prepending the victim ASN).

        Implementation notes
        --------------------
        * A simple route-map ASPATH-FORGE is installed on r3.
        * The route-map prepends 65001 65001 to outbound announcements.
        * The victim prefix 10.10.1.0/24 is originated from r3.
        """
        print("[*] Setting scenario: AS-PATH forgery hijack")
        # Cleanup previous scenario configs by resetting to normal
        self.scenario_normal()
        # Add static route for the hijacked prefix
        self.vtysh_global_config(
            container="r3",
            commands=["ip route 10.10.1.0/24 Null0"],
        )
        # Install / refresh the route-map.
        self.vtysh_global_config(
            container="r3",
            commands=[
                "no route-map ASPATH-FORGE permit 10",
                "route-map ASPATH-FORGE permit 10",
                " set as-path prepend 65001 65001",
            ],
        )
        self.vtysh_bgp_config(
            container="r3",
            bgp_asn=65003,
            commands=[
                "network 10.20.3.0/24",
                "network 10.10.1.0/24",
                "neighbor 10.0.0.10 route-map ASPATH-FORGE out",
            ],
        )
        print("[+] Scenario 'aspath' applied.")

    def scenario_blackhole(self) -> None:
        """Configure a remotely triggered blackhole (RTBH) style scenario.

        The attacker advertises the victim prefix 10.10.1.0/24 but
        installs a static route to Null0 so that traffic sent towards the
        hijacked prefix is discarded once it reaches the attacker.

        This models the *effect* of RTBH in a minimal way suitable for this
        router lab.
        """
        print("[*] Setting scenario: blackhole (RTBH-style for 10.10.1.0/24)")
        # Cleanup previous scenario configs by resetting to normal
        self.scenario_normal()
        # Ensure the static blackhole route exists on the attacker.
        self.vtysh_global_config(
            container="r3",
            commands=["ip route 10.10.1.0/24 Null0"],
        )
        self.vtysh_bgp_config(
            container="r3",
            bgp_asn=65003,
            commands=[
                "network 10.20.3.0/24",
                "network 10.10.1.0/24",
            ],
        )
        print("[+] Scenario 'blackhole' applied.")

    def run_scenario(self, scenario_name: str) -> None:
        """Execute a named scenario.

        Parameters
        ----------
        scenario_name:
            The name of the scenario to run (normal, hijack, more-specific,
            leak, aspath, blackhole).

        Raises
        ------
        ValueError
            If the scenario name is not recognized.
        """
        scenario_handlers: Dict[str, Callable[[], None]] = {
            "normal": self.scenario_normal,
            "hijack": self.scenario_hijack,
            "more-specific": self.scenario_more_specific,
            "leak": self.scenario_leak,
            "aspath": self.scenario_aspath,
            "blackhole": self.scenario_blackhole,
        }

        try:
            handler = scenario_handlers[scenario_name]
        except KeyError as exc:
            valid = ", ".join(sorted(scenario_handlers))
            raise ValueError(
                f"Unhandled scenario name: {scenario_name!r}. "
                f"Valid scenarios: {valid}"
            ) from exc

        handler()
