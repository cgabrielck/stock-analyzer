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
