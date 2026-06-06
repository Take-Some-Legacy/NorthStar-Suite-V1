# North Star LIVE Log Reader

Canonical CLI + UI diagnostic reader for logger-published live URL streams.

## UI-first command

The UI can be launched with one command:

```powershell
northstar-log-reader ui
```

No arguments are required. The live URL field is prefilled with `http://127.0.0.1:8765/logs` and can be edited inside the UI.

Optional arguments prefill or override the UI launch:

```powershell
northstar-log-reader ui --url http://127.0.0.1:8765/logs
northstar-log-reader html --url http://127.0.0.1:8765/logs --out log-reader.html
northstar-log-reader ui --no-open
```

Behavior:

- without `--url`: URL field is prefilled with `http://127.0.0.1:8765/logs`
- with `--url`: URL field is prefilled
- without `--out`: HTML is written next to the executable
- without `--no-open`: generated UI opens automatically

## Live CLI

```powershell
northstar-log-reader live --format table
northstar-log-reader live --format jsonl > live_logs.jsonl
northstar-log-reader live --url http://127.0.0.1:4319/logs/live --format table
northstar-log-reader live --url http://127.0.0.1:4319/logs/live --format jsonl > live_logs.jsonl
```

## Snapshot CLI

```powershell
northstar-log-reader read --format table
northstar-log-reader tail --count 50 --format jsonl
northstar-log-reader read --url file://logs/live.ulog.jsonl --format table
northstar-log-reader tail --url file://logs/live.ulog.jsonl --count 50 --format jsonl
```

## Boundary

The tool consumes logger-published URL payloads. It does not import engine internals and does not create an engine-owned network reader.

Live read belongs to the logger/plugin side; this tool is only an external diagnostic consumer.
