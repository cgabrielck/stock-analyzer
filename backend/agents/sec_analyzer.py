import re
import time
from typing import Optional, Dict, List, Any

import requests

from utils.constants import SEC_HEADERS, CIK_MAP_URL
from utils.cache import cache
from agents.auto_upgrader import agent_state

try:
    from agents.llm_agent import summarize_sec_filing
except Exception:
    summarize_sec_filing = None

_last_request_time: float = 0
_cik_map: Optional[Dict[str, int]] = None


def _rate_limit() -> None:
    global _last_request_time
    now = time.time()
    if now - _last_request_time < 1.0:
        time.sleep(1.0 - (now - _last_request_time))
    _last_request_time = time.time()


def _fetch_cik_map() -> Dict[str, int]:
    global _cik_map
    if _cik_map is not None:
        return _cik_map

    cached = cache.get("map", "cik_map")
    if cached:
        _cik_map = cached
        return _cik_map

    try:
        resp = requests.get(
            CIK_MAP_URL,
            headers={**SEC_HEADERS, "Host": "www.sec.gov"},
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()
        mapping: Dict[str, int] = {}
        for entry in raw.values():
            ticker = entry.get("ticker", "").upper()
            cik = entry.get("cik_str")
            if ticker and cik:
                mapping[ticker] = int(cik)
        _cik_map = mapping
        cache.set("map", "cik_map", mapping)
        agent_state.log_source_result("sec:cik_map", True)
        return mapping
    except Exception as e:
        agent_state.log_source_result("sec:cik_map", False, str(e))
        return {}


def ticker_to_cik(ticker: str) -> Optional[int]:
    mapping = _fetch_cik_map()
    cik = mapping.get(ticker.upper())
    if cik:
        agent_state.log_source_result(f"sec:cik_lookup:{ticker}", True)
    else:
        agent_state.log_source_result(f"sec:cik_lookup:{ticker}", False, "CIK not found for ticker")
    return cik


def cik_to_padded(cik: Optional[int]) -> Optional[str]:
    if cik is None:
        return None
    return str(cik).zfill(10)


def get_latest_filing(cik: Optional[int], ticker: str, lang: str = "zh_tw") -> Optional[Dict[str, Any]]:
    if cik is None:
        cik = ticker_to_cik(ticker)
    if cik is None:
        return None

    cache_key = f"sec_{ticker}_{lang}"
    cached = cache.get(cache_key, "sec_filings")
    if cached:
        return cached

    cik_padded = cik_to_padded(cik)
    if not cik_padded:
        return None

    try:
        _rate_limit()
        url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
        headers = {**SEC_HEADERS, "Host": "data.sec.gov"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        agent_state.log_source_result(f"sec:submissions:{ticker}", True)
    except Exception as e:
        agent_state.log_source_result(f"sec:submissions:{ticker}", False, str(e))
        return _try_alternative_sec(cik_padded, ticker, lang)

    try:
        filings = data.get("filings", {}).get("recent", {})
        if not filings:
            return None

        forms: List[str] = filings.get("form", [])
        dates: List[str] = filings.get("filingDate", [])
        prim_docs: List[str] = filings.get("primaryDocument", [])
        accession_numbers: List[str] = filings.get("accessionNumber", [])

        target_forms = ["10-K", "10-Q"]
        for i, form in enumerate(forms):
            if form in target_forms:
                filing_date = dates[i] if i < len(dates) else ""
                prim_doc = prim_docs[i] if i < len(prim_docs) else ""
                accession = accession_numbers[i] if i < len(accession_numbers) else ""

                archive_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik_padded)}/"
                    f"{accession.replace('-', '')}/{prim_doc}"
                )

                insights = _fetch_filing_insights(archive_url, ticker, lang)

                result: Dict[str, Any] = {
                    "form_type": form,
                    "filing_date": filing_date,
                    "url": archive_url,
                    "insights": insights,
                }
                cache.set(cache_key, "sec_filings", result)
                return result

        agent_state.log_source_result(f"sec:filings:{ticker}", False, "No 10-K/10-Q found")
        return {"form_type": None, "insights": None, "url": None}

    except Exception as e:
        agent_state.log_source_result(f"sec:parse:{ticker}", False, str(e))
        return {"form_type": None, "insights": None, "url": None}


