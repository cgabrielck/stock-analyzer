from agents import sec_analyzer
from agents.sec_analyzer import cik_to_padded, _extract_key_sentences


def test_cik_to_padded() -> None:
    assert cik_to_padded(320193) == "0000320193"


def test_cik_to_padded_none() -> None:
    assert cik_to_padded(None) is None


def test_extract_key_sentences() -> None:
    text = "Revenue increased by 20% year over year. The company expects strong growth. This is just some filler text."
    sentences = _extract_key_sentences(text)
    assert len(sentences) >= 1
    assert any("Revenue increased" in s for s in sentences)
    assert any("expects" in s.lower() for s in sentences)


def test_extract_key_sentences_no_match() -> None:
    text = "The weather is nice today. Python programming is fun. Hello world."
    sentences = _extract_key_sentences(text)
    assert len(sentences) == 0


def test_html_filing_parser_extracts_visible_evidence(monkeypatch) -> None:
    class Response:
        text = "<html><script>revenue increased fake</script><body><h2>Item 7. Management's Discussion</h2><p>Revenue increased by 20 percent because customer demand improved substantially.</p></body></html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(sec_analyzer.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(sec_analyzer, "_rate_limit", lambda: None)
    monkeypatch.setattr(sec_analyzer, "summarize_sec_filing", None)

    result = sec_analyzer._fetch_filing_insights("https://sec.test/filing", "TEST", include_llm_summary=False)

    text = " ".join(result.get("sections", {}).values())
    assert "Revenue increased" in text
    assert "<script>" not in text


def test_latest_filing_maps_identity_and_citation(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"filings": {"recent": {
                "form": ["8-K", "10-Q"], "filingDate": ["2026-07-01", "2026-06-20"],
                "reportDate": ["", "2026-05-31"], "acceptanceDateTime": ["", "20260620160000"],
                "primaryDocument": ["event.htm", "quarter.htm"],
                "accessionNumber": ["0000000000-26-000001", "0000000000-26-000002"],
            }}}

    monkeypatch.setattr(sec_analyzer.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(sec_analyzer, "_rate_limit", lambda: None)
    monkeypatch.setattr(sec_analyzer.cache, "get", lambda *args, **kwargs: None)
    monkeypatch.setattr(sec_analyzer.cache, "set", lambda *args, **kwargs: None)
    monkeypatch.setattr(sec_analyzer, "_fetch_filing_insights", lambda *args, **kwargs: {"sections": {}})

    result = sec_analyzer.get_latest_filing(123, "TEST", include_llm_summary=False)

    assert result["available"] is True
    assert result["form_type"] == "10-Q"
    assert result["report_date"] == "2026-05-31"
    assert result["accession_number"] == "0000000000-26-000002"
    assert result["citations"][0]["url"] == result["url"]
