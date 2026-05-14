"""CLI: show or change the adv_name of the attached MeshCore node.

The adv_name is the human-readable label that the node broadcasts in its
periodic adverts.  Other nodes see this string as the contact's name.

Usage:
    meshcore-name                # print current name
    meshcore-name "Rob's Laptop" # set new name and broadcast an advert
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
        description="Show or set the adv_name of the attached MeshCore node.",
    )
    p.add_argument(
        "name",
        nargs="?",
        default=None,
        help="New name. Omit to just print the current name.",
    )
    p.add_argument(
        "-p",
        "--port",
        default=None,
        help="Serial device path. Falls back to $MESHCORE_SERIAL.",
    )
    p.add_argument("--baud", type=int, default=115200, help="Serial baud (default 115200).")
    p.add_argument(
        "--no-advert",
        action="store_true",
        help="After setting the name, don't broadcast a fresh advert.",
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
        current = mesh.self_info.get("name", "") if mesh.self_info else ""

        if args.name is None:
            print(current or "(no name set)")
            return 0

        if args.name == current:
            print(f"already named {current!r}, nothing to do")
            return 0

        res = await mesh.commands.set_name(args.name)
        if res is None or res.type == EventType.ERROR:
            print(f"error: set_name failed: {getattr(res, 'payload', None)}", file=sys.stderr)
            return 1

        print(f"renamed: {current!r} -> {args.name!r}")

        if not args.no_advert:
            adv = await mesh.commands.send_advert(flood=True)
            if adv is None or adv.type == EventType.ERROR:
                print(
                    f"warning: advert broadcast failed: {getattr(adv, 'payload', None)}",
                    file=sys.stderr,
                )
            else:
                print("broadcast advert so neighbors learn the new name")
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
