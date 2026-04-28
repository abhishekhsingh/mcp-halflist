import sys
from pathlib import Path

import pytest

SERVERS_DIR = Path(__file__).parent / "servers"


@pytest.fixture
def good_server_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'good_server.py'}"


@pytest.fixture
def bad_server_cmd() -> str:
    return f"{sys.executable} {SERVERS_DIR / 'bad_server.py'}"
