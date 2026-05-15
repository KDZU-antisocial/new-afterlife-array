# MeshCore → Bitwig MIDI bridge

Reads incoming MeshCore companion-radio messages from a **USB serial** device
and sends **MIDI** that Bitwig Studio can receive (virtual port or IAC).

Six commands are installed:

| Command | What it does |
| --- | --- |
| `meshcore-bitwig-bridge` | Receive messages and forward them as MIDI to Bitwig. |
| `meshcore-send` | Send a message from this computer's USB-attached node. |
| `meshcore-listen` | Print incoming messages (and adverts) on stdout (no MIDI dependency). |
| `meshcore-name` | Show or set the adv_name of the attached node. |
| `meshcore-advert` | Broadcast a fresh advert from the attached node. |
| `meshcore-lurch` | GOLDFINCH role: periodically send lurch-tempo commands to another node. |

All six resolve the serial port from `-p / --port` or `$MESHCORE_SERIAL`.

## Setup with uv

Requires Python 3.11+. Install [uv](https://docs.astral.sh/uv/) if needed,
then from this repo:

```bash
uv sync
```

List serial ports and MIDI outputs:

```bash
uv run meshcore-bitwig-bridge --list-serial
uv run meshcore-bitwig-bridge --list-midi
```

To avoid typing the device path every time, set it once in your shell
(e.g. `~/.zshrc`):

```bash
export MESHCORE_SERIAL="/dev/cu.usbmodemXXXX"
```

(`-p` overrides `MESHCORE_SERIAL` when you pass it.)

## Run the MeshCore → MIDI bridge

Use the `cu.` device from `--list-serial`:

```bash
uv run meshcore-bitwig-bridge -p /dev/cu.usbmodemXXXX --virtual-midi
```

Or with `MESHCORE_SERIAL` set:

```bash
uv run meshcore-bitwig-bridge --virtual-midi
```

In **Bitwig**: Settings → Controllers → Add controller, or use an
**Instrument** track → note receiver / MIDI input → choose **MeshCore →
Bitwig** (or your `--virtual-name`).

### Message → MIDI mapping

- If the mesh text is `cc12:64`, sends control change CC12 = 64.
- If the text is `n60` or `n60 v100`, sends note on/off (or poly pressure if
  you switch the mapper later).
- If the text is `lurch-tempo:<delta_bpm>:<duration_ms>`, the bridge dips its
  baseline tempo down by `delta_bpm` for `duration_ms`, then recovers — see
  [The GOLDFINCH Instruments](#the-goldfinch-instruments) below.
- Otherwise, a **short note** is derived from a hash of sender + text so each
  message still triggers something predictable.

Pass `--verbose` if the radio connection needs debugging.

## Naming the attached node

Each MeshCore node has an **adv_name** that it broadcasts in its periodic
adverts. Other nodes see this as the contact's name (the same string that
`meshcore-send --list-contacts` shows in the `adv_name` column).

Print the current name:

```bash
uv run meshcore-name
```

Set a new one:

```bash
uv run meshcore-name "Rob's Laptop"
```

After setting, a flood advert is sent automatically so nearby nodes pick up
the new name; pass `--no-advert` to skip that.

## Verifying adverts are working

Adverts are how MeshCore nodes find each other. To check that they're flowing:

**See what this node has heard.** Each contact in this list got there because
its advert reached you:

```bash
uv run meshcore-send --list-contacts
```

**Watch adverts arrive in real time.** `meshcore-listen` now prints a line
like `[13:42:07] ADVERT  from <name>` every time a neighbor's advert is
received:

```bash
uv run meshcore-listen -v
```

**Force this node to broadcast one.** Without changing its name as a side
effect:

```bash
uv run meshcore-advert          # zero-hop to direct neighbors
uv run meshcore-advert --flood  # flood across the mesh
```

To confirm the round trip, run `meshcore-listen` on another node in the
array, then `meshcore-advert --flood` here — the other node should print an
ADVERT line within a second or two.

## Sending and listening between two computers

`meshcore-send` and `meshcore-listen` let you verify a node-to-node link
end-to-end without involving MIDI or Bitwig at all.

### Quick test on the public channel (no pairing required)

On **computer B** (the receiver), start the listener:

```bash
uv run meshcore-listen -v
```

On **computer A** (the sender), publish on public channel 0:

```bash
uv run meshcore-send "hello from rob"
```

Computer B will print a line like:

```text
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

## The GOLDFINCH Instruments
The New AfterLife Array is comprised of nine meshcore-linked units that send compositional suggestions to other nodes in the New AfterLife Array. These are called the GOLDFINCH instruments and each node is assigned a letter from that word and are assigned compositional intentions. 

### Compositional Roles
Each node is assigned a letter and **sends** its compositional intentions to the others in the group.

- G = GATE block flows and expressions
- O = ORBIT looping gestures
- L = LURCH slurring the tempo and pitch
- D = DRIFT free from the grid
- F = FLICKER flutter
- I = INTERRUPT break the groove
- N = NUDGE small changes to tempo or pitch
- C = CLUSTER entangling events
- H = HAILSTORM sudden bursts

Each node also **recieves** compositional suggestions from the other nodes. Nodes can always decide to reject recieved suggestions.

### Impersonation
Nodes can also choose to impersonate other nodes if they are feeling devious. More about that later.

### LURCH ↔ FLICKER lurch-tempo

LURCH's first implemented behavior is to slow FLICKER's Bitwig tempo by a
random amount, for a random short duration, on a fixed cadence.

The wire protocol is one direct message per dip:

```text
lurch-tempo:<delta_bpm>:<duration_ms>
```

`delta_bpm` is a positive integer (LURCH only slows down). The receiver
recognizes this verb in `meshcore-bitwig-bridge` and, instead of going
through the default MIDI mapping, sends a CC down to a Bitwig-mapped tempo
control, sleeps for `duration_ms`, then sends the CC back to the baseline.

#### On the FLICKER laptop (the receiver)

1. In Bitwig, right-click the **Tempo** display in the transport bar →
   *Learn Controller Assignment* → wiggle a controller (or send a manual CC
   from a tool) to bind CC20 on MIDI channel 1.
2. After learning, edit the assignment so the **mapped range** spans the
   BPM extremes you're comfortable with — e.g. **60 BPM at value 0** and
   **180 BPM at value 127** (so CC20 = 64 → 120 BPM).
3. Run the bridge, telling it what that mapping is so it can compute the
   right CC values:

   ```bash
   uv run meshcore-bitwig-bridge --virtual-midi \
     --tempo-cc 20 --midi-channel 0 \
     --baseline-bpm 120 --bpm-min 60 --bpm-max 180
   ```

   (Defaults already match this example, so plain
   `uv run meshcore-bitwig-bridge --virtual-midi` works for now.)

   The bridge treats `--baseline-bpm` as the tempo to **recover to** after a
   dip — it doesn't read Bitwig's current tempo, so set this to whatever
   tempo your project is sitting at.

#### On the LURCH laptop (the sender)

```bash
uv run meshcore-lurch                       # defaults: FLICKER, 30s cooldown, 7–27 BPM, 3–13 s
uv run meshcore-lurch --to FLICKER          # explicit target adv_name
uv run meshcore-lurch --once --dry-run      # see one cycle without transmitting
```

Useful knobs:

- `--to NAME` — target contact (default `FLICKER`).
- `--cooldown SECONDS` — seconds between dip starts (default 30).
- `--delta-min` / `--delta-max` — slow-down BPM range (default 7..27).
- `--duration-min` / `--duration-max` — dip duration in seconds (default 3..13).
- `--once` — send one dip and exit (handy for testing).
- `--dry-run` — print what would be sent, don't open the serial port.

Before LURCH can DM FLICKER, both nodes need to have heard each other's
adverts. Run `uv run meshcore-send --list-contacts` on the LURCH laptop;
`FLICKER` should appear. If not, run `meshcore-advert --flood` on FLICKER
(or wait for the next periodic advert).
