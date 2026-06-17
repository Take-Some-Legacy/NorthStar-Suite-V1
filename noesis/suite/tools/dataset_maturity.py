from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from ..logs import TeeLog


def _bridge_context(repo_root: Path, *, write_enabled: bool):
    tools_root = repo_root / "tools" / "scripts"
    if str(tools_root) not in sys.path:
        sys.path.insert(0, str(tools_root))
    from noesis.bridge.contracts import BridgeContext

    return BridgeContext(root=repo_root, write_enabled=write_enabled, python_cmd=[sys.executable], interactive=False)


def dataset_maturity_scan(repo_root: Path, *, strict: bool = False, write: bool = True, log: TeeLog | None = None) -> int:
    own_log = log or TeeLog()
    ctx = _bridge_context(repo_root, write_enabled=write)
    from noesis.bridge import dataset
    from noesis.bridge.contracts import BridgeError

    try:
        result = dataset.write_maturity_index(ctx, {}) if write else dataset.maturity_scan(ctx, {})
        if write:
            own_log.emit(f"[OK] dataSet maturity report written: {result.get('scan_path')} / {result.get('report_path')}")
            own_log.emit(f"[OK] audit report: {result.get('audit_report_path')}")
            scan_path = repo_root / str(result.get("scan_path", ""))
            scan = json.loads(scan_path.read_text(encoding="utf-8")) if scan_path.exists() else dataset.maturity_scan(ctx, {})
        else:
            scan = result
            own_log.emit(json.dumps(result, ensure_ascii=False, indent=2))
        findings = dataset.strict_findings(scan)
        if strict and findings:
            for item in findings[:100]:
                own_log.emit(f"[ERROR] {item.get('check')} {item.get('domain') or item.get('archive')}: {item.get('message') or item.get('missing')}")
            own_log.emit(f"[ERROR] strict dataSet maturity failed: {len(findings)} finding(s)")
            return 1
        own_log.emit(f"[OK] dataSet maturity scan completed: records={len(scan.get('module_completeness_matrix') or [])} p0={len((scan.get('repair_queue') or {}).get('P0', []))} p1={len((scan.get('repair_queue') or {}).get('P1', []))} p2={len((scan.get('repair_queue') or {}).get('P2', []))}")
        return 0
    except BridgeError as exc:
        own_log.emit(f"[ERROR] {exc} code={exc.code} data={exc.data}")
        return 2
    except Exception as exc:
        own_log.emit(f"[ERROR] dataset maturity scan crashed: {type(exc).__name__}: {exc}")
        return 1


def dataset_maturity_command(repo_root: Path, ns: SimpleNamespace | None = None, *, log: TeeLog | None = None) -> int:
    ns = ns or SimpleNamespace(strict=False, no_write=False)
    return dataset_maturity_scan(repo_root, strict=bool(getattr(ns, "strict", False)), write=not bool(getattr(ns, "no_write", False)), log=log)
