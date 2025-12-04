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
Show IP assignments of BGP lab containers and their BGP session status.

This script reports:

    - Docker-assigned interface IPs for r1 / r2 / r3
    - BGP session summary for each router:
        vtysh -c "show ip bgp summary"

Assumes:
    - docker-compose.yml defines services: r1, r2, r3
    - FRR is running and vtysh is available inside containers
"""

import subprocess
import sys
from typing import List, Tuple, Dict


ROUTERS = ("r1", "r2", "r3")


def run(cmd: List[str]) -> Tuple[int, str, str]:
    """Run a shell command and capture exit code, stdout, stderr."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def docker_ip(container: str) -> Dict[str, str]:
    """
    Return all network names → IPs for a container using:
        docker inspect -f '{{json .NetworkSettings.Networks}}'
    """

    code, out, err = run(
        ["docker", "inspect", "-f",
         "{{json .NetworkSettings.Networks}}", container]
    )
    if code != 0:
        return {"error": err or "unable to inspect"}

    try:
        import json
        nets = json.loads(out)
    except Exception:
        return {"error": "parse-error"}

    results = {}
    for net_name, cfg in nets.items():
        ip = cfg.get("IPAddress", "")
        results[net_name] = ip
    return results


def bgp_summary(container: str) -> str:
    """
    Run FRR BGP summary inside a router:

        vtysh -c "show ip bgp summary"
    """
    code, out, err = run(
        ["docker", "compose", "exec", "-T",
         container, "vtysh", "-c", "show ip bgp summary"]
    )

    if code != 0:
        return f"[ERROR running vtysh] {err}"

    return out


def main() -> None:
    print("=== BGP LAB STATUS ===\n")

    for r in ROUTERS:
        print(f"--- {r.upper()} ---")

        # IP ADDRESSES
        print("IPs:")
        ips = docker_ip(f"bgp_{r}")
        if "error" in ips:
            print(f"  error: {ips['error']}")
        else:
            for net, ip in ips.items():
                print(f"  {net:20s} {ip}")

        # BGP SUMMARY
        print("\nBGP Sessions:")
        summary = bgp_summary(r)
        print(summary)
        print("\n")

    print("=== END ===")


if __name__ == "__main__":
    main()
