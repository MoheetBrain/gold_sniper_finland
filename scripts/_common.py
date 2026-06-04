"""
Shared helpers for the GeoArb_Finland Step 1 pipeline.

Keeps config loading, path resolution and logging in one place so the numbered
scripts stay focused on their actual job. Nothing here is geology-specific.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

import yaml

# Repo root = parent of the scripts/ folder, resolved so scripts work from anywhere.
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "configs" / "config.yaml"

# Standard project CRS — every spatial output must end up in this.
PROJECT_CRS = "EPSG:3067"  # ETRS89 / TM35FIN


def get_logger(name: str) -> logging.Logger:
    """Return a console logger with a readable, consistent format."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                              datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def load_config(config_path: str | Path | None = None) -> dict:
    """Load configs/config.yaml (or an explicit path) and fail loudly if missing."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found at {path}. Expected configs/config.yaml in the repo."
        )
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config at {path} did not parse to a mapping.")
    return cfg


def resolve_path(rel_or_abs: str | Path) -> Path:
    """Resolve a config path against the repo root (absolute paths pass through)."""
    p = Path(rel_or_abs)
    return p if p.is_absolute() else (REPO_ROOT / p)


def ensure_dir(path: str | Path) -> Path:
    """Create a directory (and parents) if needed; return it as a Path."""
    p = resolve_path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def import_script(module_file: str, name: str | None = None):
    """
    Import a sibling pipeline script (whose name may start with a digit) by file.

    Lets one numbered script reuse another's tested functions without renaming.
    """
    scripts_dir = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        name or Path(module_file).stem, scripts_dir / module_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_path(cfg: dict, key: str, *, create: bool = False) -> Path:
    """Look up paths.<key> in config, resolve it, optionally create it."""
    try:
        rel = cfg["paths"][key]
    except KeyError as exc:
        raise KeyError(f"paths.{key} missing from config.yaml") from exc
    return ensure_dir(rel) if create else resolve_path(rel)
