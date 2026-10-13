"""Execute mailbox boundaries in isolated Unicorn memory, without device access.

Run: uv run --with unicorn==2.1.4 scripts/firmware/verify-mailbox.py
"""
if not __debug__:
    raise SystemExit('Run without -O or PYTHONOPTIMIZE. Assertions are required.')

import hashlib
from pathlib import Path
import struct

from unicorn import (
    Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS,
    UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_CODE, UC_HOOK_MEM_READ,
    UC_HOOK_MEM_WRITE,
)
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
)

IMAGE = Path('/tmp/apogee-fw/flash.bin')
SHA256 = 'a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8'
DEST = 0x1FFFA030
TIMER = 0x1FFFA0A8
COUNT = 0x1FFF9000
RETURN = 0x10000
MARKER = 0xDEC0AD01
CALLBACK = 0x17519
ARGUMENT = 0x55667788
CODE = (
    (0x11614, 0x1165E), (0x116F8, 0x1174E),
    (0x11F68, 0x12102), (0x12610, 0x12658),
    (0x153F8, 0x1546E), (0x15640, 0x15662), (0x15F34, 0x15F54),
    (0x1FD84, 0x1FE86), (0x1FEE8, 0x1FF58), (0x1FF6C, 0x200D0),
    (0x2014C, 0x20192), (0x2019C, 0x2022C), (0x20280, 0x2035C),
    (0x22080, 0x2209C), (0x2210C, 0x2211E), (0x22124, 0x22136),
    (0x232BC, 0x232D4),
)


def main():
    image = IMAGE.read_bytes()
    assert len(image) == 0x30000
    assert hashlib.sha256(image).hexdigest() == SHA256
    print('SHA256', SHA256)
    cases = 0
    for slot in range(8):
        for state in range(64):
            check_receive(image, slot, state)
            cases += 1
        for state in (0x100, 0x80000000, 0x8000001E, 0x8000001F, 0xFFFFFFFF):
            check_receive(image, slot, state)
            cases += 1
    print(f'PASS {cases} direct cases: slots 0..7, states 0..63 and five high-bit states')
    for gate in ('empty', 'null-destination', 'null-count'):
        check_receive(image, 0, 31, gate)
    print('PASS 3 direct rejection cases: empty ring and null pointers')
    for slot in range(8):
        for state in (0, 0x20, 30, 31, 0x3E, 0x3F):
            check_outer(image, slot, state, 'interrupt')
    print('PASS 48 ISR-to-outer cases: all slots, states 0,32,30,31,62,63')
    for gate in ('idle', 'no-receive-event', 'host-zero', 'host-one', 'pending'):
        check_outer(image, 0, 31, gate)
    print('PASS 5 outer gate cases: idle, unrelated event, host states 0/1, pending drain')
    machine, _, _ = fixture(image, 0, 31)
    for state in (0, 1, 2, 3, 4, 5, 0xFFFFFFFF):
        put(machine, 0x1FFF8F0C, state)
        run(machine, 0x15F34)
        assert machine.reg_read(UC_ARM_REG_R0) == 1
    print('PASS 7 protocol-state probes: helper 0x15f34 always returned 1')
    put(machine, 0x40004F08, 0xFFFE)
    run(machine, 0x20280, stop=0x2033A)
    assert machine.reg_read(UC_ARM_REG_R3) == CALLBACK
    assert machine.reg_read(UC_ARM_REG_R0) == ARGUMENT
    print('PASS timer scheduler: expected stop at 0x2033a before BLX, callback and argument match')
    machine, _, _ = fixture(image, 0, 31)
    run(machine, 0x11F68, DEST, COUNT)
    put(machine, 0x40004F08, 0xFFFE)
    run(machine, 0x20280, stop=0x2033A)
    assert machine.reg_read(UC_ARM_REG_R3) == MARKER
    assert machine.reg_read(UC_ARM_REG_R0) == ARGUMENT
    print('PASS overwritten callback reaches BLX operand, stopped before the branch')
    print('PASS all runs: expected return/stop, at most 20,000 instructions and one second per call')


def check_receive(image, slot, state, gate=None):
    machine, stores, reads = fixture(image, slot, state)
    if gate == 'empty':
        put(machine, 0x60800BEC, slot)
    destination = 0 if gate == 'null-destination' else DEST
    count = 0 if gate == 'null-count' else COUNT
    run(machine, 0x11F68, destination, count)
    words = 0 if gate else state & 31
    verify_copy(machine, stores, reads, slot, words)
    assert machine.reg_read(UC_ARM_REG_R0) == words
    assert get(machine, COUNT) == (0xDEADBEEF if gate else words)
    consumed = state != 0 and gate is None
    assert get(machine, 0x60800BF0) == ((slot + 1) & 7 if consumed else slot)
    assert get(machine, 0x60800BC0 + 4 * slot) == (0 if consumed else state)


