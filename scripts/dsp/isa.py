"""Decodes DSP core opcodes on the unit. NOTES-vendor-driver.md 8.3 lists the results.

Usage: python3 scripts/dsp/isa.py sweep|pairs|units|jumps|selectors|idle|copies|modes|stores|copybits|stall|extra|unknown|writes|routes|state|monitor|resume

The tests run in thread 0. DSP I/O channel 0 feeds Analog 1, panned hard
left in Mixer 1, and channel 1 feeds Analog 2, panned hard right. Record
channels 30 and 31 carry Mixer 1. The left channel carries 0.25 b, where b
steps through a circular group of eight state words, so each capture gives
eight points. The right channel carries the result. Pan 127 leaks 1.8 % of
the right channel into the left, which the matching tolerates. A right
channel at full scale moves the left one by 0.018, so the b = 0 samples can
mix into the b = 0.1 point.
"""
import asyncio
import sys

import numpy as np

from dsp import Src, block, copy, f32, gain, ins, jump, message, record, session, store, transfers

B_VALUES = [-2.0, -0.75, -0.1, 0.0, 0.1, 0.5, 1.0, 3.0]
SCALE, REF = 0.1, 0.25
P, Q = -0.5, 0.5
LEAK = 0.018
# A one-word 0xD4 write changes other state words, so the test writes all of them once.
STATE = [0.0] * 8 + B_VALUES + [0.0] * (255 - 16)
MIXER = {"mixers/channels/1/enabled": True, "mixers/channels/2/enabled": True,
         "mixers/1/channels/1/mute": False, "mixers/1/channels/1/pan": 0,
         "mixers/1/channels/2/mute": False, "mixers/1/channels/2/pan": 127,
         **{f"mixers/{m}/channels/{c}/mute": True for m in (2, 3, 4) for c in (1, 2)}}
# The monitor test sends raw 0x15 messages to Headphone 1 and ends them with Mixer 2.
SETTINGS = {"monitor": {"outputs/headphone1/mute": True, "routing/headphone1": "Mixer 2"}}
# Tests with unbounded results put LIMIT and -LIMIT in c4 and c5 and end the body with CLAMP,
# so the right channel stays within full scale.
LIMIT = 10.0
CLAMP = [ins(0x27, a=4, b_src=Src.R), ins(0x26, a=5, b_src=Src.R)]


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


async def run(core, code, length=32):
    """Runs code and records both channels. If the thread stays halted after the swap, with
    exact zeros on both channels, it sends another resume-all."""
    for _ in range(3):
        await core.swap(code, length)
        await asyncio.sleep(0.3)
        await core.check_protected()
        left, right = record([30, 31])
        if left.any() or right.any():
            return left, right
        print("the thread stayed halted after a swap", file=sys.stderr, flush=True)
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


async def units(core):
    """0x0E, 0x11, and 0x2B read the unit inputs that the instruction before them set."""
    print(f"{'b =':24}" + " ".join(f"{b:+9.2f}" for b in B_VALUES))
    await core.coefs(coefs(0.5, LIMIT, -LIMIT))
    for first in (0x06, 0x07, 0x08, 0x09, 0x0A, 0x0C, 0x0D, 0x0F, 0x10):
        for second in (0x0E, 0x11, 0x2B):
            body = [ins(first, a=1, b_src=Src.R), ins(second, a=1, b_src=Src.R), *CLAMP]
            print(row(f"{first:02x} then {second:02x}", await points(core, program(body))), flush=True)
    keep_x = ins(5, a=0, b_src=Src.X, to_r=False)
    for second in (0x0E, 0x11, 0x2B):
        body = [ins(0x0D, a=1, b_src=Src.R), keep_x, ins(second, a=1, b_src=Src.R), *CLAMP]
        print(row(f"0d, x = 1 x, {second:02x}", await points(core, program(body))), flush=True)


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


