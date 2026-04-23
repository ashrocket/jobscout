from unittest.mock import patch, MagicMock
from jobscout.llm import call_llm, LLMResponse


def test_call_llm_returns_response():
    mock_response = LLMResponse(text="extracted data", tokens_in=100, tokens_out=50,
                                 model="gpt-4o-mini", provider="openai")
    with patch("jobscout.llm._call_openai", return_value=mock_response):
        result = call_llm(
            task="extract",
            system="You are a job extractor.",
            prompt="Extract this job listing.",
            conn=None,
        )
    assert result.text == "extracted data"
    assert result.provider == "openai"


def test_call_llm_falls_back_on_error():
    fallback_response = LLMResponse(text="fallback result", tokens_in=100, tokens_out=50,
                                     model="claude-haiku-4-5-20251001", provider="anthropic")
    with patch("jobscout.llm._call_openai", side_effect=Exception("quota exceeded")):
        with patch("jobscout.llm._call_anthropic", return_value=fallback_response):
            result = call_llm(
                task="extract",
                system="You are a job extractor.",
                prompt="Extract this.",
                conn=None,
            )
    assert result.provider == "anthropic"
    assert result.text == "fallback result"
