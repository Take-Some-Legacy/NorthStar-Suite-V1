from __future__ import annotations

import argparse
from pathlib import Path

from ..archive import pack_source
from ..clean import clean_workspace, clear_cache
from ..game import run_game
from ..git_batch import git_batch_push_command
from ..importers import build_importers, build_tool
from ..import_pipeline import import_pipeline_command
from ..migration import apply_delete_list, apply_patch_files, sync_workspace_state
from ..plugin_build import build_codecs, build_plugin_entry, build_plugins
from ..plugin_cleanup import plugin_cleanup_command
from ..plugin_status import plugin_status_command
from ..suite.approval import apply_sudo_from_args
from ..suite_shell import suite_command
from ..third_party_tests import third_party_test_all_command
from ..first_party_tests import first_party_test_all_command
from ..tools import tools_command, validate_build_tools
from ..workspace_health import workspace_health_command
from ..workspace_registry import workspace_registry_command
from ..endless.cli import endless_stream_command
from .cli_hooks import REGISTRY_COMMAND_IDS, try_handle_registry_command

CORE_COMMANDS = {
    "apply-delete-list",
    "apply-patches",
    "sync",
    "build-plugins",
    "build-plugin",
    "build-importers",
    "build-codecs",
    "build-tool",
    "clear-cache",
    "clean-workspace",
    "pack-source",
    "workspace-health",
    "plugin-cleanup",
    "run-game",
    "plugin-status",
    "workspace-registry",
    "git-batch-push",
    "tools",
    "suite",
    "endless-stream",
    "third-party-test-all",
    "first-party-test-all",
    "import-ui-assets",
    "validate-build",
}


def register_core_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    sub.add_parser("apply-delete-list")
    sub.add_parser("apply-patches")
    sub.add_parser("sync")

    p = sub.add_parser("build-plugins")
    p.add_argument("args", nargs=argparse.REMAINDER)

    p = sub.add_parser("build-plugin")
    p.add_argument("--plugin-dir", required=True)
    p.add_argument("--entry", default="build")
    p.add_argument("args", nargs=argparse.REMAINDER)

    p = sub.add_parser("build-importers")
    p.add_argument("args", nargs=argparse.REMAINDER)

    p = sub.add_parser("build-codecs")
    p.add_argument("args", nargs=argparse.REMAINDER)

    p = sub.add_parser("build-tool")
    p.add_argument("--tool-dir", required=True)
    p.add_argument("--release", action="store_true")

    sub.add_parser("clear-cache")

    p = sub.add_parser("clean-workspace")
    p.add_argument("--full", action="store_true", help="Also clean logs/cache/build-state/runtime plugin binaries. Default mode cleans selected target directories only.")
    p.add_argument("--keep-logs", action="store_true", help="With --full, keep logs and buildInfo reports.")
    p.add_argument("--keep-cache", action="store_true", help="With --full, keep caches and tool registry cache.")
    p.add_argument("--keep-plugin-binaries", action="store_true", help="With --full, keep installed runtime plugin DLLs.")
    p.add_argument("--target", "--target-scope", dest="target_scope", default="", help="Target cleanup scope: 0/all target dirs, number, comma-list (1,3,8), engine or plugin/tool/importer key. Use skip/none/no to skip target cleanup.")

    p = sub.add_parser("pack-source")
    p.add_argument("--output", "-o", default="")
    p.add_argument("--exclude-dir", action="append")
    p.add_argument("--exclude-ext", action="append")
    p.add_argument("--exclude-file", action="append")
    p.add_argument("--verbose", action="store_true")

    sub.add_parser("workspace-health", help="Generate Build Health Report with plugin, dataset, diagnostics, hygiene and optimization warnings.")
    p = sub.add_parser("plugin-cleanup", help="Scan or remove whitelisted temporary plugin cleanup artifacts.")
    p.add_argument("--apply", action="store_true", help="Delete only whitelisted temporary plugin artifacts: _split_stage/ and split_staging.rs.")

    for command_id in REGISTRY_COMMAND_IDS:
        sub.add_parser(command_id, help=f"Registry-driven command: {command_id}.")

    p = sub.add_parser("run-game")
    p.add_argument("--sync-plugins", action="store_true", help="Run plugin sync even when status is clean.")
    p.add_argument("--force-plugins", action="store_true", help="Force rebuild all runtime plugin targets before running.")
    p.add_argument("--no-plugin-sync", action="store_true", help="Report plugin status but do not sync stale targets.")
    p.add_argument("--check-plugins-only", action="store_true", help="Report plugin status and stop before game build/run.")
    p.add_argument("args", nargs=argparse.REMAINDER)

    p = sub.add_parser("plugin-status")
    p.add_argument("build_type", nargs="?", default="dev", choices=["dev", "debug", "release"])
    p.add_argument("--platform", "--build-platform", default="")
    p.add_argument("--target", "--rust-target", dest="rust_target", default="")
    p.add_argument("--force", "-f", action="store_true")

    p = sub.add_parser("workspace-registry")
    p.add_argument("--output", "-o", default="", help="Output directory for workspace registry JSON/MD reports.")

    p = sub.add_parser("git-batch-push")
    p.add_argument("message_pos", nargs="?", default="", help="Commit message. Alternative to --message.")
    p.add_argument("--message", "-m", default="", help="Commit message.")
    p.add_argument("--dry-run", action="store_true", help="Print git commands without changing repositories.")
    p.add_argument("--no-push", action="store_true", help="Commit but do not push.")
    p.add_argument("--allow-empty", action="store_true", help="Allow empty commits for clean repositories.")
    p.add_argument("--remote", default="origin", help="Remote to use when the current branch has no upstream.")
    p.add_argument("--max-depth", type=int, default=4, help="Maximum nested directory depth for Git repository discovery.")
    p.add_argument("--only", action="append", help="Restrict the batch to a specific repository path. Can be repeated.")

    _register_tools_parser(sub)
    _register_suite_parser(sub)
    _register_endless_parser(sub)

    p = sub.add_parser("third-party-test-all", help="Run all third-party package smoke tests through tools/toolbelt/third_party/testAll.bat.")
    p = sub.add_parser("first-party-test-all", help="Run all first-party package smoke tests through tools/toolbelt/first_party/testAll.bat.")

    p = sub.add_parser("import-ui-assets")
    p.add_argument("--check", action="store_true", help="Validate/import graph and NEUI manifests without writing runtime .neui files.")
    p.add_argument("--skip-neui", action="store_true", help="Write/check the generated runtime graph but skip invoking the native NEUI packer.")
    p.add_argument("--changed-source", action="append", default=[], help="Source ref to use when producing/checking an invalidation plan. Can be repeated.")
    p.add_argument("--write-invalidation-plan", action="store_true", help="Write invalidation plan even with --check.")

    sub.add_parser("validate-build")