async def selectors(core):
    """Bits 16:14 of 0x01 with x = 0.5. Each landing block stores its own value and ends the sample."""
    targets = {P: "stopped", 0.5: "no jump", 0.25: "absolute target", -0.25: "relative target"}
    await core.coefs(coefs(0.5, *targets))
    land = [[ins(6, a=c), store(io=1, offset=0), 0x17 | 255 << 6] for c in (5, 6, 7)]
    for selector in range(8):
        for condition in (0b010, 0b011, 0b110):
            code = [ins(5, a=3, b=8, b_src=Src.STATE, k=3), store(io=0, offset=1),
                    ins(6, a=4), store(io=1, offset=0),
                    ins(6, a=1, to_r=False), ins(5, a=0, b=8, b_src=Src.STATE, k=3),
                    jump(10, condition, selector), *land[0], *land[1], 0, 0, 0, *land[2]]
            _, right = await run(core, code)
            value = float(np.median(right))
            name = next((n for t, n in targets.items() if abs(value - t) < 0.01), f"{value:+.4f}")
            print(f"bits 16:14 = {selector}, condition {condition:03b}: {name}", flush=True)


async def idle(core):
    """Bits 27:24 of 0x01 with a jump at address 5 over address 6. The last address at which a
    store still takes effect shows the cycles that the jump used."""
    await core.coefs(coefs(0.5, P, Q))
    print(f"{'no jump':40} last store at {await last_store(core, 0)}", flush=True)
    for selector in range(8):
        for condition in (0b111, 0b110):
            label = f"bits 16:14 = {selector}, condition {condition:03b}, idle 4"
            print(f"{label:40} last store at {await last_store(core, jump(2, condition, selector, 4))}", flush=True)
    for offset in (3, 5):
        label = f"bits 16:14 = 3, offset {offset}, idle 0"
        print(f"{label:40} last store at {await last_store(core, jump(offset, 0b111, 3, 0))}", flush=True)


async def last_store(core, word, low=150, high=166):
    """Returns the last address at which a store after word puts Q on the right channel."""
    head = [ins(5, a=3, b=8, b_src=Src.STATE, k=3), store(io=0, offset=1),
            ins(6, a=4), store(io=1, offset=0), ins(6, a=5), word]
    while high - low > 1:
        middle = (low + high) // 2
        _, right = await run(core, head + [0] * (middle - len(head)) + [store(io=1, offset=0)], length=255)
        low, high = (middle, high) if abs(np.median(right) - Q) < 0.01 else (low, middle)
    return low


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


async def modes(core):
    """Bits 20:18 of 0x14 and 0x15 with the source in the s8 group."""
    print(f"{'b =':24}" + " ".join(f"{b:+9.2f}" for b in B_VALUES))
    await core.coefs(coefs(0.5))
    for op in (0x14, 0x15):
        for mode in range(8):
            body = [copy(op, 8, 20, mode=mode), ins(5, b=20, b_src=Src.STATE)]
            print(row(f"{op:02x} mode {mode}, read s20", await points(core, program(body))), flush=True)
    for read, tail in (("r", []), ("x", [ins(0x2A, a_src=Src.X)])):
        body = [copy(0x15, 8, 20, mode=3), *tail]
        print(row(f"15 mode 3, read {read}", await points(core, program(body))), flush=True)


async def stores(core):
    """Bits 20:18 of 0x02: a store of b to s128 with mode m, then 0x15 with mode m reads offset j
    of the group. The first row reads b of the sample before."""
    print(f"{'b =':24}" + " ".join(f"{b:+9.2f}" for b in B_VALUES))
    await core.coefs(coefs(0.5))
    print(row("s8 group, offset 1", await points(core, program([ins(5, b=9, b_src=Src.STATE, k=3)]))), flush=True)
    for mode in range(8):
        for offset in (0, 1):
            body = [store(offset=128, mode=mode, out=False), copy(0x15, 128 + offset, 40, mode=mode)]
            print(row(f"mode {mode}, offset {offset}", await points(core, program(body))), flush=True)


