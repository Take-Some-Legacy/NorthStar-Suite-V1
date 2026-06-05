from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


DEFAULT_PILOT_PYTHON = Path(r"D:\TakeSomeData\venvs\northstar-llm-pilot\Scripts\python.exe")
DEFAULT_MODEL_ROOT = Path(r"D:\LLM\DeepSeek-R1-Distill-Qwen-7B-PyTorch")
RESULT_REL = Path(".takesome") / "intelligence" / "smoke-deepseek.json"


def _status_from_steps(steps: list[dict[str, Any]]) -> dict[str, bool]:
    by_name = {str(step.get("name")): bool(step.get("ok")) for step in steps}
    return {
        "runtime_ok": by_name.get("python", False)
        and by_name.get("torch_import", False)
        and by_name.get("transformers_import", False)
        and by_name.get("accelerate_import", False)
        and by_name.get("safetensors_import", False),
        "cuda_ok": by_name.get("cuda_probe", False),
        "model_ok": by_name.get("model_root", False) and by_name.get("config_load", False),
        "tokenizer_ok": by_name.get("tokenizer_load", False),
        "generation_ok": by_name.get("tiny_generate", False),
    }


def _classify(result: dict[str, Any]) -> dict[str, Any]:
    flags = _status_from_steps(result.get("steps", []) if isinstance(result.get("steps"), list) else [])
    result.update(flags)
    if flags["runtime_ok"] and flags["cuda_ok"] and flags["model_ok"] and flags["tokenizer_ok"] and flags["generation_ok"]:
        result["status"] = "OK"
        result["ok"] = True
        result["partial"] = False
    elif flags["runtime_ok"] and flags["cuda_ok"] and flags["model_ok"] and flags["tokenizer_ok"]:
        result["status"] = "PARTIAL"
        result["ok"] = True
        result["partial"] = True
    else:
        result["status"] = "FAIL"
        result["ok"] = False
        result["partial"] = False
    return result


def _inner_smoke_code(model_root: Path, try_generate: bool) -> str:
    return rf'''
from __future__ import annotations
import json, os, time, traceback
from pathlib import Path
out = {{"schema":"northstar.deepseek_smoke.v1", "ok": False, "partial": False, "status": "FAIL", "steps": []}}
model_root = Path(r"{model_root}")
try_generate = {"True" if try_generate else "False"}

def step(name, ok, **kw):
    item = {{"name": name, "ok": bool(ok)}}
    item.update(kw)
    out["steps"].append(item)

try:
    import sys
    step("python", True, executable=sys.executable)
    import torch
    step("torch_import", True, version=getattr(torch, "__version__", "?"), cuda=getattr(getattr(torch, "version", object()), "cuda", None))
    cuda = bool(torch.cuda.is_available())
    devices = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if cuda else []
    step("cuda_probe", cuda, device_count=torch.cuda.device_count() if cuda else 0, devices=devices, selected="cuda:0" if cuda else "cpu")
    import transformers
    step("transformers_import", True, version=getattr(transformers, "__version__", "?"))
    import accelerate
    step("accelerate_import", True, version=getattr(accelerate, "__version__", "?"))
    import safetensors
    step("safetensors_import", True, version=getattr(safetensors, "__version__", "?"))
    from transformers import AutoConfig, AutoTokenizer
    exists = model_root.exists()
    files = sorted(str(p.relative_to(model_root)) for p in model_root.rglob("*") if p.is_file()) if exists else []
    step("model_root", exists, path=str(model_root), file_count=len(files), first_files=files[:24])
    t0 = time.time()
    cfg = AutoConfig.from_pretrained(str(model_root), trust_remote_code=True, local_files_only=True)
    step("config_load", True, model_type=getattr(cfg, "model_type", "?"), architectures=getattr(cfg, "architectures", []), elapsed_sec=round(time.time()-t0, 2))
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(str(model_root), trust_remote_code=True, local_files_only=True)
    encoded = tok("NorthStar smoke test:", return_tensors="pt")
    step("tokenizer_load", True, vocab_size=getattr(tok, "vocab_size", None), encoded_tokens=int(encoded["input_ids"].shape[-1]), elapsed_sec=round(time.time()-t0, 2))
    if not try_generate:
        step("tiny_generate", False, skipped=True, reason="generation disabled for metadata smoke")
    else:
        from transformers import AutoModelForCausalLM
        t0 = time.time()
        kwargs = dict(trust_remote_code=True, local_files_only=True, dtype=torch.float16 if cuda else torch.float32)
        if cuda:
            kwargs["device_map"] = "auto"
            kwargs["max_memory"] = {{0: "9GiB", 1: "9GiB", "cpu": "24GiB"}}
            os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
        model = AutoModelForCausalLM.from_pretrained(str(model_root), **kwargs)
        model.eval()
        device = next(model.parameters()).device
        encoded = {{k: v.to(device) for k, v in encoded.items()}}
        with torch.no_grad():
            gen = model.generate(**encoded, max_new_tokens=8, do_sample=False, pad_token_id=tok.eos_token_id)
        text = tok.decode(gen[0], skip_special_tokens=True)
        step("tiny_generate", True, elapsed_sec=round(time.time()-t0, 2), first_param_device=str(device), output=text[:240])
except Exception as exc:
    step("exception", False, type=type(exc).__name__, message=str(exc)[-1200:], traceback=traceback.format_exc()[-2400:])
print(json.dumps(out, ensure_ascii=False, indent=2))
'''


