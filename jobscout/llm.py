import json
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass

import anthropic
import google.generativeai as genai
import openai

from jobscout.config import MODELS, LOCAL_MODE, OLLAMA_MODEL, read_credential
from jobscout.budget import record_usage

_anthropic_client = None
_gemini_configured = False
_openai_client = None


@dataclass
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    provider: str


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=read_credential("jobscout-anthropic-key"))
    return _anthropic_client


def _configure_gemini():
    global _gemini_configured
    if not _gemini_configured:
        genai.configure(api_key=read_credential("jobscout-gemini-key"))
        _gemini_configured = True


def _call_anthropic(model: str, system: str, prompt: str) -> LLMResponse:
    client = _get_anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return LLMResponse(
        text=response.content[0].text,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
        model=model,
        provider="anthropic",
    )


def _call_gemini(model: str, system: str, prompt: str) -> LLMResponse:
    _configure_gemini()
    gm = genai.GenerativeModel(model, system_instruction=system)
    response = gm.generate_content(prompt)
    tokens_in = response.usage_metadata.prompt_token_count
    tokens_out = response.usage_metadata.candidates_token_count
    return LLMResponse(
        text=response.text,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model=model,
        provider="gemini",
    )


def _get_openai():
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.OpenAI(api_key=read_credential("jobscout-openai-key"))
    return _openai_client


def _call_openai(model: str, system: str, prompt: str) -> LLMResponse:
    client = _get_openai()
    response = client.chat.completions.create(
        model=model,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return LLMResponse(
        text=response.choices[0].message.content,
        tokens_in=response.usage.prompt_tokens,
        tokens_out=response.usage.completion_tokens,
        model=model,
        provider="openai",
    )


def _run_cli(cmd: list[str], timeout: int = 120) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {result.stderr[:500]}")
    return result.stdout.strip()


def _call_local_claude(model: str, system: str, prompt: str) -> LLMResponse:
    bin_path = shutil.which("claude")
    if not bin_path:
        raise RuntimeError("claude CLI not found on PATH")
    raw = _run_cli([
        bin_path, "-p", prompt,
        "--system-prompt", system,
        "--output-format", "json",
        "--tools", "",
        "--model", model,
    ])
    data = json.loads(raw)
    return LLMResponse(
        text=data.get("result", raw),
        tokens_in=data.get("usage", {}).get("input_tokens", 0),
        tokens_out=data.get("usage", {}).get("output_tokens", 0),
        model=model,
        provider="local_claude",
    )


def _call_local_gemini(model: str, system: str, prompt: str) -> LLMResponse:
    bin_path = shutil.which("gemini")
    if not bin_path:
        raise RuntimeError("gemini CLI not found on PATH")
    combined = f"SYSTEM INSTRUCTIONS:\n{system}\n\nUSER REQUEST:\n{prompt}"
    text = _run_cli([bin_path, "-p", combined])
    return LLMResponse(
        text=text,
        tokens_in=0,
        tokens_out=0,
        model=model,
        provider="local_gemini",
    )


_ollama_client = None


def _get_ollama():
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = openai.OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    return _ollama_client


def _call_ollama(model: str, system: str, prompt: str) -> LLMResponse:
    client = _get_ollama()
    response = client.chat.completions.create(
        model=model,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return LLMResponse(
        text=response.choices[0].message.content,
        tokens_in=response.usage.prompt_tokens,
        tokens_out=response.usage.completion_tokens,
        model=model,
        provider="ollama",
    )


def _call_local_codex(model: str, system: str, prompt: str) -> LLMResponse:
    bin_path = shutil.which("codex")
    if not bin_path:
        raise RuntimeError("codex CLI not found on PATH")
    combined = f"SYSTEM INSTRUCTIONS:\n{system}\n\nUSER REQUEST:\n{prompt}"
    text = _run_cli([bin_path, "exec", combined])
    return LLMResponse(
        text=text,
        tokens_in=0,
        tokens_out=0,
        model=model,
        provider="local_codex",
    )


import sys as _sys

_PROVIDERS = {
    "anthropic": "_call_anthropic",
    "gemini": "_call_gemini",
    "openai": "_call_openai",
    "ollama": "_call_ollama",
    "local_claude": "_call_local_claude",
    "local_gemini": "_call_local_gemini",
    "local_codex": "_call_local_codex",
}

_LOCAL_REMAP = {
    "anthropic": "local_claude",
    "openai": "local_codex",
    "gemini": "ollama",
}


def call_llm(*, task: str, system: str, prompt: str,
             conn: sqlite3.Connection | None) -> LLMResponse:
    config = MODELS[task]
    primary = dict(config["primary"])
    fallback = dict(config["fallback"])

    if LOCAL_MODE:
        for slot in [primary, fallback]:
            orig_provider = slot["provider"]
            slot["provider"] = _LOCAL_REMAP.get(orig_provider, orig_provider)
            if slot["provider"] == "ollama":
                slot["model"] = OLLAMA_MODEL

    for attempt in [primary, fallback]:
        try:
            fn_name = _PROVIDERS[attempt["provider"]]
            fn = getattr(_sys.modules[__name__], fn_name)
            response = fn(attempt["model"], system, prompt)
            if conn is not None:
                record_usage(conn, provider=response.provider, tokens_in=response.tokens_in,
                             tokens_out=response.tokens_out, task=task, model=response.model)
            return response
        except Exception:
            if attempt is fallback:
                raise
            continue

    raise RuntimeError("All LLM providers failed")
