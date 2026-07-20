import json
import os
import pytest

from agents.auto_upgrader import agent_state
from utils.constants import DATA_DIR


@pytest.fixture(autouse=True)
def reset_agent_state():
    agent_state._state = {
        "source_health": {},
        "recommendation_history": [],
        "failed_sources": {},
        "upgrade_logs": [],
        "scoring_metrics_performance": {},
        "detected_issues": [],
        "resolved_issues": [],
        "version": 2,
        "last_upgrade": None,
    }
    yield
    agent_state._save()


def test_log_source_result_tracks_success() -> None:
    agent_state.log_source_result("test:source", True)
    health = agent_state.get_health_status()
    assert "test:source" in health
    assert health["test:source"]["success"] == 1
    assert health["test:source"]["failure"] == 0


def test_log_source_result_tracks_failure() -> None:
    agent_state.log_source_result("test:source", False, "timeout")
    health = agent_state.get_health_status()
    assert health["test:source"]["failure"] == 1
    assert health["test:source"]["last_status"] == "failed"


def test_should_try_fallback_true() -> None:
    for _ in range(5):
        agent_state.log_source_result("test:source", False)
    assert agent_state.should_try_fallback("test:source") is True


def test_should_try_fallback_false() -> None:
    for _ in range(5):
        agent_state.log_source_result("test:source", True)
    assert agent_state.should_try_fallback("test:source") is False


def test_log_upgrade() -> None:
    agent_state.log_upgrade("测试升级消息")
    logs = agent_state.get_upgrade_logs()
    assert any("测试升级消息" in l.get("message", "") for l in logs)


def test_get_summary() -> None:
    agent_state.log_source_result("test:source", True)
    agent_state.log_upgrade("测试")
    summary = agent_state.get_summary()
    assert "数据源健康度" in summary
    assert "升级日志数" in summary
