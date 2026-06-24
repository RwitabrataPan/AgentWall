import pytest
import tempfile
import shutil
from pathlib import Path
from agentwall.storage.database import Database


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="agentwall_test_")
    d = Database(path=Path(tmpdir) / "test.db")
    yield d
    d.close()
    shutil.rmtree(tmpdir, ignore_errors=True)
