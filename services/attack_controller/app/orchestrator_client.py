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
