from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable

from .contracts import BridgeContext, BridgeError

SKIP_DIRS = {'.git', '.hg', '.svn', '.idea', '.vs', '.takesome', '__pycache__', 'target', 'node_modules', 'dist', 'build', 'out', 'bin', 'obj'}
BINARY_EXTS = {'.dll', '.so', '.dylib', '.exe', '.pdb', '.ilk', '.obj', '.o', '.lib', '.exp', '.zip', '.7z', '.rar', '.tar', '.gz', '.xz', '.zst', '.png', '.jpg', '.jpeg', '.webp', '.ico', '.ttf', '.otf', '.woff', '.woff2', '.dds', '.ytd', '.ydd', '.nepak'}
TEXT_EXTS = {'.py', '.rs', '.toml', '.json', '.md', '.txt', '.bat', '.cmd', '.ps1', '.yml', '.yaml', '.js', '.ts', '.css', '.html', '.xml', '.glsl', '.hlsl', '.wgsl', '.c', '.cpp', '.h', '.hpp'}


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def _safe_path(root: Path, raw: str, *, must_exist: bool = False) -> Path:
    if not raw:
        raise BridgeError('empty path', 'invalid_path')
    path = (root / raw).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        raise BridgeError('path escapes repository root', 'invalid_path', {'path': raw})
    if must_exist and not path.exists():
        raise BridgeError('path does not exist', 'missing_path', {'path': raw})
    return path


def _require_write(ctx: BridgeContext, action: str) -> None:
    if not ctx.write_enabled:
        raise BridgeError(f'{action} requires bridge write/sudo mode', 'write_disabled', {'action': action})


def _run(root: Path, cmd: list[str], *, timeout: int = 120) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(root), text=True, encoding='utf-8', errors='replace', stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=None, shell=False)
        stdout = proc.stdout or ''
        stderr = proc.stderr or ''
        return {'ok': proc.returncode == 0, 'exit_code': proc.returncode, 'elapsed_ms': int((time.time() - started) * 1000), 'cmd': [Path(cmd[0]).name, *cmd[1:]], 'stdout': stdout[-40000:], 'stderr': stderr[-12000:], 'truncated': len(stdout) > 40000 or len(stderr) > 12000, 'wait_policy': 'wait_until_completion', 'requested_timeout_sec': timeout}
    except subprocess.TimeoutExpired as exc:
        return {'ok': False, 'exit_code': 124, 'elapsed_ms': int((time.time() - started) * 1000), 'cmd': [Path(cmd[0]).name, *cmd[1:]], 'stdout': (exc.stdout or '')[-40000:] if isinstance(exc.stdout, str) else '', 'stderr': (exc.stderr or '')[-12000:] if isinstance(exc.stderr, str) else '', 'truncated': True, 'error': 'wait_interrupted', 'wait_policy': 'wait_until_completion', 'requested_timeout_sec': timeout}


def _artifact_dir(root: Path) -> Path:
    path = root / '.takesome' / 'ai-bridge' / 'artifacts' / 'operator-tools'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _iter_files(root: Path, roots: Iterable[str] | None = None) -> Iterable[Path]:
    for raw in roots or ['.']:
        start = _safe_path(root, raw, must_exist=False)
        if not start.exists():
            continue
        if start.is_file():
            yield start
            continue
        for current, dirs, files in os.walk(start):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.venv')]
            for name in files:
                yield Path(current) / name


