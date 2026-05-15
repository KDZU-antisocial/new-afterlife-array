"""Map MeshCore message payloads to MIDI channel voice messages."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, Optional

import mido

# Optional compact control syntax in message text, e.g. "cc1:64" or "n60 v90"
_CC_RE = re.compile(r"^\s*cc\s*(\d{1,2})\s*:\s*(\d{1,3})\s*$", re.I)
_NOTE_RE = re.compile(
    r"^\s*n\s*(\d{1,3})(?:\s+v\s*(\d{1,3}))?\s*$", re.I
)
# GOLDFINCH compositional verb: "lurch-tempo:<delta_bpm>:<duration_ms>"
# delta_bpm is a positive integer to slow by (LURCH only slows down).
_LURCH_TEMPO_RE = re.compile(
    r"^\s*lurch-tempo\s*:\s*(\d{1,3})\s*:\s*(\d{1,7})\s*$", re.I
)


@dataclass(frozen=True)
class MidiMapConfig:
    """Routing and scaling for default (non-parse) mapping."""

    midi_channel: int = 0  # 0–15 → Bitwig track MIDI channel 1–16
    base_note: int = 48  # C3
    note_span: int = 36  # map hash into base_note .. base_note+span-1
    use_note_on_off: bool = True  # False → use poly pressure only (quieter)


@dataclass(frozen=True)
class TempoCCConfig:
    """How to translate BPM values into a single Bitwig-mapped CC.

    The user is expected to right-click Bitwig's Tempo display and 'Learn
    Controller Assignment' for this CC on this channel, with the mapping
    range set to ``bpm_min`` .. ``bpm_max``.
    """

    cc: int = 20
    midi_channel: int = 0
    baseline_bpm: float = 120.0
    bpm_min: float = 60.0
    bpm_max: float = 180.0


def parse_lurch_tempo(text: str) -> Optional[tuple[int, int]]:
    """Return (delta_bpm, duration_ms) for a lurch-tempo command, else None."""
    m = _LURCH_TEMPO_RE.match(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def bpm_to_cc_value(bpm: float, cfg: TempoCCConfig) -> int:
    """Convert a BPM into a 0–127 CC value using cfg's linear mapping."""
    span = cfg.bpm_max - cfg.bpm_min
    if span <= 0:
        return 64
    frac = (bpm - cfg.bpm_min) / span
    return _clamp_byte(round(frac * 127))


def tempo_cc_message(bpm: float, cfg: TempoCCConfig) -> mido.Message:
    """Build the MIDI CC message that sets Bitwig's mapped tempo to ``bpm``."""
    return mido.Message(
        "control_change",
        channel=cfg.midi_channel,
        control=cfg.cc,
        value=bpm_to_cc_value(bpm, cfg),
    )


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
