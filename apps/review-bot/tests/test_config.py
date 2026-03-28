"""Tests for review_bot.config — registry loading and config precedence resolution."""

from __future__ import annotations

import textwrap

import pytest

import review_bot.config as config_module
from review_bot.config import (
    EffectiveConfig,
    RegistryError,
    load_registry,
    merge_per_repo_config,
    resolve_effective_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REGISTRY_YAML = textwrap.dedent("""\
    defaults:
      model: "gemini/gemini-2.0-flash"

    repositories:
      - repo: "owner/repo-a"
        model: "anthropic/claude-sonnet-4-20250514"
      - repo: "owner/repo-b"
        # inherits global default model
""")

_REGISTRY_YAML_NO_ENTRY_MODEL = textwrap.dedent("""\
    defaults:
      model: "gemini/gemini-2.0-flash"

    repositories:
      - repo: "owner/repo-b"
""")


@pytest.fixture(autouse=True)
def reset_registry(tmp_path):
    """Reset the module-level registry singleton before each test."""
    config_module._registry = None
    yield
    config_module._registry = None


@pytest.fixture()
def registry_file(tmp_path):
    """Write a standard registry YAML to a temp file and return its path."""
    path = tmp_path / "repos.yml"
    path.write_text(_REGISTRY_YAML)
    return str(path)


@pytest.fixture()
def registry_loaded(registry_file):
    """Load the standard test registry and return it."""
    load_registry(registry_file)
    return config_module.get_registry()


# ---------------------------------------------------------------------------
# load_registry
# ---------------------------------------------------------------------------


class TestLoadRegistry:
    def test_loads_defaults_and_repositories(self, registry_file):
        load_registry(registry_file)
        reg = config_module.get_registry()
        assert reg.defaults.model == "gemini/gemini-2.0-flash"
        assert len(reg.repositories) == 2

    def test_per_repo_model_present(self, registry_file):
        load_registry(registry_file)
        reg = config_module.get_registry()
        entry = next(r for r in reg.repositories if r.repo == "owner/repo-a")
        assert entry.model == "anthropic/claude-sonnet-4-20250514"

    def test_per_repo_model_absent(self, registry_file):
        load_registry(registry_file)
        reg = config_module.get_registry()
        entry = next(r for r in reg.repositories if r.repo == "owner/repo-b")
        assert entry.model is None


# ---------------------------------------------------------------------------
# resolve_effective_config — precedence
# ---------------------------------------------------------------------------


class TestResolveEffectiveConfig:
    def test_registry_entry_model_overrides_global_default(self, registry_loaded, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("GITHUB_TOKEN", "gh-test")
        result = resolve_effective_config("owner/repo-a")
        assert result.model == "anthropic/claude-sonnet-4-20250514"

    def test_global_default_used_when_no_per_repo_model(self, registry_loaded, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gk-test")
        monkeypatch.setenv("GITHUB_TOKEN", "gh-test")
        result = resolve_effective_config("owner/repo-b")
        assert result.model == "gemini/gemini-2.0-flash"

    def test_unregistered_repo_raises_registry_error(self, registry_loaded):
        with pytest.raises(RegistryError, match="owner/unknown"):
            resolve_effective_config("owner/unknown")

    def test_registry_error_message_is_descriptive(self, registry_loaded):
        with pytest.raises(RegistryError) as exc_info:
            resolve_effective_config("owner/unknown")
        assert "repos.yml" in str(exc_info.value)

    def test_default_prompt_mode_is_base(self, registry_loaded, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("GITHUB_TOKEN", "gh-test")
        result = resolve_effective_config("owner/repo-a")
        assert result.prompt_mode == "base"
        assert result.prompt_extension is None

    def test_github_token_resolved_from_env(self, registry_loaded, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp-global-token")
        result = resolve_effective_config("owner/repo-a")
        assert result.github_token == "ghp-global-token"

    def test_per_repo_github_token_takes_precedence(self, registry_loaded, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp-global")
        monkeypatch.setenv("REPO_OWNER_REPO_A_GITHUB_TOKEN", "ghp-per-repo")
        result = resolve_effective_config("owner/repo-a")
        assert result.github_token == "ghp-per-repo"

    def test_per_repo_yml_model_overrides_registry_entry(self, registry_loaded, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gk-test")
        monkeypatch.setenv("GITHUB_TOKEN", "gh-test")
        per_repo_yml = "model: gemini/gemini-1.5-pro\n"
        result = resolve_effective_config("owner/repo-a", per_repo_yml_content=per_repo_yml)
        assert result.model == "gemini/gemini-1.5-pro"

    def test_per_repo_yml_none_leaves_config_from_registry(self, registry_loaded, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("GITHUB_TOKEN", "gh-test")
        result = resolve_effective_config("owner/repo-a", per_repo_yml_content=None)
        assert result.model == "anthropic/claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# merge_per_repo_config — prompt modes
# ---------------------------------------------------------------------------


class TestMergePerRepoConfig:
    @pytest.fixture()
    def base_effective(self, monkeypatch) -> EffectiveConfig:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-base")
        monkeypatch.setenv("GITHUB_TOKEN", "gh-base")
        return EffectiveConfig(
            repo="owner/repo-a",
            model="anthropic/claude-sonnet-4-20250514",
            prompt_mode="base",
            prompt_extension=None,
            api_key="sk-base",
            github_token="gh-base",
        )

    def test_prompt_mode_extend(self, base_effective):
        per_repo_yml = textwrap.dedent("""\
            prompt:
              mode: extend
              text: "Focus on type safety."
        """)
        result = merge_per_repo_config(base_effective, per_repo_yml)
        assert result.prompt_mode == "extend"
        assert result.prompt_extension == "Focus on type safety."

    def test_prompt_mode_replace(self, base_effective):
        per_repo_yml = textwrap.dedent("""\
            prompt:
              mode: replace
              text: "Use this prompt instead of the base."
        """)
        result = merge_per_repo_config(base_effective, per_repo_yml)
        assert result.prompt_mode == "replace"
        assert result.prompt_extension == "Use this prompt instead of the base."

    def test_model_override_in_merge(self, base_effective, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gk-test")
        per_repo_yml = "model: gemini/gemini-1.5-pro\n"
        result = merge_per_repo_config(base_effective, per_repo_yml)
        assert result.model == "gemini/gemini-1.5-pro"

    def test_unknown_keys_silently_ignored(self, base_effective):
        per_repo_yml = textwrap.dedent("""\
            unknown_key: ignored_value
            another: also_ignored
        """)
        result = merge_per_repo_config(base_effective, per_repo_yml)
        assert result.model == base_effective.model
        assert result.prompt_mode == base_effective.prompt_mode

    def test_malformed_yaml_returns_effective_unchanged(self, base_effective):
        bad_yaml = "key: [unclosed bracket"
        result = merge_per_repo_config(base_effective, bad_yaml)
        assert result == base_effective

    def test_repo_preserved_after_merge(self, base_effective):
        per_repo_yml = "model: gemini/gemini-2.0-flash\n"
        result = merge_per_repo_config(base_effective, per_repo_yml)
        assert result.repo == "owner/repo-a"

    def test_github_token_preserved_after_merge(self, base_effective):
        per_repo_yml = "model: gemini/gemini-2.0-flash\n"
        result = merge_per_repo_config(base_effective, per_repo_yml)
        assert result.github_token == "gh-base"


# ---------------------------------------------------------------------------
# API key resolution
# ---------------------------------------------------------------------------


class TestApiKeyResolution:
    def test_gemini_key_resolved_from_env(self, registry_loaded, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gk-global")
        monkeypatch.setenv("GITHUB_TOKEN", "gh-test")
        result = resolve_effective_config("owner/repo-b")
        assert result.api_key == "gk-global"

    def test_anthropic_key_resolved_from_env(self, registry_loaded, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-global")
        monkeypatch.setenv("GITHUB_TOKEN", "gh-test")
        result = resolve_effective_config("owner/repo-a")
        assert result.api_key == "sk-global"

    def test_per_repo_gemini_key_overrides_global(self, registry_loaded, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gk-global")
        monkeypatch.setenv("GITHUB_TOKEN", "gh-test")
        monkeypatch.setenv("REPO_OWNER_REPO_B_GEMINI_API_KEY", "gk-per-repo")
        result = resolve_effective_config("owner/repo-b")
        assert result.api_key == "gk-per-repo"
