from __future__ import annotations

from pathlib import Path
from typing import List, Optional


class AppPaths:
    """
    Program-level standard directory paths relative to the repository root.
    Call AppPaths.init(root) once at application startup (from main.py).
    All directories are created on first access via ensure_dirs().
    """

    _root: Optional[Path] = None

    @classmethod
    def init(cls, root: Path) -> None:
        """Initialise with the repository root directory. Called once from main.py."""
        cls._root = Path(root).resolve()
        cls.ensure_dirs()

    @classmethod
    def _require_root(cls) -> Path:
        if cls._root is None:
            raise RuntimeError("AppPaths.init() has not been called")
        return cls._root

    # ── Standard directory properties ────────────────────────────────────────

    @classmethod
    @property
    def root(cls) -> Path:
        return cls._require_root()

    @classmethod
    @property
    def scripts_dir(cls) -> Path:
        return cls._require_root() / "scripts"

    @classmethod
    @property
    def models_dir(cls) -> Path:
        return cls._require_root() / "models"

    @classmethod
    @property
    def acquisition_configs_dir(cls) -> Path:
        return cls._require_root() / "configs" / "acquisition"

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create all standard directories if they don't exist (idempotent)."""
        for d in [
            cls.scripts_dir,
            cls.models_dir,
            cls.acquisition_configs_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    # ── Named resource helpers ────────────────────────────────────────────────

    @classmethod
    def list_acquisition_configs(cls) -> List[str]:
        return sorted(p.stem for p in cls.acquisition_configs_dir.glob("*.json"))

    @classmethod
    def list_scripts(cls) -> List[str]:
        return sorted(p.stem for p in cls.scripts_dir.glob("*.acq"))
