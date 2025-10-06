"""
Shared utility functions for EvidentFit.

Common utilities used across agents, API, and other modules.

Usage:
    from evidentfit_shared.utils import PROJECT_ROOT
    
    # Use PROJECT_ROOT for all file paths
    data_dir = PROJECT_ROOT / "data" / "ingest" / "runs"
    logs_dir = PROJECT_ROOT / "logs"
"""

import os
from pathlib import Path


def get_project_root() -> Path:
    """
    Find the EvidentFit project root directory.
    
    Searches for the 'evidentfit' directory by walking up from the current file.
    Falls back to looking for .git or shared/ directory markers.
    Can be overridden with PROJECT_ROOT environment variable.
    
    Returns:
        Path: Absolute path to the project root directory
        
    Examples:
        >>> root = get_project_root()
        >>> data_dir = root / "data" / "ingest" / "runs"
        >>> logs_dir = root / "logs"
    """
    # Check for environment variable override
    if env_root := os.getenv("PROJECT_ROOT"):
        return Path(env_root).resolve()
    
    # Primary: Look for 'evidentfit' directory name
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if current.name == "evidentfit":
            return current
        current = current.parent
    
    # Fallback: Look for .git or shared/ directory markers
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() or (current / "shared").exists():
            return current
        current = current.parent
    
    # Last fallback: current working directory
    return Path.cwd()


# Singleton instance for consistent root across modules
PROJECT_ROOT = get_project_root()

