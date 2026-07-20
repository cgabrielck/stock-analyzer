from utils.constants import (
    STOCK_UNIVERSE,
    SCORING_WEIGHTS,
    SECTOR_CN_MAP,
    CACHE_TTL,
)


def test_stock_universe_has_44_stocks() -> None:
    assert len(STOCK_UNIVERSE) == 44


def test_stock_universe_all_have_ticker_and_name() -> None:
    for stock in STOCK_UNIVERSE:
        assert "ticker" in stock
        assert "name_cn" in stock
        assert len(stock["ticker"]) > 0


def test_scoring_weights_sum_positive() -> None:
    total = sum(SCORING_WEIGHTS.values())
    assert 0 < total <= 1.0


def test_scoring_weights_positive() -> None:
    for key, val in SCORING_WEIGHTS.items():
        assert val > 0, f"Weight {key} must be positive"


def test_sector_cn_map_has_all_sectors() -> None:
    required = {"Technology", "Healthcare", "Financial"}
    for s in required:
        assert s in SECTOR_CN_MAP


def test_cache_ttl_positive() -> None:
    for key, val in CACHE_TTL.items():
        assert val > 0, f"TTL for {key} must be positive"
