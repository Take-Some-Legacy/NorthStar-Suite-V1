# Local Operator Access

Take Some Suite must not accept anonymous local control requests.

The allowed model is:

```text
workspace owner grant
operator allowlist
local access key
session record
visible diagnostics
```

No YouTube binding is part of this model.

The local grant file is:

```text
.takesome/authority/trusted_owner.json
```

The local allowlist file is:

```text
.takesome/authority/operators.json
```

A bridge request is accepted only when its operator id is present in the allowlist and the supplied local access key matches the configured key fingerprint.

Risk labels and operation reports stay visible. The access gate answers who may operate the workspace; it does not rename operations as safe.
