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

## Sending and listening between two computers

Two extra CLIs are provided for verifying a node-to-node link end-to-end (no
MIDI needed):

- `meshcore-send` — send a message from this computer's USB node
- `meshcore-listen` — print messages received by this computer's USB node

Both honour `-p / --port` and `$MESHCORE_SERIAL` exactly like the bridge does.

### Quick test on the public channel (no pairing required)

On **computer B** (the receiver), start the listener:

```bash
uv run meshcore-listen -p /dev/cu.usbmodem... -v
```

On **computer A** (the sender), publish on public channel 0:

```bash
uv run meshcore-send -p /dev/cu.usbmodem... "hello from rob"
```

Computer B will print a line like:

```
[22:41:03] CHAN 0 : hello from rob
```

### Direct message to a specific node

MeshCore nodes learn about each other from periodic adverts. After a short
while you can list the contacts your node has heard:

```bash
uv run meshcore-send --list-contacts
```

Then send a DM to one by name:

```bash
uv run meshcore-send --to "Rob's Heltec" "ping"
```

`meshcore-send` uses `send_msg_with_retry`, so it waits for an ACK and falls
back to a flood path after a couple of attempts. Pass `--no-retry` to fire
once without waiting.

### Message → MIDI mapping

- If the mesh text is `cc12:64`, sends control change CC12 = 64.
- If the text is `n60` or `n60 v100`, sends note on/off (or poly pressure if you switch the mapper later).
- Otherwise, a **short note** is derived from a hash of sender + text so each message still triggers something predictable.

Use `--verbose` if the radio connection needs debugging.
