"""Map MeshCore message payloads to MIDI channel voice messages."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

import mido

# Optional compact control syntax in message text, e.g. "cc1:64" or "n60 v90"
_CC_RE = re.compile(r"^\s*cc\s*(\d{1,2})\s*:\s*(\d{1,3})\s*$", re.I)
_NOTE_RE = re.compile(
    r"^\s*n\s*(\d{1,3})(?:\s+v\s*(\d{1,3}))?\s*$", re.I
)


@dataclass(frozen=True)
class MidiMapConfig:
    """Routing and scaling for default (non-parse) mapping."""

    midi_channel: int = 0  # 0–15 → Bitwig track MIDI channel 1–16
    base_note: int = 48  # C3
    note_span: int = 36  # map hash into base_note .. base_note+span-1
    use_note_on_off: bool = True  # False → use poly pressure only (quieter)


def _clamp_byte(n: int) -> int:
    return max(0, min(127, n))


def _hash_bytes(data: bytes) -> int:
    return int.from_bytes(hashlib.sha256(data).digest()[:4], "little")


def text_to_midi_messages(
    text: str,
    meta: dict,
    cfg: MidiMapConfig,
) -> list[mido.Message]:
    """
    Convert mesh message text to a small list of mido messages.

    If `text` matches ``ccN:VV`` or ``nNN [vVV]``, that wins; otherwise a
    deterministic note-on/note-off pair is produced from the full payload.
    """
    raw = text.strip()
    m = _CC_RE.match(raw)
    if m:
        cc = int(m.group(1))
        val = int(m.group(2))
        if 0 <= cc <= 127 and 0 <= val <= 127:
            return [
                mido.Message(
                    "control_change",
                    channel=cfg.midi_channel,
                    control=cc,
                    value=val,
                )
            ]
        return []

    m = _NOTE_RE.match(raw)
    if m:
        note = int(m.group(1))
        vel = int(m.group(2)) if m.group(2) else 100
        note = _clamp_byte(note)
        vel = _clamp_byte(vel)
        if cfg.use_note_on_off:
            return [
                mido.Message(
                    "note_on",
                    channel=cfg.midi_channel,
                    note=note,
                    velocity=vel,
                ),
                mido.Message(
                    "note_off",
                    channel=cfg.midi_channel,
                    note=note,
                    velocity=0,
                ),
            ]
        return [
            mido.Message(
                "polytouch",
                channel=cfg.midi_channel,
                note=note,
                value=vel,
            )
        ]

    # Default: hash pubkey prefix + text for stable pitch / velocity
    key_bits = (
        meta.get("pubkey_prefix")
        or meta.get("path")
        or meta.get("channel_idx")
        or meta.get("channel_hash")
        or ""
    )
    if isinstance(key_bits, bytes):
        key_bytes = key_bits
    else:
        key_bytes = str(key_bits).encode("utf-8", errors="replace")
    digest = _hash_bytes(key_bytes + b"|" + text.encode("utf-8", errors="replace"))
    note = cfg.base_note + (digest % max(1, cfg.note_span))
    vel = 40 + (digest >> 8) % 88
    note = _clamp_byte(note)
    vel = _clamp_byte(vel)
    if cfg.use_note_on_off:
        return [
            mido.Message(
                "note_on",
                channel=cfg.midi_channel,
                note=note,
                velocity=vel,
            ),
            mido.Message(
                "note_off",
                channel=cfg.midi_channel,
                note=note,
                velocity=0,
            ),
        ]
    return [
        mido.Message(
            "polytouch",
            channel=cfg.midi_channel,
            note=note,
            value=vel,
        )
    ]


def send_messages(port: mido.ports.BaseOutput, messages: Iterable[mido.Message]) -> None:
    for msg in messages:
        port.send(msg)
