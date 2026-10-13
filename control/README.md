# ensemble-control

A service that exposes the Ensemble's settings as JSON-RPC 2.0 over a
WebSocket, with a web UI. It talks to `EnsembleDriver` through the dext's
user client.

## Run

`make install` in the repository root installs the service as the launch
agent `dev.ensemble.control`. `make service` builds a release binary and
signs it ad hoc with `com.apple.developer.driverkit.userclient-access`. The
signature needs SIP disabled, like the dext build. To run a new build:

    make service && launchctl kickstart -k gui/$(id -u)/dev.ensemble.control

The service exits when `EnsembleDriver` leaves the IORegistry, for example
on a dext reload. launchd starts it again within 10 s. The dext accepts one
subscriber: `driver/build/ensemblectl` takes the report stream from a
running service.

- Web UI: `http://<host>:8737`
- JSON-RPC: `ws://<host>:8738`

Both listen on all interfaces, with no authentication.

## JSON-RPC methods

Each WebSocket text message holds one JSON-RPC 2.0 request. The service
does not support batch requests. If a request has no `id`, the service
runs it and sends no reply.

| Method | Params | Result |
|--------|--------|--------|
| `describe` | none | List of `{path, kind}`, `{path, kind, min, max}`, or `{path, kind, choices}` |
| `get` | none | Object of path: value, for every value reported so far |
| `set` | Object of path: value | `true` after the commands are queued |
| `raw.send` | `{words: [...]}`, 3 to 30 unsigned 32-bit integers | `true` |

`kind` is `bool`, `int`, or `choice`. Only an `int` has `min` and `max`.
Only a `choice` has `choices`. In `set`, a `bool` value must be a JSON
boolean. An `int` value must be a JSON integer from `min` to `max`. A
`choice` value must be a name from `choices`, for example `"96000"` for
`clock/sampleRate`. In `get` and `changed`, a choice value is its name.
If the device reports a code with no name, the value is the integer code.

`set` checks every path and value before it sends a command. If one check
fails, the service sends nothing. The result `true` does not confirm the
change. `get` and `changed` show the new value after the dext reports the
sent command. If the user client fails partway through a `set`, the
earlier commands stay sent.

`raw.send` sends the words to the PSoC unchanged. Words 0 and 1 are the
header `1, 0`. Records follow, 4 bytes to a word, low byte first.
`EnsembleModel/Wire.swift` encodes set and block records.

| Code | Cause |
|------|-------|
| -32700 | The message is not valid JSON |
| -32600 | The message is not an object with `"jsonrpc": "2.0"` and a string `method` |
| -32601 | The method is unknown |
| -32602 | A param, path, or value is not valid |
| -32000 | The user client failed. `message` holds the error |

An error reply to -32700 or -32600 has `"id": null`.

The server sends three notifications:

- `changed`: object of path: new value. The dext reports every sent set
  command and every front-panel change, so all clients get each change once.
- `report`: a PSoC report with no parameter, as
  `{type, command, p1, p2, data}`. `type` 1 is a set record: `p2` is 0
  and `data` holds one byte. `type` 2 is a block record with up to 100
  bytes of `data`.
- `meters`: peak levels as `{inputs, outputs, outputGroup, group2,
  mixers}`, arrays of 30, 30, 4, 16, and 8 integers. `inputs` follows
  mixer channels 1-30. `outputs` holds the 30 physical outputs.
  `outputGroup` is Headphone 1 L/R, then Headphone 2 L/R. `group2` is
  Playback 1-16 before the mixers.
  `mixers` is the L/R master of each of the 4 mixers. Each value is
  linear, with full scale at 16384: dBFS = 20 * log10(value / 16384).
  The FPGA updates the meters 30 times a second.

`EnsembleModel/Parameters.swift` defines the paths and their PSoC commands.
Mixer paths are `mixers/<1-4>/channels/<n>/{fader,mute,pan}`. Channel
numbers follow the input meter order (1-30), then Playback 1-16 (31-46),
then master L/R (47-48). Channel 10, the second half of the front panel
mic, has no controls. A fader is 0 to 720 in 0.1 dB steps, with 600 at
0 dB. The vendor HAL stops at 660 (+6 dB). A pan is 0 to 127, with 64 at
the center. Mixer 1 also has `solo` and `soloSafe`.

Two channel flags apply to all four mixers. `mixers/channels/<n>/enabled`
lets channel n into the mixers: a disabled channel is not mixed.
`mixers/channels/<n>/stereo` exists for the first channel of each pair
(1, 3, 5, 7, 11, ..., 45) and flags the pair n, n+1 as stereo. The front
panel mic (9, 10) has no pair.

A stereo pair moves together, as in the vendor HAL. A set of `fader`,
`mute`, `solo`, `soloSafe`, or `enabled` on either channel also writes
the partner. Turning stereo on copies these values from the first channel
to the partner. Each channel keeps its own `pan`.

Routing paths name the output pair: `routing/line1-2` to
`routing/line9-10`, `routing/guitar1-2`, `routing/spdif`,
`routing/optical1-2` to `routing/optical15-16`, `routing/headphone1`, and
`routing/headphone2`. The value is a source name, for example
`Mixer 1`, `Playback 3-4`, `Analog 1-2`, or `Optical 1-2`.

`outputs/speakerSource` sets the source of every speaker set in one step,
like the vendor's speaker source setting. It writes `routing/line1-2`, plus
`routing/line3-4` in "2 Speaker Sets" mode, plus `routing/line5-6` in
"3 Speaker Sets" mode. Its value shows the route of speaker set A.

## Test

    cd control && swift test
