"""Wrapper around the legacy orchestrator.py script."""

import subprocess
from pathlib import Path


class OrchestratorClient:
    """Minimal shim that shells out to orchestrator.py."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path("/workspace/BGP_Lab")
        self._entrypoint = self.repo_root / "orchestrator.py"

    def run_scenario(self, entrypoint: str) -> subprocess.CompletedProcess[str]:
        cmd = ["python3", str(self._entrypoint), "scenario", entrypoint]
        return subprocess.run(cmd, capture_output=True, text=True, check=False)
