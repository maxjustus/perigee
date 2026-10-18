"""Check the audio data path with a capture route and no cables.

Usage:
    uv run --with sounddevice --with numpy --with websockets python3 scripts/loopback.py

The script plays 24-bit noise on Playback 33-34 and records computer inputs 29-30, first with
their own route and then with capture/29-30 set to Playback 33-34. It restores the route at the
end. Playback 33-34 feeds no mixer, and the script stops if an output plays it, so nothing
reaches the speakers. It exits with 1 if the noise does not arrive bit for bit at 24 bits.
"""

import asyncio
from pathlib import Path
import runpy
import sys

import numpy as np

RATE = 48000
LEAD = RATE // 4
PAIR, SOURCE = "capture/29-30", "Playback 33-34"
INPUTS, OUTPUTS = [29, 30], [33, 34]


def main():
    sys.exit(asyncio.run(run()))


async def run():
    client = await runpy.run_path(str(Path(__file__).with_name("rpc.py")))["Client"].connect()
    values = await client.call("get")
    users = [path for path, value in values.items() if value == SOURCE and not path.startswith("capture/")]
    if users:
        print(f"{SOURCE} plays on {', '.join(users)}. Stop.")
        return 1
    original = values[PAIR]
    sent = signal()
    try:
        if original != SOURCE:
            print(f"route {original}: peak {np.abs(playrec(sent)).max() / 2**31:.6f} of full scale")
        await route(client, PAIR, SOURCE)
        results = [compare(sent[:, side], got) for side, got in enumerate(playrec(sent).T)]
    finally:
        await route(client, PAIR, original)
    for name, result in zip("LR", results):
        print(f"route {SOURCE}, {name}: " + (", ".join(f"{key} {value}" for key, value in result.items())
                                             if result else "no signal"))
    return 0 if all(result and result["exact24"] == 1 for result in results) else 1


# Independent noise per side, so a swap of L and R fails the check. The low 8 bits are 0, so
# the float conversions of CoreAudio keep every sample.
def signal():
    noise = np.random.default_rng(1).integers(-2**22, 2**22, size=(2 * RATE, 2)) << 8
    out = np.zeros((LEAD + len(noise) + RATE // 2, 2), np.int32)
    out[LEAD:LEAD + len(noise)] = noise
    return out


async def route(client, path, value):
    await client.call("set", {path: value})
    for _ in range(50):
        if (await client.call("get"))[path] == value:
            return
        await asyncio.sleep(0.05)
    raise RuntimeError(f"{path} did not report {value}")


def playrec(out):
    import sounddevice as sd
    device = next(i for i, d in enumerate(sd.query_devices()) if d["name"] == "Ensemble")
    return sd.playrec(out, RATE, device=device, dtype="int32", input_mapping=INPUTS, output_mapping=OUTPUTS,
                      blocking=True, latency="low")


# The lag includes the host buffers, so it is not the latency of the unit.
def compare(sent, got):
    probe = sent[LEAD:LEAD + 4096].astype(np.float64)
    lag = int(np.argmax(np.abs(np.correlate(got[:RATE].astype(np.float64), probe, "valid")))) - LEAD
    end = np.flatnonzero(sent)[-1] + 1
    if lag < 0 or end + lag > len(got):
        return None
    received = got[LEAD + lag:end + lag].astype(np.int64)
    expected = sent[LEAD:end].astype(np.int64)
    error = received - expected
    return {"lag": lag, "exact32": float(np.mean(error == 0)), "max_error": int(np.abs(error).max()),
            "exact24": float(np.mean(np.round(received / 256) * 256 == expected))}


if __name__ == "__main__":
    main()
