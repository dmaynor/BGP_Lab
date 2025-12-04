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
Shutdown and optionally purge the BGP lab environment.

This script wraps:
    docker compose down
    docker compose down --rmi all
    docker system prune

Modes:
    python3 stop_lab.py
        - Normal shutdown: stops containers, removes lab networks.

    python3 stop_lab.py --purge
        - Removes containers, networks, and FRR images used only by this lab.

    python3 stop_lab.py --nuke
        - Full wipe: purge + system prune (volumes, networks, unused images).

Author: Violator Actual
"""

import argparse
import os
import subprocess
import sys
from typing import List, Tuple

DOCKER = ["docker"]  # Change to ["sudo", "docker"] if desired


def run_command(cmd: List[str]) -> Tuple[int, str, str]:
    """Run a shell command and return (exit_code, stdout, stderr)."""
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        return p.returncode, p.stdout, p.stderr
    except OSError as exc:
        raise RuntimeError(f"OS error running command: {cmd}") from exc


def ensure_dir() -> None:
    """Change into the script directory so docker compose runs relative to it."""
    os.chdir(os.path.dirname(os.path.abspath(__file__)))


def shutdown() -> None:
    """Stop containers and remove lab networks."""
    print("[*] Stopping lab: docker compose down")
    code, out, err = run_command(DOCKER + ["compose", "down"])
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    if code != 0:
        raise RuntimeError(f"docker compose down failed ({code})")
    print("[+] Lab containers and networks stopped.")


def purge_images() -> None:
    """Remove FRR images used by lab."""
    print("[*] Purging images used by lab (docker compose down --rmi all)")
    code, out, err = run_command(
        DOCKER + ["compose", "down", "--rmi", "all"]
    )
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    if code != 0:
        raise RuntimeError(f"docker compose purge failed ({code})")
    print("[+] Images purged.")


def nuke_system() -> None:
    """Full system prune."""
    print("[*] Nuclear wipe: docker system prune -af --volumes")
    code, out, err = run_command(
        DOCKER + ["system", "prune", "-af", "--volumes"]
    )
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    if code != 0:
        raise RuntimeError(f"docker system prune failed ({code})")
    print("[+] System prune complete.")


def parse_args() -> argparse.Namespace:
    """Parse CLI options."""
    parser = argparse.ArgumentParser(
        description="Shutdown and optionally purge BGP lab artifacts."
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Remove containers, networks, and images."
    )
    parser.add_argument(
        "--nuke",
        action="store_true",
        help="Full wipe: purge + prune (volumes, networks, unused images)."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_dir()

    if args.nuke:
        shutdown()
        purge_images()
        nuke_system()
        print("[✓] Lab fully wiped (nuclear).")
        return

    if args.purge:
        shutdown()
        purge_images()
        print("[✓] Lab purged (containers, networks, images).")
        return

    # Default: gentle shutdown
    shutdown()
    print("[✓] Lab shut down cleanly.")


if __name__ == "__main__":
    main()

