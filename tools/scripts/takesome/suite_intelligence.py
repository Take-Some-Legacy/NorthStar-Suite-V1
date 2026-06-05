from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import rel
from .suite.registry import build_suite_registry


@dataclass(frozen=True)
class TorchStatus:
    available: bool
    version: str = ""
    cuda_available: bool = False
    cuda_device_count: int = 0
    cuda_devices: tuple[str, ...] = ()
    selected_device: str = "cpu"
    error: str = ""


@dataclass(frozen=True)
class OpenAIStatus:
    configured: bool
    source: str = "missing"
    model: str = "gpt-5.2"
    attempted: bool = False
    ok: bool = False
    summary: str = ""
    error: str = ""


@dataclass(frozen=True)
class TaskCandidate:
    action_id: str
    label: str
    detail: str
    category: str
    target_domain: str
    primary_tag: str
    risk_level: str
    profile: str
    features: tuple[float, ...]
    score: float
    reasons: tuple[str, ...]


_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("error", re.compile(r"\b(ERROR|error:|failed|panic|traceback|exception)\b", re.IGNORECASE)),
    ("warning", re.compile(r"\b(WARN|warning:)\b", re.IGNORECASE)),
    ("tools", re.compile(r"\b(tool|toolbelt|packer|registry|descriptor|doctor)\b", re.IGNORECASE)),
    ("plugins", re.compile(r"\b(plugin|plugins|cargo|rustc|dll|codec)\b", re.IGNORECASE)),
    ("engine", re.compile(r"\b(engine|runtime|neocore2|ecs|scene|world|render|physics|assets|input|gateway)\b", re.IGNORECASE)),
    ("game_ai", re.compile(r"\b(engine\.ai|gameplay ai|npc|perception|behavior|intent|AiFrameInput|AiFrameOutput)\b", re.IGNORECASE)),
    ("ui", re.compile(r"\b(ui|neui|aurelia|font|surface|widget)\b", re.IGNORECASE)),
    ("textures", re.compile(r"\b(ytd|texture|dds|mip|rgba|netd)\b", re.IGNORECASE)),
    ("metadata", re.compile(r"\b(ytyp|metadata|archetype|xml)\b", re.IGNORECASE)),
    ("vendor", re.compile(r"\b(vendor|gnuwin32|diff|sed|tail|tar|fgrep|third.party|third-party)\b", re.IGNORECASE)),
)

_RISK_WEIGHT = {
    "readonly": 0.08,
    "safe": 0.12,
    "normal": 0.20,
    "writes_workspace": -0.15,
    "dangerous": -0.50,
}

_TAG_WEIGHT = {
    "TOOLS": 0.30,
    "ACTION": 0.14,
    "BUILD": 0.10,
    "PLUGIN": 0.16,
    "ENGINE": 0.18,
    "RUN": -0.10,
    "CLEAN": -0.28,
    "PACK": -0.05,
}

_MAX_OPENAI_CONTEXT_CHARS = 18000
_OPENAI_TIMEOUT_SEC = 45


