"""Configuration helpers for the Observer service."""

import os
from pathlib import Path
from typing import Any, Dict

import yaml


class ObserverSettings:
    def __init__(self) -> None:
        self.attack_controller_url = os.getenv("ATTACK_CONTROLLER_URL", "http://attack_controller:9000")
        lab_config_path = os.getenv("LAB_CONFIG", "/lab/lab_config.yaml")
        with Path(lab_config_path).open("r", encoding="utf-8") as handle:
            self.lab_config: Dict[str, Any] = yaml.safe_load(handle)
