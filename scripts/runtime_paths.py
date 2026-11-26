"""Helpers for resolving project imports when a script runs by file path."""

import sys
from pathlib import Path


def ensure_project_root_on_path(script_file: str) -> Path:
    """Put the repository root first on ``sys.path`` and return it.

    When Python starts ``python scripts/cloud_launcher.py``, ``sys.path[0]`` is
    the scripts directory even if the launcher later changes its working
    directory. Add the project root explicitly so root modules such as
    ``config`` resolve consistently in Render and local runs.
    """
    project_root = Path(script_file).resolve().parent.parent
    root_string = str(project_root)
    if root_string in sys.path:
        sys.path.remove(root_string)
    sys.path.insert(0, root_string)
    return project_root
