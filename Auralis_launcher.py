from __future__ import annotations

import os
import sys
from pathlib import Path


if getattr(sys, "frozen", False):
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    os.environ["PATH"] = str(bundle_dir) + os.pathsep + os.environ.get("PATH", "")


import Auralis  # noqa: E402


Auralis.DEFAULT_OUTPUT_DIR = Path.home() / "Music" / "Auralis Output"


if __name__ == "__main__":
    raise SystemExit(Auralis.main())
