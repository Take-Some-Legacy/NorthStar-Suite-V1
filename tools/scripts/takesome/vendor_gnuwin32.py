from __future__ import annotations

import argparse
import ctypes
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from .paths import rel

VENDOR_ROOT = Path("tools") / "vendor" / "gnuwin32"
BIN_ROOT = VENDOR_ROOT / "bin"
HASH_FILE = VENDOR_ROOT / "HASHES.sha256.txt"


def vendor_bin(root: Path, name: str) -> Path:
    exe_name = name if name.lower().endswith((".exe", ".dll")) else f"{name}.exe"
    return root / BIN_ROOT / exe_name


def require_vendor_tool(root: Path, name: str) -> Path | None:
    path = vendor_bin(root, name)
    if not path.exists():
        print(f"[ERROR] missing vendor tool: {rel(root, path)}")
        print(f"[INFO] expected directory: {rel(root, root / BIN_ROOT)}")
        return None
    return path


def verify_vendor_hashes(root: Path) -> bool:
    hashes = root / HASH_FILE
    if not hashes.exists():
        print(f"[ERROR] missing vendor hash manifest: {rel(root, hashes)}")
        return False
    ok = True
    for raw_line in hashes.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        expected, file_rel = line.split(None, 1)
        file_path = root / VENDOR_ROOT / file_rel.strip()
        if not file_path.exists():
            print(f"[ERROR] missing vendor payload: {rel(root, file_path)}")
            ok = False
            continue
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual.lower() != expected.lower():
            print(f"[ERROR] hash mismatch: {rel(root, file_path)} expected={expected} actual={actual}")
            ok = False
        else:
            print(f"[OK] hash: {rel(root, file_path)}")
    return ok


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
    src_dir = root / BIN_ROOT
    runtime = Path(tempfile.gettempdir()) / "northstar_gnuwin32_bin"
    legacy_bin = Path(tempfile.gettempdir()) / "bin"
    runtime.mkdir(parents=True, exist_ok=True)
    legacy_bin.mkdir(parents=True, exist_ok=True)
    for src in src_dir.iterdir():
        if not src.is_file() or src.suffix.lower() not in {".exe", ".dll"}:
            continue
        for dst in (runtime / src.name, legacy_bin / src.name):
            if not dst.exists() or dst.stat().st_size != src.stat().st_size or int(dst.stat().st_mtime) < int(src.stat().st_mtime):
                shutil.copy2(src, dst)
    return runtime / (name if name.lower().endswith(".exe") else f"{name}.exe")


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
