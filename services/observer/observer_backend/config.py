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
        self.topology_metadata_path = os.getenv("TOPOLOGY_METADATA_PATH", "/lab/topology-metadata.json")
