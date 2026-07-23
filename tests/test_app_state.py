import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from streamlit.testing.v1 import AppTest
import pandas as pd

import app as stock_app


APP_PATH = str(Path(__file__).resolve().parents[1] / "backend" / "app.py")


def test_app_exposes_monotonic_timer_for_progress() -> None:
    assert stock_app.time.monotonic() > 0


def test_primary_routes_render_without_exceptions() -> None:
    for route in ("home", "scan", "picks", "picks_news", "portfolio"):
        app = AppTest.from_file(APP_PATH, default_timeout=30)
        app.session_state["app_route"] = route

        app.run()

        assert not app.exception, route


def test_clear_picks_callback_clears_selection_and_results() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=30)
    app.session_state["app_route"] = "picks"
    app.session_state["picks_selection_widget"] = ["AAPL"]
    app.session_state["picks_results"] = {"AAPL": {"ticker": "AAPL"}}
    app.session_state["picks_analyzed_tickers"] = ["AAPL"]
    app.session_state["picks_successful_tickers"] = ["AAPL"]
    app.session_state["picks_recent_successful_tickers"] = ["AAPL"]
    app.run()

    clear_button = next(button for button in app.button if button.key == "picks_clear")
    clear_button.click().run()

    assert app.session_state["picks_selection_widget"] == []
    assert app.session_state["picks_results"] == {}
    assert app.session_state["picks_analyzed_tickers"] == []
    assert app.session_state["picks_successful_tickers"] == []
    assert app.session_state["picks_recent_successful_tickers"] == []


def test_legacy_news_and_portfolio_routes_open_deep_workspaces() -> None:
    for route, workspace in (("picks_news", "news"), ("portfolio", "portfolio")):
        app = AppTest.from_file(APP_PATH, default_timeout=30)
        app.session_state["app_route"] = route
        app.run()

        assert not app.exception
        assert app.session_state["app_route"] == "picks"
        assert app.session_state["deep_workspace"] == workspace


def test_home_has_three_tour_actions() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    button_keys = {button.key for button in app.button}

    assert {"landing_picks", "landing_scan", "landing_portfolio"} <= button_keys
    assert "route_picks_news" not in button_keys
    assert "route_portfolio" not in button_keys


def test_successful_deep_results_are_remembered_for_news() -> None:
    stock_app.st.session_state["picks_successful_tickers"] = ["MSFT"]
    stock_app.st.session_state["picks_recent_successful_tickers"] = ["MSFT"]
    stock_app.st.session_state["picks_news_selection_widget"] = []

    successful = stock_app._remember_successful_picks(
        ["AAPL", "NVDA"],
        {"AAPL": {"ticker": "AAPL"}, "NVDA": {"error": "timeout"}},
    )

    assert successful == ["AAPL"]
    assert stock_app.st.session_state["picks_successful_tickers"] == ["AAPL"]
    assert stock_app.st.session_state["picks_recent_successful_tickers"] == ["MSFT", "AAPL"]
    assert stock_app.st.session_state["picks_news_selection_widget"] == ["MSFT", "AAPL"]


def test_backtest_scope_uses_latest_analyzed_tickers_not_old_success_memory() -> None:
    stock_app.st.session_state["picks_analyzed_tickers"] = ["TSLA", "MU"]
    stock_app.st.session_state["picks_selection_widget"] = ["ASTS"]
    stock_app.st.session_state["picks_successful_tickers"] = ["MSFT"]

    assert stock_app._current_backtest_tickers() == ["TSLA", "MU"]


def test_backtest_request_signature_changes_with_ticker_scope() -> None:
    first = stock_app._backtest_request_signature(["AAPL"], "2023-01-01", "2026-01-01", False, "equal", 15)
    second = stock_app._backtest_request_signature(["NVDA"], "2023-01-01", "2026-01-01", False, "equal", 15)

    assert first != second


def test_tech_chart_builds_from_normalized_data_without_quote_lookup(monkeypatch) -> None:
    index = pd.date_range("2026-01-01", periods=80, freq="B", tz="America/New_York")
    history = pd.DataFrame({
        "Open": [100 + i * 0.1 for i in range(80)],
        "High": [101 + i * 0.1 for i in range(80)],
        "Low": [99 + i * 0.1 for i in range(80)],
        "Close": [100.5 + i * 0.1 for i in range(80)],
        "Volume": [1000 + i for i in range(80)],
    }, index=index)
    monkeypatch.setattr(
        "utils.chart_utils.fetch_chart_data",
        lambda *args, **kwargs: {"data": history, "provider": "test", "interval": "1d", "period": "1y"},
    )

    result = stock_app._build_tech_chart("TEST", current_price=1000)

    assert "error" not in result
    assert result["rows"] == 80
    assert result["figure"].data[0].type == "candlestick"
    assert all(shape.y0 != 1000 for shape in result["figure"].layout.shapes)
    assert all("$1000.00" not in str(annotation.text) for annotation in result["figure"].layout.annotations)
