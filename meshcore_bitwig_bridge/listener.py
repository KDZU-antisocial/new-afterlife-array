"""CLI: print MeshCore messages as they arrive, with no MIDI dependency.

Useful for verifying a node-to-node link end-to-end before wiring MIDI/Bitwig
into the loop.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
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
        description="Print incoming MeshCore messages (no MIDI).",
    )
    p.add_argument(
        "-p",
        "--port",
        default=None,
        help="Serial device path. Falls back to $MESHCORE_SERIAL.",
    )
    p.add_argument("--baud", type=int, default=115200, help="Serial baud (default 115200).")
    p.add_argument(
        "--list-serial",
        action="store_true",
        help="List local serial ports and exit.",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args(argv)


def _now() -> str:
    return _dt.datetime.now().strftime("%H:%M:%S")


async def _run(args: argparse.Namespace) -> int:
    mesh = await MeshCore.create_serial(args.port, args.baud, debug=args.verbose)
    if mesh is None:
        print("error: could not connect to MeshCore node on serial", file=sys.stderr)
        return 1

    await mesh.commands.get_contacts()
    await mesh.start_auto_message_fetching()

    async def on_contact_msg(event):
        p = event.payload
        prefix = p.get("pubkey_prefix", "")
        contact = mesh.get_contact_by_key_prefix(prefix) if prefix else None
        name = (contact or {}).get("adv_name") or f"key:{prefix}"
        print(f"[{_now()}] DM      from {name}: {p.get('text','')}")

    async def on_channel_msg(event):
        p = event.payload
        ch = p.get("channel_idx", "?")
        print(f"[{_now()}] CHAN {ch} : {p.get('text','')}")

    async def on_advert(event):
        p = event.payload or {}
        pubkey = p.get("public_key", "")
        # meshcore subscribes internally to ADVERTISEMENT and adds the sender to
        # `mesh.contacts`, so by the time this fires the adv_name is usually
        # already resolvable. Fall back to a short pubkey if not.
        contact = mesh.get_contact_by_key_prefix(pubkey) if pubkey else None
        if contact and contact.get("adv_name"):
            who = contact["adv_name"]
        else:
            who = f"key:{pubkey[:12]}" if pubkey else "(unknown)"
        print(f"[{_now()}] ADVERT  from {who}")

    mesh.subscribe(EventType.CONTACT_MSG_RECV, on_contact_msg)
    mesh.subscribe(EventType.CHANNEL_MSG_RECV, on_channel_msg)
    mesh.subscribe(EventType.ADVERTISEMENT, on_advert)

    print(f"listening on {args.port} — Ctrl-C to quit")
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await mesh.stop_auto_message_fetching()
        await mesh.disconnect()
    return 0


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
        log.info("exit")
        rc = 0
    sys.exit(rc)


if __name__ == "__main__":
    main()