def suite_intelligence_command(root: Path, args: argparse.Namespace) -> int:
    goal = str(getattr(args, "goal", "") or "").strip()
    output = str(getattr(args, "output", "") or "").strip()
    top = max(1, int(getattr(args, "top", 8) or 8))
    json_mode = bool(getattr(args, "json", False))
    no_openai = bool(getattr(args, "no_openai", False))
    self_check_only = bool(getattr(args, "self_check", False))
    openai_model = str(getattr(args, "openai_model", "") or os.environ.get("NORTHSTAR_SUITE_OPENAI_MODEL") or "gpt-5.5").strip()

    torch_status = detect_torch_status()
    log_text, log_sources = collect_context_logs(root)
    scan = scan_suite_workspace(root)
    signals = classify_signals(goal, log_text)
    registry = build_suite_registry(root)
    candidates = score_actions(registry.actions(), goal=goal, signals=signals, torch_status=torch_status)
    selected = candidates[:top]
    self_checks = run_self_checks(root, registry_actions=[candidate.action_id for candidate in candidates], torch_status=torch_status)

    openai_status = OpenAIStatus(configured=bool(read_openai_key(root)[0]), source=read_openai_key(root)[1], model=openai_model)
    openai_advice = ""
    if not no_openai and not self_check_only:
        openai_status, openai_advice = ask_openai_for_task_plan(
            root=root,
            goal=goal,
            model=openai_model,
            scan=scan,
            signals=signals,
            recommendations=[candidate_to_json(candidate) for candidate in selected],
            log_sources=[rel(root, path) for path in log_sources],
        )

    result = {
        "schema": "northstar.suite_intelligence.report.v2",
        "goal": goal,
        "self_check_only": self_check_only,
        "torch": torch_status_to_json(torch_status),
        "openai": openai_status_to_json(openai_status),
        "openai_advice": openai_advice,
        "self_checks": self_checks,
        "scan": scan,
        "signals": signals,
        "log_sources": [rel(root, path) for path in log_sources],
        "recommendations": [candidate_to_json(candidate) for candidate in selected],
        "next_command": f"python tools/scripts/takesome.py suite --run {selected[0].action_id}" if selected else "",
        "notes": build_notes(torch_status, openai_status),
    }

    if output:
        out_path = (root / output).resolve() if not Path(output).is_absolute() else Path(output)
    else:
        out_path = root / ".takesome" / "intelligence" / "suite-task-report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if all(check["ok"] for check in self_checks) else 1

    print("[INFO] NorthStar Suite Intelligence — self-check, scan, OpenAI task analysis")
    print(f"[INFO] Report: {rel(root, out_path)}")
    if goal:
        print(f"[INFO] Goal: {goal}")
    print(_torch_line(torch_status))
    print(_openai_line(openai_status))
    print("[SCAN] " + ", ".join(f"{key}={value}" for key, value in scan.items()))
    print("[SELF-CHECK]")
    for check in self_checks:
        tag = "OK" if check["ok"] else "ERROR"
        print(f"  [{tag}] {check['name']}: {check['detail']}")
    print("[INFO] Signals: " + ", ".join(f"{key}={value}" for key, value in signals.items()))
    print("[PLAN] Recommended suite actions:")
    for index, candidate in enumerate(selected, start=1):
        reasons = "; ".join(candidate.reasons[:3])
        print(f"  {index}. {candidate.action_id:<32} score={candidate.score:.3f} [{candidate.primary_tag}] {candidate.label}")
        if reasons:
            print(f"     why: {reasons}")
    if openai_advice:
        print("[OPENAI] " + openai_advice.replace("\n", "\n[OPENAI] "))
    if selected:
        print(f"[NEXT] {result['next_command']}")
    for note in result["notes"]:
        print(f"[NOTE] {note}")
    return 0 if all(check["ok"] for check in self_checks) else 1


def detect_torch_status() -> TorchStatus:
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on operator machine
        return TorchStatus(available=False, error=f"{type(exc).__name__}: {exc}")

    try:
        cuda_available = bool(torch.cuda.is_available())
        count = int(torch.cuda.device_count()) if cuda_available else 0
        names: list[str] = []
        for index in range(count):
            try:
                names.append(str(torch.cuda.get_device_name(index)))
            except Exception:
                names.append(f"cuda:{index}")
        selected = "cuda:0" if cuda_available and count > 0 else "cpu"
        return TorchStatus(
            available=True,
            version=str(getattr(torch, "__version__", "unknown")),
            cuda_available=cuda_available,
            cuda_device_count=count,
            cuda_devices=tuple(names),
            selected_device=selected,
        )
    except Exception as exc:  # pragma: no cover - defensive diagnostics
        return TorchStatus(available=True, version=str(getattr(torch, "__version__", "unknown")), error=f"{type(exc).__name__}: {exc}")



