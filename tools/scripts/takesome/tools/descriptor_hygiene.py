from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..logs import TeeLog
from ..paths import rel

REPORT_DIR = Path("NewEngine/neocore2/buildInfo/tools")
REPORT_JSON = REPORT_DIR / "TOOL_DESCRIPTOR_HYGIENE.json"
REPORT_MD = REPORT_DIR / "TOOL_DESCRIPTOR_HYGIENE.md"


def _command_ids(commands: Any) -> list[str]:
    if isinstance(commands, list):
        return [str(item.get("id")) for item in commands if isinstance(item, dict) and item.get("id")]
    if isinstance(commands, dict):
        return [str(key) for key in commands.keys()]
    return []


def _issue(path: Path, code: str, detail: str, severity: str = "error") -> dict[str, str]:
    return {
        "severity": severity,
        "code": code,
        "path": path.as_posix(),
        "detail": detail,
    }


def scan_tool_descriptor_hygiene(repo_root: Path) -> dict[str, Any]:
    tool_paths = sorted((repo_root / "tools/toolbelt").glob("**/tool.json"))
    issues: list[dict[str, str]] = []
    suite_commands: list[tuple[str, str]] = []
    counts = Counter()

    for path in tool_paths:
        rel_path = path.relative_to(repo_root)
        try:
            descriptor = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            issues.append(_issue(rel_path, "parse_error", str(exc)))
            continue

        counts["tools"] += 1
        if "tools/toolbelt/first_party/" in path.as_posix():
            counts["first_party"] += 1
            first_party = True
        else:
            first_party = False
        if "tools/toolbelt/third_party/" in path.as_posix():
            counts["third_party"] += 1

        description = str(descriptor.get("description") or "").strip()
        if len(description) < 24:
            issues.append(_issue(rel_path, "weak_description", description or "missing description", "warning"))

        commands = descriptor.get("commands") or []
        command_ids = _command_ids(commands)
        for required in ("help", "version"):
            if required not in command_ids:
                issues.append(_issue(rel_path, "missing_lifecycle_command", required))
        if first_party:
            for required in ("accepted-inputs", "doctor"):
                if required not in command_ids:
                    issues.append(_issue(rel_path, "missing_first_party_lifecycle", required))
        for command_id, duplicate_count in Counter(command_ids).items():
            if duplicate_count > 1:
                issues.append(_issue(rel_path, "duplicate_command_id", f"{command_id} x{duplicate_count}"))

        package_root = descriptor.get("package_root")
        executable = descriptor.get("executable")
        if package_root and executable:
            exe = repo_root / str(package_root) / str(executable)
            if not exe.exists():
                issues.append(_issue(rel_path, "missing_executable", rel(repo_root, exe)))
        elif executable:
            exe = repo_root / str(executable)
            if not exe.exists():
                issues.append(_issue(rel_path, "missing_executable", rel(repo_root, exe)))

        for suite_command in descriptor.get("suite_commands") or []:
            if not isinstance(suite_command, dict):
                issues.append(_issue(rel_path, "bad_suite_command", "suite command is not an object"))
                continue
            command_id = str(suite_command.get("id") or "")
            if command_id:
                suite_commands.append((command_id, rel_path.as_posix()))
            else:
                issues.append(_issue(rel_path, "suite_command_missing_id", "missing id"))
            if len(str(suite_command.get("description") or "").strip()) < 20:
                issues.append(_issue(rel_path, "suite_command_weak_description", command_id or "<missing>", "warning"))
            if not suite_command.get("riskTier"):
                issues.append(_issue(rel_path, "suite_command_missing_riskTier", command_id or "<missing>"))
            for arg in suite_command.get("args") or []:
                if not isinstance(arg, dict):
                    issues.append(_issue(rel_path, "suite_arg_bad_shape", command_id))
                    continue
                name = str(arg.get("name") or "")
                if not name:
                    issues.append(_issue(rel_path, "suite_arg_missing_name", command_id))
                if not arg.get("flags"):
                    issues.append(_issue(rel_path, "suite_arg_missing_flags", f"{command_id}:{name}"))
                if len(str(arg.get("help") or "").strip()) < 8:
                    issues.append(_issue(rel_path, "suite_arg_weak_help", f"{command_id}:{name}", "warning"))

    by_suite_id: dict[str, list[str]] = defaultdict(list)
    for command_id, source in suite_commands:
        by_suite_id[command_id].append(source)
    for command_id, sources in sorted(by_suite_id.items()):
        if len(sources) > 1:
            issues.append({
                "severity": "error",
                "code": "duplicate_suite_command_id",
                "path": "<suite_commands>",
                "detail": f"{command_id}: {sources}",
            })

    severity_counts = Counter(issue["severity"] for issue in issues)
    code_counts = Counter(issue["code"] for issue in issues)
    return {
        "schema": "northstar.tool_descriptor_hygiene.v1",
        "ok": severity_counts.get("error", 0) == 0,
        "counts": dict(counts),
        "suite_command_count": len(suite_commands),
        "unique_suite_command_count": len(by_suite_id),
        "issue_count": len(issues),
        "severity_counts": dict(severity_counts),
        "code_counts": dict(code_counts),
        "issues": issues,
    }


def write_tool_descriptor_hygiene_report(repo_root: Path, *, log: TeeLog | None = None) -> int:
    report = scan_tool_descriptor_hygiene(repo_root)
    out_dir = repo_root / REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = repo_root / REPORT_JSON
    md_path = repo_root / REPORT_MD
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Tool Descriptor Hygiene",
        "",
        f"Status: {'OK' if report['ok'] else 'FAILED'}",
        f"Tools: {report['counts'].get('tools', 0)}",
        f"First-party: {report['counts'].get('first_party', 0)}",
        f"Third-party: {report['counts'].get('third_party', 0)}",
        f"Suite commands: {report['suite_command_count']} / unique {report['unique_suite_command_count']}",
        f"Issues: {report['issue_count']}",
        "",
        "## Issue counts",
        "",
    ]
    if report["code_counts"]:
        for code, count in sorted(report["code_counts"].items()):
            lines.append(f"- {code}: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "## Issues", ""])
    if report["issues"]:
        for issue in report["issues"]:
            lines.append(f"- [{issue['severity']}] {issue['code']} — `{issue['path']}` — {issue['detail']}")
    else:
        lines.append("No issues found.")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if log is not None:
        log.emit(f"[OK] Wrote descriptor hygiene JSON: {rel(repo_root, json_path)}")
        log.emit(f"[OK] Wrote descriptor hygiene MD: {rel(repo_root, md_path)}")
        log.emit(f"[INFO] descriptor_hygiene ok={report['ok']} issues={report['issue_count']}")
    return 0 if report["ok"] else 1
