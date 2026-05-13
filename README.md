# MeshCore → Bitwig MIDI bridge

Reads incoming MeshCore companion-radio messages from a **USB serial** device and sends **MIDI** that Bitwig Studio can receive (virtual port or IAC).

## Setup with uv

Install [uv](https://docs.astral.sh/uv/) if needed, then from this repo:

```bash
uv sync
```

List serial ports and MIDI outputs:

```bash
uv run meshcore-bitwig-bridge --list-serial
uv run meshcore-bitwig-bridge --list-midi
```

Run the bridge (use the `cu.` device from `--list-serial`):

```bash
uv run meshcore-bitwig-bridge -p /dev/cu.usbmodemXXXX --virtual-midi
```

To avoid typing the path every time, set once in your shell (e.g. `~/.zshrc`):

```bash
export MESHCORE_SERIAL="/dev/cu.usbmodem90706984E98C1"
uv run meshcore-bitwig-bridge --virtual-midi
```

(`-p` overrides `MESHCORE_SERIAL` when you pass it.)

In **Bitwig**: Settings → Controllers → Add controller or use an **Instrument** track → note receiver / MIDI input → choose **MeshCore → Bitwig** (or your `--virtual-name`).

### Message → MIDI mapping

- If the mesh text is `cc12:64`, sends control change CC12 = 64.
- If the text is `n60` or `n60 v100`, sends note on/off (or poly pressure if you switch the mapper later).
- Otherwise, a **short note** is derived from a hash of sender + text so each message still triggers something predictable.

Use `--verbose` if the radio connection needs debugging.