def _is_text_candidate(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTS:
        return False
    if path.suffix.lower() in TEXT_EXTS:
        return True
    try:
        return b'\x00' not in path.read_bytes()[:4096]
    except Exception:
        return False


def repo_status(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    return {'schema': 'northstar.repo.status.v1', **_run(ctx.root, ['git', 'status', '--short', '--branch'], timeout=int(args.get('timeout_sec', 30) or 30))}


def repo_diff(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    paths = [str(x) for x in args.get('paths', []) or []]
    cmd = ['git', 'diff', '--no-ext-diff'] + (['--', *paths] if paths else [])
    res = _run(ctx.root, cmd, timeout=int(args.get('timeout_sec', 60) or 60))
    max_bytes = max(1024, min(int(args.get('max_bytes', 40000) or 40000), 200000))
    text = res.get('stdout', '')
    res['stdout'] = text[-max_bytes:]
    res['truncated'] = bool(res.get('truncated')) or len(text) > max_bytes
    return {'schema': 'northstar.repo.diff.v1', **res}


def repo_changed_files(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    include_untracked = bool(args.get('include_untracked', True))
    res = _run(ctx.root, ['git', 'status', '--porcelain=v1', '--untracked-files=all'], timeout=30)
    files: list[dict[str, str]] = []
    for raw in res.get('stdout', '').splitlines():
        if not raw:
            continue
        status = raw[:2]
        path = raw[3:].strip()
        if ' -> ' in path:
            path = path.split(' -> ', 1)[1]
        if status == '??' and not include_untracked:
            continue
        files.append({'status': status, 'path': path})
    return {'schema': 'northstar.repo.changed_files.v1', 'ok': res['ok'], 'files': files, 'count': len(files), 'git': res}


def _patch_input(ctx: BridgeContext, args: Dict[str, Any]) -> tuple[Path, bool]:
    patch_path = str(args.get('patch_path') or '')
    patch_text = str(args.get('patch_text') or '')
    if patch_path:
        return _safe_path(ctx.root, patch_path, must_exist=True), False
    if not patch_text:
        raise BridgeError('patch_text or patch_path is required', 'missing_patch')
    tmp = ctx.root / '.takesome' / 'ai-bridge' / 'tmp'
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / f'operator-patch-{int(time.time() * 1000)}.patch'
    path.write_text(patch_text, encoding='utf-8')
    return path, True


def repo_patch_preview(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    path, temporary = _patch_input(ctx, args)
    check = _run(ctx.root, ['git', 'apply', '--check', str(path)], timeout=int(args.get('timeout_sec', 60) or 60))
    stat = _run(ctx.root, ['git', 'apply', '--stat', str(path)], timeout=60)
    summary = _run(ctx.root, ['git', 'apply', '--summary', str(path)], timeout=60)
    if temporary:
        path.unlink(missing_ok=True)
    return {'schema': 'northstar.repo.patch.preview.v1', 'ok': check['ok'], 'patch': _rel(ctx.root, path), 'check': check, 'stat': stat, 'summary': summary}


def repo_patch_apply(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    _require_write(ctx, 'repo.patch.apply')
    path, temporary = _patch_input(ctx, args)
    check = _run(ctx.root, ['git', 'apply', '--check', str(path)], timeout=int(args.get('timeout_sec', 60) or 60))
    if not check['ok']:
        return {'schema': 'northstar.repo.patch.apply.v1', 'ok': False, 'applied': False, 'patch': _rel(ctx.root, path), 'check': check}
    if bool(args.get('dry_run', False)):
        return {'schema': 'northstar.repo.patch.apply.v1', 'ok': True, 'applied': False, 'dry_run': True, 'patch': _rel(ctx.root, path), 'check': check}
    apply = _run(ctx.root, ['git', 'apply', str(path)], timeout=int(args.get('timeout_sec', 60) or 60))
    if temporary:
        path.unlink(missing_ok=True)
    return {'schema': 'northstar.repo.patch.apply.v1', 'ok': apply['ok'], 'applied': apply['ok'], 'check': check, 'apply': apply}


def validate_python_changed(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    import py_compile
    explicit = [str(x) for x in args.get('paths', []) or []]
    if explicit:
        paths = [_safe_path(ctx.root, p, must_exist=True) for p in explicit]
    else:
        changed = repo_changed_files(ctx, {'include_untracked': True})['files']
        paths = [_safe_path(ctx.root, f['path'], must_exist=True) for f in changed if f['path'].endswith('.py') and (ctx.root / f['path']).exists()]
    checked: list[str] = []
    failures: list[dict[str, Any]] = []
    for path in paths:
        if path.suffix != '.py':
            continue
        checked.append(_rel(ctx.root, path))
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            failures.append({'path': _rel(ctx.root, path), 'error': str(exc)})
    return {'schema': 'northstar.validate.python_changed.v1', 'ok': not failures, 'checked': checked, 'checked_count': len(checked), 'failures': failures}


def bridge_inspect_tool_descriptors(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from .registry import build_tools
    from .rpc import public_tool_descriptors
    query = str(args.get('query') or '').lower()
    rows = []
    for desc in public_tool_descriptors(build_tools(ctx)):
        if query and query not in desc.get('name', '').lower() and query not in desc.get('description', '').lower():
            continue
        meta = desc.get('_meta', {})
        ann = desc.get('annotations', {})
        rows.append({'name': desc.get('name'), 'title': desc.get('title'), 'readOnlyHint': ann.get('readOnlyHint'), 'destructiveHint': ann.get('destructiveHint'), 'idempotentHint': ann.get('idempotentHint'), 'riskTier': meta.get('northstar/riskTier'), 'sudo': meta.get('northstar/sudo'), 'schema_keys': sorted((desc.get('inputSchema', {}).get('properties') or {}).keys())})
    return {'schema': 'northstar.bridge.inspect_tool_descriptors.v1', 'ok': True, 'write_enabled': ctx.write_enabled, 'sudo': getattr(ctx, 'sudo', False), 'count': len(rows), 'tools': rows}


def repo_search_text(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get('query') or '')
    if not query:
        raise BridgeError('query is required', 'missing_query')
    regex = bool(args.get('regex', False))
    flags = 0 if bool(args.get('case_sensitive', False)) else re.IGNORECASE
    pattern = re.compile(query if regex else re.escape(query), flags)
    before = max(0, min(int(args.get('context_before', 2) or 2), 20))
    after = max(0, min(int(args.get('context_after', 2) or 2), 20))
    limit = max(1, min(int(args.get('limit', 50) or 50), 500))
    roots = [str(x) for x in args.get('roots', []) or ['.']]
    results = []
    for path in _iter_files(ctx.root, roots):
        if len(results) >= limit:
            break
        if not _is_text_candidate(path):
            continue
        try:
            lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
        except Exception:
            continue
        for index, line in enumerate(lines):
            if pattern.search(line):
                lo = max(0, index - before)
                hi = min(len(lines), index + after + 1)
                results.append({'path': _rel(ctx.root, path), 'line': index + 1, 'text': line, 'context': [{'line': j + 1, 'text': lines[j]} for j in range(lo, hi)]})
                if len(results) >= limit:
                    break
    return {'schema': 'northstar.repo.search_text.v1', 'ok': True, 'query': query, 'count': len(results), 'results': results}


def archive_changed_files_zip(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    _require_write(ctx, 'archive.changed_files_zip')
    changed = repo_changed_files(ctx, {'include_untracked': True})['files']
    out = _artifact_dir(ctx.root) / str(args.get('output') or f'changed-files-{int(time.time())}.zip')
    manifest = []
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in changed:
            path = ctx.root / item['path']
            if path.is_file():
                zipf.write(str(path), item['path'])
                manifest.append(item)
        zipf.writestr('CHANGED_FILES_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    return {'schema': 'northstar.archive.changed_files_zip.v1', 'ok': True, 'path': _rel(ctx.root, out), 'file_count': len(manifest)}


def archive_full_zip(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    _require_write(ctx, 'archive.full_zip')
    out = _artifact_dir(ctx.root) / str(args.get('output') or f'NorthStar-Engine-source-{int(time.time())}.zip')
    count = 0
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for path in _iter_files(ctx.root, ['.']):
            relp = _rel(ctx.root, path)
            if path.suffix.lower() in BINARY_EXTS or any(part in SKIP_DIRS for part in Path(relp).parts) or relp == _rel(ctx.root, out):
                continue
            zipf.write(str(path), relp)
            count += 1
    return {'schema': 'northstar.archive.full_zip.v1', 'ok': True, 'path': _rel(ctx.root, out), 'file_count': count}


def archive_patch(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    _require_write(ctx, 'archive.patch')
    out = _artifact_dir(ctx.root) / str(args.get('output') or f'repo-diff-{int(time.time())}.patch')
    res = _run(ctx.root, ['git', 'diff', '--binary'], timeout=int(args.get('timeout_sec', 60) or 60))
    out.write_text(res.get('stdout', ''), encoding='utf-8')
    return {'schema': 'northstar.archive.patch.v1', 'ok': res['ok'], 'path': _rel(ctx.root, out), 'bytes': out.stat().st_size, 'git': {k: v for k, v in res.items() if k != 'stdout'}}


def terminal_simulate_resize(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    widths = [int(x) for x in args.get('widths', [160, 120, 100, 80, 140])]
    heights = [int(x) for x in args.get('heights', [40, 24, 18, 50])]
    cases = []
    ok = True
    for width in widths:
        paint_width = max(1, width - 1)
        autowrap = paint_width >= width
        ok = ok and not autowrap
        cases.append({'terminal_width': width, 'paint_width': paint_width, 'autowrap_risk': autowrap})
    return {'schema': 'northstar.terminal.simulate_resize.v1', 'ok': ok, 'heights': heights, 'cases': cases, 'policy': 'paint at width-1 and clear tracked footer rows before redraw'}


def python_symbols(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    path = _safe_path(ctx.root, str(args.get('path') or ''), must_exist=True)
    tree = ast.parse(path.read_text(encoding='utf-8', errors='replace'))
    rows = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            rows.append({'name': node.name, 'kind': 'class' if isinstance(node, ast.ClassDef) else 'function', 'line': node.lineno, 'end_line': getattr(node, 'end_lineno', node.lineno)})
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = ','.join(alias.name for alias in node.names) if isinstance(node, ast.Import) else ('.' * node.level + (node.module or ''))
            rows.append({'name': mod, 'kind': 'import', 'line': node.lineno, 'end_line': node.lineno})
    return {'schema': 'northstar.python.symbols.v1', 'ok': True, 'path': _rel(ctx.root, path), 'symbols': rows, 'count': len(rows)}


def _module_name(root: Path, path: Path) -> str:
    relp = _rel(root, path)
    if relp.endswith('__init__.py'):
        relp = str(Path(relp).parent)
    elif relp.endswith('.py'):
        relp = relp[:-3]
    return relp.replace('/', '.')


def python_import_graph(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    roots = [str(x) for x in args.get('roots', []) or ['noesis']]
    limit = max(1, min(int(args.get('limit', 1000) or 1000), 5000))
    edges = []
    for path in _iter_files(ctx.root, roots):
        if len(edges) >= limit or path.suffix != '.py':
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8', errors='replace'))
        except Exception:
            continue
        source = _module_name(ctx.root, path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append({'from': source, 'to': alias.name, 'line': node.lineno})
            elif isinstance(node, ast.ImportFrom):
                edges.append({'from': source, 'to': '.' * node.level + (node.module or ''), 'line': node.lineno})
            if len(edges) >= limit:
                break
    return {'schema': 'northstar.python.import_graph.v1', 'ok': True, 'edge_count': len(edges), 'edges': edges}


def python_call_graph(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    path = _safe_path(ctx.root, str(args.get('path') or ''), must_exist=True)
    tree = ast.parse(path.read_text(encoding='utf-8', errors='replace'))
    calls = []
    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.current = ''
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            old = self.current
            self.current = node.name
            self.generic_visit(node)
            self.current = old
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_Call(self, node: ast.Call) -> None:
            name = ''
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if self.current and name:
                calls.append({'caller': self.current, 'callee': name, 'line': node.lineno})
            self.generic_visit(node)
    Visitor().visit(tree)
    return {'schema': 'northstar.python.call_graph.v1', 'ok': True, 'path': _rel(ctx.root, path), 'calls': calls, 'call_count': len(calls)}


def repo_split_python_module(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    _require_write(ctx, 'repo.split_python_module')
    source = _safe_path(ctx.root, str(args.get('source') or ''), must_exist=True)
    target = _safe_path(ctx.root, str(args.get('target') or ''), must_exist=False)
    symbols = [str(x) for x in args.get('symbols', []) or []]
    apply = bool(args.get('apply', False))
    if not symbols:
        raise BridgeError('symbols are required', 'missing_symbols')
    text = source.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines()
    tree = ast.parse(text)
    moves = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in symbols:
            moves.append((node.name, node.lineno, getattr(node, 'end_lineno', node.lineno)))
    found = {name for name, _, _ in moves}
    if found != set(symbols):
        raise BridgeError('some symbols were not found', 'missing_symbols', {'missing': [s for s in symbols if s not in found]})
    moved = []
    remove: set[int] = set()
    for _, lo, hi in moves:
        moved.extend(lines[lo - 1:hi])
        moved.append('')
        remove.update(range(lo, hi + 1))
    new_source = '\n'.join(line for i, line in enumerate(lines, 1) if i not in remove).rstrip() + '\n'
    import_name = target.with_suffix('').relative_to(source.parent).as_posix().replace('/', '.')
    new_source = f'from {import_name} import {", ".join(symbols)}\n' + new_source
    new_target = '\n'.join(moved).rstrip() + '\n'
    if not apply:
        return {'schema': 'northstar.repo.split_python_module.v1', 'ok': True, 'applied': False, 'source': _rel(ctx.root, source), 'target': _rel(ctx.root, target), 'symbols': symbols, 'preview': {'source_removed_lines': sum(hi - lo + 1 for _, lo, hi in moves), 'target_bytes': len(new_target)}}
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        new_target = target.read_text(encoding='utf-8', errors='replace').rstrip() + '\n\n' + new_target
    source.write_text(new_source, encoding='utf-8')
    target.write_text(new_target, encoding='utf-8')
    return {'schema': 'northstar.repo.split_python_module.v1', 'ok': True, 'applied': True, 'source': _rel(ctx.root, source), 'target': _rel(ctx.root, target), 'symbols': symbols}


def validate_no_legacy(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    deny = [str(x) for x in args.get('deny', []) or ['.neytd@', 'asset.codec.pak', 'newengine.container.pak', 'render.api', 'physics.api', 'ai.api', '&mut World']]
    roots = [str(x) for x in args.get('roots', []) or ['noesis', 'NewEngine', 'Plugins']]
    limit = max(1, min(int(args.get('limit', 200) or 200), 2000))
    findings = []
    for path in _iter_files(ctx.root, roots):
        if len(findings) >= limit or not _is_text_candidate(path):
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        for token in deny:
            pos = text.find(token)
            if pos >= 0:
                findings.append({'path': _rel(ctx.root, path), 'line': text.count('\n', 0, pos) + 1, 'token': token})
                break
    return {'schema': 'northstar.validate.no_legacy.v1', 'ok': not findings, 'finding_count': len(findings), 'findings': findings}


def validate_line_count(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    max_lines = int(args.get('max_lines', 550) or 550)
    roots = [str(x) for x in args.get('roots', []) or ['noesis', 'NewEngine', 'Plugins']]
    findings = []
    for path in _iter_files(ctx.root, roots):
        if path.suffix.lower() not in {'.py', '.rs', '.ts', '.js'}:
            continue
        try:
            count = sum(1 for _ in path.open('r', encoding='utf-8', errors='replace'))
        except Exception:
            continue
        if count > max_lines:
            findings.append({'path': _rel(ctx.root, path), 'lines': count, 'over_by': count - max_lines})
    findings.sort(key=lambda item: item['lines'], reverse=True)
    return {'schema': 'northstar.validate.line_count.v1', 'ok': not findings, 'max_lines': max_lines, 'finding_count': len(findings), 'findings': findings[:500]}


def validate_import_cycles(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    graph = python_import_graph(ctx, args)['edges']
    internal_prefix = str(args.get('internal_prefix') or 'tools.scripts')
    adjacency: dict[str, set[str]] = {}
    for edge in graph:
        dst = edge['to'].lstrip('.')
        if dst.startswith(internal_prefix):
            adjacency.setdefault(edge['from'], set()).add(dst)
    cycles: list[list[str]] = []
    stack: list[str] = []
    seen: set[str] = set()
    def dfs(node: str) -> None:
        if node in stack:
            cycles.append(stack[stack.index(node):] + [node])
            return
        if node in seen:
            return
        seen.add(node)
        stack.append(node)
        for nxt in adjacency.get(node, set()):
            dfs(nxt)
        stack.pop()
    for node in list(adjacency):
        dfs(node)
    return {'schema': 'northstar.validate.import_cycles.v1', 'ok': not cycles, 'cycle_count': len(cycles), 'cycles': cycles[:100]}
