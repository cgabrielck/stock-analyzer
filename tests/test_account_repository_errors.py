import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from accounts.repository import AccountStorageError, SupabaseAccountRepository


class Response:
    ok = False
    content = b"error"

    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_ambiguous_rpc_error_requests_migration_update(monkeypatch) -> None:
    repository = SupabaseAccountRepository("https://test.supabase.co", "secret")
    monkeypatch.setattr(
        repository.session, "request",
        lambda *args, **kwargs: Response(400, {"code": "42702", "message": 'column reference "ticker" is ambiguous'}),
    )

    with pytest.raises(AccountStorageError) as error:
        repository._request("POST", "rpc/save_saved_plan_version", json={})

    assert error.value.code == "migration_update_required"


def test_missing_rpc_requests_migration_install(monkeypatch) -> None:
    repository = SupabaseAccountRepository("https://test.supabase.co", "secret")
    monkeypatch.setattr(
        repository.session, "request",
        lambda *args, **kwargs: Response(404, {"code": "PGRST202", "message": "function not found"}),
    )

    with pytest.raises(AccountStorageError) as error:
        repository._request("POST", "rpc/save_saved_plan_version", json={})

    assert error.value.code == "migration_required"
