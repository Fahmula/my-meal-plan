import io
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="mealplan-test-")
os.environ["DATA_DIR"] = _tmp
os.environ["SCHEDULER_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app import config, db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
    for f in config.UPLOAD_DIR.glob("*"):
        f.unlink()
    db.init_db()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def png_bytes():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (220, 120, 80)).save(buf, "PNG")
    return buf.getvalue()
