"""Tests for cave_onc.config — secret masking, env loading, validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from cave_onc.config import Settings, get_settings


class TestSecretMasking:
    """SecretStr fields must never leak into repr / str."""

    API_KEY_FIELDS = [
        "cdisc_library_api_key",
        "cdisc_library_api_key_secondary",
        "deepseek_api_key",
        "glm_api_key",
    ]

    @pytest.fixture(autouse=True)
    def _set_fake_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Inject a known fake value into every API key env var."""
        for field in self.API_KEY_FIELDS:
            env_name = field.upper()
            monkeypatch.setenv(env_name, "sk-FAKE-VALUE-12345")

    def test_repr_hides_keys(self) -> None:
        settings = Settings()  # type: ignore[call-arg]
        r = repr(settings)
        assert "sk-FAKE-VALUE-12345" not in r

    def test_str_hides_keys(self) -> None:
        settings = Settings()  # type: ignore[call-arg]
        s = str(settings)
        assert "sk-FAKE-VALUE-12345" not in s

    def test_model_dump_hides_keys(self) -> None:
        settings = Settings()  # type: ignore[call-arg]
        dumped = settings.model_dump()
        for field in self.API_KEY_FIELDS:
            assert isinstance(dumped[field], SecretStr)
        # JSON serialization must mask values
        dumped_json = settings.model_dump(mode="json")
        for field in self.API_KEY_FIELDS:
            assert "sk-FAKE-VALUE-12345" not in dumped_json[field]


class TestDefaults:
    """All API key fields are Optional and default to None when unset."""

    def test_keys_none_by_default(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # Remove env vars and chdir to a clean tmp_path with no .env file
        for var in (
            "CDISC_LIBRARY_API_KEY",
            "CDISC_LIBRARY_API_KEY_SECONDARY",
            "DEEPSEEK_API_KEY",
            "GLM_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.chdir(tmp_path)

        settings = Settings()  # type: ignore[call-arg]
        assert settings.cdisc_library_api_key is None
        assert settings.cdisc_library_api_key_secondary is None
        assert settings.deepseek_api_key is None
        assert settings.glm_api_key is None

    def test_defaults_populated(self) -> None:
        settings = Settings()  # type: ignore[call-arg]
        assert settings.deepseek_base_url == "https://api.deepseek.com"
        assert settings.deepseek_model == "deepseek-chat"
        assert settings.glm_base_url == "https://open.bigmodel.cn/api/paas/v4"
        assert settings.glm_model == "glm-4.6"
        assert settings.local_llm_model == "qwen2.5-7b-instruct"
        assert settings.audit_db_path == Path("audit/cave_audit.db")


class TestEnvLoading:
    """Settings correctly reads from environment variables."""

    def test_deepseek_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.deepseek_api_key is not None
        assert settings.deepseek_api_key.get_secret_value() == "sk-test-deepseek"

    def test_base_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GLM_BASE_URL", "http://localhost:8080")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.glm_base_url == "http://localhost:8080"


class TestGetSettings:
    """get_settings() returns a cached singleton."""

    def test_caching(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEEPSEEK_MODEL", "test-model")
        # Clear the lru_cache to pick up new env
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
        assert s1.deepseek_model == "test-model"
        # Clean up cache for other tests
        get_settings.cache_clear()
