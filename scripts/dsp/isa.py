"""Decodes DSP core opcodes on the unit. NOTES-vendor-driver.md 8.3 lists the results.

Usage: python3 scripts/dsp/isa.py sweep|pairs|jumps|copies|stall|extra|routes|state

The tests run in thread 0. DSP I/O channel 0 feeds Analog 1, panned hard
left in Mixer 1, and channel 1 feeds Analog 2, panned hard right. Record
channels 30 and 31 carry Mixer 1. The left channel carries 0.25 b, where b
steps through a circular group of eight state words, so each capture gives
eight points. The right channel carries the result. Pan 127 leaks 1.8 % of
the right channel into the left, which the matching tolerates.
"""
import asyncio
import sys

import numpy as np

from dsp import Src, block, copy, ins, jump, record, session, store

B_VALUES = [-2.0, -0.75, -0.1, 0.0, 0.1, 0.5, 1.0, 3.0]
SCALE, REF = 0.1, 0.25
P, Q = -0.5, 0.5
# A one-word 0xD4 write changes other state words, so the test writes all of them once.
STATE = [0.0] * 8 + B_VALUES + [0.0] * (255 - 16)
MIXER = {"mixers/1/channels/1/mute": False, "mixers/1/channels/1/pan": 0,
         "mixers/1/channels/2/mute": False, "mixers/1/channels/2/pan": 127,
         **{f"mixers/{m}/channels/{c}/mute": True for m in (2, 3, 4) for c in (1, 2)}}


def coefs(a, *extra):
    return [1.0, a, SCALE, REF, *extra]


def program(body, read=Src.R):
    """Puts 0.25 b on the left, sets x = c1 and r = b, runs body, and puts 0.1 r (or x) on the right."""
    return [ins(5, a=3, b=8, b_src=Src.STATE, k=3), store(io=0, offset=1),
            ins(6, a=1, to_r=False),
            ins(5, a=0, b=8, b_src=Src.STATE, k=3),
            *body,
            ins(5, a=2, b_src=read), store(io=1, offset=0)]


def marker(word):
    """Like program, but the right channel shows P if word skips 2 or more, b if it skips 1, else Q."""
    return [ins(5, a=3, b=8, b_src=Src.STATE, k=3), store(io=0, offset=1),
            ins(6, a=4), store(io=1, offset=0),
            ins(6, a=1, to_r=False),
            ins(5, a=0, b=8, b_src=Src.STATE, k=3),
            word, ins(6, a=5), store(io=1, offset=0)]


async def run(core, code):
    """Runs code and records both channels. A swap now and then leaves the thread
    halted, with exact zeros on both channels. A second resume-all restarts it."""
    for _ in range(3):
        await core.swap(code)
        await asyncio.sleep(0.3)
        await core.check_protected()
        left, right = record([30, 31])
        if left.std() > 0:
            return left, right
        await core.resume_all()
    raise RuntimeError("thread stays halted")


async def points(core, code):
    left, right = await run(core, code)
    out = []
    for b in B_VALUES:
        near = np.abs(left - REF * b) < 0.012
        out.append(float(np.median(right[near])) if near.sum() > 1000 else None)
    return out


def row(label, values, scale=SCALE):
    cells = ("     ----" if v is None else f"{v / scale:+9.4f}" for v in values)
    return f"{label:24}" + " ".join(cells)


async def sweep(core):
    print(f"{'b =':24}" + " ".join(f"{b:+9.2f}" for b in B_VALUES))
    forms = {"AB": lambda op: [ins(op, a=1, b_src=Src.R)],
             "BA": lambda op: [ins(op, a_src=Src.R, b_src=Src.X)],
             "U": lambda op: [ins(op, a_src=Src.R)]}
    for op in (0x05, 0x06, 0x07, 0x08, 0x12, 0x26, 0x27, 0x28, 0x2B, 0x09, 0x0A, 0x0C, 0x0E, 0x0F, 0x11):
        for form, body in forms.items():
            for a in ((0.5, -1.5) if form != "U" else (0.5,)):
                await core.coefs(coefs(a))
                print(row(f"{op:02x} {form} a={a}", await points(core, program(body(op)))), flush=True)


async def pairs(core):
    print(f"{'b =':24}" + " ".join(f"{b:+9.2f}" for b in B_VALUES))
    for first, second in ((0x0C, 0x0E), (0x0F, 0x11), (0x09, 0x2B), (0x0A, 0x2B)):
        for a in (0.5, 2.0):
            await core.coefs(coefs(a))
            body = [ins(first, a=1, b_src=Src.R), ins(second, a=1, b_src=Src.R)]
            print(row(f"{first:02x}+{second:02x} AB a={a}", await points(core, program(body))), flush=True)
        body = [ins(first, a_src=Src.R), ins(second, a_src=Src.R)]
        print(row(f"{first:02x}+{second:02x} U", await points(core, program(body))), flush=True)


async def jumps(core):
    xs = (-0.5, -1e-30, 0.0, 1e-30, 0.5)
    print("bits 23:21 | jump for x =", " ".join(f"{x:g}" for x in xs))
    for condition in range(8):
        word = jump(3, condition)
        taken = []
        for x in xs:
            await core.coefs(coefs(x, P, Q))
            _, right = await run(core, marker(word))
            taken.append("jump" if abs(np.median(right) - P) < 0.01 else "  - ")
        print(f"{condition:03b} ({word:08x}) | " + "  ".join(taken), flush=True)


