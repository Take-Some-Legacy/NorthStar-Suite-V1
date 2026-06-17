from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .git_tools import discover_git_repositories, git_available, git_repo_info, run_git_stream
from .console import ANSI_BOLD, ANSI_BRIGHT_GREEN, ANSI_BRIGHT_RED, ANSI_BRIGHT_WHITE, ANSI_BRIGHT_YELLOW, ANSI_DARK_GRAY, colorize_script_line, paint
from .console_menu import ConsoleChoice, ConsoleMenuOption, interactive_menu_enabled, run_confirm_button, run_multi_select_menu
from .logs import TeeLog
from .paths import now_stamp, rel, suite_path, utc_iso


@dataclass(frozen=True)
class GitRepoMenuItem:
    repo: Path
    info: dict[str, Any]

    @property
    def dirty_files(self) -> int:
        try:
            return int(self.info.get("dirty_files", 0) or 0)
        except (TypeError, ValueError):
            return 0



def _write_report(root: Path, *, stamp: str, started_utc: str, finished_utc: str, message: str, dry_run: bool, no_push: bool, records: list[dict[str, Any]], exit_code: int) -> tuple[Path, Path]:
    out_dir = suite_path(root, "git")
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "takesome.gitBatch.v1",
        "run_stamp": stamp,
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "root": str(root.resolve()),
        "message": message,
        "dry_run": dry_run,
        "no_push": no_push,
        "exit_code": exit_code,
        "summary": {
            "repositories": len(records),
            "committed": sum(1 for r in records if r.get("commit") == "ok"),
            "pushed": sum(1 for r in records if r.get("push") == "ok"),
            "skipped_clean": sum(1 for r in records if r.get("status") == "clean"),
            "failed": sum(1 for r in records if r.get("result") == "failed"),
        },
        "records": records,
    }
    json_path = out_dir / f"git-batch-{stamp}.json"
    md_path = out_dir / f"git-batch-{stamp}.md"
    latest_json = out_dir / "git-batch-latest.json"
    latest_md = out_dir / "git-batch-latest.md"
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    json_path.write_text(text, encoding="utf-8")
    latest_json.write_text(text, encoding="utf-8")

    lines = [
        "# North Star / Take Some Git batch report",
        "",
        f"- started_utc: `{started_utc}`",
        f"- finished_utc: `{finished_utc}`",
        f"- exit_code: `{exit_code}`",
        f"- dry_run: `{dry_run}`",
        f"- no_push: `{no_push}`",
        f"- message: `{message}`",
        "",
        "| result | repo | branch | dirty | ignored | tracked-ignored | commit | push | upstream |",
        "|---|---|---|---:|---:|---:|---|---|---|",
    ]
    for record in records:
        info = record.get("git", {}) or {}
        lines.append(
            "| {result} | `{repo}` | `{branch}` | {dirty} | {ignored} | {tracked_ignored} | {commit} | {push} | `{upstream}` |".format(
                result=record.get("result", ""),
                repo=record.get("repo", ""),
                branch=info.get("branch", ""),
                dirty=record.get("dirty_files", 0),
                ignored=record.get("ignored_untracked_files", 0),
                tracked_ignored=record.get("tracked_ignored_files", 0),
                commit=record.get("commit", ""),
                push=record.get("push", ""),
                upstream=info.get("upstream", ""),
            )
        )
    md_text = "\n".join(lines) + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    return json_path, md_path


def _repo_status(root: Path, repo: Path) -> tuple[int, str]:
    from .git_tools import _run_capture  # private helper stays inside script plane

    result = _run_capture(["git", "-C", str(repo), "status", "--porcelain=v1"], cwd=root)
    return result.code, result.stdout


def _remote_exists(root: Path, repo: Path, remote: str) -> bool:
    from .git_tools import _run_capture

    result = _run_capture(["git", "-C", str(repo), "remote", "get-url", remote], cwd=root)
    return result.code == 0 and bool(result.stdout)


def _has_upstream(root: Path, repo: Path) -> bool:
    from .git_tools import _run_capture

    result = _run_capture(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=root)
    return result.code == 0 and bool(result.stdout)


