from __future__ import annotations

import argparse
import ctypes
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from .paths import rel

TOOLBELT_THIRD_PARTY_ROOT = Path("tools") / "toolbelt" / "third_party"
LEGACY_VENDOR_ROOTS = [
    Path("tools") / "vendor" / "gnuwin32",
    Path("tools") / "toolbelt" / "third_party" / "gnuwin32",
]

GNUWIN32_TOOL_SLUGS = {
    "bison": "bison",
    "diff": "diff",
    "diff3": "diff3",
    "fgrep": "fgrep",
    "flex": "flex",
    "flex++": "flexpp",
    "flex++.exe": "flexpp",
    "funzip": "funzip",
    "m4": "m4",
    "make": "make",
    "sdiff": "sdiff",
    "sed": "sed",
    "tail": "tail",
    "tar": "tar",
    "touch": "touch",
}


def _tool_slug(name: str) -> str:
    key = name.lower()
    if key.endswith(".exe") and key not in GNUWIN32_TOOL_SLUGS:
        key = key[:-4]
    return GNUWIN32_TOOL_SLUGS.get(key, key)


def _exe_name(name: str) -> str:
    if name.lower().endswith(".exe"):
        return name
    if name.lower() == "flex++":
        return "flex++.exe"
    return f"{name}.exe"


def tool_package_dir(root: Path, name: str) -> Path:
    return root / TOOLBELT_THIRD_PARTY_ROOT / _tool_slug(name)


def tool_bin_dir(root: Path, name: str) -> Path:
    return tool_package_dir(root, name) / "bin"


def vendor_bin(root: Path, name: str) -> Path:
    return tool_bin_dir(root, name) / _exe_name(name)


