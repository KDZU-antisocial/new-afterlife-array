"""CLI: send a MeshCore message from the attached node.

By default the message goes out on public channel 0, which any other node
listening on that channel will receive without any contact/pairing setup.

Use ``--to NAME`` (or ``--to-key PREFIX``) to send a direct message to a
contact that the local node already knows about.  Contact discovery happens
automatically as nodes hear each other's adverts; you can inspect the
current list with ``--list-contacts``.
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
        description="Send a MeshCore message via the USB-attached node.",
    )
    p.add_argument(
        "message",
        nargs="?",
        default=None,
        help="Text to send. Omit when using --list-contacts or --list-serial.",
    )
    p.add_argument(
        "-p",
        "--port",
        default=None,
        help="Serial device path. Falls back to $MESHCORE_SERIAL.",
    )
    p.add_argument("--baud", type=int, default=115200, help="Serial baud (default 115200).")
    p.add_argument(
        "--to",
        default=None,
        help="Send a direct message to the contact with this adv_name.",
    )
    p.add_argument(
        "--to-key",
        default=None,
        help="Send a direct message to a contact by public-key prefix (hex).",
    )
    p.add_argument(
        "--channel",
        type=int,
        default=0,
        help="Channel index for broadcast (default 0). Ignored if --to/--to-key is set.",
    )
    p.add_argument(
        "--no-retry",
        action="store_true",
        help="For direct messages, send once without retry/ACK wait.",
    )
    p.add_argument(
        "--list-contacts",
        action="store_true",
        help="Fetch and print known contacts, then exit.",
    )
    p.add_argument(
        "--list-serial",
        action="store_true",
        help="List local serial ports and exit.",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args(argv)


async def _print_contacts(mesh: MeshCore) -> None:
    res = await mesh.commands.get_contacts()
    if res.type == EventType.ERROR:
        print(f"error fetching contacts: {res.payload}", file=sys.stderr)
        return
    contacts = mesh.contacts
    if not contacts:
        print("(no contacts known yet — wait for adverts or run --to-key)")
        return
    print(f"{'adv_name':<24} {'pubkey_prefix':<14} path")
    for c in contacts.values():
        name = c.get("adv_name", "")
        pk = (c.get("public_key") or "")[:12]
        path = "flood" if c.get("out_path_len", -1) == -1 else c.get("out_path", "")
        print(f"{name:<24} {pk:<14} {path}")


async def _resolve_contact(mesh: MeshCore, name: str | None, key: str | None):
    await mesh.commands.get_contacts()
    if name:
        c = mesh.get_contact_by_name(name)
        if c is None:
            raise SystemExit(
                f"error: no contact named {name!r}. Run with --list-contacts to see known nodes."
            )
        return c
    if key:
        c = mesh.get_contact_by_key_prefix(key.lower())
        if c is None:
            raise SystemExit(
                f"error: no contact with pubkey prefix {key!r}. Run with --list-contacts."
            )
        return c
    return None


async def _run(args: argparse.Namespace) -> int:
    mesh = await MeshCore.create_serial(args.port, args.baud, debug=args.verbose)
    if mesh is None:
        print("error: could not connect to MeshCore node on serial", file=sys.stderr)
        return 1

    try:
        if args.list_contacts:
            await _print_contacts(mesh)
            return 0

        if args.message is None:
            print("error: missing message text", file=sys.stderr)
            return 2

        contact = await _resolve_contact(mesh, args.to, args.to_key)

        if contact is None:
            log.info("sending on channel %d: %s", args.channel, args.message)
            res = await mesh.commands.send_chan_msg(args.channel, args.message)
            if res.type == EventType.ERROR:
                print(f"send failed: {res.payload}", file=sys.stderr)
                return 1
            print(f"sent on channel {args.channel}: {args.message!r}")
            return 0

        name = contact.get("adv_name", "?")
        log.info("sending DM to %s: %s", name, args.message)
        if args.no_retry:
            res = await mesh.commands.send_msg(contact, args.message)
            if res is None or res.type == EventType.ERROR:
                print(f"send failed: {getattr(res, 'payload', None)}", file=sys.stderr)
                return 1
            print(f"sent (no-ack) to {name}: {args.message!r}")
            return 0

        res = await mesh.commands.send_msg_with_retry(contact, args.message)
        if res is None:
            print(
                f"warning: no ACK from {name} after retries (message may still arrive)",
                file=sys.stderr,
            )
            return 1
        print(f"delivered to {name}: {args.message!r}")
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
