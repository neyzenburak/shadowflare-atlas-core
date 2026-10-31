"""Explicit build context; never falls back to a developer directory."""
import os
from pathlib import Path

WORK=Path(os.environ['ATLAS_BUILD_WORK']).resolve()
GAME=Path(os.environ['ATLAS_GAME_ROOT']).resolve()
OUTPUT=Path(os.environ['ATLAS_BUILD_OUTPUT']).resolve()
