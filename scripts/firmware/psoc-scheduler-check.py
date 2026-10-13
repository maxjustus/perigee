"""Check PSoC scheduler instructions offline with bounded Unicorn calls.

Run: uv run --offline --with unicorn python scripts/firmware/psoc-scheduler-check.py
Only counter reads and EEPROM row writes use substitutes. No device access.
"""

import hashlib
from pathlib import Path

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_MCLASS, UC_MODE_THUMB, Uc
from unicorn.arm_const import (
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
    UC_ARM_REG_SP,
)


def main():
    image = Path("/tmp/apogee-fw/flash.bin").read_bytes()
    check(
        hashlib.sha256(image).hexdigest()
        == "a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8",
        "image identity",
    )
    fw = Firmware(image)
    for start, now, expected in (
        (0, 3000, 3000),
        (0, 3001, 3001),
        (65535, 0, 0),
        (65530, 5, 10),
        (0, 65535, 65535),
        (3000, 3000, 0),
    ):
        fw.now = now
        check(fw.call(0x20378, start) == expected, "elapsed arithmetic")
    fw.now = 0
    fw.call(0x2014C)
    handles = [fw.call(0x2019C, 0x17519, 0, 1000) for _ in range(10)]
    check(handles == list(range(1, 11)), "timer handles")
    check(fw.call(0x2019C, 0x17519, 0, 1000) == 0, "timer exhaustion")
    check(fw.call(0x20230, 0) == 0, "invalid timer handle")
    check(fw.call(0x20230, 11) == 0, "timer upper bound")
    check(fw.call(0x20230, 1) == 1, "timer removal")
    check(fw.call(0x20230, 1) == 1, "empty slot removal")
    fw.call(0x2014C)
    handle = fw.call(0x2019C, 0x17519, 0, 1000)
    fw.put(0x1FFF914C, handle)
    fw.put(0x1FFF82F8, 1)
    fw.now = 999
    fw.call(0x20280)
    check(fw.get(0x1FFF82F8) == 1, "callback not due")
    fw.now = 1000
    fw.call(0x20280)
    check(fw.get(0x1FFF82F8) == 0, "callback executes")
    check(fw.get(0x1FFFA0A8) == 0, "callback removes itself")
    fw.call(0x2019C, 0x17519, 0, 65000)
    fw.put(0x1FFFA0B2, 2000, 2)
    fw.now = 65535
    fw.call(0x20280)
    check(fw.get(0x1FFFA0B2, 2) == 999, "elapsed accumulator wraps")
    check(fw.get(0x1FFFA0A8) == 0x17519, "overflow skips due callback")

    fw = Firmware(image)
    check(fw.call(0x203B4) == 1, "identify test defaults")
    message = bytearray(112)
    message[8] = 0x27
    message[11] = 1
    fw.uc.mem_write(0x20006000, bytes(message))
    fw.call(0x16228, 0x20006000, 0)
    fw.call(0x16228, 0x20006000, 0)
    check(fw.get(0x1FFF8F18) == 2, "identify replaces saved handle")
    message[11] = 0
    fw.uc.mem_write(0x20006000, bytes(message))
    fw.call(0x16228, 0x20006000, 0)
    check(fw.get(0x1FFFA0A8) == 0x10545, "first identify timer survives cancel")
    check(fw.get(0x1FFFA0B8) == 0, "latest identify timer removed")
    check(
        [fw.call(0x105CC, phase, 2) for phase in range(3)] == [1, 0, 0],
        "identify phase helper",
    )

    fw = Firmware(image)
    check(fw.call(0x203B4) == 1, "settings initialization")
    fw.put(0x1FFF9014, 1)
    fw.call(0x204DC)
    check(fw.get(0x1FFF9014) == 1 and not fw.rows, "dirty-only finish does not save")
    fw.now = 3000
    fw.call(0x20498)
    check(fw.get(0x1FFF902C) == 0 and not fw.rows, "strict threshold")
    fw.now = 3001
    fw.call(0x20498)
    check(fw.get(0x1FFF902C) == 1 and fw.rows == [0], "save starts at 3001")
    steps = fw.finish()
    check(fw.call(0x20B78) == 1, "complete save validates")
    check(len(fw.rows) == 82, "81 rows plus header patch")
    print(f"save: {steps} advance calls, {len(fw.rows)} row requests")

    fw.rows.clear()
    fw.call(0x210B0)
    fw.put(0x1FFF9014, 1)
    fw.put(0x1FFF9018, 0, 2)
    fw.call(0x20498)
    check(fw.get(0x1FFF901C) == 3, "dirty timeout restarts active save")
    check(fw.rows == [0, 0], "active restart rewrites first row")
    fw.finish()

    fw.call(0x210B0)
    for _ in range(40):
        if fw.get(0x1FFF902C) != 1:
            break
        check(fw.call(0x211DC) == 1, "descriptor phase remains active")
    else:
        raise AssertionError("descriptor phase exceeded 40 calls")
    check(fw.call(0x211DC) == 1, "first live data chunk")
    old = fw.get(0x1FFFA148, 1)
    fw.set_byte(1, (old + 1) & 255)
    fw.finish()
    check(fw.call(0x20B78) == 1, "mixed-time save validates")
    check(fw.get(0x400080AC, 1) == old, "already copied value stays old")
    check(fw.get(0x1FFF9014) == 1, "mutation remains dirty after commit")
    rows = len(fw.rows)
    fw.call(0x204DC)
    check(len(fw.rows) == rows, "finish omits second dirty save")

    fw = Firmware(image)
    check(fw.call(0x203B4) == 1, "factory test defaults")
    fw.call(0x210B0)
    state = fw.get(0x1FFF902C)
    cursor = fw.get(0x1FFF901C)
    fw.call(0x205CC)
    fw.call(0x20F5C)
    saved = bytes(fw.uc.mem_read(0x40008000, 0x50B))
    check(saved[:3] == b"\xae\x02\x2a" and saved[3] == crc8(saved[4:]), "factory CRC")
    check(fw.get(0x1FFF902C) == state, "factory save leaves active state")
    check(fw.get(0x1FFF901C) == cursor, "factory save leaves async cursor")
    fw.finish()
    check(fw.call(0x20B78) == 0, "async continuation invalidates factory save")

    fw = Firmware(image)
    check(fw.call(0x203B4) == 1, "fresh settings initialization")
    fw.call(0x20F5C)
    old_image = bytearray(fw.uc.mem_read(0x40008000, 0x50B))
    hybrid = bytearray(old_image)
    hybrid[0xAC] ^= 1
    tail = next(
        value for value in range(256) if crc8(hybrid[4:-1] + bytes([value])) == 0
    )
    fw.uc.mem_write(0x1FFFA7A5, bytes([tail]))
    fw.call(0x20F5C)
    old_image = bytes(fw.uc.mem_read(0x40008000, 0x50B))
    fw.set_byte(1, hybrid[0xAC])
    fw.set_byte(0xA0, tail ^ 1)
    fw.call(0x210B0)
    for _ in range(200):
        if 10 in fw.rows[-1:]:
            break
        check(fw.call(0x211DC) == 1, "interrupted save remains active")
    else:
        raise AssertionError("first payload row not reached")
    partial = bytes(fw.uc.mem_read(0x40008000, 0x50B))
    check(partial[0xAC] != old_image[0xAC], "hybrid contains new prefix")
    check(partial[-1] == tail, "hybrid retains old suffix")
    check(partial[3] == 0 and crc8(partial[4:]) == 0, "zero CRC hybrid")
    reboot = Firmware(image)
    check(reboot.call(0x203B4) == 1, "reboot defaults")
    reboot.uc.mem_write(0x40008000, partial)
    check(reboot.call(0x20B78) == 1, "interrupted hybrid accepted after reboot")

    fw = Firmware(image)
    check(fw.call(0x203B4) == 1, "write-failure defaults")
    fw.fail_rows = True
    fw.call(0x210B0)
    fw.call(0x204DC)
    check(
        fw.get(0x1FFF902C) == 0 and fw.get(0x1FFF9014) == 0,
        "failed rows still complete",
    )
    check(fw.call(0x20B78) == 0, "failed rows leave invalid EEPROM")
    print(
        "PASS: timer, save threshold, mutation, reset overlap, interrupted CRC, row failure"
    )


