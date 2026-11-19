import uuid

import pytest

from tus_koc.coach import Koc
from tus_koc.db import DB
from tus_koc.search import IndeksOnbellegi
from tus_koc.vault import Vault


@pytest.fixture
def koc(tmp_path):
    db = DB(tmp_path / "db.sqlite3")
    user_id = db.kullanici_olustur(f"{uuid.uuid4().hex[:6]}@ornek.com", "gizli-sifre")
    return Koc(Vault(tmp_path / "vaults", user_id), db, IndeksOnbellegi())
