from __future__ import annotations

RISK_LABELS = {
    "readonly": "readonly",
    "diagnostics": "diagnostics",
    "writes_cache": "writes cache",
    "writes_reports": "writes reports",
    "writes_runtime_plugins": "writes runtime DLLs",
    "writes_runtime_codecs": "writes codec DLLs",
    "writes_tools": "writes tools",
    "writes_zip": "writes zip",
    "runs_process": "runs process",
    "mutates_git": "mutates git",
    "migration": "migration hooks",
    "destructive_cleanup": "destructive cleanup",
    "force_rebuild": "force rebuild",
}

TAG_DESCRIPTIONS = {
    "BUILD": "compile or synchronize build artifacts",
    "RUN": "launch a runtime/application process",
    "DOC": "inspect or document workspace state",
    "GIT": "operate on Git repositories",
    "CLEAN": "remove generated state",
    "PACK": "create distributable/source archives",
    "DIAG": "collect diagnostics/reports",
    "SYNC": "apply migration or workspace synchronization",
    "FIX": "repair generated workspace state",
    "STATUS": "show current build/runtime state",
    "CACHE": "operate on suite cache",
    "CODEC": "build or validate codec workers",
    "IMPORT": "build importer tools",
    "TOOLS": "operate on first-party tools",
    "MISSION": "run a production workflow chain",
}


def risk_label(risk_level: str) -> str:
    return RISK_LABELS.get(risk_level, str(risk_level or "").replace("_", " "))


def compact_chips(*values: str) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)