def check(condition, label):
    if not condition:
        raise AssertionError(label)


class Firmware:
    def __init__(self, image):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.uc.mem_map(0x10000, 0x30000)
        self.uc.mem_write(0x10000, image)
        self.uc.mem_map(0x1FFF8000, 0x10000)
        self.uc.mem_write(0x1FFF8108, image[0x153D8:0x161A0])
        self.uc.mem_map(0x40008000, 0x1000)
        self.uc.mem_write(0x40008000, b"\xff" * 0x800)
        self.now = 0
        self.rows = []
        self.fail_rows = False
        self.uc.hook_add(UC_HOOK_CODE, self.substitute)

    def substitute(self, uc, address, size, data):
        if address == 0x232BC:
            uc.reg_write(UC_ARM_REG_R0, (~self.now) & 0xFFFF)
        elif address == 0x23064:
            pointer = uc.reg_read(UC_ARM_REG_R0)
            row = uc.reg_read(UC_ARM_REG_R1)
            check(row < 128, "EEPROM row bound")
            self.rows.append(row)
            if not self.fail_rows:
                uc.mem_write(0x40008000 + row * 16, bytes(uc.mem_read(pointer, 16)))
            uc.reg_write(UC_ARM_REG_R0, 4 if self.fail_rows else 0)
        else:
            return
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def call(self, address, *args):
        for register, value in zip(
            (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args
        ):
            self.uc.reg_write(register, value)
        self.uc.reg_write(UC_ARM_REG_SP, 0x20007000)
        self.uc.reg_write(UC_ARM_REG_LR, 0x3F001)
        self.uc.emu_start(address | 1, 0x3F000, count=1_000_000)
        check(self.uc.reg_read(UC_ARM_REG_PC) == 0x3F000, f"return from {address:#x}")
        check(self.uc.reg_read(UC_ARM_REG_SP) == 0x20007000, f"stack at {address:#x}")
        return self.uc.reg_read(UC_ARM_REG_R0)

    def put(self, address, value, width=4):
        self.uc.mem_write(address, value.to_bytes(width, "little"))

    def get(self, address, width=4):
        return int.from_bytes(self.uc.mem_read(address, width), "little")

    def finish(self):
        for steps in range(1, 201):
            result = self.call(0x211DC)
            check(result in (0, 1), "save return is boolean")
            if result == 0:
                return steps
        raise AssertionError("save exceeded 200 calls")

    def set_byte(self, command, value):
        message = bytearray(112)
        message[8] = command
        message[11] = value
        self.uc.mem_write(0x20006000, bytes(message))
        self.call(0x20918, 0x20006000, 1)


def crc8(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ (7 if crc & 0x80 else 0)) & 255
    return crc


if __name__ == "__main__":
    main()
