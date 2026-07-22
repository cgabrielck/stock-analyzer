import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from streamlit.testing.v1 import AppTest


APP_PATH = str(Path(__file__).resolve().parents[1] / "backend" / "app.py")


def test_primary_routes_render_without_exceptions() -> None:
    for route in ("home", "scan", "picks", "portfolio"):
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
    app.run()

    clear_button = next(button for button in app.button if button.key == "picks_clear")
    clear_button.click().run()

    assert app.session_state["picks_selection_widget"] == []
    assert app.session_state["picks_results"] == {}
    assert app.session_state["picks_analyzed_tickers"] == []
