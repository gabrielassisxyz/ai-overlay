"""Tests for config loading and profile resolution (docs/spec.md §2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_overlay import config as cfg


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_fills_defaults_and_resolves_default_profile(tmp_path):
    path = _write(
        tmp_path / "config.toml",
        """
        default_profile = "generic"

        [profiles.generic]
        system_prompt_file = "~/prompts/generic.md"
        """,
    )

    conf = cfg.load_config(path)

    assert conf.base_url == cfg.DEFAULT_BASE_URL
    assert conf.model == cfg.DEFAULT_MODEL
    assert conf.max_image_width == cfg.DEFAULT_MAX_IMAGE_WIDTH

    profile = conf.resolve(None)
    assert profile.name == "generic"
    assert profile.capture == cfg.DEFAULT_CAPTURE
    assert profile.model == cfg.DEFAULT_MODEL  # inherits global
    assert (
        profile.system_prompt_file == Path.home() / "prompts/generic.md"
    )  # ~ expanded


def test_globals_and_profile_overrides(tmp_path):
    path = _write(
        tmp_path / "config.toml",
        """
        default_profile = "deck"
        base_url = "http://localhost:9999/v1"
        model = "kimi-k2.7"
        max_image_width = 800

        [profiles.deck]
        system_prompt_file = "/tmp/deck.md"
        capture = "region"
        model = "gemini-3.5-flash"
        """,
    )

    conf = cfg.load_config(path)
    assert conf.base_url == "http://localhost:9999/v1"
    assert conf.max_image_width == 800

    profile = conf.resolve("deck")
    assert profile.capture == "region"
    assert profile.model == "gemini-3.5-flash"  # override wins over global


def test_unknown_profile_lists_available(tmp_path):
    path = _write(
        tmp_path / "config.toml",
        """
        default_profile = "a"
        [profiles.a]
        system_prompt_file = "/tmp/a.md"
        [profiles.b]
        system_prompt_file = "/tmp/b.md"
        """,
    )
    conf = cfg.load_config(path)

    with pytest.raises(cfg.ConfigError) as excinfo:
        conf.resolve("missing")

    message = str(excinfo.value)
    assert "missing" in message
    assert "a" in message and "b" in message  # available profiles listed


def test_missing_config_file(tmp_path):
    with pytest.raises(cfg.ConfigError, match="Config not found"):
        cfg.load_config(tmp_path / "nope.toml")


def test_missing_default_profile_key(tmp_path):
    path = _write(
        tmp_path / "config.toml",
        """
        [profiles.a]
        system_prompt_file = "/tmp/a.md"
        """,
    )
    with pytest.raises(cfg.ConfigError, match="default_profile"):
        cfg.load_config(path)


def test_default_profile_must_exist(tmp_path):
    path = _write(
        tmp_path / "config.toml",
        """
        default_profile = "ghost"
        [profiles.a]
        system_prompt_file = "/tmp/a.md"
        """,
    )
    with pytest.raises(cfg.ConfigError, match="ghost"):
        cfg.load_config(path)


def test_no_profiles_defined(tmp_path):
    path = _write(tmp_path / "config.toml", 'default_profile = "a"\n')
    with pytest.raises(cfg.ConfigError, match="no \\[profiles"):
        cfg.load_config(path)


def test_invalid_capture_mode(tmp_path):
    path = _write(
        tmp_path / "config.toml",
        """
        default_profile = "a"
        [profiles.a]
        system_prompt_file = "/tmp/a.md"
        capture = "webcam"
        """,
    )
    with pytest.raises(cfg.ConfigError, match="invalid capture"):
        cfg.load_config(path)


def test_missing_system_prompt_file_key(tmp_path):
    path = _write(
        tmp_path / "config.toml",
        """
        default_profile = "a"
        [profiles.a]
        capture = "fullscreen"
        """,
    )
    with pytest.raises(cfg.ConfigError, match="system_prompt_file"):
        cfg.load_config(path)


def test_read_system_prompt_success_and_missing(tmp_path):
    prompt = _write(tmp_path / "p.md", "You are a helpful assistant.")
    path = _write(
        tmp_path / "config.toml",
        f"""
        default_profile = "a"
        [profiles.a]
        system_prompt_file = "{prompt}"
        """,
    )
    profile = cfg.load_config(path).resolve("a")
    assert profile.read_system_prompt() == "You are a helpful assistant."

    prompt.unlink()
    with pytest.raises(cfg.ConfigError, match="cannot read system_prompt_file"):
        profile.read_system_prompt()


def _config(**overrides):
    base = dict(
        default_profile="a",
        base_url="http://localhost:4000/v1",
        model="m",
        max_image_width=1280,
        profiles={},
    )
    base.update(overrides)
    return cfg.Config(**base)


def test_resolve_api_key_prefers_raw_config(monkeypatch):
    monkeypatch.setenv("AI_OVERLAY_API_KEY", "env-key")
    assert cfg.resolve_api_key(_config(api_key="raw-key")) == "raw-key"


def test_resolve_api_key_uses_named_env(monkeypatch):
    monkeypatch.setenv("MY_PROXY_KEY", "from-named-env")
    assert cfg.resolve_api_key(_config(api_key_env="MY_PROXY_KEY")) == "from-named-env"


def test_resolve_api_key_named_env_unset_raises(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    with pytest.raises(cfg.ConfigError, match="MISSING_KEY"):
        cfg.resolve_api_key(_config(api_key_env="MISSING_KEY"))


def test_resolve_api_key_falls_back_to_env_chain(monkeypatch):
    monkeypatch.delenv("AI_OVERLAY_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "from-openai-var")
    assert cfg.resolve_api_key(_config()) == "from-openai-var"


def test_resolve_api_key_placeholder_when_nothing_set(monkeypatch):
    monkeypatch.delenv("AI_OVERLAY_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cfg.resolve_api_key(_config()) == cfg.KEYLESS_PLACEHOLDER


def test_load_config_parses_key_fields(tmp_path):
    path = _write(
        tmp_path / "config.toml",
        """
        default_profile = "a"
        api_key_env = "LITELLM_KEY"
        [profiles.a]
        system_prompt_file = "/tmp/a.md"
        """,
    )
    conf = cfg.load_config(path)
    assert conf.api_key is None
    assert conf.api_key_env == "LITELLM_KEY"
