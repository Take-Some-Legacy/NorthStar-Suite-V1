#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from northstar_bridge.workspace_config import apply_workspace_environment, load_workspace_config, resolve_tool_root, resolve_workspace_root

SPIN = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def read_text(path: Path, max_chars: int = 6000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-max_chars:]


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def read_jsonl_tail(path: Path, limit: int = 8) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-max(1, limit * 4):]
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out[-limit:]


def file_age(path: Path) -> str:
    try:
        age = max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return "missing"
    if age < 60:
        return f"{age:.0f}s ago"
    if age < 3600:
        return f"{age / 60:.1f}m ago"
    return f"{age / 3600:.1f}h ago"


def parse_utc(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return dt.datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def age_from_utc(value: Any) -> str:
    ts = parse_utc(value)
    if ts is None:
        return "unknown"
    age = max(0.0, time.time() - ts)
    if age < 60:
        return f"{age:.0f}s"
    return f"{age / 60:.1f}m"


def compact(value: Any, limit: int = 120) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def bar(value: float, width: int = 20) -> str:
    value = max(0.0, min(1.0, value))
    filled = int(round(value * width))
    return "[" + ("█" * filled) + ("░" * (width - filled)) + "]"


def pct_bar(value: str, width: int = 20) -> str:
    try:
        pct = int(float(str(value).replace("%", "").strip()))
    except Exception:
        return "[????????????????????] n/a"
    pct = max(0, min(100, pct))
    return f"{bar(pct / 100, width)} {pct:3d}%"


def first_request_body(text: str, limit: int = 1200) -> str:
    text = text.strip()
    if not text:
        return "<waiting for first operator request>"
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def query_nvidia_smi() -> tuple[list[dict[str, str]], str]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        common = Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe")
        exe = str(common) if common.exists() else ""
    if not exe:
        return [], "nvidia-smi not found"
    fields = [
        "index",
        "name",
        "utilization.gpu",
        "utilization.memory",
        "memory.used",
        "memory.total",
        "temperature.gpu",
        "power.draw",
        "power.limit",
    ]
    cmd = [exe, f"--query-gpu={','.join(fields)}", "--format=csv,noheader,nounits"]
    try:
        proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
    except Exception as exc:
        return [], f"nvidia-smi failed: {type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return [], compact(proc.stderr or proc.stdout or f"nvidia-smi exit={proc.returncode}", 220)
    gpus: list[dict[str, str]] = []
    for line in (proc.stdout or "").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= len(fields):
            gpus.append(dict(zip(fields, parts)))
    return gpus, ""


def query_torch_gpu_fallback(pilot_python: str) -> tuple[list[dict[str, str]], str]:
    pilot_python = str(pilot_python or "").strip()
    if not pilot_python or not Path(pilot_python).exists():
        return [], "pilot python unavailable"
    code = r'''
import json
try:
    import torch
    out=[]
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            free,total=torch.cuda.mem_get_info(i)
            used=total-free
            out.append({
                "index": str(i), "name": torch.cuda.get_device_name(i),
                "utilization.gpu": "n/a", "utilization.memory": "n/a",
                "memory.used": str(int(used/(1024*1024))), "memory.total": str(int(total/(1024*1024))),
                "temperature.gpu": "n/a", "power.draw": "n/a", "power.limit": "n/a"})
    print(json.dumps(out, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"error": type(exc).__name__ + ": " + str(exc)}, ensure_ascii=False))
'''
    try:
        proc = subprocess.run([pilot_python, "-c", code], text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
    except Exception as exc:
        return [], f"torch fallback failed: {type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return [], compact(proc.stderr or proc.stdout or f"torch fallback exit={proc.returncode}", 220)
    try:
        data = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except Exception as exc:
        return [], f"invalid torch fallback JSON: {type(exc).__name__}"
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)], ""
    if isinstance(data, dict) and data.get("error"):
        return [], str(data.get("error"))
    return [], "torch fallback returned no devices"


def query_gpu_load(pilot_python: str) -> tuple[list[dict[str, str]], str, str]:
    gpus, err = query_nvidia_smi()
    if gpus:
        return gpus, "nvidia-smi", ""
    fallback, fallback_err = query_torch_gpu_fallback(pilot_python)
    if fallback:
        return fallback, "torch-fallback", err
    return [], "unavailable", fallback_err or err


