from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

MODEL_EXTENSIONS = {".gguf", ".safetensors", ".bin", ".model", ".json"}


def load_local_llm_profile(root: Path) -> dict[str, object]:
    config_path = root / "config" / "suite" / "local_llm.deepseek.v1.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "configured": False,
            "enabled": False,
            "source": str(config_path),
            "disabled_reason": f"profile config unreadable: {type(exc).__name__}: {exc}",
        }
    selected = str(config.get("selected_profile") or "")
    profiles = config.get("profiles") if isinstance(config.get("profiles"), dict) else {}
    profile = profiles.get(selected) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        return {
            "configured": False,
            "enabled": False,
            "source": str(config_path),
            "selected_profile": selected,
            "disabled_reason": "selected local LLM profile is missing",
        }
    model_root = Path(str(os.environ.get("NORTHSTAR_LOCAL_MODEL_ROOT") or profile.get("model_root") or "D:/LLM"))
    base_url_raw = os.environ.get("NORTHSTAR_LOCAL_LLM_BASE_URL") or profile.get("server_base_url") or "http://127.0.0.1:8080/v1"
    base_url = str(base_url_raw).rstrip("/")
    files = count_model_files(model_root)
    enabled = model_root.exists() and files > 0
    return {
        "configured": True,
        "enabled": enabled,
        "source": str(config_path),
        "selected_profile": selected,
        "model_family": str(profile.get("model_family") or selected),
        "recommended_quant": str(profile.get("recommended_quant") or ""),
        "model_root": str(model_root),
        "model_root_exists": model_root.exists(),
        "model_files": files,
        "base_url": base_url,
        "chat_completions_url": base_url + "/chat/completions",
        "provider_mode": os.environ.get("NORTHSTAR_SUITE_LLM_PROVIDER", "auto"),
        "disabled_reason": "" if enabled else "model_root has no local model files yet",
    }


def count_model_files(root: Path) -> int:
    if not root.exists() or not root.is_dir():
        return 0
    try:
        return sum(1 for path in root.rglob("*") if path.is_file() and path.suffix.lower() in MODEL_EXTENSIONS)
    except OSError:
        return 0


def local_llm_scan_fields(root: Path) -> dict[str, Any]:
    profile = load_local_llm_profile(root)
    return {
        "local_llm_provider_mode": profile.get("provider_mode", "auto"),
        "local_llm_configured": int(bool(profile.get("configured", False))),
        "local_llm_enabled": int(bool(profile.get("enabled", False))),
        "local_llm_model_family": str(profile.get("model_family", "")),
        "local_llm_model_root": str(profile.get("model_root", "")),
        "local_llm_model_files": int(profile.get("model_files", 0) or 0),
        "local_llm_base_url": str(profile.get("base_url", "")),
        "local_llm_disabled_reason": str(profile.get("disabled_reason", "")),
    }
