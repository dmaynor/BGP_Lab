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