def print_gpu_load(pilot_python: str) -> None:
    gpus, source, err = query_gpu_load(pilot_python)
    print("[LIVE GPU LOAD]")
    print(f"source          : {source}")
    if err and source != "nvidia-smi":
        print(f"telemetry_note  : {compact(err, 180)}")
    if not gpus:
        print("gpu             : <no GPU telemetry available>")
        print()
        return
    for gpu in gpus:
        idx = gpu.get("index", "?")
        print(f"gpu:{idx:<2} {gpu.get('name', '?')}")
        print(f"  core          : {pct_bar(gpu.get('utilization.gpu', 'n/a'))}")
        print(f"  memory        : {gpu.get('memory.used','?')} / {gpu.get('memory.total','?')} MiB · mem-util={gpu.get('utilization.memory','n/a')}%")
        print(f"  thermal/power : {gpu.get('temperature.gpu','n/a')} C · {gpu.get('power.draw','n/a')} / {gpu.get('power.limit','n/a')} W")
    print()


def print_events(events: list[dict[str, Any]]) -> None:
    print("[LIVE EVENT TAIL]")
    if not events:
        print("events          : <waiting for loop-events.jsonl>")
        print()
        return
    for item in events[-6:]:
        stamp = item.get("utc") or item.get("time") or item.get("started_utc") or "?"
        cycle = item.get("cycle", "?")
        event = item.get("event") or item.get("message") or item.get("kind") or item.get("status") or "cycle"
        action = item.get("action_id") or item.get("next_command") or ""
        openai = item.get("openai") if isinstance(item.get("openai"), dict) else {}
        if event == "cycle" and openai:
            event = "openai=" + ("ok" if openai.get("ok") else "failed" if openai.get("attempted") else "skipped")
        print(f"- c{cycle} {compact(stamp, 24)} · {compact(event, 78)} {compact(action, 60)}")
    print()


