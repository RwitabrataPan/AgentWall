import os
import pytest
import tempfile
import shutil
from pathlib import Path

# Disable zero-config auto-instrumentation so tests can use protect_* explicitly
# without auto-mode wrapping tools first and making idempotency checks misfire.
os.environ["AGENTWALL_AUTO"] = "0"

from agentwall.storage.database import Database


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="agentwall_test_")
    d = Database(path=Path(tmpdir) / "test.db")
    yield d
    d.close()
    shutil.rmtree(tmpdir, ignore_errors=True)
