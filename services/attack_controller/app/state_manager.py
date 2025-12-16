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

"""State manager for attack controller service.

This module provides thread-safe and multi-worker safe state management
by persisting state to a file instead of using global variables.
"""

import json
import os
from pathlib import Path
from typing import Any


class StateManager:
    """Manages application state with file-based persistence.

    This implementation uses atomic file writes to ensure data integrity
    and is safe to use across multiple worker processes.
    """

    def __init__(self, state_file: str = "/tmp/bgp_attack_controller_state.json"):
        """Initialize the state manager.

        Args:
            state_file: Path to the state file. Defaults to /tmp location.
        """
        self.state_file = Path(state_file)
        self._ensure_state_file()

    def _ensure_state_file(self) -> None:
        """Ensure the state file exists with default values."""
        if not self.state_file.exists():
            default_state = {"active_scenario": "normal"}
            self._write_state(default_state)

    def _read_state(self) -> dict[str, Any]:
        """Read the current state from file.

        Returns:
            Dictionary containing the current state.
        """
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Return default state if file doesn't exist or is corrupted
            default_state = {"active_scenario": "normal"}
            self._write_state(default_state)
            return default_state

    def _write_state(self, state: dict[str, Any]) -> None:
        """Write state to file atomically.

        Uses atomic write pattern (write to temp file, then rename) to
        prevent corruption from concurrent writes.

        Args:
            state: State dictionary to write.
        """
        temp_file = self.state_file.with_suffix(".tmp")
        try:
            # Write to temporary file
            with open(temp_file, "w") as f:
                json.dump(state, f, indent=2)
            # Atomic rename (overwrites existing file)
            temp_file.replace(self.state_file)
        except Exception as e:
            # Clean up temp file if write failed
            if temp_file.exists():
                temp_file.unlink()
            raise e

    def get_active_scenario(self) -> str:
        """Get the currently active scenario.

        Returns:
            Name of the active scenario.
        """
        state = self._read_state()
        return state.get("active_scenario", "normal")

    def set_active_scenario(self, scenario_name: str) -> None:
        """Set the active scenario.

        Args:
            scenario_name: Name of the scenario to activate.
        """
        state = self._read_state()
        state["active_scenario"] = scenario_name
        self._write_state(state)