def _branch_name(root: Path, repo: Path) -> str:
    from .git_tools import _run_capture

    result = _run_capture(["git", "-C", str(repo), "branch", "--show-current"], cwd=root)
    return result.stdout if result.code == 0 else ""


def _paths_from_args(root: Path, only: Sequence[str] | None) -> list[Path] | None:
    if not only:
        return None
    paths: list[Path] = []
    for raw in only:
        p = Path(raw)
        if not p.is_absolute():
            p = root / p
        paths.append(p.resolve())
    return paths


def _git_repo_menu_detail(row: ConsoleChoice[GitRepoMenuItem]) -> str:
    item = row.value
    info = item.info
    branch = str(info.get("branch") or "detached")
    upstream = str(info.get("upstream") or "no-upstream")
    dirty = item.dirty_files
    staged = int(info.get("staged_files", 0) or 0)
    unstaged = int(info.get("unstaged_files", 0) or 0)
    untracked = int(info.get("untracked_files", 0) or 0)
    ignored = int(info.get("ignored_untracked_files", 0) or 0)
    tracked_ignored = int(info.get("tracked_ignored_files", 0) or 0)
    ahead = int(info.get("ahead", 0) or 0)
    behind = int(info.get("behind", 0) or 0)
    status_style = ANSI_BRIGHT_YELLOW + ANSI_BOLD if dirty else ANSI_BRIGHT_GREEN + ANSI_BOLD
    upstream_style = ANSI_BRIGHT_WHITE if upstream != "no-upstream" else ANSI_BRIGHT_RED + ANSI_BOLD
    bits = [
        paint("branch:", ANSI_DARK_GRAY) + " " + paint(branch, ANSI_BRIGHT_WHITE),
        paint("dirty:", ANSI_DARK_GRAY) + " " + paint(str(dirty), status_style),
        paint("staged:", ANSI_DARK_GRAY) + " " + str(staged),
        paint("unstaged:", ANSI_DARK_GRAY) + " " + str(unstaged),
        paint("untracked:", ANSI_DARK_GRAY) + " " + str(untracked),
        paint("ignored:", ANSI_DARK_GRAY) + " " + str(ignored),
        paint("tracked-ignored:", ANSI_DARK_GRAY) + " " + str(tracked_ignored),
        paint("upstream:", ANSI_DARK_GRAY) + " " + paint(upstream, upstream_style),
    ]
    if ahead or behind:
        bits.append(paint("sync:", ANSI_DARK_GRAY) + f" ahead={ahead} behind={behind}")
    return "  ".join(bits)


def _select_repositories_interactive(root: Path, repos: list[Path]) -> list[Path] | None:
    rows: list[GitRepoMenuItem] = [GitRepoMenuItem(repo=repo, info=git_repo_info(root, repo)) for repo in repos]
    choices: list[ConsoleChoice[GitRepoMenuItem]] = []
    for item in rows:
        label = rel(root, item.repo)
        choices.append(ConsoleChoice(value=item, number=None, label=label, checked=item.dirty_files > 0))
    result = run_multi_select_menu(
        title="Select Git repositories to commit and push",
        choices=choices,
        action_label="Next",
        options=[
            ConsoleMenuOption("select_all", "A", "All", "check every discovered repository"),
            ConsoleMenuOption("select_none", "N", "None", "clear selected repositories"),
            ConsoleMenuOption("cancel", "Q", "Cancel", "do not run batch git"),
        ],
        footer="Tab options/list  ↑/↓ move  Space toggle repositories/options  Enter next/apply  Esc cancel",
        row_status_provider=_git_repo_menu_detail,
    )
    if result.special == "cancel":
        return None
    return [item.repo for item in result.selected_values]


def _prompt_commit_message_interactive(default_message: str = "") -> str | None:
    print()
    print(colorize_script_line("[MENU] Commit message"))
    print(colorize_script_line("[MENU] Type a clear commit message. Empty message cancels."))
    prompt = "[GIT] Commit message"
    if default_message:
        prompt += f" [{default_message}]"
    prompt += ": "
    while True:
        try:
            value = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not value and default_message:
            value = default_message
        if value:
            return value
        print(colorize_script_line("[WARN] Commit message cannot be empty. Press Ctrl+C to cancel."))