def require_vendor_tool(root: Path, name: str) -> Path | None:
    path = vendor_bin(root, name)
    if not path.exists():
        print(f"[ERROR] missing vendor tool: {rel(root, path)}")
        print(f"[INFO] expected self-contained package: {rel(root, tool_package_dir(root, name))}")
        print("[INFO] migrate payload into tools/toolbelt/third_party/<tool>/bin/ and keep tool.json in sync.")
        return None
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_vendor_hashes(root: Path) -> bool:
    ok = True
    descriptors = sorted((root / TOOLBELT_THIRD_PARTY_ROOT).glob("*/tool.json"), key=lambda p: p.as_posix().lower())
    descriptors = [p for p in descriptors if json_tool_id(p).startswith("vendor.gnuwin32.")]
    if not descriptors:
        print("[ERROR] no per-tool GNUWin32 descriptors found under tools/toolbelt/third_party/<tool>/tool.json")
        return False
    for descriptor in descriptors:
        try:
            data = __import__("json").loads(descriptor.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[ERROR] invalid descriptor: {rel(root, descriptor)}: {exc}")
            ok = False
            continue
        package_root_raw = str(data.get("package_root", "")).strip()
        executable_raw = str(data.get("executable", "")).strip()
        package_root = root / package_root_raw if package_root_raw else descriptor.parent
        executable = package_root / executable_raw if executable_raw else None
        expected_hash = str(data.get("expected_sha256", "")).strip().lower()
        expected_size = int(data.get("expected_size_bytes", 0) or 0)
        if executable is None or not executable.exists():
            print(f"[ERROR] missing vendor payload: {rel(root, executable or package_root)}")
            ok = False
            continue
        actual_size = executable.stat().st_size
        actual_hash = _sha256(executable).lower()
        if expected_size and actual_size != expected_size:
            print(f"[ERROR] size mismatch: {rel(root, executable)} expected={expected_size} actual={actual_size}")
            ok = False
        if expected_hash and actual_hash != expected_hash:
            print(f"[ERROR] hash mismatch: {rel(root, executable)} expected={expected_hash} actual={actual_hash}")
            ok = False
        if (not expected_size or actual_size == expected_size) and (not expected_hash or actual_hash == expected_hash):
            print(f"[OK] payload: {rel(root, executable)}")
    for legacy_root in LEGACY_VENDOR_ROOTS:
        legacy_path = root / legacy_root
        if legacy_path.exists():
            print(f"[ERROR] legacy GNUWin32 vault still exists: {rel(root, legacy_path)}")
            ok = False
    return ok


def json_tool_id(path: Path) -> str:
    try:
        import json
        return str(json.loads(path.read_text(encoding="utf-8")).get("id", ""))
    except Exception:
        return ""


def windows_short_path(path: Path) -> str:
    if not path.exists():
        return str(path)
    try:
        raw = str(path.resolve())
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.kernel32.GetShortPathNameW(raw, buffer, len(buffer))
        if result > 0 and result < len(buffer):
            return buffer.value
    except Exception:
        pass
    return str(path)


def vendor_runtime_exe(root: Path, name: str) -> Path:
    src_dir = tool_bin_dir(root, name)
    runtime = Path(tempfile.gettempdir()) / f"northstar_gnuwin32_{_tool_slug(name)}_bin"
    legacy_bin = Path(tempfile.gettempdir()) / "bin"
    runtime.mkdir(parents=True, exist_ok=True)
    legacy_bin.mkdir(parents=True, exist_ok=True)
    for src in src_dir.iterdir():
        if not src.is_file() or src.suffix.lower() not in {".exe", ".dll"}:
            continue
        for dst in (runtime / src.name, legacy_bin / src.name):
            if not dst.exists() or dst.stat().st_size != src.stat().st_size or int(dst.stat().st_mtime) < int(src.stat().st_mtime):
                shutil.copy2(src, dst)
    return runtime / _exe_name(name)


def run_vendor_command(command: list[str], *, cwd: Path, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=capture, encoding="utf-8", errors="replace")


def repo_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def vendor_arg_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def diff_files_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] GNUWin32 diff started")
    exe = require_vendor_tool(root, "diff")
    if exe is None:
        return 2
    left = repo_path(root, ns.left)
    right = repo_path(root, ns.right)
    completed = run_vendor_command([vendor_arg_path(root, exe), "-u", vendor_arg_path(root, left), vendor_arg_path(root, right)], cwd=root, capture=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode == 0:
        print("[OK] files are identical")
        return 0
    if completed.returncode == 1:
        print("[OK] diff completed: files differ")
        return 0
    print(f"[ERROR] diff failed exit_code={completed.returncode}")
    return int(completed.returncode)


def sdiff_files_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] GNUWin32 sdiff started")
    if require_vendor_tool(root, "sdiff") is None:
        return 2
    left = repo_path(root, ns.left)
    right = repo_path(root, ns.right)
    exe = vendor_runtime_exe(root, "sdiff")
    work = Path(tempfile.gettempdir()) / "northstar_sdiff_work"
    work.mkdir(parents=True, exist_ok=True)
    left_copy = work / "left.txt"
    right_copy = work / "right.txt"
    shutil.copy2(left, left_copy)
    shutil.copy2(right, right_copy)
    completed = run_vendor_command([str(exe), str(left_copy), str(right_copy)], cwd=exe.parent, capture=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if "extra operand" in output or "Try `" in output:
        print("[ERROR] sdiff failed: GNUWin32 argument parsing error")
        return 2
    if completed.returncode in (0, 1):
        print("[OK] sdiff completed")
        return 0
    print(f"[ERROR] sdiff failed exit_code={completed.returncode}")
    return int(completed.returncode)

def diff3_files_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] GNUWin32 diff3 started")
    exe = require_vendor_tool(root, "diff3")
    if exe is None:
        return 2
    base = repo_path(root, ns.base)
    mine = repo_path(root, ns.mine)
    theirs = repo_path(root, ns.theirs)
    completed = run_vendor_command([vendor_arg_path(root, exe), "-m", vendor_arg_path(root, mine), vendor_arg_path(root, base), vendor_arg_path(root, theirs)], cwd=root, capture=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode in (0, 1):
        print("[OK] diff3 completed")
        return 0
    print(f"[ERROR] diff3 failed exit_code={completed.returncode}")
    return int(completed.returncode)


def sed_file_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] GNUWin32 sed started")
    exe = require_vendor_tool(root, "sed")
    if exe is None:
        return 2
    source = repo_path(root, ns.input)
    output = repo_path(root, ns.output)
    if not ns.script:
        print("[ERROR] sed-file requires --script")
        return 2
    completed = run_vendor_command([vendor_arg_path(root, exe), "-e", ns.script, vendor_arg_path(root, source)], cwd=root, capture=True)
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode != 0:
        print(f"[ERROR] sed failed exit_code={completed.returncode}")
        return int(completed.returncode)
    if ns.check:
        print(completed.stdout, end="")
        print("[OK] sed check completed; output was not written")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(completed.stdout, encoding="utf-8", newline="")
    print(f"[OK] sed wrote: {rel(root, output)}")
    return 0


