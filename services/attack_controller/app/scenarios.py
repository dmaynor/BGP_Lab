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

"""Scenario registry abstractions."""

from dataclasses import dataclass
from typing import Dict, Iterable, Optional


@dataclass
class Scenario:
    name: str
    description: str
    orchestrator_entrypoint: str


class ScenarioRegistry:
    """In-memory registry backed by lab_config.yaml data."""

    def __init__(self, scenarios: Dict[str, Dict]) -> None:
        self._registry = {
            name: Scenario(
                name=name,
                description=value.get("description", ""),
                orchestrator_entrypoint=value.get("orchestrator_entrypoint", name),
            )
            for name, value in scenarios.items()
        }

    def list(self) -> Iterable[Scenario]:
        return self._registry.values()

    def get(self, name: str) -> Optional[Scenario]:
        return self._registry.get(name)