def _confirm_git_push_interactive(root: Path, *, repos: list[Path], message: str, dry_run: bool, no_push: bool) -> bool:
    mode = "dry-run" if dry_run else "write"
    push = "disabled" if no_push else "enabled"
    body = [
        f"mode: {mode}",
        f"push: {push}",
        f"repositories: {len(repos)}",
        f"commit message: {message}",
        "",
    ]
    max_repo_lines = 12
    for repo in repos[:max_repo_lines]:
        body.append(f"- {rel(root, repo)}")
    hidden = len(repos) - max_repo_lines
    if hidden > 0:
        body.append(f"... {hidden} more")
    label = "CONFIRM DRY RUN" if dry_run else ("CONFIRM COMMIT" if no_push else "CONFIRM PUSH")
    result = run_confirm_button(
        title="Confirm Git batch operation",
        body_lines=body,
        confirm_label=label,
        footer="Tab option/button  Enter apply  Esc cancel",
    )
    return result.confirmed


def _interactive_git_batch_setup(root: Path, ns: argparse.Namespace, repos: list[Path], message: str) -> tuple[str, list[Path]] | None:
    if not repos:
        print(colorize_script_line("[WARN] No Git repositories were found under this workspace."))
        return None
    selected_repos = _select_repositories_interactive(root, repos)
    if selected_repos is None:
        print(colorize_script_line("[SKIP] Git batch cancelled."))
        return None
    if not selected_repos:
        print(colorize_script_line("[SKIP] No repositories selected."))
        return None
    message = _prompt_commit_message_interactive(message)
    if not message:
        print(colorize_script_line("[SKIP] Git batch cancelled."))
        return None
    if not _confirm_git_push_interactive(root, repos=selected_repos, message=message, dry_run=bool(ns.dry_run), no_push=bool(ns.no_push)):
        print(colorize_script_line("[SKIP] Git batch cancelled before execution."))
        return None
    return message, selected_repos