def dispatch_core_command(command: str, root: Path, ns: argparse.Namespace) -> int | None:
    if command == "apply-delete-list":
        return apply_delete_list(root)
    if command == "apply-patches":
        return apply_patch_files(root)
    if command == "sync":
        return sync_workspace_state(root)
    if command == "build-plugins":
        return build_plugins(root, list(ns.args))
    if command == "build-plugin":
        return build_plugin_entry(root, Path(ns.plugin_dir), ns.entry, list(ns.args))
    if command == "build-importers":
        return build_importers(root, list(ns.args))
    if command == "build-codecs":
        return build_codecs(root, list(ns.args))
    if command == "build-tool":
        return build_tool(root, Path(ns.tool_dir), ns.release)
    if command == "clear-cache":
        return clear_cache(root, ns)
    if command == "clean-workspace":
        return clean_workspace(root, ns)
    if command == "pack-source":
        return pack_source(root, ns)
    if command == "run-game":
        run_args = list(ns.args)
        if ns.sync_plugins:
            run_args.append("--sync-plugins")
        if ns.force_plugins:
            run_args.append("--force-plugins")
        if ns.no_plugin_sync:
            run_args.append("--no-plugin-sync")
        if ns.check_plugins_only:
            run_args.append("--check-plugins-only")
        return run_game(root, run_args)
    if command == "plugin-status":
        status_args = [ns.build_type]
        if getattr(ns, "platform", ""):
            status_args.extend(["--platform", ns.platform])
        if getattr(ns, "rust_target", ""):
            status_args.extend(["--target", ns.rust_target])
        if ns.force:
            status_args.append("--force")
        return plugin_status_command(root, status_args)
    if command == "workspace-registry":
        return workspace_registry_command(root, ns)
    if command == "workspace-health":
        return workspace_health_command(root, ns)
    if command == "plugin-cleanup":
        return plugin_cleanup_command(root, ns)

    registry_result = try_handle_registry_command([command], root)
    if registry_result is not None:
        return registry_result

    if command == "git-batch-push":
        return git_batch_push_command(root, ns)
    if command == "tools":
        return tools_command(root, ns)
    if command == "suite":
        apply_sudo_from_args(ns)
        return suite_command(root, ns)
    if command == "endless-stream":
        return endless_stream_command(root, ns)
    if command == "third-party-test-all":
        return third_party_test_all_command(root, ns)
    if command == "first-party-test-all":
        return first_party_test_all_command(root, ns)
    if command == "import-ui-assets":
        return import_pipeline_command(root, ns)
    if command == "validate-build":
        apply_delete_list(root)
        return validate_build_tools(root)
    return None


