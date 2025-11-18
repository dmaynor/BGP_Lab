"""Lightweight helpers for PCAP inspection."""

from pathlib import Path
from typing import List


def list_pcaps(base_path: Path) -> List[Path]:
    return sorted(base_path.glob("*.pcap"))