def detect_torch_status_for_python(python_executable: str) -> TorchStatus:
    exe = str(python_executable or "").strip()
    if not exe:
        return TorchStatus(available=False, error="NORTHSTAR_SUITE_LLM_PYTHON is not configured")
    code = (
        "import json, torch; "
        "print(json.dumps({"
        "'available': True, "
        "'version': getattr(torch, '__version__', 'unknown'), "
        "'cuda_available': bool(torch.cuda.is_available()), "
        "'cuda_device_count': int(torch.cuda.device_count()) if torch.cuda.is_available() else 0, "
        "'cuda_devices': [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if torch.cuda.is_available() else [], "
        "'selected_device': 'cuda:0' if torch.cuda.is_available() and torch.cuda.device_count() > 0 else 'cpu'"
        "}, ensure_ascii=False))"
    )
    try:
        completed = subprocess.run([exe, "-c", code], text=True, capture_output=True, timeout=60)
    except Exception as exc:
        return TorchStatus(available=False, error=f"{type(exc).__name__}: {exc}")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-1000:]
        return TorchStatus(available=False, error=f"external python exited {completed.returncode}: {detail}")
    try:
        data = json.loads(completed.stdout.strip())
    except Exception as exc:
        return TorchStatus(available=False, error=f"external python returned invalid json: {type(exc).__name__}: {exc}")
    return TorchStatus(
        available=bool(data.get("available")),
        version=str(data.get("version") or ""),
        cuda_available=bool(data.get("cuda_available")),
        cuda_device_count=int(data.get("cuda_device_count") or 0),
        cuda_devices=tuple(str(x) for x in data.get("cuda_devices") or []),
        selected_device=str(data.get("selected_device") or "cpu"),
        error="",
    )


