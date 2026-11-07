"""Hosts such as Render can define a variable with a blank value; that must mean "use the default"."""
from app.core.config import Settings


def test_blank_environment_values_fall_back_to_defaults(monkeypatch):
    for name in ("STORAGE_ROOT", "ONNX_THREADS", "STORAGE_PERSISTENT", "CORS_ORIGINS", "AI_PROVIDER", "LOG_LEVEL"):
        monkeypatch.setenv(name, "")
    settings = Settings(_env_file=None)
    assert settings.storage_root  # filled in, not blank
    assert settings.onnx_threads == 2
    assert settings.storage_persistent is True
    assert settings.ai_provider == "none"
    assert settings.log_level == "INFO"
    assert settings.cors_origin_list  # default origins, never a crash
