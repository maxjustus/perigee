"""Probes the FPGA routing matrix with PSoC commands. NOTES-vendor-driver.md 5.10 lists the results.

Usage: python3 scripts/dsp/matrix.py playback|record|speakers|taps

The tests use the set-up of isa.py: DSP I/O channel 0 feeds Analog 1, panned hard
left in Mixer 1, and channel 1 feeds Analog 2, panned hard right. 0xD3 with
p1 = d - 0x60 and data = n, s - 0x70, 1 puts source s on destination d (8.6). Each
test adds the messages that undo its routes to the restore file before it sends
them, and sends them again when it ends.
"""
import asyncio
import sys

import numpy as np

from dsp import Src, block, gain, ins, message, play, record, remember, session, store
from isa import MIXER, STATE, coefs, program

MUTE_HEADPHONES = {"outputs/headphone1/mute": True, "outputs/headphone2/mute": True}
SETTINGS = {"speakers": {**MUTE_HEADPHONES, "outputs/mainMode": "2 Speaker Sets",
                         "outputs/activeSpeakerSet": "A", "routing/line3-4": "Mixer 1"},
            "taps": MUTE_HEADPHONES}
PLAYBACK = 30
DSP_OUTPUT = 3
LEVEL = 0.2


async def playback(core):
    """0xD3 puts Playback 31 on DSP input 0, and the program puts 0.1 times DSP input 0 on the
    right channel. The test stops if an output route carries Playback 31."""
    code = 0x30 + PLAYBACK
    settings, _ = await synced(core)
    routes = {path: value for path, value in settings.items()
              if path.startswith("routing/") or path == "outputs/speakerSource"}
    used = {path: value for path, value in routes.items() if value in ("Playback 31-32", code - 1, code)}
    if used:
        raise RuntimeError(f"an output carries Playback {PLAYBACK + 1}: {used}")
    print("output routes:", sorted(set(map(str, routes.values()))), flush=True)
    undo = [block(0xD3, 0, 0, [0, 0, 1])]
    remember(undo)
    await core.send(block(0xD3, 0x60, 0, [0, code - 0x70 & 0xFF, 1]))
    await core.swap(program([ins(0x0B, a=0)]))
    try:
        for value in (None, 0.5, -0.25):
            player = play(PLAYBACK, value, 3.0) if value is not None else None
            await asyncio.sleep(1.0)
            await core.check_protected()
            _, right = record([30, 31])
            if player:
                player.wait()
            print(f"Playback {PLAYBACK + 1} = {value}: right / 0.1 = {np.median(right) / 0.1:+.4f}", flush=True)
    finally:
        for words in undo:
            await core.send(words)


async def synced(core):
    """Sends a Get-all, so the service reads every stored setting again, and returns the settings
    and the reports that no setting covers."""
    await core.send(message([4, 0, 0, 0]))
    reports = {(r["command"], r["p1"]): r["data"] for r in await core.notifications("report", 3.0)}
    return await core.call("get"), reports


async def record_route(core):
    """0x09 with code 0x70 puts DSP outputs 0 and 1 on record channels 0 and 1 (record pair 0)."""
    _, reports = await synced(core)
    original = reports[(0x09, 0)][0]
    undo = [message([1, 0x09, 0, original])]
    remember(undo)
    await core.swap(program([]))
    try:
        await core.send(message([1, 0x09, 0, 0x70]))
        await asyncio.sleep(0.4)
        await core.check_protected()
        channels = record([0, 1, 30, 31])
        for record_channel, mixer_channel in ((0, 2), (1, 3)):
            lag, g, rms = gain(channels[mixer_channel], channels[record_channel])
            print(f"record channel {record_channel} = {g:+.4f} x Mixer 1 channel {mixer_channel - 2}, lag {lag}, "
                  f"residual {rms:.5f}", flush=True)
    finally:
        for words in undo:
            await core.send(words)
    _, reports = await synced(core)
    print(f"0x09 of record pair 0: {reports[(0x09, 0)][0]:#04x}, before the test {original:#04x}", flush=True)


