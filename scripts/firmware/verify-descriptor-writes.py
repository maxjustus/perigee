"""Verify that no host command writes the settings descriptor table.

Every settings save copies its EEPROM descriptor bytes from the RAM table
at 0x1FFF8BEC. This script checks the direct callers of the EEPROM
writers. It then sends each host message that the dext accepts through
the PSoC harness and watches the table for writes. No device access.

Run: uv run --with unicorn==2.1.4 --with capstone python scripts/firmware/verify-descriptor-writes.py
"""
if not __debug__:
    raise SystemExit('Run without -O or PYTHONOPTIMIZE. Assertions are required.')

import importlib.util
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import UC_HOOK_MEM_WRITE, UcError

spec = importlib.util.spec_from_file_location(
    'psoc_harness', Path(__file__).with_name('psoc-harness.py')
)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

TABLE = 0x1FFF8BEC
TABLE_END = TABLE + 60 * 8
CODE_END = 0x25EBC
DENIED = {0x60, 0x61, 0x62, 0x63}
DIRECT_CALLERS = {
    0x23064: {0x13084, 0x13116, 0x13220, 0x13234},
    0x20EEC: {0x2101E, 0x21186, 0x21218},
    0x20EB8: {0x20F96, 0x210EA},
}
GET_ALL_REPORTS = 936


def main():
    image = h.firmware_image()
    check_direct_callers(image)
    print('PASS direct callers of the EEPROM row writer and descriptor streamers')
    machine = Machine(image)
    sent, stops = 0, []
    for command in range(1, 0xD8):
        if command in DENIED:
            continue
        for words in messages(command):
            sent += 1
            stop = machine.send(words)
            if stop is not None:
                stops.append((words, stop))
                machine = Machine(image)
    print(f'PASS {sent} accepted host messages: no descriptor table write')
    for words, stop in stops:
        record = ' '.join(f'{word:08x}' for word in words[2:4])
        print(f'stopped early, table checked up to the stop: {record}: {stop}')
    machine = Machine(image)
    reports = machine.get_all()
    assert reports == GET_ALL_REPORTS, reports
    print(f'PASS Get-all: {reports} reports, no descriptor table write')


def check_direct_callers(image):
    found = {target: set() for target in DIRECT_CALLERS}
    disassembler = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    disassembler.skipdata = True
    for insn in disassembler.disasm(image[:CODE_END - h.FLASH_BASE], h.FLASH_BASE):
        if insn.mnemonic == 'bl' and int(insn.op_str[1:], 16) in found:
            found[int(insn.op_str[1:], 16)].add(insn.address)
    assert found == DIRECT_CALLERS, found


class Machine:
    def __init__(self, image):
        self.psoc = h.PSoCMachine(
            image, resource=h.RESOURCE.read_bytes(), config=h.CONFIG.read_bytes()
        )
        self.psoc.warm_start()
        self.table = bytes(self.psoc.uc.mem_read(TABLE, TABLE_END - TABLE))
        self.writes = []
        self.psoc.uc.hook_add(
            UC_HOOK_MEM_WRITE,
            lambda _uc, _kind, address, *_: self.writes.append(address),
            begin=TABLE,
            end=TABLE_END - 1,
        )

    def send(self, words):
        try:
            self.psoc.host_write_slot(words)
            self.psoc.step()
            self.psoc.step()
            self.drain()
            stop = None
        except (AssertionError, UcError) as error:
            stop = str(error)
        self.check_table(words)
        return stop

    def get_all(self):
        self.psoc.host_write_slot([1, 0, 4])
        reports = 0
        for _ in range(400):
            self.psoc.step()
            reports += self.drain()
        self.check_table([1, 0, 4])
        return reports

    def drain(self):
        try:
            return len(self.psoc.read_reports())
        except AssertionError:
            return 0

    def check_table(self, words):
        table = bytes(self.psoc.uc.mem_read(TABLE, TABLE_END - TABLE))
        assert not self.writes and table == self.table, (
            [hex(word) for word in words],
            [hex(address) for address in self.writes],
        )


def messages(command):
    for p1 in (0, 2, 3, 7, 0x1F, 0x20, 0x7F, 0xFF):
        for value in (0, 1, 0xAB, 0xFF):
            yield [1, 0, 1 | command << 8 | p1 << 16 | value << 24]
        for p2 in (0, 3, 0xFF):
            for length in (1, 2, 4, 16, 99):
                record = bytes([2, command, p1, p2, length]) + b'\xff' * length
                record += bytes(-len(record) % 4)
                yield [1, 0] + [
                    int.from_bytes(record[i:i + 4], 'little')
                    for i in range(0, len(record), 4)
                ]


if __name__ == '__main__':
    main()
