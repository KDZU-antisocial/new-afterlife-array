"""CLI: MeshCore serial → MIDI for Bitwig."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import mido
from meshcore import EventType, MeshCore

from meshcore_bitwig_bridge._serial import (
    list_serial_ports,
    require_port_or_exit,
    resolve_port,
)
from meshcore_bitwig_bridge.midi_map import (
    MidiMapConfig,
    TempoCCConfig,
    parse_lurch_tempo,
    tempo_cc_message,
    text_to_midi_messages,
)

log = logging.getLogger(__name__)


def _open_midi_out(
    name: str | None,
    *,
    virtual: bool,
    virtual_name: str,
) -> mido.ports.BaseOutput:
    names = mido.get_output_names()
    if not names and not virtual:
        print(
            "No MIDI output devices found. On macOS, enable IAC in "
            "Audio MIDI Setup, or use --virtual-midi.",
            file=sys.stderr,
        )
        sys.exit(1)
    if virtual:
        return mido.open_output(virtual_name, virtual=True)
    if name:
        for candidate in names:
            if name in candidate or candidate == name:
                return mido.open_output(candidate)
        print(f"MIDI output {name!r} not found. Available:\n", file=sys.stderr)
        for n in names:
            print(f"  {n}", file=sys.stderr)
        sys.exit(1)
    return mido.open_output(names[0])


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Read MeshCore companion messages over USB serial and send MIDI."
    )
    p.add_argument(
        "-p",
        "--port",
        default=None,
        help="Serial device path (e.g. /dev/cu.usbmodem* on macOS, COM3 on Windows). "
        "If omitted, uses env MESHCORE_SERIAL. Required except with --list-serial or --list-midi.",
    )
    p.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Serial baud rate (default 115200).",
    )
    p.add_argument(
        "--midi-out",
        default=None,
        help="Substring of a real MIDI output name. Ignored if --virtual-midi is set.",
    )
    p.add_argument(
        "--virtual-midi",
        action="store_true",
        help="Expose a virtual MIDI port (visible in Bitwig as an input).",
    )
    p.add_argument(
        "--virtual-name",
        default="MeshCore → Bitwig",
        help="Name of the virtual MIDI port when --virtual-midi is used.",
    )
    p.add_argument(
        "--midi-channel",
        type=int,
        default=0,
        help="MIDI channel 0–15 (Bitwig shows as 1–16). Default 0.",
    )
    p.add_argument(
        "--tempo-cc",
        type=int,
        default=20,
        help="CC# mapped to Bitwig Tempo for lurch-tempo handling (default 20).",
    )
    p.add_argument(
        "--baseline-bpm",
        type=float,
        default=120.0,
        help="Baseline tempo the bridge recovers to after a dip (default 120).",
    )
    p.add_argument(
        "--bpm-min",
        type=float,
        default=60.0,
        help="BPM that corresponds to CC value 0 in Bitwig's tempo mapping.",
    )
    p.add_argument(
        "--bpm-max",
        type=float,
        default=180.0,
        help="BPM that corresponds to CC value 127 in Bitwig's tempo mapping.",
    )
    p.add_argument(
        "--list-midi",
        action="store_true",
        help="List MIDI output names and exit.",
    )
    p.add_argument(
        "--list-serial",
        action="store_true",
        help="List serial ports and exit.",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging (meshcore + this bridge).",
    )
    return p.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    if args.midi_channel < 0 or args.midi_channel > 15:
        print("--midi-channel must be 0–15", file=sys.stderr)
        sys.exit(1)

    midi_cfg = MidiMapConfig(midi_channel=args.midi_channel)
    tempo_cfg = TempoCCConfig(
        cc=args.tempo_cc,
        midi_channel=args.midi_channel,
        baseline_bpm=args.baseline_bpm,
        bpm_min=args.bpm_min,
        bpm_max=args.bpm_max,
    )
    midi_out = _open_midi_out(
        args.midi_out,
        virtual=args.virtual_midi,
        virtual_name=args.virtual_name,
    )
    log.info("MIDI output: %s", midi_out.name)

    mesh = await MeshCore.create_serial(args.port, args.baud, debug=args.verbose)
    await mesh.start_auto_message_fetching()

    # Serialize concurrent lurch-tempo requests so a second message arriving
    # mid-dip can't strand Bitwig at the slowed tempo.
    dip_lock = asyncio.Lock()

    async def _apply_lurch_tempo(delta_bpm: int, duration_ms: int, source: str) -> None:
        if dip_lock.locked():
            log.info("lurch-tempo from %s ignored: a dip is already in progress", source)
            return
        async with dip_lock:
            target = tempo_cfg.baseline_bpm - delta_bpm
            log.info(
                "lurch-tempo from %s: %.1f → %.1f BPM for %d ms",
                source,
                tempo_cfg.baseline_bpm,
                target,
                duration_ms,
            )
            midi_out.send(tempo_cc_message(target, tempo_cfg))
            try:
                await asyncio.sleep(duration_ms / 1000.0)
            finally:
                midi_out.send(tempo_cc_message(tempo_cfg.baseline_bpm, tempo_cfg))
                log.info("lurch-tempo recovered to %.1f BPM", tempo_cfg.baseline_bpm)

    def _maybe_handle_lurch_tempo(text: str, source: str) -> bool:
        parsed = parse_lurch_tempo(text)
        if parsed is None:
            return False
        delta, duration_ms = parsed
        asyncio.create_task(_apply_lurch_tempo(delta, duration_ms, source))
        return True

    async def on_contact_msg(event):
        payload = event.payload
        text = str(payload.get("text") or "")
        prefix = payload.get("pubkey_prefix", "")
        contact = mesh.get_contact_by_key_prefix(prefix) if prefix else None
        source = (contact or {}).get("adv_name") or f"key:{prefix}"
        if _maybe_handle_lurch_tempo(text, source):
            return
        meta = {k: payload.get(k) for k in ("pubkey_prefix", "path")}
        msgs = text_to_midi_messages(text, meta, midi_cfg)
        if msgs:
            for m in msgs:
                midi_out.send(m)
            log.info("contact msg → MIDI (%d msgs): %s", len(msgs), text[:80])

    async def on_channel_msg(event):
        payload = event.payload
        text = str(payload.get("text") or "")
        ch = payload.get("channel_idx", "")
        source = f"channel {ch}"
        if _maybe_handle_lurch_tempo(text, source):
            return
        meta = {"channel_idx": ch}
        msgs = text_to_midi_messages(text, meta, midi_cfg)
        if msgs:
            for m in msgs:
                midi_out.send(m)
            log.info("channel msg → MIDI (%d msgs): %s", len(msgs), text[:80])

    mesh.subscribe(EventType.CONTACT_MSG_RECV, on_contact_msg)
    mesh.subscribe(EventType.CHANNEL_MSG_RECV, on_channel_msg)

    log.info("Connected to MeshCore on %s; waiting for messages…", args.port)
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        raise
    finally:
        await mesh.stop_auto_message_fetching()
        await mesh.disconnect()
        midi_out.close()


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if args.list_midi:
        for n in mido.get_output_names():
            print(n)
        return
    if args.list_serial:
        print(list_serial_ports())
        return

    args.port = require_port_or_exit(resolve_port(args.port))

    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        log.info("exit")


if __name__ == "__main__":
    main()
