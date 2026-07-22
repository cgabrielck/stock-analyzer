import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents.auto_upgrader import AgentState


def test_agent_state_concurrent_updates_are_not_lost(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agents.auto_upgrader.DATA_DIR", str(tmp_path))
    state = AgentState()

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: state.log_source_result("test", True), range(40)))

    assert state.get_health_status()["test"]["success"] == 40
    with open(tmp_path / "agent_state.json") as file:
        persisted = json.load(file)
    assert persisted["source_health"]["test"]["success"] == 40
