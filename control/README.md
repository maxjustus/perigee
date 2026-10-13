# ensemble-control

A service that exposes the Ensemble's settings as JSON-RPC 2.0 over a
WebSocket, with a web UI. It talks to `EnsembleDriver` through the dext's
user client.

## Run

    control/run.sh

The script builds a release binary, signs it ad hoc with
`com.apple.developer.driverkit.userclient-access`, and runs it in a loop.
The service exits when `EnsembleDriver` leaves the IORegistry, for example
on `driver/reload.sh`, and the loop starts it again after 2 s. The
signature needs SIP disabled, like the dext build. The dext accepts one
subscriber: `driver/build/ensemblectl` takes the report stream from a
running service.

- Web UI: `http://<host>:8737`
- JSON-RPC: `ws://<host>:8738`

Both listen on all interfaces, with no authentication.

## JSON-RPC methods

| Method | Params | Result |
|--------|--------|--------|
| `describe` | none | List of `{path, kind, min, max}` or `{path, kind, choices}` |
| `get` | none | Object of path: value, for every value reported so far |
| `set` | Object of path: value | `true` after the commands are queued |
| `raw.send` | `{words: [...]}`, 3 to 30 words | `true` |

`kind` is `bool`, `int`, or `choice`. A `choice` value is its name, for
example `"96000"` for `clock/sampleRate`.

The server sends two notifications:

- `changed`: object of path: new value. The dext reports every sent set
  command and every front-panel change, so all clients get each change once.
- `report`: a PSoC report with no parameter, as
  `{type, command, p1, p2, data}`.

`EnsembleModel/Parameters.swift` defines the paths and their PSoC commands.
Mixer paths are `mixers/<1-4>/channels/<1-48>/{fader,mute,pan}`. A fader
is 0 to 720 in 0.1 dB steps, with 600 at 0 dB. A pan is 0 to 127, with 64
at the center.
Routing paths are `routing/<1-17>`, one per output pair. The value is a
source name: `Playback 1-2` to `Playback 35-36`, `Mixer 1` to `Mixer 6`,
`Inputs 1-2` to `Inputs 7-8`, or `FX Send`. The physical names of the 17
output pairs are unknown, so they stay numbered.

## Test

    cd control && swift test
