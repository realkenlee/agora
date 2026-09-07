"""Paid LLM_* env must win over OpenRouter free-tier assumptions."""

from __future__ import annotations

import importlib

import ai.config as config


def test_paid_llm_env_skips_free_openrouter(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.anthropic.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-paid-key")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-5")
    monkeypatch.setenv("VISION_MODEL", "claude-sonnet-4-5")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    importlib.reload(config)
    s = config.llm_settings()
    assert s["paid"] is True
    assert s["model"] == "claude-sonnet-4-5"
    assert s["using_openrouter"] is False


def test_explicit_paid_model_on_openrouter(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-or-key")
    monkeypatch.setenv("LLM_MODEL", "anthropic/claude-sonnet-4.5")
    importlib.reload(config)
    s = config.llm_settings()
    assert s["paid"] is True
    assert ":free" not in s["model"]


def test_free_openrouter_default_is_not_paid(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-free")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    importlib.reload(config)
    s = config.llm_settings()
    assert s["paid"] is False
    assert "50" in s["free_tier_note"]


def test_llm_api_key_preferred_over_openrouter(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_API_KEY", "from-llm")
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-openrouter")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4.1-mini")
    importlib.reload(config)
    s = config.llm_settings()
    assert s["api_key"] == "from-llm"
    assert s["paid"] is True
