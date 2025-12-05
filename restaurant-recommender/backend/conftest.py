import sys
from pathlib import Path


# Ensure backend/src is on sys.path for tests so that imports like `services.*` and `src.*` work.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