def git_batch_push_command(root: Path, ns: argparse.Namespace) -> int:
    message = (getattr(ns, "message", "") or getattr(ns, "message_pos", "") or "").strip()
    if not git_available(root):
        print("[ERROR] git executable is not available in PATH.")
        return 127

    paths = _paths_from_args(root, getattr(ns, "only", None))
    repos = discover_git_repositories(root, max_depth=int(getattr(ns, "max_depth", 4) or 4), paths=paths)

    interactive = (
        not message
        and not getattr(ns, "only", None)
        and not os.environ.get("CI")
        and not os.environ.get("NEWENGINE_PARENT_SCRIPT")
        and sys.stdin.isatty()
        and interactive_menu_enabled()
    )
    if interactive:
        setup = _interactive_git_batch_setup(root, ns, repos, message)
        if setup is None:
            return 0
        message, repos = setup
    elif not message:
        print("[ERROR] Commit message is required.")
        print("[INFO] Example: gitBatchPush.bat \"workspace registry pass\"")
        return 2

    stamp = now_stamp()
    started_utc = utc_iso()
    out_dir = suite_path(root, "git")
    out_dir.mkdir(parents=True, exist_ok=True)
    current_log = out_dir / f"git-batch-{stamp}.log"
    latest_log = out_dir / "git-batch-latest.log"
    root_last = root / "lastgit.log"
    records: list[dict[str, Any]] = []
    exit_code = 0

    with TeeLog(current_log, latest_log, root_last) as log:
        log.emit(f"[INFO] Git batch root: {root}")
        log.emit(f"[INFO] Mode: {'dry-run' if ns.dry_run else 'write'}; push={'off' if ns.no_push else 'on'}")
        log.emit(f"[INFO] Repositories selected: {len(repos)}")
        if not repos:
            log.emit("[WARN] No Git repositories were selected or found under this workspace.")
        for repo in repos:
            info = git_repo_info(root, repo)
            status_code, status_text = _repo_status(root, repo)
            dirty_lines = [line for line in status_text.splitlines() if line.strip()]
            record: dict[str, Any] = {
                "repo": rel(root, repo),
                "git": info,
                "dirty_files": len(dirty_lines),
                "ignored_untracked_files": int(info.get("ignored_untracked_files", 0) or 0),
                "tracked_ignored_files": int(info.get("tracked_ignored_files", 0) or 0),
                "ignored_untracked_sample": info.get("ignored_untracked_sample", []),
                "tracked_ignored_sample": info.get("tracked_ignored_sample", []),
                "status": "dirty" if dirty_lines else "clean",
                "commit": "not_started",
                "push": "not_started",
                "result": "pending",
            }
            log.emit("")
            log.emit(f"[INFO] Repository: {record['repo']}")
            log.emit(f"[STATE] branch={info.get('branch', '')} upstream={info.get('upstream', '')} dirty={len(dirty_lines)} ignored_untracked={record['ignored_untracked_files']} tracked_ignored={record['tracked_ignored_files']}")
            if record["ignored_untracked_files"]:
                log.emit(f"[INFO] .gitignore/exclude is active: {record['ignored_untracked_files']} ignored untracked file(s) will not be added.")
                for ignored_path in list(record.get("ignored_untracked_sample", []))[:5]:
                    log.emit(f"[INFO] ignored: {ignored_path}")
            if record["tracked_ignored_files"]:
                log.emit(f"[WARN] {record['tracked_ignored_files']} tracked file(s) match ignore rules; Git will still track already-versioned files until they are removed from index.")
            if status_code != 0:
                record["result"] = "failed"
                record["commit"] = "status_failed"
                records.append(record)
                exit_code = exit_code or status_code
                continue
            if not dirty_lines and not ns.allow_empty:
                record["result"] = "skipped"
                record["commit"] = "clean"
                record["push"] = "skipped"
                records.append(record)
                log.emit("[SKIP] Clean repository; no commit created.")
                continue

            # `git add -A -- .` uses Git's normal ignore engine: .gitignore,
            # .git/info/exclude and configured global excludes protect
            # untracked generated artifacts from entering the batch.
            add_code = run_git_stream(["git", "-C", str(repo), "add", "-A", "--", "."], cwd=root, log=log, dry_run=ns.dry_run)
            if add_code != 0:
                record["result"] = "failed"
                record["commit"] = "add_failed"
                records.append(record)
                exit_code = exit_code or add_code
                continue
            commit_args = ["git", "-C", str(repo), "commit", "-m", message]
            if ns.allow_empty:
                commit_args.insert(4, "--allow-empty")
            commit_code = run_git_stream(commit_args, cwd=root, log=log, dry_run=ns.dry_run)
            if commit_code != 0:
                record["result"] = "failed"
                record["commit"] = "failed" if not ns.dry_run else "dry"
                records.append(record)
                exit_code = exit_code or commit_code
                continue
            record["commit"] = "dry" if ns.dry_run else "ok"

            if ns.no_push:
                record["push"] = "disabled"
                record["result"] = "ok"
                records.append(record)
                continue
            branch = _branch_name(root, repo)
            if _has_upstream(root, repo):
                push_args = ["git", "-C", str(repo), "push"]
            elif branch and _remote_exists(root, repo, ns.remote):
                push_args = ["git", "-C", str(repo), "push", "-u", ns.remote, branch]
            else:
                record["push"] = "no_upstream_or_remote"
                record["result"] = "failed"
                records.append(record)
                exit_code = exit_code or 3
                log.emit("[ERROR] Cannot push: no upstream branch and no usable remote/branch.")
                continue
            push_code = run_git_stream(push_args, cwd=root, log=log, dry_run=ns.dry_run)
            if push_code != 0:
                record["push"] = "failed" if not ns.dry_run else "dry"
                record["result"] = "failed"
                records.append(record)
                exit_code = exit_code or push_code
                continue
            record["push"] = "dry" if ns.dry_run else "ok"
            record["result"] = "ok"
            records.append(record)

        finished_utc = utc_iso()
        json_path, md_path = _write_report(
            root,
            stamp=stamp,
            started_utc=started_utc,
            finished_utc=finished_utc,
            message=message,
            dry_run=ns.dry_run,
            no_push=ns.no_push,
            records=records,
            exit_code=exit_code,
        )
        log.emit("")
        log.emit(f"[INFO] Git batch report JSON: {rel(root, json_path)}")
        log.emit(f"[INFO] Git batch report MD  : {rel(root, md_path)}")
        log.emit(f"[INFO] Latest log: {rel(root, latest_log)}")
    return exit_code
