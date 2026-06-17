# North Star Bridge Auth Model

North Star remote MCP is no longer a `noauth` surface.

The canonical MCP endpoint is defined by `mcp_routes.py` and defaults to:

```text
/mcp
```

Experimental route names such as `/mcp-v2` and `/mcp-noauth` must not be hardcoded in `server.py`.  They are not part of the default route profile.

Remote ChatGPT-style connectors use OAuth discovery:

```text
/.well-known/oauth-protected-resource
/.well-known/oauth-authorization-server
/.well-known/openid-configuration
/oauth/register
/oauth/authorize
/oauth/token
```

MCP handshake methods remain reachable so clients can discover capabilities:

```text
initialize
tools/list
resources/list
resources/templates/list
prompts/list
ping
```

Actual `tools/call` execution requires an OAuth bearer token or the local bridge token.  Direct `/tools/call` remains local-operator protected.

Local trusted-owner authority still controls whether write/sudo handlers are allowed to mutate the workspace; OAuth answers who is allowed to call the remote MCP surface.