async def speakers(core):
    """0x15 puts DSP outputs 0 and 1 (0.5 and 0.25) on Line 3-4, the outputs of speaker set B.
    Mixer 1 on Line 1-2, set A, carries them too. 0x10 then selects the active sets."""
    await core.coefs([1.0, 0.0, 0.0, 0.0, 0.5, 0.25])
    await core.swap([ins(6, a=4), store(io=0, offset=1), ins(6, a=5), store(io=1, offset=0)])
    await change(core, "routing/line3-4", message([1, 0x15, 1, 0x70]))
    for label, mask in (("A", 1), ("B", 2), ("A and B", 3)):
        await change(core, "outputs/activeSpeakerSet", message([1, 0x10, 0, mask]))
        await core.check_protected()
        outputs = (await peaks(core))["outputs"]
        print(f"active set {label:8} Line 1-4 meters: {outputs[:4]}", flush=True)


async def change(core, path, words):
    """Sends a raw message that changes the setting at path. The service follows the message, so
    the session protects the new value."""
    await core.send(words)
    core.protected[path] = (await core.call("get"))[path]


async def peaks(core):
    """Returns the meter peaks of 1 second, after the old peaks expire."""
    await core.notifications("meters", 3.0)
    frames = await core.notifications("meters", 1.0)
    return {key: [max(f[key][i] for f in frames) for i in range(len(frames[0][key]))] for key in frames[0]}


async def taps(core):
    """Puts DSP output 3, at 0.2, on destinations 0x80, 0xB0, and 0xE0, and reads the host meters.
    Then puts it on destination 0x94 and reads source 0x94 back through DSP input 0."""
    _, reports = await synced(core)
    fx_send = reports[(0x09, 16)][0]
    undo = [block(0xD3, 0x80, 0, [0, 0x90 - 0x70, 1]), block(0xD3, 0x50, 0, [0, 0x60 - 0x70 & 0xFF, 1]),
            block(0xD3, 0x20, 0, [0, 0x30 - 0x70 & 0xFF, 1]), message([1, 0x09, 16, fx_send]),
            block(0xD3, 0x34, 0, [0, 0x04 - 0x70 & 0xFF, 1]), block(0xD3, 4, 0, [0, 0, 0]),
            block(0xD3, 0, 0, [0, 0, 1])]
    remember(undo)
    await core.coefs([1.0, 0.0, 0.1, 0.0, LEVEL])
    await core.swap([ins(5), store(io=0, offset=1), ins(6, a=4), store(io=DSP_OUTPUT, offset=2),
                     ins(0x0B, a=0), ins(5, a=2, b_src=Src.R), store(io=1, offset=0)])
    try:
        await show(core, "default routes")
        for destination in (0x80, 0xB0, 0xE0):
            await core.send(block(0xD3, destination - 0x60, 0, [0, DSP_OUTPUT, 1]))
            await show(core, f"destination {destination:#04x} = DSP output {DSP_OUTPUT}")
            for words in undo[:3]:
                await core.send(words)
        for label, source in (("DSP output 3", 0x70 + DSP_OUTPUT), ("source 0x94", 0x94)):
            await core.send(block(0xD3, 0x94 - 0x60, 0, [0, DSP_OUTPUT, 1]))
            await core.send(block(0xD3, 0x60, 0, [0, source - 0x70 & 0xFF, 1]))
            await asyncio.sleep(0.4)
            await core.check_protected()
            _, right = record([30, 31])
            print(f"destination 0x94 = DSP output 3, DSP input 0 = {label}: "
                  f"right / 0.1 = {np.median(right) / 0.1:+.4f}", flush=True)
    finally:
        for words in undo:
            await core.send(words)


async def show(core, label):
    """Prints each host meter at or above 1/16 of full scale."""
    await core.check_protected()
    lit = {f"{key}[{i}]": v for key, values in (await peaks(core)).items() for i, v in enumerate(values) if v >= 1024}
    print(f"{label:36} meters at or above 1024: {lit}", flush=True)


async def main(test):
    async with session({**MIXER, **SETTINGS.get(test.__name__, {})}) as core:
        await core.load([0], coefs(0.5), STATE)
        await core.route(0, io=0)
        await core.route(1, io=1)
        await test(core)


if __name__ == "__main__":
    tests = {"playback": playback, "record": record_route, "speakers": speakers, "taps": taps}
    if len(sys.argv) != 2 or sys.argv[1] not in tests:
        sys.exit(__doc__)
    asyncio.run(main(tests[sys.argv[1]]))