async def copybits(core):
    """Bits 31:29 of 0x14 and 0x16, from thread 0 s9 (-0.75) and thread 1 s30 (0.77) to s20.
    The last read copies s20 of thread 1 (0.456) back to s21 of thread 0."""
    print(f"{'b =':32}" + " ".join(f"{b:+9.2f}" for b in B_VALUES))
    other = [0.0] * 255
    other[20], other[30] = 0.456, 0.77
    await core.coefs(coefs(0.5))
    reads = {"s20": [ins(5, b=20, b_src=Src.STATE)], "x": [ins(0x2A, a_src=Src.X)], "r": [],
             "t1 s20": [copy(0x14, 20, 21, thread=1), ins(5, b=21, b_src=Src.STATE)]}
    for op in (0x14, 0x16):
        for bit in (29, 30, 31):
            for thread, source in ((0, 9), (1, 30)):
                for read, tail in reads.items():
                    await core.state(other, thread=1)
                    await core.state(STATE)
                    body = [copy(op, source, 20, thread) | 1 << bit, *tail]
                    label = f"{op:02x} bit {bit} t{thread} read {read}"
                    print(row(f"{label:32}", await points(core, program(body))), flush=True)


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


async def unknown(core):
    """Opcodes without a known function, after 0x0D and 0x10. Prints a row only where r is not b or
    x is not c1. 0x38 to 0x3F also get raw integer words as operand A."""
    print(f"{'b =':24}" + " ".join(f"{b:+9.2f}" for b in B_VALUES))
    await core.coefs(coefs(0.5, LIMIT, -LIMIT))
    expected = {"r": B_VALUES, "x": [0.5] * len(B_VALUES)}
    for op in (0x00, 0x03, *range(0x18, 0x26), *range(0x2C, 0x40)):
        for first in (0x0D, 0x10):
            launch = ins(first, a=1, b_src=Src.R)
            for read, body in (("r", [launch, ins(op, a=1, b_src=Src.R)]),
                               ("x", [launch, ins(op, a=1, b_src=Src.R, to_r=False), ins(0x2A, a_src=Src.X)])):
                values = await points(core, program(body + CLAMP))
                if any(v is None or abs(v / SCALE - e) > 0.002 for v, e in zip(values, expected[read])):
                    print(row(f"{first:02x} then {op:02x}, read {read}", values), flush=True)
        print(f"{op:02x} done", flush=True)
    raw = [1, 2, 3, 100, 0xFFFFFFFF, f32(1.0), f32(2.0), 0x00800000]
    await core.write(0xD4, 0, 0, [f32(v) for v in STATE[:16]] + raw + [0] * (255 - 24))
    for op in (0x2A, *range(0x38, 0x40)):
        body = [ins(op, a=16, a_src=Src.STATE, k=3), *CLAMP]
        print(row(f"{op:02x} A = raw s16 group", await points(core, program(body))), flush=True)


async def writes(core):
    """Opcodes without a known function, in the arithmetic, store, and copy field layouts. s20 to
    s23 hold 0.111 to 0.444. Prints a row only where a state word or DSP I/O channel 0 changes."""
    state = list(STATE)
    state[20:24] = [0.111, 0.222, 0.333, 0.444]
    await core.coefs(coefs(0.5))
    setup = [ins(6, a=3), ins(6, a=1, to_r=False)]
    for op in (0x00, 0x03, 0x0D, 0x10, *range(0x18, 0x26), *range(0x2C, 0x40)):
        layouts = {
            "arithmetic, s20 and s21": ([*setup, ins(op, a=20, a_src=Src.STATE, b=21, b_src=Src.STATE)], 20, 21),
            "arithmetic bit 31, s20 and s21": (
                [*setup, ins(op, a=20, a_src=Src.STATE, b=21, b_src=Src.STATE, write=True)], 20, 21),
            "store to s22 and channel 0": (
                [ins(5), store(io=0, offset=30), *setup, op | 22 << 6 | 1 << 22], None, 22),
            "copy s20 to s23": ([*setup, copy(op, 20, 23)], 20, 23)}
        for label, (body, left_word, right_word) in layouts.items():
            reads = [ins(5, b=left_word, b_src=Src.STATE)] if left_word else []
            code = [*body, *reads, store(io=0, offset=1) if reads else 0,
                    ins(5, b=right_word, b_src=Src.STATE), store(io=1, offset=0)]
            await core.state(state)
            left, right = await run(core, code)
            got = (float(np.median(left)), float(np.median(right)))
            want = ((state[left_word] if left_word else 0.0) + LEAK * state[right_word], state[right_word])
            if any(abs(g - w) > 0.002 for g, w in zip(got, want)):
                print(f"{op:02x} {label:32} left {got[0]:+.4f} (want {want[0]:+.4f}), "
                      f"right {got[1]:+.4f} (want {want[1]:+.4f})", flush=True)
        print(f"{op:02x} done", flush=True)


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


