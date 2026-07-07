import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
for src in ROOT.glob("libs/*/src"):
    if src.is_dir():
        sys.path.insert(0, str(src))
for src in ROOT.glob("apps/*/src"):
    if src.is_dir():
        sys.path.insert(0, str(src))


@pytest.fixture(params=["asyncio"])
def anyio_backend():
    return "asyncio"
