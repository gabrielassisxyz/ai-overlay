"""Load and resolve the TOML config into typed profiles.

The behavioral contract lives in ``docs/spec.md`` §2. Kept pure (no screenshot or
network side effects) so it is trivially testable; the only I/O is reading the TOML
file and, on demand, a profile's prompt file.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "http://localhost:4000/v1"
DEFAULT_MODEL = "kimi-k2.7"
DEFAULT_MAX_IMAGE_WIDTH = 1280
DEFAULT_CAPTURE = "fullscreen"
CAPTURE_MODES = ("fullscreen", "active-window", "region")
# Env vars checked, in order, when the config names no key. Matches docs/spec.md §2.
DEFAULT_API_KEY_ENVS = ("AI_OVERLAY_API_KEY", "OPENAI_API_KEY")
# The proxy may be keyless, but the openai client still requires a non-empty string.
KEYLESS_PLACEHOLDER = "sk-noop"


class ConfigError(Exception):
    """The config is missing, malformed, or points at something that isn't there."""


@dataclass(frozen=True)
class Profile:
    """One task profile: which prompt to inject, what to capture, which model."""

    name: str
    system_prompt_file: Path
    capture: str
    model: str

    def read_system_prompt(self) -> str:
        """Read the profile's prompt file, or fail loudly naming the path."""
        try:
            return self.system_prompt_file.read_text(encoding="utf-8")
        except OSError as err:
            raise ConfigError(
                f"Profile {self.name!r}: cannot read system_prompt_file "
                f"{self.system_prompt_file}: {err.strerror or err}."
            ) from err


@dataclass(frozen=True)
class Config:
    default_profile: str
    base_url: str
    model: str
    max_image_width: int
    profiles: dict[str, Profile]
    api_key: str | None = None
    api_key_env: str | None = None

    def resolve(self, name: str | None) -> Profile:
        """Pick ``name`` (or the default). Unknown names fail listing the options."""
        chosen = name or self.default_profile
        try:
            return self.profiles[chosen]
        except KeyError:
            available = ", ".join(sorted(self.profiles)) or "(none)"
            raise ConfigError(
                f"Unknown profile {chosen!r}. Available: {available}."
            ) from None


def load_config(path: Path) -> Config:
    """Parse the TOML at ``path`` into a validated :class:`Config`."""
    if not path.exists():
        raise ConfigError(f"Config not found: {path}. See docs/spec.md §2.")

    with path.open("rb") as handle:
        try:
            raw = tomllib.load(handle)
        except tomllib.TOMLDecodeError as err:
            raise ConfigError(f"Config {path} is not valid TOML: {err}.") from err

    default_profile = raw.get("default_profile")
    if not default_profile:
        raise ConfigError("Config is missing the required 'default_profile' key.")

    base_url = raw.get("base_url", DEFAULT_BASE_URL)
    model = raw.get("model", DEFAULT_MODEL)
    max_image_width = raw.get("max_image_width", DEFAULT_MAX_IMAGE_WIDTH)
    api_key = raw.get("api_key")
    api_key_env = raw.get("api_key_env")

    raw_profiles = raw.get("profiles", {})
    if not raw_profiles:
        raise ConfigError("Config defines no [profiles.*]; at least one is required.")

    profiles = {
        name: _parse_profile(name, body, default_model=model)
        for name, body in raw_profiles.items()
    }

    if default_profile not in profiles:
        available = ", ".join(sorted(profiles))
        raise ConfigError(
            f"default_profile {default_profile!r} is not a defined profile. "
            f"Available: {available}."
        )

    return Config(
        default_profile=default_profile,
        base_url=base_url,
        model=model,
        max_image_width=max_image_width,
        profiles=profiles,
        api_key=api_key,
        api_key_env=api_key_env,
    )


def resolve_api_key(config: Config) -> str:
    """Resolve the proxy key: a raw ``api_key``, a named ``api_key_env``, or the chain.

    Precedence: explicit ``api_key`` > ``api_key_env`` (named var) > the default env
    chain > a placeholder for a keyless proxy. The key never lives in git; a raw
    ``api_key`` in the local config is a convenience the user opts into (spec §2).
    """
    if config.api_key:
        return config.api_key
    if config.api_key_env:
        value = os.environ.get(config.api_key_env)
        if not value:
            raise ConfigError(
                f"api_key_env points at ${config.api_key_env}, but it is unset."
            )
        return value
    for name in DEFAULT_API_KEY_ENVS:
        value = os.environ.get(name)
        if value:
            return value
    return KEYLESS_PLACEHOLDER


def _parse_profile(name: str, body: dict, *, default_model: str) -> Profile:
    prompt_file = body.get("system_prompt_file")
    if not prompt_file:
        raise ConfigError(
            f"Profile {name!r} is missing the required 'system_prompt_file' key."
        )

    capture = body.get("capture", DEFAULT_CAPTURE)
    if capture not in CAPTURE_MODES:
        allowed = ", ".join(CAPTURE_MODES)
        raise ConfigError(
            f"Profile {name!r} has invalid capture {capture!r}; "
            f"expected one of: {allowed}."
        )

    return Profile(
        name=name,
        system_prompt_file=Path(prompt_file).expanduser(),
        capture=capture,
        model=body.get("model", default_model),
    )