def touch_file_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] GNUWin32 touch started")
    exe = require_vendor_tool(root, "touch")
    if exe is None:
        return 2
    target = repo_path(root, ns.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    args = [vendor_arg_path(root, exe)]
    if getattr(ns, "no_create", False):
        args.append("-c")
    if getattr(ns, "reference", ""):
        args.extend(["-r", vendor_arg_path(root, repo_path(root, ns.reference))])
    args.append(vendor_arg_path(root, target))
    completed = run_vendor_command(args, cwd=root, capture=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode != 0:
        print(f"[ERROR] touch failed exit_code={completed.returncode}")
        return int(completed.returncode)
    print(f"[OK] touched: {rel(root, target)}")
    return 0


def fgrep_files_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] GNUWin32 fgrep started")
    exe = require_vendor_tool(root, "fgrep")
    if exe is None:
        return 2
    args = [vendor_arg_path(root, exe), "-n"]
    if getattr(ns, "ignore_case", False):
        args.append("-i")
    if getattr(ns, "word", False):
        args.append("-w")
    args.append(ns.pattern)
    args.extend(vendor_arg_path(root, repo_path(root, item)) for item in ns.files)
    completed = run_vendor_command(args, cwd=root, capture=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode == 0:
        print("[OK] fgrep completed: matches found")
        return 0
    if completed.returncode == 1:
        print("[OK] fgrep completed: no matches")
        return 0
    print(f"[ERROR] fgrep failed exit_code={completed.returncode}")
    return int(completed.returncode)


def vendor_tail_lines(root: Path, path: Path, *, max_lines: int = 160) -> list[str]:
    exe = vendor_bin(root, "tail")
    if not exe.exists() or not path.exists():
        return []
    lines = max(1, min(int(max_lines), 1000))
    completed = run_vendor_command([vendor_arg_path(root, exe), "-n", str(lines), vendor_arg_path(root, path)], cwd=root, capture=True)
    if completed.returncode != 0:
        return []
    return completed.stdout.splitlines()


def tail_file_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] GNUWin32 tail started")
    exe = require_vendor_tool(root, "tail")
    if exe is None:
        return 2
    lines = max(1, min(int(ns.lines), 1000))
    source = repo_path(root, ns.input)
    completed = run_vendor_command([vendor_arg_path(root, exe), "-n", str(lines), vendor_arg_path(root, source)], cwd=root, capture=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode != 0:
        print(f"[ERROR] tail failed exit_code={completed.returncode}")
        return int(completed.returncode)
    print("[OK] tail completed")
    return 0


def tar_list_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] GNUWin32 tar list started")
    exe = require_vendor_tool(root, "tar")
    if exe is None:
        return 2
    archive = repo_path(root, ns.archive)
    completed = run_vendor_command([vendor_arg_path(root, exe), "-tf", vendor_arg_path(root, archive)], cwd=root, capture=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode != 0:
        print(f"[ERROR] tar list failed exit_code={completed.returncode}")
        return int(completed.returncode)
    print("[OK] tar list completed")
    return 0


def tar_extract_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] GNUWin32 tar extract started")
    exe = require_vendor_tool(root, "tar")
    if exe is None:
        return 2
    archive = repo_path(root, ns.archive)
    output = repo_path(root, ns.output)
    output.mkdir(parents=True, exist_ok=True)
    completed = run_vendor_command([vendor_arg_path(root, exe), "-xf", vendor_arg_path(root, archive), "-C", vendor_arg_path(root, output)], cwd=root, capture=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode != 0:
        print(f"[ERROR] tar extract failed exit_code={completed.returncode}")
        return int(completed.returncode)
    print(f"[OK] tar extracted to: {rel(root, output)}")
    return 0


def tar_create_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] GNUWin32 tar create started")
    exe = require_vendor_tool(root, "tar")
    if exe is None:
        return 2
    archive = repo_path(root, ns.archive)
    archive.parent.mkdir(parents=True, exist_ok=True)
    inputs = [repo_path(root, item) for item in ns.inputs]
    completed = run_vendor_command([vendor_arg_path(root, exe), "-cf", vendor_arg_path(root, archive), *[vendor_arg_path(root, item) for item in inputs]], cwd=root, capture=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode != 0:
        print(f"[ERROR] tar create failed exit_code={completed.returncode}")
        return int(completed.returncode)
    print(f"[OK] tar created: {rel(root, archive)}")
    return 0


def vendor_gnuwin32_doctor_command(root: Path, _ns: argparse.Namespace) -> int:
    print("[INFO] GNUWin32 vendor doctor started")
    ok = verify_vendor_hashes(root)
    if ok:
        print("[OK] GNUWin32 vendor payload complete")
        return 0
    print("[ERROR] GNUWin32 vendor payload incomplete or hash-mismatched")
    return 1
