# ensemble-control

A service that exposes the Ensemble's settings as JSON-RPC 2.0 over a
WebSocket, with a web UI. It talks to `EnsembleDriver` through the dext's
user client.

## Run

`make install` in the repository root installs the service as the launch
agent `dev.ensemble.control`. `make service` builds the web UI and the
release binaries.
It signs `ensemble-control` and `ensemblectl` ad hoc with
`com.apple.developer.driverkit.userclient-access`. The signature needs SIP
disabled, like the dext build. To run a new build:

    make service && launchctl kickstart -k gui/$(id -u)/dev.ensemble.control

The service exits when `EnsembleDriver` leaves the IORegistry, for example
on a dext reload. launchd starts it again within 10 s.

- Web UI: `http://<host>:8737`
- JSON-RPC: `ws://<host>:8738`
- Remote monitor: `ws://<host>:8739`

All three listen on all interfaces, with no authentication.

## Web UI

The web UI source is TypeScript in `web/`. `npm run build` bundles
`web/src/main.ts` with esbuild into one page, with the script and the
styles inline: `Sources/ensemble-control/Public/index.html`. Git ignores
the page. `swift build` copies it into the service bundle, so build the
page before `swift build` or `swift test`. If the page is missing,
`swift build` fails.

`main.swift` replaces `@RPC_PORT@`, `@MONITOR_PORT@` and
`@CAPTURE_NAMES@` in the page. Only the config script in
`web/index.html` holds them.

Run these commands in `control/web`:

| Command | Result |
|---------|--------|
| `npm ci` | Installs esbuild and TypeScript |
| `npm run build` | Writes the page |
| `npm run check` | Runs the TypeScript type check |
| `npm test` | Runs the tests of the pure modules with `node --test` |

Node.js runs the `.ts` test files directly, with type stripping. The
source thus uses only erasable TypeScript syntax: no enums, no
namespaces, and no parameter properties. Node.js 26 passes the tests.

## JSON-RPC methods

Each WebSocket text message holds one JSON-RPC 2.0 request. The service
does not support batch requests. If a request has no `id`, the service
runs it and sends no reply.

| Method | Params | Result |
|--------|--------|--------|
| `describe` | none | List of `{path, kind}`, `{path, kind, min, max}`, or `{path, kind, choices}` |
| `get` | none | Object of path: value, for every value reported so far |
| `set` | Object of path: value | `true` after the commands are queued |
| `raw.send` | `{words: [...]}`, 3 to 29 unsigned 32-bit integers | `true` |
| `presets.list` | none | List of preset names, sorted |
| `presets.save` | `{name}` | `true` |
| `presets.load` | `{name}` | `{skipped: [...]}` |
| `presets.delete` | `{name}` | `true` |

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

Stereo links and speaker sets read `outputs/mainMode` and the stereo
flags from the reported values. Thus `set` sends these paths first. It
waits up to 1 s for their reports, and then it sends the other paths.

`raw.send` sends the words to the PSoC unchanged. Words 0 and 1 are the
header `1, 0`. One record follows, 4 bytes to a word, low byte first.
The dext rejects a message that has more than one record, a record type
other than 1 to 4, a type-2 length outside 1 to 99, nonzero pad bytes,
or command 0x60 to 0x63. Only a bootloader session can
send command 0x60, and only as a type-1 record with p1 0 and value 0.
`EnsembleModel/Wire.swift` encodes set and block records.

| Code | Cause |
|------|-------|
| -32700 | The message is not valid JSON |
| -32600 | The message is not an object with `"jsonrpc": "2.0"` and a string `method` |
| -32601 | The method is unknown |
| -32602 | A param, path, or value is not valid |
| -32000 | The user client failed, the driver outbox stayed full for 1 s, or a mode or stereo report did not arrive in 1 s. `message` holds the error |

An error reply to -32700 or -32600 has `"id": null`.

A preset holds the `get` result of the time of `presets.save`, without
`clock/sampleRate` and `outputs/speakerSource`. A save with the name of a preset replaces it.
The service keeps all presets in
`~/Library/Application Support/ensemble-control/presets.json`.
`presets.load` sets each saved value that differs from the reported
value, as one `set`. It skips each path that the service does not know
or that has an invalid value, and returns these paths in `skipped`.

Like Apogee Control, `presets.load` mutes the speakers and both
headphones, and waits 500 ms. Then it sets the other values, and last
the saved mutes. If only mutes differ, it sets them with no wait. If the
load fails, the outputs stay muted.

The server sends five notifications:

- `changed`: object of path: new value. The dext reports every sent set
  command and every front-panel change, so all clients get each change once.
- `report`: a PSoC report with no parameter, as
  `{type, command, p1, p2, data}`. `type` 1 is a set record: `p2` is 0
  and `data` holds one byte. `type` 2 is a block record with up to 100
  bytes of `data`.
- `presets`: `{names}`, the sorted preset names after a save or a delete.
- `restarted`: the PSoC restarted, with empty params. The PSoC replays
  its saved settings, and `changed` notifications follow from the
  Get-all that the dext sends. The restart removes the DSP routes (0xD3).
  Whether the DSP programs stay in the FPGA is unknown. A client that
  loaded DSP programs or routes must load them again.
- `meters`: peak levels as `{inputs, outputs, headphones, playback,
  mixers}`, arrays of 30, 30, 4, 16, and 8 integers. `inputs` follows
  mixer channels 1-30. `outputs` holds the 30 physical outputs.
  `headphones` is Headphone 1 L/R, then Headphone 2 L/R. `playback` is
  Playback 1-16 before the mixers.
  `mixers` is the L/R master of each of the 4 mixers. Bits 13:0 of each
  value are a linear peak level, with full scale at 0x3FFF:
  dBFS = 20 * log10((value & 0x3FFF) / 0x3FFF). Bit 15 is an over flag.
  Each value is the peak of one update. The FPGA updates the meters 30
  times a second and applies no fall time.

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

## Remote monitor

The remote monitor streams one capture channel of the CoreAudio device
"Ensemble". The Monitor tab of the web UI plays it, for example on a
phone. Expect about 150 ms of delay over Wi-Fi. iOS Safari stops the
audio when the screen locks.

A client sends a text message `{"channel": n}` to `ws://<host>:8739`.
`n` is 1 to 34, the element of a CoreAudio input channel of the device
"Ensemble". The Monitor tab lists the channel names that the driver gives
them. A new message changes the channel.
After each CoreAudio IO cycle, the service sends the new samples in
binary messages: the nominal sample rate as a little-endian uint32, then
the samples as little-endian int16. The service runs CoreAudio input only while a client
has a channel.

macOS treats the input as a microphone. At the first capture, macOS asks
to allow ensemble-control to use the microphone. Until you answer, the
capture waits. If you deny it, the stream is silent. The ad hoc signature
changes with each build, so macOS can ask again after `make install`.

## Test

    cd control && swift test
    cd control/web && npm test
