from __future__ import annotations

import sys
from collections.abc import Sequence

from noesis.runtime.services import resolve_service, run_service


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return run_service("suite", ["suite"])

    command = args[0]
    service = resolve_service(command)
    if service is not None and service.consumes_command_token:
        return run_service(command, args[1:])
    if command == "takesome":
        return run_service("suite", args[1:])
    return run_service("suite", args)


if __name__ == "__main__":
    raise SystemExit(main())
