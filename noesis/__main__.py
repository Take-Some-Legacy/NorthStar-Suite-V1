from __future__ import annotations

import sys

from noesis.runtime.services import SERVICE_REGISTRY, resolve_service

_DIRECT_SUITE_COMMANDS = {
    "suite",
    "tools",
    "env-doctor",
    "env-tools",
    "env-toolchains",
    "env-status",
    "java",
    "noesis-test-dev-repo",
    "registry-report",
    "registry-preflight",
    "observability",
    "suite-actions-list",
    "suite-actions-validate",
    "suite-bridge-menu-generate",
    "suite-intelligence",
    "suite-intelligence-loop",
    "suite-intelligence-loop-check",
    "suite-intelligence-smoke-deepseek",
    "tools-list",
    "tools-validate",
    "tools-doctor",
}


def _suite_main():
    from noesis.suite.cli import main as suite_main

    return suite_main


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print("NOESIS runtime")
        print("Usage: python -m noesis <service-or-suite-command> [args...]")
        print("Services:")
        for service_id, spec in sorted(SERVICE_REGISTRY.items()):
            print(f"  {service_id:18} {spec.description}")
        print("Suite commands may also be called directly, e.g.:")
        print("  python -m noesis env-doctor --repo-dir %USERPROFILE%\\Documents\\Repos\\java-platformer")
        print("  python -m noesis noesis-test-dev-repo verify --scope noesis-core")
        return 0

    token = args[0]
    if token in _DIRECT_SUITE_COMMANDS:
        # Keep the Suite command token. `suite` CLI expects it as its subcommand.
        return int(_suite_main()(args) or 0)

    service = resolve_service(token)
    if service is None:
        print(f"Unknown NOESIS service or Suite command: {token}", file=sys.stderr)
        print("Run `python -m noesis --help` for available services.", file=sys.stderr)
        return 2

    remaining = args[1:]
    if not service.consumes_command_token:
        remaining = [service.name, *remaining]
    return int(service.load()(remaining) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
