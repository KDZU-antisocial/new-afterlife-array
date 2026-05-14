"""CLI: broadcast a fresh advert from the attached MeshCore node.

Adverts are how nodes learn about each other.  This command is useful for
verifying the radio link end-to-end ("did my neighbor hear me just now?")
without changing the node's adv_name as a side effect.

Usage:
    meshcore-advert            # zero-hop advert (direct neighbors only)
    meshcore-advert --flood    # flood across the mesh
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from meshcore import EventType, MeshCore

from meshcore_bitwig_bridge._serial import (
    list_serial_ports,
    require_port_or_exit,
    resolve_port,
)

log = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Broadcast a MeshCore advert from the USB-attached node.",
    )
    p.add_argument(
        "-p",
        "--port",
        default=None,
        help="Serial device path. Falls back to $MESHCORE_SERIAL.",
    )
    p.add_argument("--baud", type=int, default=115200, help="Serial baud (default 115200).")
    p.add_argument(
        "--flood",
        action="store_true",
        help="Flood the advert across the mesh (default: zero-hop to neighbors only).",
    )
    p.add_argument(
        "--list-serial",
        action="store_true",
        help="List local serial ports and exit.",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    mesh = await MeshCore.create_serial(args.port, args.baud, debug=args.verbose)
    if mesh is None:
        print("error: could not connect to MeshCore node on serial", file=sys.stderr)
        return 1

    try:
        name = (mesh.self_info or {}).get("name", "") or "(unnamed node)"
        scope = "flood" if args.flood else "zero-hop"
        res = await mesh.commands.send_advert(flood=args.flood)
        if res is None or res.type == EventType.ERROR:
            print(
                f"error: advert broadcast failed: {getattr(res, 'payload', None)}",
                file=sys.stderr,
            )
            return 1
        print(f"broadcast {scope} advert from {name!r}")
        return 0
    finally:
        await mesh.disconnect()


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.list_serial:
        print(list_serial_ports())
        return

    args.port = require_port_or_exit(resolve_port(args.port))

    try:
        rc = asyncio.run(_run(args))
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()
