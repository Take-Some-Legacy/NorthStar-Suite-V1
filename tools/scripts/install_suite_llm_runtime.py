from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

RUNTIME_PACKAGES = [
    "transformers",
    "accelerate",
    "safetensors",
    "huggingface_hub",
]
TORCH_PACKAGES = ["torch", "torchvision", "torchaudio"]
TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu118"
REPORT = Path(".takesome/intelligence/llm-runtime-install-report.json")
MODEL_ROOT = Path(r"D:\LLM\DeepSeek-R1-Distill-Qwen-7B-PyTorch")
MODEL_ID = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> dict[str, object]:
    print("[CMD]", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    if proc.stdout:
        print(proc.stdout[-12000:], flush=True)
    return {"cmd": cmd, "exit_code": proc.returncode, "output_tail": (proc.stdout or "")[-12000:]}


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    MODEL_ROOT.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []

    results.append(run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"]))
    results.append(run([sys.executable, "-m", "pip", "install", *TORCH_PACKAGES, "--index-url", TORCH_CUDA_INDEX]))
    results.append(run([sys.executable, "-m", "pip", "install", *RUNTIME_PACKAGES]))

    modules = {name: module_available(name) for name in ["torch", *RUNTIME_PACKAGES]}
    torch_status: dict[str, object] = {"available": modules.get("torch", False)}
    if modules.get("torch", False):
        import torch  # type: ignore

        torch_status = {
            "available": True,
            "version": getattr(torch, "__version__", "unknown"),
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
            "devices": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if torch.cuda.is_available() else [],
        }

    download_result: dict[str, object] = {"attempted": False}
    if modules.get("huggingface_hub", False):
        from huggingface_hub import snapshot_download  # type: ignore

        print(f"[INFO] downloading {MODEL_ID} -> {MODEL_ROOT}", flush=True)
        path = snapshot_download(repo_id=MODEL_ID, local_dir=str(MODEL_ROOT), local_dir_use_symlinks=False)
        download_result = {"attempted": True, "ok": True, "path": path}

    model_files = 0
    if MODEL_ROOT.exists():
        model_files = sum(1 for p in MODEL_ROOT.rglob("*") if p.is_file())

    report = {
        "schema": "northstar.suite.llm_runtime_install_report.v1",
        "python": sys.executable,
        "results": results,
        "modules": modules,
        "torch": torch_status,
        "model_id": MODEL_ID,
        "model_root": str(MODEL_ROOT),
        "model_root_exists": MODEL_ROOT.exists(),
        "model_files": model_files,
        "download": download_result,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] report={REPORT}")
    return 0 if modules.get("torch") and modules.get("transformers") and modules.get("huggingface_hub") else 1


if __name__ == "__main__":
    raise SystemExit(main())