def check_outer(image, slot, state, gate):
    machine, stores, reads = fixture(image, slot, state)
    put(machine, 0x1FFF8FC4, 2)
    if gate == 'interrupt':
        put(machine, 0x6080001C, 2)
        run(machine, 0x1FD84)
        assert get(machine, 0x1FFF8FA8) == 1
        assert get(machine, 0x1FFF8FBC) == 2
        assert machine.mem_read(0x60800024, 1) == b'\x02'
    elif gate == 'pending':
        put(machine, 0x1FFF8FC0, 1)
    elif gate != 'idle':
        put(machine, 0x1FFF8FA8, 1)
        put(machine, 0x1FFF8FBC, 0 if gate == 'no-receive-event' else 2)
        if gate in ('host-zero', 'host-one'):
            put(machine, 0x1FFF8FC4, 0 if gate == 'host-zero' else 1)
            put(machine, 0x60800002, 1)
    run(machine, 0x1FF6C)
    accepted = gate in ('interrupt', 'pending')
    words = (state & 31) if accepted else 0
    verify_copy(machine, stores, reads, slot, words)
    consumed = accepted and state != 0
    assert get(machine, 0x60800BF0) == ((slot + 1) & 7 if consumed else slot)
    assert get(machine, 0x60800BC0 + 4 * slot) == (0 if consumed else state)


def fixture(image, slot, state):
    machine = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    for address, size in ((0x10000, 0x30000), (0x1FFF8000, 0x8000),
                          (0x60800000, 0x1000), (0x40004000, 0x1000),
                          (0xE000E000, 0x1000)):
        machine.mem_map(address, size)
    machine.mem_write(0x10000, image)
    machine.mem_protect(0x10000, 0x30000, UC_PROT_READ | UC_PROT_EXEC)
    machine.hook_add(UC_HOOK_CODE, check_code)
    stores, reads = [], []

    def access(uc, kind, address, size, value, data):
        pc = uc.reg_read(UC_ARM_REG_PC)
        if pc == 0x120B8:
            stores.append((address, size, value))
        elif pc in (0x1206E, 0x12082, 0x1209A, 0x120B0):
            reads.append((address, size))

    machine.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, access)
    put(machine, 0x40004F08, 0xFFFF)
    run(machine, 0x2014C)
    run(machine, 0x2019C, CALLBACK, ARGUMENT, 1)
    assert machine.reg_read(UC_ARM_REG_R0) == 1
    assert machine.mem_read(TIMER, 16) == struct.pack('<IIHHI', CALLBACK, ARGUMENT, 1, 0, 1)
    machine.mem_write(DEST - 4, b'\xA5' * 124)
    put(machine, COUNT, 0xDEADBEEF)
    source = 0x60800800 + slot * 120
    machine.mem_write(source, b''.join(struct.pack('<I', i << 8) for i in range(30)))
    put(machine, source + 120, MARKER)
    put(machine, 0x60800BC0 + 4 * slot, state)
    put(machine, 0x60800BEC, (slot + 1) & 7)
    put(machine, 0x60800BF0, slot)
    return machine, stores, reads


def check_code(machine, address, size, data):
    assert any(start <= address < end for start, end in CODE), hex(address)


def run(machine, address, r0=0, r1=0, r2=0, stop=RETURN):
    for register, value in ((UC_ARM_REG_SP, 0x1FFFF000), (UC_ARM_REG_LR, RETURN | 1),
                            (UC_ARM_REG_R0, r0), (UC_ARM_REG_R1, r1), (UC_ARM_REG_R2, r2)):
        machine.reg_write(register, value)
    machine.emu_start(address | 1, stop, timeout=1_000_000, count=20_000)
    pc = machine.reg_read(UC_ARM_REG_PC)
    assert pc == stop, f'Unexpected stop at {pc:#x}, expected {stop:#x}'
    if stop == RETURN:
        assert machine.reg_read(UC_ARM_REG_SP) == 0x1FFFF000


def verify_copy(machine, stores, reads, slot, words):
    source = 0x60800800 + slot * 120
    expected = [(DEST + 4 * i, 4, MARKER if i == 30 else i << 8) for i in range(words)]
    assert stores == expected, (slot, words, stores)
    assert reads == [(source + i, 1) for i in range(words * 4)]
    assert machine.mem_read(DEST - 4, 4) == b'\xA5' * 4
    expected_buffer = b''.join(struct.pack('<I', i << 8) for i in range(min(words, 30)))
    expected_buffer += b'\xA5' * (120 - len(expected_buffer))
    assert machine.mem_read(DEST, 120) == expected_buffer
    assert get(machine, TIMER) == (MARKER if words == 31 else CALLBACK)
    assert machine.mem_read(TIMER + 4, 12) == struct.pack('<IHHI', ARGUMENT, 1, 0, 1)


def put(machine, address, value):
    machine.mem_write(address, struct.pack('<I', value))


def get(machine, address):
    return int.from_bytes(machine.mem_read(address, 4), 'little')


if __name__ == '__main__':
    main()
