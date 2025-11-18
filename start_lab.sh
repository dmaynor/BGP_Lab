#!/usr/bin/env python3
"""
Start the BGP lab Docker stack and show basic status.

This script is a thin wrapper around:

    docker compose up -d
    docker compose ps

It assumes:
    - The docker-compose.yml file lives in the same directory
      as this script.
    - Docker and the docker compose plugin are installed and
      available in the current $PATH.

Usage:
    python3 start_lab.py
    ./start_lab.py
"""

import os
import subprocess
import sys
from typing import List, Tuple


def run_command(command: List[str]) -> Tuple[int, str, str]:
    """
    Run a shell command and capture its output.

    Args:
        command:
            Command and arguments as a list of strings.

    Returns:
        A tuple of (exit_code, stdout, stderr).

    Raises:
        RuntimeError:
            If the subprocess invocation fails in an unexpected way,
            such as an OS-level error during process creation.
    """
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


def ensure_repo_directory() -> None:
    """
    Change the current working directory to the script's directory.

    This ensures that docker compose is run from the directory that
    contains docker-compose.yml regardless of where the user
    launches this script from.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)


def start_docker_stack() -> None:
    """
    Start the BGP lab Docker stack using docker compose.

    This function calls:

        docker compose up -d

    If the command fails, an exception is raised with the captured
    output for easier troubleshooting.
    """
    print("[*] Starting BGP lab containers with 'docker compose up -d'...")
    exit_code, stdout, stderr = run_command(
        ["docker", "compose", "up", "-d"]
    )

    if stdout:
        print(stdout, end="")
    if stderr:
        # docker compose can emit non-fatal warnings on stderr.
        print(stderr, file=sys.stderr, end="")

    if exit_code != 0:
        raise RuntimeError(
            f"'docker compose up -d' failed with exit code {exit_code}."
        )

    print("[+] Docker stack started.")


def show_container_status() -> None:
    """
    Display the current status of the lab containers.

    This function runs:

        docker compose ps

    and prints the output so the user can confirm that r1, r2, and r3
    are in the 'running' state.
    """
    print("[*] Showing container status with 'docker compose ps'...")
    exit_code, stdout, stderr = run_command(
        ["docker", "compose", "ps"]
    )

    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, file=sys.stderr, end="")

    if exit_code != 0:
        raise RuntimeError(
            f"'docker compose ps' failed with exit code {exit_code}."
        )


def main() -> None:
    """
    Main entry point for the start_lab script.

    Steps:
        1. Change directory to the script location.
        2. Start the docker compose stack.
        3. Show container status.
    """
    try:
        ensure_repo_directory()
        start_docker_stack()
        show_container_status()
        print(
            "[+] Lab startup complete. You can now use orchestrator.py "
            "to set scenarios, and exec into the routers as needed."
        )
    except RuntimeError as exc:
        print(f"[!] Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

