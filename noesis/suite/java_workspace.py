from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


GRADLE_MODES = {
    "clean": ["clean"],
    "build": ["build"],
    "check": ["check"],
    "test": ["test"],
    "tasks": ["tasks", "--all"],
    "run": ["run"],
    "package": ["build"],
    "dependency-report": ["dependencies"],
}

MAVEN_MODES = {
    "clean": ["clean"],
    "build": ["compile"],
    "check": ["verify"],
    "test": ["test"],
    "tasks": ["help:describe", "-Dcmd=compile"],
    "run": ["exec:java"],
    "package": ["package"],
    "dependency-report": ["dependency:tree"],
}


def register_java_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = sub.add_parser("java", help="Run universal Java workspace actions through Gradle or Maven.")
    parser.add_argument(
        "mode",
        nargs="?",
        default="doctor",
        choices=["doctor", "tasks", "clean", "build", "check", "test", "run", "package", "dependency-report"],
        help="Java action to run.",
    )
    parser.add_argument("--project-dir", default=".", help="Repository-relative or absolute Java project directory.")
    parser.add_argument("--tool", default="auto", choices=["auto", "gradle", "maven"], help="Build tool selection. Default: auto.")
    parser.add_argument("--executable", default="", help="Build executable override, e.g. gradle, ./gradlew, mvn, ./mvnw.")
    parser.add_argument("--task", action="append", default=[], help="Override task/goal. Can be repeated.")
    parser.add_argument("--info", action="store_true", help="Pass verbose/info flag to the selected build tool.")
    parser.add_argument("--stacktrace", action="store_true", help="Pass Gradle --stacktrace when Gradle is selected.")
    parser.add_argument("--offline", action="store_true", help="Pass offline flag to the selected build tool.")
    parser.add_argument("--dry-run", action="store_true", help="Print resolved command without executing it.")
    parser.add_argument("tool_args", nargs=argparse.REMAINDER, help="Additional build-tool args after --.")


def java_command(root: Path, args: argparse.Namespace) -> int:
    project_dir = _resolve_project_dir(root, str(getattr(args, "project_dir", ".") or "."))
    if str(getattr(args, "project_dir", ".") or ".") == "." and not _looks_like_java_project(project_dir):
        discovered = _discover_java_projects(root)
        if len(discovered) == 1:
            project_dir = discovered[0]
        elif len(discovered) > 1:
            print("[ERROR] Multiple Java projects detected. Pass --project-dir explicitly.")
            for item in discovered:
                print("[JAVA] candidate:", item)
            return 2

    if not project_dir.exists():
        print(f"[ERROR] Java project directory does not exist: {project_dir}")
        return 2
    if not project_dir.is_dir():
        print(f"[ERROR] Java project path is not a directory: {project_dir}")
        return 2

    selected = _select_tool(project_dir, str(getattr(args, "tool", "auto") or "auto"))
    if selected == "":
        print(f"[ERROR] Could not detect Java build tool in: {project_dir}")
        print("[INFO] Expected one of: build.gradle, settings.gradle, gradlew, pom.xml, mvnw")
        return 2

    if str(getattr(args, "mode", "doctor") or "doctor") == "doctor":
        return _doctor(project_dir, selected, args)

    executable = _resolve_executable(project_dir, selected, str(getattr(args, "executable", "") or ""))
    if not executable:
        print(f"[ERROR] {selected} executable not found. Add wrapper or install tool on PATH.")
        return 127

    tasks = _tasks_for_mode(selected, str(getattr(args, "mode", "") or ""), list(getattr(args, "task", []) or []))
    if not tasks:
        print(f"[ERROR] No task/goal resolved for mode: {getattr(args, 'mode', '')}")
        return 2

    cmd = [executable, *tasks]
    _append_common_flags(cmd, selected, args)
    cmd.extend(_strip_remainder_separator(list(getattr(args, "tool_args", []) or [])))

    print("[JAVA] project:", project_dir)
    print("[JAVA] tool:", selected)
    print("[JAVA] command:", " ".join(cmd))
    if bool(getattr(args, "dry_run", False)):
        return 0

    completed = subprocess.run(cmd, cwd=project_dir)
    return int(completed.returncode)


