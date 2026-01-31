import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for src in ROOT.glob('apps/*/src'):
    if src.is_dir():
        sys.path.insert(0, str(src))
