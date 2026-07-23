from typing import Any, MutableMapping, Optional

import streamlit as st

from accounts.models import UserPreferences
from accounts.repository import AccountRepository, UsernameTakenError
from accounts.session import current_context, logout, set_authenticated
from i18n import t


def render_account_panel(
    repository: Optional[AccountRepository], lang: str, state: MutableMapping[str, Any]
) -> None:
    st.sidebar.markdown(
        f'<div class="sidebar-section">{t("account.title", lang)}</div>',
        unsafe_allow_html=True,
    )
    context = current_context(state)
    if context.is_authenticated:
        if repository is None:
            st.sidebar.error(t("account.not_configured", lang))
            return
        st.sidebar.caption(t("account.signed_in_as", lang, username=context.user.username))
        _render_favorites(repository, context.user.id, lang, state)
        if st.sidebar.button(t("account.save_preferences", lang), key="account_save_preferences", width="stretch"):
            repository.save_preferences(
                context.user.id,
                UserPreferences(
                    language=state.get("lang", "zh_tw"),
                    portfolio_capital=int(state.get("picks_account_capital", state.get("portfolio_capital", 100_000))),
                    risk_budget_pct=float(state.get("picks_risk_budget_pct", 1.0)),
                    include_ai_news=bool(state.get("picks_news_include_ai", True)),
                ),
            )
            st.sidebar.success(t("account.preferences_saved", lang))
        if st.sidebar.button(t("account.logout", lang), key="account_logout", width="stretch"):
            logout(state, repository)
            st.rerun()
        return

    if repository is None:
        st.sidebar.caption(t("account.not_configured", lang))
        return

    login_tab, register_tab = st.sidebar.tabs([t("account.login", lang), t("account.register", lang)])
    with login_tab:
        with st.form("account_login_form"):
            username = st.text_input(t("account.username", lang), key="account_login_username")
            pin = st.text_input(t("account.pin", lang), type="password", key="account_login_pin")
            submitted = st.form_submit_button(t("account.login", lang), width="stretch")
        if submitted:
            user, result = repository.authenticate(username, pin)
            if result == "username_not_found":
                st.error(t("account.username_not_found", lang))
            elif result == "incorrect_pin":
                st.error(t("account.incorrect_pin", lang))
            elif user:
                token = repository.create_session(user.id)
                set_authenticated(state, user.id, user.username, token)
                st.rerun()

    with register_tab:
        with st.form("account_register_form"):
            username = st.text_input(t("account.username", lang), key="account_register_username")
            pin = st.text_input(t("account.pin", lang), type="password", key="account_register_pin")
            submitted = st.form_submit_button(t("account.register", lang), width="stretch")
        if submitted:
            try:
                user = repository.register(username, pin)
            except UsernameTakenError:
                st.error(t("account.username_taken", lang))
            except ValueError:
                st.error(t("account.username_required", lang))
            else:
                token = repository.create_session(user.id)
                set_authenticated(state, user.id, user.username, token)
                st.rerun()


def _render_favorites(
    repository: AccountRepository, user_id: str, lang: str, state: MutableMapping[str, Any]
) -> None:
    favorites = list(state.get("account_favorites", []))
    with st.sidebar.expander(t("favorites.title", lang), expanded=bool(favorites)):
        ticker = st.text_input(
            t("favorites.ticker", lang), key="account_favorite_ticker",
            placeholder="AAPL", label_visibility="collapsed",
        )
        if st.button(t("favorites.add", lang), key="account_favorite_add", width="stretch"):
            repository.add_favorite(user_id, ticker)
            state["account_favorites"] = repository.list_favorites(user_id)
            st.rerun()
        if not favorites:
            st.caption(t("favorites.empty", lang))
        for symbol in favorites:
            label, action = st.columns([4, 1])
            label.code(symbol)
            if action.button("×", key=f"account_favorite_remove_{symbol}"):
                repository.remove_favorite(user_id, symbol)
                state["account_favorites"] = repository.list_favorites(user_id)
                st.rerun()
