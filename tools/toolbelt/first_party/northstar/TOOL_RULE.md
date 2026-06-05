# North Star First-Party Tool Rule

This rule applies to every tool under:

```text
tools/toolbelt/first_party/northstar
```

and to its Rust source under:

```text
tools/toolsSrc
```

## 1. Required CLI Contract

Every first-party North Star CLI tool MUST support:

```text
--help
version
accepted-inputs
doctor
```

The commands MUST be non-mutating and safe to run from test runners, GUI tooling, CI, and descriptor discovery.

### `--help`

Prints human-facing usage, examples, command list, accepted inputs, and produced outputs.

### `version`

Prints the tool name and semantic version.

Example:

```text
northstar-ytd-packer 0.3.1
```

### `accepted-inputs`

Prints a diagnostic contract summary using status output.

Example:

```text
[INFO] northstar-ytd-packer version=0.3.1
[INFO] accepted input files: *.png, *.dds, *.ytd
[INFO] produced output files: *.ytd, extracted *.dds
```

### `doctor`

Runs a lightweight self-check and prints status output.

Example:

```text
[OK] northstar-ytd-packer doctor passed
[INFO] version=0.3.1
```

## 2. Status Output vs Payload Output

North Star tools have two output classes. They MUST NOT be mixed.

### 2.1 Status Output

Status output is human-facing UX and MAY use ANSI colors.

Use only for:

```text
help
version
accepted-inputs
doctor
build status
validation status
warnings
errors
progress messages
```

Status output MUST go through the shared helper:

```rust
northstar_cli::ansi::info(...)
northstar_cli::ansi::ok(...)
northstar_cli::ansi::warn(...)
northstar_cli::ansi::error(...)
```

Color rule:

```text
[ and ] -> grey / ANSI 90
INFO    -> blue / ANSI 94
OK      -> green / ANSI 92
WARN    -> yellow / ANSI 93
ERROR   -> red / ANSI 91
```

The textual tag MUST remain readable as:

```text
[INFO]
[OK]
[WARN]
[ERROR]
```

### 2.2 Payload Output

Payload output is machine-readable or pipeline-readable data. It MUST remain clean raw stdout.

Payload output MUST NOT contain:

```text
ANSI escape sequences
[INFO]
[OK]
[WARN]
[ERROR]
human progress text
```

Payload output includes:

```text
hash lines
JSON inspect output
JSON manifest output
XML dumps
body dumps
plain extracted file paths
CSV/list outputs intended for piping
```

Use raw output APIs for payload:

```rust
println!(...)
write!(...)
writeln!(...)
serde_json::to_writer(...)
serde_json::to_writer_pretty(...)
```

Valid examples:

```powershell
northstar-hasher names.txt > hashes.txt
northstar-nepak-packer manifest archive.nepak > manifest.json
northstar-ytd-packer inspect car.ytd > report.json
```

The redirected files MUST contain only payload data.

## 3. Shared CLI Helper

All first-party Rust tools MUST use:

```text
tools/shared/northstar_cli
```

for shared terminal/status UX.

Do not duplicate local `ansi.rs` modules inside individual tools. If status formatting changes, it must be changed once in:

```text
tools/shared/northstar_cli/src/ansi.rs
```

## 4. Toolbelt Binary Rule

Built release binaries live in:

```text
tools/toolbelt/first_party/northstar/<tool>/bin
```

Source of truth lives in:

```text
tools/toolsSrc/<tool>
```

After changing source, always run:

```text
cargo build --release
```

and copy the release executable into the corresponding toolbelt `bin` directory.

## 5. Test Contract

Every tool package SHOULD contain:

```text
test/test.bat
testData/
```

Local `test/test.bat` MUST check at least:

```text
version
accepted-inputs
doctor
```

and then run tool-specific smoke tests.

The global runner is:

```text
tools/toolbelt/first_party/testAll.bat
```

It MUST be able to run:

```text
version
accepted-inputs
doctor
local-test
```

for every active first-party North Star tool.

## 6. Descriptor Rule

Every active first-party tool MUST have:

```text
tool.json
```

using schema:

```text
takesome.tool.v2
```

The descriptor MUST declare the same safe commands exposed by the binary:

```text
help
version
accepted-inputs
doctor
```

## 7. Legacy Rule

Legacy tools MUST NOT remain active in first-party discovery.

If a tool is replaced, the replacement must be under:

```text
tools/toolbelt/first_party/northstar
```

and the old third-party or legacy descriptor must be removed or disabled.

## 8. Release Gate

A first-party tool update is not complete until all are true:

```text
cargo build --release passes
release exe copied to toolbelt bin
version passes
accepted-inputs passes
doctor passes
local test passes, when present
testAll.bat passes or any failure is explicitly documented
payload commands remain clean raw stdout
```
