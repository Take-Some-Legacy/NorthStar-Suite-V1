# North Star Hasher

First-party Rust RAGE/JOAAT string hash utility for newline-separated name lists.

## Commands

```text
northstar-hasher --help
northstar-hasher version
northstar-hasher accepted-inputs
northstar-hasher doctor
northstar-hasher [-stripext] [-literal] filename [hashcode]
```

## Output

```text
ATSTRINGHASH("adder",0xb779a091)
ATLITERALSTRINGHASH("Adder",0x2153f8fd)
```

## Source

```text
tools/toolsSrc/northstar_hasher
```

## Tests

Run:

```bat
tools\toolbelt\first_party\northstar\hasher\test\test.bat
```
