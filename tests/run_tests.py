import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Test constants
from utils.constants import STOCK_UNIVERSE, SCORING_WEIGHTS, SECTOR_CN_MAP, CACHE_TTL

assert len(STOCK_UNIVERSE) == 44, f"Expected 44 stocks, got {len(STOCK_UNIVERSE)}"
print("✅ constants: 44 stocks")

for stock in STOCK_UNIVERSE:
    assert "ticker" in stock
    assert "name_cn" in stock
print("✅ constants: all stocks have ticker and name_cn")

# Weights sum to 0.85 because some metrics are optional (partial scoring supported)
total_w = sum(SCORING_WEIGHTS.values())
assert 0 < total_w <= 1.0, f"Weights sum to {total_w}"
print(f"✅ constants: scoring weights sum to {total_w}")

for key, val in SCORING_WEIGHTS.items():
    assert val > 0
print("✅ constants: all weights positive")

for key, val in CACHE_TTL.items():
    assert val > 0
print("✅ constants: all TTLs positive")

required = {"Semiconductors", "Technology", "Healthcare", "Financial", "Consumer", "Industrials", "Energy", "Space", "Memory & Storage", "Defense & Aerospace"}
for s in required:
    assert s in SECTOR_CN_MAP
print("✅ constants: sector map complete")

# Test fundamental_analyzer
from agents.fundamental_analyzer import calculate_growth_score

data = {
    "revenue_growth": 20.0,
    "eps_growth": 20.0,
    "profit_margin": 20.0,
    "peg": 0.5,
    "roe": 30.0,
    "debt_equity": 0.3,
    "sector": "Semiconductors",
}
score, details, metrics_used = calculate_growth_score(data)
assert score == 100.0, f"Expected 100, got {score}"
assert len(details) == 6
assert metrics_used == 6, f"Expected 6 metrics used, got {metrics_used}"
print("✅ fundamental_analyzer: perfect score = 100")

data = {
    "revenue_growth": None,
    "eps_growth": None,
    "profit_margin": None,
    "peg": None,
    "roe": None,
    "debt_equity": None,
    "sector": "Technology",
}
score, details, metrics_used = calculate_growth_score(data)
assert score == 0
assert len(details) == 0
assert metrics_used == 0
print("✅ fundamental_analyzer: no data = 0")

# Test sec_analyzer
from agents.sec_analyzer import cik_to_padded, _extract_key_sentences

assert cik_to_padded(320193) == "0000320193"
assert cik_to_padded(None) is None
print("✅ sec_analyzer: cik_to_padded")

text = "Revenue increased by 20% year over year. The company expects strong growth."
sentences = _extract_key_sentences(text)
assert len(sentences) >= 1
print("✅ sec_analyzer: extract_key_sentences")

# Test auto_upgrader
from agents.auto_upgrader import agent_state

# Reset in-memory and on-disk state for clean test
agent_state._state["source_health"] = {}
agent_state._state["upgrade_logs"] = []
agent_state._save()

agent_state.log_source_result("test:source", True)
health = agent_state.get_health_status()
assert health["test:source"]["success"] == 1
assert health["test:source"]["failure"] == 0
print("✅ auto_upgrader: log source success")

agent_state.log_source_result("test:source", False, "timeout")
health = agent_state.get_health_status()
assert health["test:source"]["failure"] == 1
print("✅ auto_upgrader: log source failure")

assert agent_state.should_try_fallback("nonexistent") is False
print("✅ auto_upgrader: should_try_fallback (nonexistent)")

agent_state.log_upgrade("测试升级")
logs = agent_state.get_upgrade_logs()
assert any("测试升级" in l.get("message", "") for l in logs)
print("✅ auto_upgrader: log upgrade")

summary = agent_state.get_summary()
assert "数据源健康度" in summary
assert "升级日志数" in summary
print("✅ auto_upgrader: get_summary")

# Test cache
from utils.cache import cache
import time

cache.set("test_key", "test_category", {"value": 42})
result = cache.get("test_key", "test_category")
assert result == {"value": 42}
print("✅ cache: set/get")

print("\n🎉 ALL TESTS PASSED!")
