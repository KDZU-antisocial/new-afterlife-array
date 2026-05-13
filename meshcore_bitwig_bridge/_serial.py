"""Shared helpers for resolving the serial port and listing devices."""

from __future__ import annotations

import os
import sys


def resolve_port(arg_port: str | None) -> str | None:
    """Return the serial port from --port, or MESHCORE_SERIAL, or None."""
    if arg_port:
        return arg_port
    env_port = (os.environ.get("MESHCORE_SERIAL") or "").strip()
    return env_port or None


def list_serial_ports() -> str:
    """Pretty-printed list of available serial devices."""
    try:
        from serial.tools import list_ports

        lines = [f"  {p.device} — {p.description}" for p in list_ports.comports()]
        return "\n".join(lines) if lines else "  (no serial ports found)"
    except Exception as exc:  # pragma: no cover
        return f"  (could not list ports: {exc})"


def require_port_or_exit(port: str | None) -> str:
    """Exit with a friendly error if no port has been resolved."""
    if port:
        return port
    print(
        "error: serial --port is required (e.g. -p /dev/cu.usbmodem1101), "
        "or set MESHCORE_SERIAL. Use --list-serial to discover devices.",
        file=sys.stderr,
    )
    sys.exit(2)