def _resolve_project_dir(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def _looks_like_java_project(project_dir: Path) -> bool:
    return any((project_dir / name).exists() for name in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "pom.xml", "gradlew", "gradlew.bat", "mvnw", "mvnw.cmd"))


def _discover_java_projects(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        if _looks_like_java_project(child):
            candidates.append(child.resolve())
    return candidates


def _select_tool(project_dir: Path, requested: str) -> str:
    if requested in {"gradle", "maven"}:
        return requested
    if (project_dir / "gradlew").exists() or (project_dir / "gradlew.bat").exists():
        return "gradle"
    if (project_dir / "build.gradle").exists() or (project_dir / "settings.gradle").exists() or (project_dir / "build.gradle.kts").exists() or (project_dir / "settings.gradle.kts").exists():
        return "gradle"
    if (project_dir / "mvnw").exists() or (project_dir / "mvnw.cmd").exists() or (project_dir / "pom.xml").exists():
        return "maven"
    return ""


def _resolve_executable(project_dir: Path, tool: str, override: str) -> str:
    if override:
        return override
    if tool == "gradle":
        wrapper = project_dir / ("gradlew.bat" if sys.platform.startswith("win") else "gradlew")
        if wrapper.exists():
            return str(wrapper)
        return shutil.which("gradle") or ""
    if tool == "maven":
        wrapper = project_dir / ("mvnw.cmd" if sys.platform.startswith("win") else "mvnw")
        if wrapper.exists():
            return str(wrapper)
        return shutil.which("mvn") or ""
    return ""


def _tasks_for_mode(tool: str, mode: str, overrides: list[str]) -> list[str]:
    if overrides:
        return [item for item in overrides if item]
    if tool == "gradle":
        return list(GRADLE_MODES.get(mode, []))
    if tool == "maven":
        return list(MAVEN_MODES.get(mode, []))
    return []


def _append_common_flags(cmd: list[str], tool: str, args: argparse.Namespace) -> None:
    if bool(getattr(args, "offline", False)):
        cmd.append("--offline" if tool == "gradle" else "-o")
    if bool(getattr(args, "info", False)):
        cmd.append("--info" if tool == "gradle" else "-X")
    if tool == "gradle" and bool(getattr(args, "stacktrace", False)):
        cmd.append("--stacktrace")


def _doctor(project_dir: Path, selected: str, args: argparse.Namespace) -> int:
    java = shutil.which("java")
    javac = shutil.which("javac")
    executable = _resolve_executable(project_dir, selected, str(getattr(args, "executable", "") or ""))

    print("[JAVA] project:", project_dir)
    print("[JAVA] selected_tool:", selected)
    print("[JAVA] build.gradle:", "yes" if any((project_dir / name).exists() for name in ("build.gradle", "build.gradle.kts")) else "no")
    print("[JAVA] settings.gradle:", "yes" if any((project_dir / name).exists() for name in ("settings.gradle", "settings.gradle.kts")) else "no")
    print("[JAVA] pom.xml:", "yes" if (project_dir / "pom.xml").exists() else "no")
    print("[JAVA] executable:", executable or "missing")
    print("[JAVA] java:", java or "missing")
    print("[JAVA] javac:", javac or "missing")

    rc = 0
    if not executable or not java or not javac:
        rc = 1
    if executable and not bool(getattr(args, "dry_run", False)):
        version_cmd = [executable, "--version"] if selected == "gradle" else [executable, "--version"]
        print("[JAVA] version command:", " ".join(version_cmd))
        completed = subprocess.run(version_cmd, cwd=project_dir)
        if completed.returncode != 0:
            rc = int(completed.returncode)
    return rc


def _strip_remainder_separator(args: list[str]) -> list[str]:
    if args and args[0] == "--":
        return args[1:]
    return args
