import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from config import get_account_settings, normalize_supabase_url


def test_supabase_project_ref_expands_to_full_url() -> None:
    assert normalize_supabase_url("abcdefghijk") == "https://abcdefghijk.supabase.co"


def test_full_supabase_url_is_preserved_without_trailing_slash() -> None:
    assert normalize_supabase_url(" https://abcdefghijk.supabase.co/ ") == "https://abcdefghijk.supabase.co"


def test_empty_supabase_url_is_disabled() -> None:
    assert normalize_supabase_url("") is None


def test_account_settings_load_project_env_file() -> None:
    settings = get_account_settings()
    assert settings.supabase_url is None or settings.supabase_url.startswith("https://")
