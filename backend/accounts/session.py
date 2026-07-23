from typing import Any, MutableMapping, Optional

from accounts.models import AuthContext, UserPreferences
from accounts.repository import AccountRepository


ACCOUNT_STATE_KEYS = (
    "account_user_id",
    "account_username",
    "account_session_token",
    "account_hydrated_user_id",
    "account_favorites",
)

ACCOUNT_PREFERENCE_DEFAULTS = {
    "portfolio_capital": 100_000,
    "picks_account_capital": 100_000,
    "picks_risk_budget_pct": 1.0,
    "picks_news_include_ai": True,
}


def current_context(state: MutableMapping[str, Any]) -> AuthContext:
    user_id = state.get("account_user_id")
    username = state.get("account_username")
    token = state.get("account_session_token")
    if not user_id or not username or not token:
        return AuthContext()
    from accounts.models import User
    return AuthContext(user=User(id=user_id, username=username), session_token=token)


def set_authenticated(state: MutableMapping[str, Any], user_id: str, username: str, token: str) -> None:
    clear_account_state(state)
    state["account_user_id"] = user_id
    state["account_username"] = username
    state["account_session_token"] = token


def clear_account_state(state: MutableMapping[str, Any]) -> None:
    for key in ACCOUNT_STATE_KEYS:
        state.pop(key, None)
    for key, value in ACCOUNT_PREFERENCE_DEFAULTS.items():
        state[key] = value


def hydrate_account_state(state: MutableMapping[str, Any], repository: AccountRepository) -> None:
    context = current_context(state)
    if not context.is_authenticated or state.get("account_hydrated_user_id") == context.user.id:
        return
    preferences = repository.get_preferences(context.user.id)
    state["account_favorites"] = repository.list_favorites(context.user.id)
    state["lang"] = preferences.language
    state["portfolio_capital"] = preferences.portfolio_capital
    state["picks_account_capital"] = preferences.portfolio_capital
    state["picks_risk_budget_pct"] = preferences.risk_budget_pct
    state["picks_news_include_ai"] = preferences.include_ai_news
    state["account_hydrated_user_id"] = context.user.id


def logout(state: MutableMapping[str, Any], repository: Optional[AccountRepository] = None) -> None:
    token = state.get("account_session_token")
    if token and repository is not None:
        repository.revoke_session(token)
    clear_account_state(state)
