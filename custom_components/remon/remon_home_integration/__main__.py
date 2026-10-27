"""Read one device from the command line: ``python -m remon_home_integration <host> [--port N]``.

Prints the validated status as JSON, for checking a device on the LAN without Home Assistant.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys

from .client import DEFAULT_PORT, DEFAULT_TIMEOUT, RemonClient
from .exceptions import RemonError


async def _run(host: str, port: int, request_timeout: float) -> int:
    try:
        async with RemonClient(host, port=port, request_timeout=request_timeout) as client:
            status = await client.get_status()
    except (RemonError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    out = dataclasses.asdict(status) | {"display_name": status.display_name, "mac": status.mac}
    print(json.dumps(out, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, read the device, return the process exit code."""
    parser = argparse.ArgumentParser(prog="python -m remon_home_integration", description=__doc__)
    parser.add_argument(
        "host", help="IP address or hostname, for example SaltBuddy-a1b2c3d4e5f6.local"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.host, args.port, args.timeout))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
