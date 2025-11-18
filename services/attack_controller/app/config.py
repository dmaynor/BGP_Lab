"""Settings helpers for the attack controller service."""

from pathlib import Path
from typing import Any, Dict

import yaml


class LabSettings:
    """Loads data shared across attack-controller components."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or Path("/lab/lab_config.yaml")
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        with self.config_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    @property
    def scenarios(self) -> Dict[str, Any]:
        return self._data.get("scenarios", {})

    def refresh(self) -> None:
        self._data = self._load()