async def monitor(core):
    """0xD3 with p1 = 0x60 puts Mixer 1 L on DSP input 0 (8.6). 0x15 puts DSP outputs 0 and 1 on Headphone 1."""
    code = program([ins(0x0B, a=0)])
    for label, words in (("Analog 1", None), ("Mixer 1 L", block(0xD3, 0x60, 0, [0, 0x60 - 0x70 & 0xFF, 1]))):
        if words:
            await core.send(words)
        left, right = await run(core, code)
        _, g, rms = gain(left, right)
        print(f"DSP input 0 = {label}: right = {g / SCALE:+.4f} x left, residual {rms:.5f}", flush=True)
    for label, code in (("DSP outputs 0-1", 0x70), ("Mixer 2", 0x62)):
        await core.send(message([1, 0x15, 15, code]))
        await core.notifications("meters", 3.0)
        frames = await core.notifications("meters", 1.0)
        print(f"Headphone 1 = {label}: peaks", [max(f["headphones"][i] for f in frames) for i in (0, 1)], flush=True)
    await core.route(0, io=0)


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


async def resume(core):
    """Repeats swap sequences and counts the ones after which a thread stays halted. Thread 0 puts
    0.25 b on the left channel, and thread 1 puts 0.3 on the right one."""
    left = [ins(5, a=3, b=8, b_src=Src.STATE, k=3), store(io=0, offset=1)]
    right = [ins(6, a=2), store(io=1, offset=50)]

    async def load_both():
        await core.load(left, coefs(0.5), STATE)
        await core.coefs([1.0, 0.0, 0.3], thread=1)
        await core.swap(right, thread=1)

    async def fast_swaps():
        for _ in range(5):
            await core.swap(left)

    async def no_pauses():
        for words in (block(0xD7, 0, 0, [0, 0, 0, 32]), block(0xD7, 0, 0, [0, 0, 0, 32]),
                      *(block(0xD0, p1, p2, data) for p1, p2, data in transfers(0, 0, left)),
                      block(0xD7, 1, 0, [0, 0, 0, 0])):
            await core.call("raw.send", {"words": words})

    async def nine_halts():
        for _ in range(9):
            await core.halt(0, 0, 32)
        await core.code(left + [0] * 30)
        await core.resume_all()

    async def get_all_then_swap():
        await core.send(message([4, 0, 0, 0]))
        await core.swap(left)

    async def thread_1_swaps():
        for _ in range(5):
            await core.swap(right, thread=1)

    sequences = {"one swap": lambda: core.swap(left), "five swaps": fast_swaps,
                 "two halts, code, resume, no pauses": no_pauses, "nine halts, code, resume": nine_halts,
                 "five swaps in thread 1": thread_1_swaps, "get-all, swap": get_all_then_swap,
                 "erase all, load": load_both}
    await load_both()
    for label, sequence in sequences.items():
        halted = [0, 0]
        for _ in range(10):
            await sequence()
            await asyncio.sleep(0.3)
            await core.check_protected()
            left_channel, right_channel = record([30, 31])
            stopped = (left_channel.std() < 0.01, np.median(right_channel) < 0.1)
            halted = [h + s for h, s in zip(halted, stopped)]
            if any(stopped):
                await core.resume_all()
        print(f"{label:36} 10 runs: thread 0 halted {halted[0]}, thread 1 halted {halted[1]}", flush=True)


async def main(test, settings):
    async with session({**MIXER, **settings.get(test.__name__, {})}) as core:
        await core.load([0], coefs(0.5), STATE)
        await core.route(0, io=0)
        await core.route(1, io=1)
        await test(core)


if __name__ == "__main__":
    tests = {f.__name__: f for f in (sweep, pairs, units, jumps, selectors, idle, copies, modes, stores, copybits,
                                      stall, extra, unknown, writes, routes, state, monitor, resume)}
    if len(sys.argv) != 2 or sys.argv[1] not in tests:
        sys.exit(__doc__)
    asyncio.run(main(tests[sys.argv[1]], SETTINGS))