def detect_external_torch_status(python_exe: str) -> dict[str, object]:
    """Probe the Suite/tool-plane LLM pilot Python without importing it into this process."""
    python_exe = str(python_exe or "").strip()
    if not python_exe:
        return {"available": False, "configured": False, "error": "NORTHSTAR_SUITE_LLM_PYTHON is not set"}
    exe_path = Path(python_exe)
    if not exe_path.exists():
        return {"available": False, "configured": True, "python": python_exe, "error": "pilot python does not exist"}
    probe = (
        "import json, sys\n"
        "try:\n"
        "    import torch\n"
        "    payload={\n"
        "      'available': True,\n"
        "      'configured': True,\n"
        "      'python': sys.executable,\n"
        "      'version': getattr(torch, '__version__', 'unknown'),\n"
        "      'cuda': getattr(getattr(torch, 'version', object()), 'cuda', None),\n"
        "      'cuda_available': bool(torch.cuda.is_available()),\n"
        "      'cuda_device_count': int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,\n"
        "      'cuda_devices': [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if torch.cuda.is_available() else [],\n"
        "      'selected_device': 'cuda:0' if torch.cuda.is_available() and torch.cuda.device_count() > 0 else 'cpu',\n"
        "      'error': ''\n"
        "    }\n"
        "except Exception as exc:\n"
        "    payload={'available': False, 'configured': True, 'python': sys.executable, 'error': type(exc).__name__ + ': ' + str(exc)}\n"
        "print(json.dumps(payload, ensure_ascii=False))\n"
    )
    try:
        completed = subprocess.run([str(exe_path), "-c", probe], text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
    except Exception as exc:
        return {"available": False, "configured": True, "python": python_exe, "error": f"{type(exc).__name__}: {exc}"}
    if completed.returncode != 0:
        return {"available": False, "configured": True, "python": python_exe, "error": (completed.stderr or completed.stdout or f"exit_code={completed.returncode}")[-1000:]}
    try:
        data = json.loads((completed.stdout or "").strip().splitlines()[-1])
    except Exception as exc:
        return {"available": False, "configured": True, "python": python_exe, "error": f"invalid probe output: {type(exc).__name__}: {(completed.stdout or '')[-500:]}"}
    if isinstance(data, dict):
        return data
    return {"available": False, "configured": True, "python": python_exe, "error": "probe returned non-object JSON"}


def collect_context_logs(root: Path) -> tuple[str, list[Path]]:
    candidates: list[Path] = []
    for name in ("lastbuild.log", "lastbuild-all.log"):
        path = root / name
        if path.exists():
            candidates.append(path)
    candidates.extend(sorted(root.glob("buildERR-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:3])
    incidents = root / ".takesome" / "incidents"
    if incidents.exists():
        candidates.extend(sorted(incidents.glob("*/summary.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:3])

    parts: list[str] = []
    used: list[Path] = []
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        used.append(path)
        parts.append(f"\n--- {path.name} ---\n{text[-12000:]}")
    return "\n".join(parts), used


def scan_suite_workspace(root: Path) -> dict[str, int | str]:
    actions_dir = root / "tools" / "suite" / "actions"
    scripts_dir = root / "tools" / "scripts" / "takesome"
    toolbelt_dir = root / "tools" / "toolbelt"
    engine_root = root / "EngineRepo" / "NewEngine" / "neocore2"
    if not engine_root.exists():
        engine_root = root / "NewEngine" / "neocore2"
    plugins_root = engine_root / "plugins"
    source_plugins_root = root / "Plugins"
    cargo_toml = engine_root / "Cargo.toml"
    status = _git_status_short(root)
    last_build = root / "lastbuild-all.log"
    last_build_errs = sorted(root.glob("buildERR-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "suite_actions": _count_files(actions_dir, "*.json"),
        "take_some_python_files": _count_files(scripts_dir, "*.py"),
        "toolbelt_tool_descriptors": _count_files(toolbelt_dir, "tool.json"),
        "engine_root_exists": 1 if engine_root.exists() else 0,
        "engine_cargo_exists": 1 if cargo_toml.exists() else 0,
        "engine_rust_files": _count_files(engine_root, "*.rs"),
        "engine_cargo_tomls": _count_files(engine_root, "Cargo.toml"),
        "engine_plugins_installed": _count_files(plugins_root, "*.dll"),
        "source_plugins": _count_files(source_plugins_root, "Cargo.toml"),
        "plugin_descriptors": _count_files(source_plugins_root, "*.json"),
        "recent_build_error_logs": len(last_build_errs),
        "lastbuild_all_exists": 1 if last_build.exists() else 0,
        "changed_files": len([line for line in status.splitlines() if line.strip()]),
        "git_branch": _git_branch(root),
        "script_python": sys.executable,
    }


def run_self_checks(root: Path, *, registry_actions: list[str], torch_status: TorchStatus) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    cli_path = root / "tools" / "scripts" / "takesome.py"
    checks.append(_check("takesome.py exists", cli_path.exists(), rel(root, cli_path)))
    checks.append(_check("suite-intelligence registry hook registered", "suite-intelligence" in _read_text(root / "tools" / "scripts" / "takesome" / "commands" / "cli_hooks.py"), "registry command hook should exist"))
    checks.append(_check("suite action descriptor exists", (root / "tools" / "suite" / "actions" / "suite.intelligence.analyze.json").exists(), "tools/suite/actions/suite.intelligence.analyze.json"))
    checks.append(_check("suite registry sees intelligence action", "suite.intelligence.analyze" in registry_actions, "action_id=suite.intelligence.analyze"))
    engine_root = root / "EngineRepo" / "NewEngine" / "neocore2"
    if not engine_root.exists():
        engine_root = root / "NewEngine" / "neocore2"
    checks.append(_check("engine root exists", engine_root.exists(), rel(root, engine_root)))
    checks.append(_check("engine Cargo.toml exists", (engine_root / "Cargo.toml").exists(), rel(root, engine_root / "Cargo.toml")))
    checks.append(_check("plugin build actions registered", any(action.startswith("plugins.build") for action in registry_actions), "plugins.build.* actions should exist"))
    checks.append(_check("runtime run action registered", any(action.startswith("runtime.run") for action in registry_actions), "runtime.run.* actions should exist"))
    checks.append(_check("PyTorch import path checked", True, _torch_line(torch_status)))
    key, source = read_openai_key(root)
    checks.append(_check("OpenAI key configured", bool(key), f"source={source}" if key else "OPENAI_API_KEY or suite secret cache is missing"))
    return checks


def classify_signals(goal: str, log_text: str) -> dict[str, int]:
    corpus = f"{goal}\n{log_text}"
    signals: dict[str, int] = {}
    for key, pattern in _SIGNAL_PATTERNS:
        signals[key] = len(pattern.findall(corpus))
    signals["has_goal"] = 1 if goal.strip() else 0
    return signals


def score_actions(actions: tuple[Any, ...], *, goal: str, signals: dict[str, int], torch_status: TorchStatus) -> list[TaskCandidate]:
    raw: list[tuple[Any, tuple[float, ...], tuple[str, ...]]] = []
    goal_terms = set(_tokens(goal))
    max_signal = max([1, *signals.values()])

    for action in actions:
        text = " ".join([action.key, action.label, action.detail, action.category, action.target_domain, action.primary_tag]).lower()
        action_terms = set(_tokens(text))
        overlap = len(goal_terms & action_terms) / max(1, len(goal_terms)) if goal_terms else 0.0
        domain_signal = float(signals.get(action.target_domain, 0) + signals.get(action.category, 0)) / max_signal
        tool_signal = float(signals.get("tools", 0)) / max_signal
        error_signal = float(signals.get("error", 0)) / max_signal
        warning_signal = float(signals.get("warning", 0)) / max_signal
        risk = _RISK_WEIGHT.get(str(action.risk_level), 0.0)
        tag = _TAG_WEIGHT.get(str(action.primary_tag), 0.0)
        validate_hint = 1.0 if any(word in text for word in ("validate", "doctor", "test", "status", "list")) else 0.0
        build_hint = 1.0 if any(word in text for word in ("build", "compile", "sync")) else 0.0
        destructive_penalty = -1.0 if any(word in text for word in ("clean", "delete", "remove")) else 0.0
        features = (
            overlap,
            domain_signal,
            tool_signal,
            error_signal,
            warning_signal,
            risk,
            tag,
            validate_hint,
            build_hint,
            destructive_penalty,
        )
        reasons = _reasons(action, overlap, domain_signal, validate_hint, build_hint, destructive_penalty, torch_status)
        raw.append((action, features, reasons))

    scores = _score_with_torch([features for _, features, _ in raw], torch_status)
    candidates: list[TaskCandidate] = []
    for (action, features, reasons), score in zip(raw, scores):
        candidates.append(
            TaskCandidate(
                action_id=action.key,
                label=action.label,
                detail=action.detail,
                category=action.category,
                target_domain=action.target_domain,
                primary_tag=action.primary_tag,
                risk_level=action.risk_level,
                profile=action.profile,
                features=features,
                score=float(score),
                reasons=reasons,
            )
        )
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


def ask_openai_for_task_plan(
    *,
    root: Path,
    goal: str,
    model: str,
    scan: dict[str, int | str],
    signals: dict[str, int],
    recommendations: list[dict[str, object]],
    log_sources: list[str],
) -> tuple[OpenAIStatus, str]:
    key, source = read_openai_key(root)
    if not key:
        return OpenAIStatus(configured=False, source=source, model=model, attempted=False, ok=False, error="missing API key"), ""

    prompt = {
        "role": "NorthStar Suite/tool-plane planner for tools, plugins and engine health",
        "rules": [
            "Do not invent commands. Recommend only action_id values present in recommendations.",
            "Prefer validation/self-check actions before build/write actions.",
            "Scope includes tools, plugins, engine source, engine runtime, build logs, and gameplay AI domain health such as engine.ai, but the LLM pilot itself is not engine.ai.",
            "Return concise operator guidance in Russian.",
        ],
        "goal": goal,
        "scan": scan,
        "signals": signals,
        "log_sources": log_sources,
        "candidate_actions": recommendations,
    }
    text = json.dumps(prompt, ensure_ascii=False, indent=2)
    text = text[-_MAX_OPENAI_CONTEXT_CHARS:]
    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Analyze this NorthStar Suite scan and choose the safest next task plan.\n" + text,
                    }
                ],
            }
        ],
        "max_output_tokens": 700,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_OPENAI_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8", errors="replace")
        parsed = json.loads(body)
        advice = extract_openai_text(parsed).strip()
        if not advice:
            advice = "OpenAI returned a response, but no output_text was found. See report JSON for raw status."
        return OpenAIStatus(configured=True, source=source, model=model, attempted=True, ok=True, summary=advice[:500]), advice
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        return OpenAIStatus(configured=True, source=source, model=model, attempted=True, ok=False, error=f"HTTP {exc.code}: {detail}"), ""
    except Exception as exc:
        return OpenAIStatus(configured=True, source=source, model=model, attempted=True, ok=False, error=f"{type(exc).__name__}: {exc}"), ""


def read_openai_key(root: Path) -> tuple[str, str]:
    env = os.environ.get("OPENAI_API_KEY", "").strip()
    if env:
        return env, "env:OPENAI_API_KEY"
    suite_roots: list[Path] = []
    for name in ("NORTHSTAR_SUITE_ROOT", "NEWENGINE_SUITE_ROOT", "TAKESOME_SUITE_ROOT"):
        raw = os.environ.get(name, "").strip()
        if raw:
            suite_roots.append(Path(raw).expanduser())
    suite_roots.extend([Path(r"D:\TakeSomeData"), root / ".takesome"])
    for suite_root in suite_roots:
        path = suite_root / "secrets" / "openai_api_key.local"
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value, rel(root, path) if path.is_relative_to(root) else str(path)
    return "", "missing"


def extract_openai_text(parsed: dict[str, Any]) -> str:
    if isinstance(parsed.get("output_text"), str):
        return str(parsed["output_text"])
    chunks: list[str] = []
    for item in parsed.get("output", []) if isinstance(parsed.get("output"), list) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(str(content["text"]))
    return "\n".join(chunks)


def _score_with_torch(features: list[tuple[float, ...]], torch_status: TorchStatus) -> list[float]:
    weights = (1.80, 1.25, 0.70, 0.85, 0.35, 0.75, 0.70, 1.15, 0.35, 0.90)
    bias = 0.05
    if not features:
        return []
    if torch_status.available:
        try:
            import torch  # type: ignore

            device = torch_status.selected_device if torch_status.selected_device.startswith("cuda") else "cpu"
            x = torch.tensor(features, dtype=torch.float32, device=device)
            w = torch.tensor(weights, dtype=torch.float32, device=device)
            y = torch.matmul(x, w) + bias
            y = torch.sigmoid(y)
            return [float(value) for value in y.detach().cpu().tolist()]
        except Exception:
            pass
    result: list[float] = []
    for row in features:
        z = sum(value * weight for value, weight in zip(row, weights)) + bias
        result.append(1.0 / (1.0 + math.exp(-z)))
    return result


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[^a-zA-Z0-9_\-.]+", text.lower()) if len(token) >= 2]


def _reasons(action: Any, overlap: float, domain_signal: float, validate_hint: float, build_hint: float, destructive_penalty: float, torch_status: TorchStatus) -> tuple[str, ...]:
    reasons: list[str] = []
    if overlap > 0:
        reasons.append("matches operator goal text")
    if domain_signal > 0:
        reasons.append(f"recent logs mention {action.target_domain or action.category}")
    if validate_hint:
        reasons.append("safe diagnostic/validation action")
    if build_hint:
        reasons.append("can materialize or verify tool outputs")
    if destructive_penalty < 0:
        reasons.append("penalized because it may clean/delete workspace state")
    if torch_status.available:
        reasons.append(f"ranked with PyTorch on {torch_status.selected_device}")
    else:
        reasons.append("ranked with deterministic fallback scorer")
    return tuple(reasons)


def torch_status_to_json(status: TorchStatus) -> dict[str, object]:
    return {
        "available": status.available,
        "version": status.version,
        "cuda_available": status.cuda_available,
        "cuda_device_count": status.cuda_device_count,
        "cuda_devices": list(status.cuda_devices),
        "selected_device": status.selected_device,
        "error": status.error,
    }


def openai_status_to_json(status: OpenAIStatus) -> dict[str, object]:
    return {
        "configured": status.configured,
        "source": status.source,
        "model": status.model,
        "attempted": status.attempted,
        "ok": status.ok,
        "summary": status.summary,
        "error": status.error,
    }


def candidate_to_json(candidate: TaskCandidate) -> dict[str, object]:
    return {
        "action_id": candidate.action_id,
        "label": candidate.label,
        "detail": candidate.detail,
        "category": candidate.category,
        "target_domain": candidate.target_domain,
        "primary_tag": candidate.primary_tag,
        "risk_level": candidate.risk_level,
        "profile": candidate.profile,
        "score": round(candidate.score, 6),
        "features": list(candidate.features),
        "reasons": list(candidate.reasons),
    }


def build_notes(torch_status: TorchStatus, openai_status: OpenAIStatus) -> list[str]:
    notes: list[str] = []
    if not torch_status.available:
        notes.append("PyTorch is optional: install a CUDA-enabled torch build to enable GPU-backed ranking.")
        if torch_status.error:
            notes.append(f"Torch import diagnostic: {torch_status.error}")
    elif not torch_status.cuda_available:
        notes.append("PyTorch is installed, but CUDA is not available; ranking used CPU tensors.")
    elif torch_status.cuda_device_count >= 2:
        notes.append("Multiple CUDA GPUs detected; task ranking currently uses cuda:0 because the workload is tiny and deterministic.")
    elif torch_status.cuda_available:
        notes.append("CUDA PyTorch is available; task ranking used GPU tensors.")

    if not openai_status.configured:
        notes.append("OpenAI key is missing; set OPENAI_API_KEY or secrets/openai_api_key.local under the suite root.")
    elif openai_status.attempted and not openai_status.ok:
        notes.append(f"OpenAI call failed: {openai_status.error}")
    return notes


def _torch_line(status: TorchStatus) -> str:
    if not status.available:
        return f"[WARN] PyTorch unavailable; fallback scorer active. {status.error}"
    if status.cuda_available:
        names = ", ".join(status.cuda_devices) if status.cuda_devices else "CUDA device"
        return f"[OK] PyTorch {status.version}; CUDA devices={status.cuda_device_count}; selected={status.selected_device}; names={names}"
    return f"[WARN] PyTorch {status.version}; CUDA unavailable; selected=cpu"


def _openai_line(status: OpenAIStatus) -> str:
    if not status.configured:
        return "[WARN] OpenAI key missing; OpenAI exchange skipped."
    if status.attempted and status.ok:
        return f"[OK] OpenAI exchange completed via {status.model}."
    if status.attempted:
        return f"[ERROR] OpenAI exchange failed via {status.model}: {status.error}"
    return f"[INFO] OpenAI key configured from {status.source}; exchange not attempted."


def _count_files(root: Path, pattern: str) -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.rglob(pattern) if path.is_file())


def _git_status_short(root: Path) -> str:
    try:
        completed = subprocess.run(["git", "status", "--short"], cwd=root, text=True, capture_output=True, timeout=10)
    except Exception:
        return ""
    return completed.stdout if completed.returncode == 0 else ""


def _git_branch(root: Path) -> str:
    try:
        completed = subprocess.run(["git", "branch", "--show-current"], cwd=root, text=True, capture_output=True, timeout=10)
    except Exception:
        return "unknown"
    return completed.stdout.strip() if completed.returncode == 0 and completed.stdout.strip() else "unknown"


def _check(name: str, ok: bool, detail: str) -> dict[str, object]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