async def copies(core):
    state = list(STATE)
    state[20] = 0.123
    await core.state(state)
    for label, word, read in (("no op, read s20", 0, None),
                              ("0x14 s9 -> s20, read s20", copy(0x14, 9, 20), None),
                              ("0x14 s9 -> s20, read x", copy(0x14, 9, 20), Src.X),
                              ("0x16 s9 -> s20, read s20", copy(0x16, 9, 20), None),
                              ("0x16 s9 -> s20, read x", copy(0x16, 9, 20), Src.X)):
        body = [word] if word else []
        body.append(ins(5, b_src=read) if read else ins(5, b=20, b_src=Src.STATE))
        print(row(label, await points(core, program(body))), flush=True)


async def stall(core):
    await core.coefs(coefs(0.5, P, Q))
    for n in (0, 50, 158, 159, 160, 161, 162, 255):
        code = marker(0x17 | n << 6)
        _, right = await run(core, code)
        print(f"STALL {n:3}: store after it {'ran' if abs(np.median(right) - Q) < 0.01 else 'did not run'}", flush=True)


async def extra(core):
    print(f"{'b =':24}" + " ".join(f"{b:+9.2f}" for b in B_VALUES))
    for op in (0x13, 0x29, 0x2A):
        for a in (0.5, -1.5):
            await core.coefs(coefs(a))
            print(row(f"{op:02x} AB a={a}", await points(core, program([ins(op, a=1, b_src=Src.R)]))), flush=True)
    for k in (0, 3):
        print(row(f"A = s8 group, k={k}", await points(core, program([ins(6, a=8, a_src=Src.STATE, k=k)]))), flush=True)
    await core.coefs([1.0, 0.0, SCALE, REF, 3.0, 0.1, 1.0])
    loop = [ins(6, a=1), ins(6, a=4, to_r=False), ins(6, a=5, b_src=Src.R),
            ins(8, a=6, b_src=Src.X, to_r=False), jump(0xFE, 0b101)]
    _, right = await run(core, program(loop))
    print(f"loop: r = 0, x = 3, three passes of r += 0.1 -> r = {np.median(right) / SCALE:+.4f}", flush=True)
    state = list(STATE)
    state[30] = 0.77
    await core.state(state, thread=1)
    await core.coefs(coefs(0.5))
    body = [copy(0x14, 30, 20, thread=1), ins(5, b=20, b_src=Src.STATE)]
    print(row("0x14 from thread 1 s30", await points(core, program(body))), flush=True)


async def routes(core):
    """0xD3 with DSP input 2 and output 3. Record channel 0 is Analog 1 as recorded."""
    await core.route(0, on=False)
    await core.coefs([1.0, 0.0, 0.25])
    await core.swap([ins(6, a=2), store(io=3)])
    for mode in (0, 1, 2, 3):
        await core.send(block(0xD3, 0, 0, [2, 3, mode]))
        await asyncio.sleep(0.4)
        await core.check_protected()
        recorded, mixer = record([0, 30])
        print(f"mode {mode}: record channel 0 = {np.median(recorded):+.4f}, Mixer 1 left = {np.median(mixer):+.4f}", flush=True)
    await core.send(block(0xD3, 0, 0, [2, 3, 0]))


async def state(core):
    """A 0xD4 write copies the whole staging buffer: state[(start + j) % 256] = staging[j]."""
    p1 = [0.01 * (i % 50) + 0.005 for i in range(255)]
    p2 = [-0.01 * (i % 37) - 0.003 for i in range(255)]
    staging = list(p2) + [0.0]
    await core.coefs([1.0, 0.0, 0.01])
    for label, values, start in (("full write p1", p1, 0), ("full write p2", p2, 0), ("s40 = 0.9", [0.9], 40), ("s100 = 0.8", [0.8], 100)):
        await core.state(values, start=start)
        staging[:len(values)] = values
        expected = {i: staging[(i - start) % 256] for i in (8, 40, 100, 200)}
        cells = []
        for word, want in expected.items():
            _, right = await run(core, [ins(5, a=2, b=8, b_src=Src.STATE, k=3), store(io=0, offset=1),
                                        ins(5, b=word, b_src=Src.STATE), store(io=1, offset=0)])
            got = float(np.median(right))
            cells.append(f"s{word} {got:+.4f} ({'as predicted' if abs(got - want) < 0.0005 else f'want {want:+.4f}'})")
        print(f"{label:14}", "  ".join(cells), flush=True)


async def main(test):
    async with session(MIXER) as core:
        await core.load([0], coefs(0.5), STATE)
        await core.route(0, io=0)
        await core.route(1, io=1)
        await test(core)


if __name__ == "__main__":
    tests = {f.__name__: f for f in (sweep, pairs, jumps, copies, stall, extra, routes, state)}
    if len(sys.argv) != 2 or sys.argv[1] not in tests:
        sys.exit(__doc__)
    asyncio.run(main(tests[sys.argv[1]]))