def _register_tools_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("tools")
    tool_sub = p.add_subparsers(dest="tools_action", required=True)
    tool_sub.add_parser("menu")
    tool_sub.add_parser("scan")
    tool_sub.add_parser("list")
    p_tool_doctor = tool_sub.add_parser("doctor")
    p_tool_doctor.add_argument("--full", action="store_true", help="Run full workspace doctor with detailed findings.")
    tool_sub.add_parser("validate")
    p_tool_invariants = tool_sub.add_parser("invariants")
    p_tool_invariants.add_argument("--strict-large-files", action="store_true")
    p_tool_invariants.add_argument("--strict-boundaries", action="store_true")
    p_tool_invariants.add_argument("--fail-tracked-large-debt", action="store_true")
    tool_sub.add_parser("conformance")
    tool_sub.add_parser("schema")
    tool_sub.add_parser("schema-runtime")
    tool_sub.add_parser("editor-shell")
    tool_sub.add_parser("import-pipeline")
    tool_sub.add_parser("world-scene")
    tool_sub.add_parser("gameplay")
    tool_sub.add_parser("rendering")
    tool_sub.add_parser("reference-completeness")
    tool_sub.add_parser("reference-completeness-strict")
    tool_sub.add_parser("dataset-ingest")
    tool_sub.add_parser("dataset-lifecycle")
    tool_sub.add_parser("dataset-entry-analysis")
    tool_sub.add_parser("dataset-maturity")
    tool_sub.add_parser("dataset-maturity-strict")
    tool_sub.add_parser("operator-memory")
    p_tool_import_ui = tool_sub.add_parser("import-ui-assets")
    p_tool_import_ui.add_argument("--check", action="store_true")
    p_tool_import_ui.add_argument("--skip-neui", action="store_true")
    p_tool_import_ui.add_argument("--changed-source", action="append", default=[])
    p_tool_import_ui.add_argument("--write-invalidation-plan", action="store_true")
    tool_sub.add_parser("collect-run")

    p_tool_build = tool_sub.add_parser("build")
    p_tool_build.add_argument("tool_id", nargs="?", default="")
    p_tool_build.add_argument("--release", action="store_true")
    p_tool_build.add_argument("--safe", action="store_true", help="Build only descriptors marked safe_for_build/build_validation.")
    p_tool_build.add_argument("--validate-after-build", action="store_true", help="Run descriptor-declared validation_args after building.")

    p_tool_run = tool_sub.add_parser("run")
    p_tool_run.add_argument("tool_id")
    p_tool_run.add_argument("--release", action="store_true")
    p_tool_run.add_argument("tool_args", nargs=argparse.REMAINDER)


def _register_suite_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("suite")
    p.add_argument("--list-actions", action="store_true", help="List grouped suite actions and exit.")
    p.add_argument("--run", default="", help="Run one suite action by key, then return/exit.")
    p.add_argument("--json", action="store_true", help="Emit SuiteOutputEnvelope JSON for --list-actions or --run.")
    p.add_argument("--compact", action="store_true", help="With --json --run, print a compact operator summary and keep full JSON in result.json.")
    p.add_argument("--output-dir", default="", help="Directory for structured Suite run artifacts. Defaults to .takesome/suite/runs.")
    p.add_argument("-sudo", dest="sudo", action="store_true", help="Run Suite-owned write confirmations in explicit operator mode.")


def _register_endless_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("endless-stream", help="Run one transparent Endless Stream operator cycle.")
    p.add_argument("--mode", default="foundation", help="Stream mode. Default: foundation.")
    p.add_argument("--message", "-m", action="append", default=[], help="Operator instruction. May be passed more than once.")
    p.add_argument("--message-file", default="", help="Read one operator instruction from a UTF-8 text file.")
    p.add_argument("--stdin", action="store_true", help="Read one operator instruction from standard input.")
