"""Exam profiles are data files: each needs a valid front matter, and the vault gets a mirror of them."""
from coach.vault import EXAMS_DIR, EXAMS_TARGET_DIR, _front_matter, exam_profile, exam_profiles

KEYS = ("id", "name", "full_name", "country", "group", "aliases", "organizer", "official_url", "last_checked")
GROUPS = {"medical", "university-entrance", "public-service", "language", "graduate-admission", "professional",
          "school"}


def test_every_profile_is_complete():
    files = [p for p in EXAMS_DIR.glob("*.md") if p.name != "README.md"]
    assert files
    for path in files:
        meta = _front_matter(path.read_text(encoding="utf-8"))
        assert all(meta.get(k) for k in KEYS), (path.name, [k for k in KEYS if not meta.get(k)])
        assert meta["id"] == path.stem
        assert meta["group"] in GROUPS
        assert isinstance(meta["aliases"], list)
    assert {p["id"] for p in exam_profiles()} == {p.stem for p in files}


def test_lookup_is_case_insensitive_and_rejects_unknown():
    assert exam_profile(" TUS ").startswith("---")
    try:
        exam_profile("../SKILL")
    except Exception as e:
        assert "No built-in profile" in str(e)
    else:
        raise AssertionError("unknown id must fail")


def test_skill_folder_is_mirrored_into_the_vault(tmp_path):
    from coach.vault import Vault
    v = Vault(tmp_path / "v", tmp_path / "s", "0" * 32)
    v.vault.mkdir(parents=True)
    stale = v.vault / EXAMS_TARGET_DIR / "old-exam.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("gone")
    v._place_skill()
    assert (v.vault / EXAMS_TARGET_DIR / "tus.md").is_file()
    assert not stale.exists()
