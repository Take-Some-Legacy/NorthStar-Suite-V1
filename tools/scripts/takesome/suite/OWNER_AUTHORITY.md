# Owner Authority

Take Some Suite supports a local owner-authority mode for a workspace operated by its owner.

Local grant file:

```text
.takesome/authority/trusted_owner.json
```

Meaning:

```text
The workspace owner has already granted Suite permission to run owner-directed write workflows in this local workspace.
```

Required behavior:

```text
show operation category
show reports
keep workspace-root boundary
keep operation manifests
allow repeated owner-directed workflows without interactive reprompt inside Suite
```

Authority file schema:

```json
{
  "schema": "northstar.suite.owner_authority.v1",
  "enabled": true,
  "owner": "Кайла",
  "workspace": "NorthStar-Engine",
  "scope": "local_workspace",
  "mode": "trusted_owner"
}
```
