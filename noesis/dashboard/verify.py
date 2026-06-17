from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .publisher import publish_dashboard
from .runs import index_payload
from .ui import render_html


def check(ok: bool, name: str, detail: str = '') -> dict[str, Any]:
    return {'name': name, 'status': 'ok' if ok else 'failed', 'detail': detail}


def verify_dashboard(root: Path) -> dict[str, Any]:
    payload = index_payload(root)
    published = publish_dashboard(root, payload, html_enabled=True)
    markup = render_html(published)
    json_path = root / '.noesis' / 'index' / 'runs.json'
    html_path = root / '.noesis' / 'dashboard' / 'index.html'
    style_path = root / 'noesis' / 'dashboard' / 'static' / 'noesis-dashboard.css'
    checks = [
        check(isinstance(payload, dict), 'payload.dict'),
        check('recent' in payload, 'payload.recent'),
        check('counts' in payload, 'payload.counts'),
        check('worker' in payload, 'payload.worker'),
        check('NOESIS Operator Dashboard' in markup, 'html.title'),
        check('burger' in markup, 'html.burger'),
        check('worker-block' in markup, 'html.worker'),
        check('controls-block' in markup, 'html.controls'),
        check(json_path.is_file(), 'publish.json', str(json_path)),
        check(html_path.is_file(), 'publish.html', str(html_path)),
        check(style_path.is_file() and style_path.stat().st_size > 0, 'static.css', str(style_path)),
    ]
    failed = [item for item in checks if item['status'] != 'ok']
    return {
        'schema': 'noesis.dashboard.verify.v1',
        'status': 'ok' if not failed else 'failed',
        'root': str(root),
        'checks': checks,
        'failed': failed,
        'artifacts': {'runsJson': str(json_path), 'html': str(html_path), 'css': str(style_path)},
    }


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    report = verify_dashboard(Path.cwd())
    if '--json' in args:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"dashboard verify: {report['status']}")
        for item in report['checks']:
            print(f"  {item['status']:6} {item['name']} {item.get('detail') or ''}")
    return 0 if report['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