def draw(root: Path, frame: int, interval: float) -> None:
    state_dir = root / ".takesome" / "intelligence"
    state_path = state_dir / "loop-state.json"
    status_path = state_dir / "pilot-status.md"
    request_path = state_dir / "operator-request.md"
    response_path = state_dir / "operator-response.md"
    events_path = state_dir / "loop-events.jsonl"

    state = read_json(state_path)
    status_md = read_text(status_path, max_chars=2600)
    request_md = read_text(request_path, max_chars=1800)
    events = read_jsonl_tail(events_path, limit=32)

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pulse = SPIN[frame % len(SPIN)]
    cycle = state.get("cycle", "?")
    started = state.get("started_utc", "?")
    cycle_age = age_from_utc(started)
    try:
        interval_sec = int(state.get("interval_sec") or 30)
    except Exception:
        interval_sec = 30
    started_ts = parse_utc(started) or time.time()
    elapsed = max(0.0, time.time() - started_ts)
    next_in = max(0.0, interval_sec - (elapsed % max(1, interval_sec)))
    progress = 1.0 - next_in / max(1, interval_sec)

    scan = state.get("scan", {}) if isinstance(state.get("scan"), dict) else {}
    signals = state.get("signals", {}) if isinstance(state.get("signals"), dict) else {}
    openai = state.get("openai", {}) if isinstance(state.get("openai"), dict) else {}
    current_started_ts = parse_utc(state.get("started_utc"))
    if current_started_ts is not None:
        filtered_events = []
        for item in events:
            item_ts = parse_utc(item.get("started_utc") or item.get("utc") or item.get("time"))
            if item_ts is None or item_ts + 0.001 >= current_started_ts:
                filtered_events.append(item)
        events = filtered_events[-8:]
    pilot = state.get("pilot", {}) if isinstance(state.get("pilot"), dict) else {}
    pilot_torch = pilot.get("torch", {}) if isinstance(pilot.get("torch"), dict) else {}
    suite_torch = state.get("suite_python_torch", {}) if isinstance(state.get("suite_python_torch"), dict) else {}
    checks = state.get("self_checks", []) if isinstance(state.get("self_checks"), list) else []
    failed = [c for c in checks if isinstance(c, dict) and not c.get("ok")]
    recommendations = state.get("recommendations", []) if isinstance(state.get("recommendations"), list) else []
    top = recommendations[0] if recommendations and isinstance(recommendations[0], dict) else {}

    clear()
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║ NorthStar Suite Intelligence — LLM Pilot Live Heartbeat                     ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print(f"{pulse} local_time      : {now}")
    print(f"cycle           : {cycle} · age={cycle_age} · next≈{next_in:04.1f}s {bar(progress, 18)}")
    print(f"freshness       : state={file_age(state_path)} · status={file_age(status_path)} · request={file_age(request_path)} · response={file_age(response_path)}")
    print("domain          : suite.tool_plane monitor; observes engine.ai, does not implement engine.ai")
    print("scope           : tools + plugins + engine + gameplay-AI domain health")
    print()

    print("[HEARTBEAT]")
    print(f"self_checks     : {'OK' if not failed else str(len(failed)) + ' FAILING'}")
    print(f"workspace       : changed={scan.get('changed_files', '?')} · branch={scan.get('git_branch', '?')} · build_err_logs={scan.get('recent_build_error_logs', '?')}")
    print(f"engine          : root={scan.get('engine_root_exists', '?')} cargo={scan.get('engine_cargo_exists', '?')} rust={scan.get('engine_rust_files', '?')}")
    print(f"plugins         : source={scan.get('source_plugins', '?')} installed_dll={scan.get('engine_plugins_installed', '?')} descriptors={scan.get('plugin_descriptors', '?')}")
    print(f"tools           : actions={scan.get('suite_actions', '?')} descriptors={scan.get('toolbelt_tool_descriptors', '?')} py={scan.get('take_some_python_files', '?')}")
    print(f"signals         : errors={signals.get('error', 0)} warnings={signals.get('warning', 0)} tools={signals.get('tools', 0)} plugins={signals.get('plugins', 0)} engine={signals.get('engine', 0)} game_ai={signals.get('game_ai', 0)}")
    print()

    print("[GPU PILOT]")
    print(f"pilot_python    : {pilot.get('python', '<not configured>')}")
    print(f"pilot_torch     : {pilot_torch.get('version', '?')} cuda={pilot_torch.get('cuda_available', '?')} devices={pilot_torch.get('cuda_device_count', '?')} selected={pilot_torch.get('selected_device', '?')}")
    devices = pilot_torch.get("cuda_devices") if isinstance(pilot_torch.get("cuda_devices"), list) else []
    if devices:
        print("pilot_devices   : " + ", ".join(str(x) for x in devices))
    print(f"suite_python    : torch={suite_torch.get('version', '?')} selected={suite_torch.get('selected_device', '?')}")
    print()
    print_gpu_load(str(pilot.get("python", "")))

    print("[OPENAI CHANNEL]")
    print(f"configured      : {openai.get('configured', '?')} · attempted={openai.get('attempted', '?')} · ok={openai.get('ok', '?')} · model={openai.get('model', '?')}")
    print(f"key_source      : {openai.get('source', '<unknown>')}")
    if 'insufficient_quota' in str(openai.get('error') or ''):
        print("quota_owner_hint: API project/org that owns this key is out of quota/budget; ChatGPT subscription is separate")
    if openai.get("error"):
        print(f"last_error      : {compact(openai.get('error'), 220)}")
    if openai.get("summary"):
        print(f"summary         : {compact(openai.get('summary'), 220)}")
    print()

    print("[CURRENT PROPOSAL]")
    print(f"action_id       : {top.get('action_id', 'none')}")
    print(f"label           : {top.get('label', '')}")
    print(f"score           : {top.get('score', '')} · risk={top.get('risk_level', '')} · domain={top.get('target_domain', '')}")
    reasons = top.get("reasons") if isinstance(top.get("reasons"), list) else []
    if reasons:
        print("why             : " + "; ".join(str(x) for x in reasons[:3]))
    print(f"next_command    : {state.get('next_command', '')}")
    print()

    print_events(events)

    print("[OPERATOR REQUEST]")
    print(first_request_body(request_md))
    print()

    print("[PILOT STATUS TAIL]")
    print(status_md[-1300:] if status_md else "<pilot-status.md has not been written yet>")
    print()
    print("Press Ctrl+C to close this heartbeat window. Main serverBridge keeps running.")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Live heartbeat viewer for NorthStar Suite Intelligence LLM pilot")
    parser.add_argument("--root", default="auto")
    parser.add_argument("--workspace-config", default="")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args(argv)
    launch_root = Path.cwd().resolve()
    workspace_config = load_workspace_config(launch_root, args.workspace_config)
    root = resolve_workspace_root(launch_root, args.root, workspace_config)
    tool_root = resolve_tool_root(launch_root, workspace_config)
    apply_workspace_environment(root, workspace_config, tool_root)
    frame = 0
    try:
        while True:
            draw(root, frame, max(1.0, args.interval))
            frame += 1
            time.sleep(max(1.0, args.interval))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