def _try_alternative_sec(cik_padded: str, ticker: str, lang: str = "zh_tw") -> Optional[Dict[str, Any]]:
    try:
        _rate_limit()
        url = f"https://efts.sec.gov/LATEST/search-index?q=%22{int(cik_padded)}%22&dateRange=all&start=0&count=5"
        headers = {**SEC_HEADERS, "Host": "efts.sec.gov"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        for hit in hits:
            source = hit.get("_source", {})
            form = source.get("form", "")
            if form in ("10-K", "10-Q"):
                cache_key = f"sec_{ticker}_{lang}"
                result = {
                    "form_type": form,
                    "filing_date": source.get("filing_date", ""),
                    "url": f"https://www.sec.gov{source.get('uri', '')}",
                    "insights": None,
                }
                cache.set(cache_key, "sec_filings", result)
                return result
    except Exception:
        pass
    return {"form_type": None, "insights": None, "url": None}


def _fetch_filing_insights(url: str, ticker: str, lang: str = "zh_tw") -> Optional[Dict[str, Any]]:
    if not url:
        return None
    try:
        _rate_limit()
        headers = {**SEC_HEADERS, "Host": "www.sec.gov"}
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        text = resp.text
        agent_state.log_source_result(f"sec:content:{ticker}", True)
    except Exception as e:
        agent_state.log_source_result(f"sec:content:{ticker}", False, str(e))
        return None

    try:
        soup = BeautifulSoup(text, "html.parser")
        raw = soup.get_text(separator="\n", strip=True)
    except Exception:
        raw = text

    sections = _extract_sections(raw)

    llm_summary = None
    if summarize_sec_filing is not None and raw and len(raw.strip()) > 50:
        try:
            llm_summary = summarize_sec_filing(raw[:4000], ticker, lang)
        except Exception:
            pass

    if llm_summary and llm_summary.get("summary") and llm_summary["summary"] != "N/A":
        pass
    else:
        key_sentences = _extract_key_sentences(raw)
        if key_sentences:
            short = " | ".join(key_sentences[:3])
            lang_prefix = {"zh_cn": "要点", "zh_tw": "要點", "en": "Key Points"}.get(lang, "要點")
            llm_summary = {"summary": short, "key_risks": [], "key_positives": []}

    result: Dict[str, Any] = {"ticker": ticker}
    if sections:
        result["sections"] = sections
    if llm_summary:
        result["llm_summary"] = llm_summary
    return result


def _extract_sections(text: str) -> Optional[Dict[str, str]]:
    patterns = [
        (r"(?i)(item\s*7\.?\s*management.s?\s*discussion)", "MD&A"),
        (r"(?i)(item\s*1a\.?\s*risk factors)", "风险因素"),
        (r"(?i)(item\s*2\.?\s*management.s?\s*discussion)", "MD&A (10-Q)"),
        (r"(?i)(item\s*1\.?\s*business)", "业务概述"),
    ]

    found_sections: Dict[str, str] = {}

    for pattern, label in patterns:
        matches = list(re.finditer(pattern, text))
        for match in matches:
            start = match.start()
            end = min(start + 3000, len(text))
            snippet = text[start:end]
            lines = [l.strip() for l in snippet.split("\n") if l.strip()]
            meaningful = [l for l in lines if len(l) > 20][:10]
            if meaningful:
                key = f"{label} (位置 {start})"
                found_sections[key] = " | ".join(meaningful[:5])

    if not found_sections:
        key_sentences = _extract_key_sentences(text)
        if key_sentences:
            found_sections["关键语句"] = " | ".join(key_sentences[:5])

    return found_sections if found_sections else None


def _extract_key_sentences(text: str) -> List[str]:
    keywords = [
        "revenue increased", "revenue growth", "net income", "operating income",
        "guidance", "outlook", "expects", "anticipates", "driven by",
        "gross margin", "operating margin", "cash flow", "share repurchase",
        "dividend", "market share", "competition", "regulatory",
    ]
    sentences = re.split(r'(?<=[.!?])\s+', text)
    found: List[str] = []
    for s in sentences:
        s_clean = s.strip()
        if any(kw in s_clean.lower() for kw in keywords):
            if 30 < len(s_clean) < 500:
                found.append(s_clean)
    return found[:10]
