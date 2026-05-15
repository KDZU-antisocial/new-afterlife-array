"""CLI: the LURCH GOLDFINCH role.

On a fixed cooldown (default 30 s), LURCH picks a random slow-down delta
(default 7–27 BPM) and a random duration (default 3–13 s), then sends a
single ``lurch-tempo:<delta_bpm>:<duration_ms>`` direct message to a target
node (default ``FLICKER``). The target node's ``meshcore-bitwig-bridge``
applies the dip and recovers to its configured baseline.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys

from meshcore import EventType, MeshCore

from meshcore_bitwig_bridge._serial import (
    list_serial_ports,
    require_port_or_exit,
    resolve_port,
)

log = logging.getLogger(__name__)

DEFAULT_TARGET = "FLICKER"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "LURCH: periodically send a lurch-tempo command to another node. "
            "Picks a random slow-down in BPM and a random duration."
        ),
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
        default=DEFAULT_TARGET,
        help=f"Target contact adv_name (default {DEFAULT_TARGET!r}).",
    )
    p.add_argument(
        "--cooldown",
        type=float,
        default=30.0,
        help="Seconds between dip starts (default 30).",
    )
    p.add_argument(
        "--delta-min",
        type=int,
        default=7,
        help="Minimum BPM to slow by (default 7).",
    )
    p.add_argument(
        "--delta-max",
        type=int,
        default=27,
        help="Maximum BPM to slow by (default 27).",
    )
    p.add_argument(
        "--duration-min",
        type=float,
        default=3.0,
        help="Minimum dip duration in seconds (default 3).",
    )
    p.add_argument(
        "--duration-max",
        type=float,
        default=13.0,
        help="Maximum dip duration in seconds (default 13).",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="Send a single dip then exit, ignoring --cooldown.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent, but do not transmit.",
    )
    p.add_argument(
        "--list-serial",
        action="store_true",
        help="List local serial ports and exit.",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args(argv)


def _validate(args: argparse.Namespace) -> None:
    if args.delta_min < 0 or args.delta_max < args.delta_min:
        raise SystemExit("error: --delta-min/--delta-max must satisfy 0 <= min <= max")
    if args.duration_min <= 0 or args.duration_max < args.duration_min:
        raise SystemExit("error: --duration-min/--duration-max must satisfy 0 < min <= max")
    if args.cooldown < args.duration_max:
        log.warning(
            "--cooldown (%.1fs) is shorter than --duration-max (%.1fs); "
            "the receiver will drop overlapping dips",
            args.cooldown,
            args.duration_max,
        )


async def _resolve_target(mesh: MeshCore, name: str):
    await mesh.commands.get_contacts()
    contact = mesh.get_contact_by_name(name)
    if contact is None:
        raise SystemExit(
            f"error: no contact named {name!r}. Run 'meshcore-send --list-contacts'."
        )
    return contact


async def _send_dip(mesh: MeshCore, contact, delta_bpm: int, duration_ms: int) -> bool:
    payload = f"lurch-tempo:{delta_bpm}:{duration_ms}"
    res = await mesh.commands.send_msg_with_retry(contact, payload)
    if res is None:
        log.warning("no ACK for %s after retries", payload)
        return False
    return True


async def _run(args: argparse.Namespace) -> int:
    rng = random.Random()

    if args.dry_run:
        contact = None
        log.info("dry-run: skipping serial connection")
    else:
        mesh = await MeshCore.create_serial(args.port, args.baud, debug=args.verbose)
        if mesh is None:
            print("error: could not connect to MeshCore node on serial", file=sys.stderr)
            return 1
        contact = await _resolve_target(mesh, args.to)
        log.info("LURCH targeting %s every %.1fs", contact.get("adv_name"), args.cooldown)

    try:
        while True:
            delta = rng.randint(args.delta_min, args.delta_max)
            duration_s = rng.uniform(args.duration_min, args.duration_max)
            duration_ms = int(round(duration_s * 1000))

            if args.dry_run:
                print(f"would send lurch-tempo:{delta}:{duration_ms} to {args.to}")
            else:
                log.info(
                    "→ lurch-tempo:%d:%d (slow %d BPM for %.2fs)",
                    delta,
                    duration_ms,
                    delta,
                    duration_s,
                )
                ok = await _send_dip(mesh, contact, delta, duration_ms)
                if not ok:
                    log.warning("dip delivery uncertain; continuing")

            if args.once:
                return 0
            await asyncio.sleep(args.cooldown)
    except asyncio.CancelledError:
        raise
    finally:
        if not args.dry_run:
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

    _validate(args)

    if not args.dry_run:
        args.port = require_port_or_exit(resolve_port(args.port))

    try:
        rc = asyncio.run(_run(args))
    except KeyboardInterrupt:
        log.info("LURCH exiting")
        rc = 0
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