def run_deepseek_smoke(root: Path, args: argparse.Namespace | None = None) -> int:
    pilot_python = Path(
        str(
            getattr(args, "pilot_python", "")
            or os.environ.get("NORTHSTAR_SUITE_LLM_PYTHON")
            or DEFAULT_PILOT_PYTHON
        )
    )
    model_root = Path(
        str(
            getattr(args, "model_root", "")
            or os.environ.get("NORTHSTAR_LOCAL_MODEL_ROOT")
            or DEFAULT_MODEL_ROOT
        )
    )
    try_generate = str(os.environ.get("NORTHSTAR_DEEPSEEK_SMOKE_GENERATE", "1")).lower() not in {"0", "false", "no"}
    timeout_sec = int(os.environ.get("NORTHSTAR_DEEPSEEK_SMOKE_TIMEOUT_SEC", "420") or "420")
    result_path = root / RESULT_REL
    result_path.parent.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "schema": "northstar.deepseek_smoke.v1",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pilot_python": str(pilot_python),
        "model_root": str(model_root),
        "try_generate": try_generate,
        "ok": False,
        "partial": False,
        "status": "FAIL",
        "steps": [],
    }

    if not pilot_python.exists():
        result["steps"].append({"name": "python", "ok": False, "error": "pilot python does not exist"})
        _classify(result)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("[ERROR] DeepSeek smoke: pilot python is missing")
        print(f"[INFO] Result: {RESULT_REL}")
        return 2

    env = os.environ.copy()
    env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    proc = subprocess.run(
        [str(pilot_python), "-c", _inner_smoke_code(model_root, try_generate)],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_sec,
        env=env,
    )
    payload = (proc.stdout or "").strip()
    try:
        parsed = json.loads(payload.splitlines()[-1] if payload else "{}")
    except Exception:
        parsed = {"steps": [{"name": "smoke_json_parse", "ok": False, "stdout_tail": payload[-4000:]}]}
    if isinstance(parsed, dict):
        result.update(parsed)
    if proc.stderr:
        result["stderr_tail"] = proc.stderr[-4000:]
    result["process_exit_code"] = proc.returncode
    _classify(result)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[STATE] DeepSeek smoke status={result['status']} runtime_ok={result['runtime_ok']} cuda_ok={result['cuda_ok']} model_ok={result['model_ok']} tokenizer_ok={result['tokenizer_ok']} generation_ok={result['generation_ok']}")
    for step in result.get("steps", []):
        name = step.get("name")
        ok = "OK" if step.get("ok") else "WARN"
        detail = ""
        if step.get("type"):
            detail = f" type={step.get('type')}"
        if step.get("message"):
            detail += f" message={str(step.get('message'))[:240]}"
        if step.get("skipped"):
            detail += f" skipped={step.get('reason', '')}"
        print(f"[{ok}] {name}{detail}")
    print(f"[INFO] Result: {RESULT_REL}")
    return 0 if result.get("ok") else 1
