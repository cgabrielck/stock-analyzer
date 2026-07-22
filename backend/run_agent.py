#!/usr/bin/env python3

import argparse
import sys
import time
from typing import Any, Dict, List

from agents.recommender import run_full_analysis
from i18n import t
from utils.constants import STOCK_UNIVERSE, SECTOR_CN_MAP, SECTOR_EN_MAP, SECTOR_TW_MAP


def _stock_name(s: Dict[str, Any], lang: str) -> str:
    if lang == "en":
        return s.get("name_en", s.get("longName", s["ticker"]))
    elif lang == "zh_tw":
        return s.get("name_tw", s.get("name_cn", s["ticker"]))
    return s.get("name_cn", s.get("longName", s["ticker"]))


def _sector_name(sec: str, lang: str) -> str:
    if lang == "en":
        return SECTOR_EN_MAP.get(sec, sec)
    elif lang == "zh_tw":
        return SECTOR_TW_MAP.get(sec, sec)
    return SECTOR_CN_MAP.get(sec, sec)


def _lookup_stock(ticker: str) -> Dict[str, Any]:
    for s in STOCK_UNIVERSE:
        if s["ticker"] == ticker:
            return s
    return {"ticker": ticker}


def print_header(lang: str) -> None:
    print("=" * 70)
    print(f"   {t('app.title', lang)} — CLI")
    print("  " + time.strftime("%Y-%m-%d %H:%M:%S"))
    print(f"  {t('sidebar.data_from', lang)}")
    print("=" * 70)


def print_progress(completed: int, total: int, lang: str = "zh_tw") -> None:
    bar_len = 30
    filled = int(bar_len * completed / total)
    bar = "█" * filled + "░" * (bar_len - filled)
    sys.stdout.write(f"\r  {t('cli.progress', lang)}: |{bar}| {completed}/{total}")
    sys.stdout.flush()


def make_progress_callback(lang: str):
    def cb(completed: int, total: int):
        print_progress(completed, total, lang)
    return cb


def print_recommendation(rec: Dict[str, Any], index: int, lang: str) -> None:
    name = _stock_name(rec, lang)
    sec = _sector_name(rec.get("sector", ""), lang)
    print(f"\n{'─' * 70}")
    print(f"   {t('cli.rank', lang, i=index)}: {rec['ticker']} — {name}")
    print(f"     {t('cli.sector', lang)}: {sec}")
    print(f"     {t('recommend.score', lang, s=rec.get('total_score', 0))}")
    print(f"     {t('metric.price', lang)}: ${rec.get('price', 0):.2f}" if rec.get("price") else f"     {t('metric.price', lang)}: N/A")
    print()

    metrics = [
        (t("metric.revenue", lang), f"{rec.get('revenue_growth', 0):.1f}%" if rec.get("revenue_growth") is not None else "N/A"),
        (t("metric.eps", lang), f"{rec.get('eps_growth', 0):.1f}%" if rec.get("eps_growth") is not None else "N/A"),
        (t("metric.profit_margin", lang), f"{rec.get('profit_margin', 0):.1f}%" if rec.get("profit_margin") is not None else "N/A"),
        (t("metric.roe", lang), f"{rec.get('roe', 0):.1f}%" if rec.get("roe") is not None else "N/A"),
        (t("metric.peg", lang), f"{rec.get('peg', 0):.2f}" if rec.get("peg") is not None else "N/A"),
        (t("metric.de", lang), f"{rec.get('debt_equity', 0):.2f}" if rec.get("debt_equity") is not None else "N/A"),
    ]
    for label, value in metrics:
        print(f"     {label:20s}: {value}")

    extra = [
        (t("metric.beta", lang), f"{rec.get('beta', 0):.2f}" if rec.get("beta") is not None else "N/A"),
        (t("metric.div_yield", lang), f"{rec.get('dividend_yield', 0)*100:.2f}%" if rec.get("dividend_yield") is not None else "N/A"),
        (t("metric.rating", lang), rec.get("rating_label") or "N/A"),
        (t("metric.inst_own", lang), f"{rec.get('held_percent_institutions', 0)*100:.1f}%" if rec.get("held_percent_institutions") is not None else "N/A"),
    ]
    print()
    for label, value in extra:
        print(f"     {label:20s}: {value}")

    dq = rec.get("data_quality", {})
    fetched = dq.get("fetched_at", rec.get("fetched_at"))
    if fetched:
        print(f"\n     {t('recommend.fetched_at', lang, time=fetched)}")
    avail = dq.get("metrics_available", 0)
    total_m = dq.get("metrics_total", 6)
    ratio = avail / total_m if total_m > 0 else 0
    conf = t("conf.high", lang) if ratio >= 0.8 else t("conf.medium", lang) if ratio >= 0.5 else t("conf.low", lang)
    print(f"     {t('recommend.confidence', lang, level=conf)}")

    reasoning = rec.get("reasoning", "")
    if reasoning:
        print(f"\n     {t('recommend.reasoning', lang)}:")
        for line in reasoning.strip().split("\n"):
            print(f"       {line.strip()}")

    sec_insights = rec.get("sec_insights") or {}
    if sec_insights.get("url"):
        print(f"\n     {t('recommend.sec_file', lang, form=sec_insights.get('form_type', 'N/A'), date=sec_insights.get('filing_date', 'N/A'))}")
        print(f"     {t('cli.sec_link', lang)}: {sec_insights['url']}")


def print_summary(results: Dict[str, Any], lang: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"   {t('ai.source_health', lang)}")
    print(f"  {'─' * 66}")

    health = results.get("source_health", {})
    for source, info in sorted(health.items()):
        total = info.get("success", 0) + info.get("failure", 0)
        rate = info.get("success", 0) / total * 100 if total > 0 else 0
        icon = "" if rate >= 80 else "" if rate >= 50 else ""
        print(f"  {icon} {source}: {rate:.0f}% {t('ai.rate', lang)} ({total} {t('cli.requests', lang)})")

    logs = results.get("upgrade_logs", [])
    if logs:
        print(f"\n   {t('cli.recent_logs', lang, n=3)}:")
        for log in logs[-3:]:
            print(f"     • {log.get('message', '')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=t("app.title"))
    parser.add_argument("--lang", choices=["zh_cn", "zh_tw", "en"], default="zh_tw", help="Language")
    args = parser.parse_args()

    lang = args.lang
    print_header(lang)

    print(f"\n  {t('cli.starting', lang)}...\n")
    results = run_full_analysis(
        progress_callback=make_progress_callback(lang),
        lang=lang,
    )
    print()

    if results.get("error"):
        print(f"\n   {t('app.error', lang, msg=results['error'])}")
        sys.exit(1)

    recs = results.get("recommendations", [])
    if not recs:
        print(f"\n   {t('cli.no_recs', lang)}")
        sys.exit(1)

    print(f"\n  {t('app.complete', lang, n=len(results.get('all_rankings', [])))}\n")

    for i, rec in enumerate(recs):
        print_recommendation(rec, i + 1, lang)

    print_summary(results, lang)

    print(f"\n{'=' * 70}")
    print(f"  {t('cli.disclaimer', lang)}")
    print(f"  {t('cli.disclaimer2', lang)}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
