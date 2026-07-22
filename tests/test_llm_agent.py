import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from agents import llm_agent
from agents.llm_agent import _normalize_news_impact, get_model_for_task, get_public_config


def test_model_routing_reserves_reasoner_for_strategy() -> None:
    config = get_public_config()
    assert get_model_for_task("strategy") == config["reasoning_model"]
    assert get_model_for_task("stock_analysis") == config["chat_model"]
    assert get_model_for_task("price_targets") == config["chat_model"]
    assert get_model_for_task("options") == config["chat_model"]
    assert get_model_for_task("sec_summary") == config["chat_model"]
    assert get_model_for_task("news_impact") == config["chat_model"]


def test_public_config_never_exposes_api_key() -> None:
    config = get_public_config()

    assert config["provider"] == "openai-compatible"
    assert "api_key" not in config


def test_reasoner_failure_falls_back_to_chat(monkeypatch) -> None:
    calls = []

    class Completions:
        def create(self, model, **kwargs):
            calls.append(model)
            if model == "reasoner":
                raise RuntimeError("unsupported")
            return "ok"

    class Client:
        class Chat:
            completions = Completions()
        chat = Chat()

    monkeypatch.setattr(llm_agent, "_REASONING_MODEL", "reasoner")
    monkeypatch.setattr(llm_agent, "_CHAT_MODEL", "chat")

    assert llm_agent._create_completion(Client(), "strategy", messages=[]) == "ok"
    assert calls == ["reasoner", "chat"]


def test_news_impact_normalization_rejects_invalid_enums_and_bounds_confidence() -> None:
    result = _normalize_news_impact({
        "direction": "guaranteed_up", "magnitude": "huge", "horizon": "tomorrow",
        "event_type": "rumor", "confidence": 150, "key_risks": "not-a-list",
    })

    assert result["direction"] == "neutral"
    assert result["magnitude"] == "low"
    assert result["event_type"] == "other"
    assert result["confidence"] == 100
