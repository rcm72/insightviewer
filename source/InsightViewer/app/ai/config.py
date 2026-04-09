from __future__ import annotations

import configparser
import os
from pathlib import Path


def project_root() -> Path:
    # app/ai/config.py -> app/ai -> app -> project root
    return Path(__file__).resolve().parents[2]


def load_config() -> configparser.ConfigParser:
    """
    Mirrors the app's config behavior but stays self-contained.
    Preference order:
    - BASE_DIR env var (if set) as root
    - repository root (two levels up from app/)
    - config_private.ini if present, else config.ini
    """
    cfg = configparser.ConfigParser()
    base_dir = Path(os.getenv("BASE_DIR") or project_root())
    private_cfg = base_dir / "config_private.ini"
    default_cfg = base_dir / "config.ini"
    path = private_cfg if private_cfg.exists() else default_cfg
    cfg.read(str(path))
    return cfg

