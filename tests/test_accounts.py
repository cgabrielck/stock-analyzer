import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from accounts.models import UserPreferences
from accounts.repository import InMemoryAccountRepository, UsernameTakenError, normalize_username
from accounts.session import clear_account_state, current_context, hydrate_account_state, set_authenticated


def test_username_is_case_insensitive_but_preserves_display_case() -> None:
    repository = InMemoryAccountRepository()
    registered = repository.register("  Alice  ", "")

    user, result = repository.authenticate("ALICE", "")

    assert normalize_username("  ALIce ") == "alice"
    assert result == "ok"
    assert user == registered
    assert user.username == "Alice"


def test_login_distinguishes_missing_username_and_incorrect_pin() -> None:
    repository = InMemoryAccountRepository()
    repository.register("alice", "123")

    assert repository.authenticate("missing", "123") == (None, "username_not_found")
    assert repository.authenticate("alice", "wrong") == (None, "incorrect_pin")


def test_duplicate_normalized_username_is_rejected() -> None:
    repository = InMemoryAccountRepository()
    repository.register("Alice", "1")

    try:
        repository.register(" alice ", "2")
    except UsernameTakenError:
        pass
    else:
        raise AssertionError("duplicate username was accepted")


def test_favorites_and_preferences_are_isolated_by_user() -> None:
    repository = InMemoryAccountRepository()
    alice = repository.register("alice", "1")
    bob = repository.register("bob", "2")
    repository.add_favorite(alice.id, "aapl")
    repository.add_favorite(alice.id, "AAPL")
    repository.add_favorite(bob.id, "NVDA")
    repository.save_preferences(alice.id, UserPreferences(language="en", portfolio_capital=250_000))

    assert repository.list_favorites(alice.id) == ["AAPL"]
    assert repository.list_favorites(bob.id) == ["NVDA"]
    assert repository.get_preferences(alice.id).portfolio_capital == 250_000
    assert repository.get_preferences(bob.id) == UserPreferences()


def test_account_hydration_and_clear_do_not_leak_user_state() -> None:
    repository = InMemoryAccountRepository()
    user = repository.register("alice", "pin")
    repository.add_favorite(user.id, "MU")
    repository.save_preferences(
        user.id,
        UserPreferences(language="en", portfolio_capital=500_000, risk_budget_pct=2.0, include_ai_news=False),
    )
    state = {}
    token = repository.create_session(user.id)

    set_authenticated(state, user.id, user.username, token)
    hydrate_account_state(state, repository)

    assert current_context(state).user == user
    assert state["account_favorites"] == ["MU"]
    assert state["lang"] == "en"
    assert state["picks_account_capital"] == 500_000
    assert state["picks_risk_budget_pct"] == 2.0
    assert state["picks_news_include_ai"] is False

    clear_account_state(state)

    assert not current_context(state).is_authenticated
    assert "account_favorites" not in state
    assert state["picks_account_capital"] == 100_000
    assert state["picks_risk_budget_pct"] == 1.0


def test_session_revocation_removes_access() -> None:
    repository = InMemoryAccountRepository()
    user = repository.register("alice", "pin")
    token = repository.create_session(user.id)

    assert repository.get_session_user(token) == user
    repository.revoke_session(token)
    assert repository.get_session_user(token) is None
