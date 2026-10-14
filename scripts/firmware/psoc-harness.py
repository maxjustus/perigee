"""Unicorn harness for the vendor PSoC application firmware.

Run the tests:
    uv run --with unicorn==2.1.4 python scripts/firmware/psoc-harness-test.py

Real instructions execute everywhere except registered substitutes. Each
substitute hooks a function entry, performs the function-level replacement,
and jumps to LR. No device access.
"""

if not __debug__:
    raise SystemExit('Run without -O or PYTHONOPTIMIZE. Assertions are required.')

import hashlib
import struct
from pathlib import Path

from unicorn import (
    UC_ARCH_ARM,
    UC_HOOK_CODE,
    UC_HOOK_MEM_READ,
    UC_HOOK_MEM_WRITE,
    UC_MODE_MCLASS,
    UC_MODE_THUMB,
    Uc,
)
from unicorn.arm_const import (
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
    UC_ARM_REG_SP,
)

FLASH = Path('/tmp/apogee-fw/flash.bin')
CONFIG = Path('/tmp/apogee-fw/config.bin')
RESOURCE = Path(
    '/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/'
    'EnsembleResourceData.bin'
)
SHA256 = 'a5e8e2c752255e627fdd4549408ed4f1a5fe1f76f7352799614a3eb386f1b9a8'

FLASH_BASE = 0x10000
SRAM_BASE = 0x1FFF8000
EEPROM_BASE = 0x40008000
CONFIG_BASE = 0x48000000
PLL_STATUS = 0x40004225
DISPLAY_TX_STATUS = 0x4000646A  # CYREG_B0_UDB10_ST
DISPLAY_RX_STATUS = 0x40006469  # CYREG_B0_UDB09_ST
FPGA_BASE = 0x60800000
BRIDGE_IMAGE_BASE = 0x380000
BRIDGE_SIZE = 0x800000

RETURN = 0x3F000
STACK = 0x20007000

# Mailbox layout inside the FPGA EMIF window (NOTES-vendor-driver.md 2.5,
# 5.3-5.5). RX = PSoC to host, TX = host to PSoC.
RX_SLOT_BASE = FPGA_BASE + 0x400
RX_STATE = FPGA_BASE + 0x7C0
RX_WRITE_INDEX = FPGA_BASE + 0xBE4
RX_READ_INDEX = FPGA_BASE + 0xBE8
TX_SLOT_BASE = FPGA_BASE + 0x800
TX_STATE = FPGA_BASE + 0xBC0
TX_WRITE_INDEX = FPGA_BASE + 0xBEC
TX_READ_INDEX = FPGA_BASE + 0xBF0
SLOT_STRIDE = 0x78
FPGA_EVENT = FPGA_BASE + 0x1C
FPGA_LINK = FPGA_BASE + 0x02
FPGA_SIGNATURE = FPGA_BASE + 0x00
FPGA_READY = FPGA_BASE + 0x35
PSOC_EVENT = FPGA_BASE + 0x7E0

HOST_HANDSHAKE_STATE = 0x1FFF8FC4
SETTINGS_INIT = 0x203B4
RESOURCE_RELOAD = 0x1C8F8
VERSION_REFRESH = 0x17404
SCHEDULER_INIT = 0x2014C
IRQ6_HANDLER = 0x1FD84
SERVICE_EVENTS = 0x1FF6C
SEND_REPORTS = 0x15668

EEPROM_WRITE = 0x23064
TICKER_READ = 0x232BC
CYDELAY = 0x23AD4
CYDELAY_US = 0x23B18
FPGA_WRITE_WORD32 = 0x12610
PREAMP_WRITE_REGISTER = 0x108BC
I2C_WRITE_RETRY = 0x11050
I2C_WRITE_REGISTER = 0x110C0
I2C_READ_REGISTER_RETRY = 0x110F0
I2C_MASTER_WRITE_BUF = 0x2278C
I2C_MASTER_READ_BUF = 0x22898
I2C_MASTER_STATUS = 0x229A8
I2C_MASTER_CLEAR_STATUS = 0x229E4
PREAMP_SPI_WRITE = 0x22244
DISPLAY_SPI_WRITE = 0x22B94

# Flash bridge inside the FPGA window (FUN_00012334/00012370/000123e0).
BRIDGE_COMMAND = FPGA_BASE + 0x2E
BRIDGE_LENGTH = FPGA_BASE + 0x2F
BRIDGE_ADDRESS = FPGA_BASE + 0x31
BRIDGE_BUFFER = FPGA_BASE + 0xC00
BRIDGE_CMD_ERASE = 0x02
BRIDGE_CMD_PROGRAM = 0x10
BRIDGE_CMD_READ = 0x12

MAIN_LOOP_START = 0x1F8FC
MAIN_LOOP_END = 0x1F9B8
RESET_HANDLER = 0x10010


def firmware_image():
    image = FLASH.read_bytes()
    if hashlib.sha256(image).hexdigest() != SHA256:
        raise SystemExit('flash.bin identity check failed')
    return image


class PSoCMachine:
    """One emulated PSoC: flash, SRAM, peripherals, FPGA window, flash bridge.

    A substitute replaces a whole hardware function at its entry address and
    jumps to LR; every hit is counted in self.hits.
    """

    def __init__(self, image, resource=None, config=None):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.uc.mem_map(FLASH_BASE, 0x30000)
        self.uc.mem_write(FLASH_BASE, image)
        self.uc.mem_map(SRAM_BASE, 0x10000)
        self.uc.mem_write(SRAM_BASE + 0x108, image[0x153D8:0x161A0])
        self.uc.mem_map(0x40000000, 0x100000)  # peripherals incl. EEPROM
        self.uc.mem_write(EEPROM_BASE, b'\xff' * 0x800)
        # Display SPI status registers, modelled as always complete:
        # the display init polls bits 0 and 4 of both (FUN_00010988 etc.).
        self.uc.mem_write(DISPLAY_TX_STATUS, b'\x11')
        self.uc.mem_write(DISPLAY_RX_STATUS, b'\x11')
        self.uc.mem_map(CONFIG_BASE, 0x8000)  # flash config words (ECC rows)
        if config is not None:
            self.uc.mem_write(CONFIG_BASE, config[:0x8000])
        self.uc.mem_map(0x49000000, 0x10000)  # factory trim bytes
        self.uc.mem_map(0xE000E000, 0x1000)  # NVIC system space
        self.uc.mem_map(FPGA_BASE, 0x10000)
        self.uc.mem_write(PLL_STATUS, b'\x01')  # PLL locked (ClockSetup poll)
        self.uc.mem_write(FPGA_SIGNATURE, b'\xab')  # FPGA_WaitReady signature
        self.uc.mem_write(FPGA_READY, b'\x02')  # status bit 1: ready
        self.uc.mem_write(FPGA_BASE + 0x06, b'\x56')  # FPGA firmware version
        self.uc.mem_write(
            FPGA_BASE + 0x1807, bytes.fromhex('01 00 00 01 00 00')
        )  # DSP core version, live-observed
        self.bridge = bytearray(BRIDGE_SIZE)
        if resource is not None:
            end = min(BRIDGE_IMAGE_BASE + len(resource), BRIDGE_SIZE)
            self.bridge[BRIDGE_IMAGE_BASE:end] = resource[
                : end - BRIDGE_IMAGE_BASE
            ]
        self.bridge_ops = {command: 0 for command in (2, 0x10, 0x12)}
        self.pending_command = None
        self.now = 0
        self.hits = {}
        self.register_substitutions()
        self.uc.hook_add(
            UC_HOOK_MEM_WRITE,
            self.note_bridge_command,
            begin=BRIDGE_COMMAND,
            end=BRIDGE_COMMAND,
        )
        self.uc.hook_add(
            UC_HOOK_MEM_READ,
            self.run_bridge_command,
            begin=BRIDGE_COMMAND,
            end=BRIDGE_COMMAND,
        )

    def register_substitutions(self):
        for address, handler in (
            (EEPROM_WRITE, self.sub_eeprom_write),
            (TICKER_READ, self.sub_ticker_read),
            (CYDELAY, self.sub_noop),
            (CYDELAY_US, self.sub_noop),
            (FPGA_WRITE_WORD32, self.sub_fpga_write_word32),
            (PREAMP_WRITE_REGISTER, self.sub_noop),
            (I2C_WRITE_RETRY, self.sub_noop),
            (I2C_WRITE_REGISTER, self.sub_noop),
            (I2C_READ_REGISTER_RETRY, self.sub_i2c_read),
            (I2C_MASTER_WRITE_BUF, self.sub_noop),
            (I2C_MASTER_READ_BUF, self.sub_noop),
            (I2C_MASTER_STATUS, self.sub_i2c_status),
            (I2C_MASTER_CLEAR_STATUS, self.sub_i2c_clear),
            (PREAMP_SPI_WRITE, self.sub_noop),
            (DISPLAY_SPI_WRITE, self.sub_noop),
        ):
            assert address not in self.hits
            self.hits[address] = 0
            self.uc.hook_add(
                UC_HOOK_CODE,
                self.make_substitute(address, handler),
                begin=address,
                end=address,
            )

    def make_substitute(self, address, handler):
        def substitute(uc, _address, _size, _data):
            self.hits[address] += 1
            handler(uc)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        return substitute

    def sub_eeprom_write(self, uc):
        pointer = uc.reg_read(UC_ARM_REG_R0)
        row = uc.reg_read(UC_ARM_REG_R1)
        assert row < 128, 'EEPROM row bound'
        uc.mem_write(EEPROM_BASE + row * 16, bytes(uc.mem_read(pointer, 16)))
        uc.reg_write(UC_ARM_REG_R0, 0)

    def sub_ticker_read(self, uc):
        uc.reg_write(UC_ARM_REG_R0, (~self.now) & 0xFFFF)

    def sub_noop(self, uc):
        pass

    def sub_fpga_write_word32(self, uc):
        offset = uc.reg_read(UC_ARM_REG_R0)
        value = uc.reg_read(UC_ARM_REG_R1)
        assert 0 <= offset < 0x10000, hex(offset)
        uc.mem_write(
            FPGA_BASE + offset, (value & 0xFFFFFFFF).to_bytes(4, 'little')
        )

    def sub_i2c_read(self, uc):
        uc.reg_write(UC_ARM_REG_R0, 0)  # no device on the bus

    def sub_i2c_status(self, uc):
        uc.reg_write(UC_ARM_REG_R0, 0x02)  # transfer complete

    def sub_i2c_clear(self, uc):
        uc.reg_write(UC_ARM_REG_R0, 0)

    # Flash bridge: the PSoC writes a command to 0x2E and polls the same
    # byte until the busy bit clears. The write hook records the command;
    # the read hook performs it and leaves 0 (not busy).
    def note_bridge_command(self, uc, _kind, _address, _size, value, _data):
        self.pending_command = value

    def run_bridge_command(self, uc, _kind, _address, _size, _value, _data):
        if self.pending_command is None:
            return
        command = self.pending_command
        self.pending_command = None
        length = self.get(BRIDGE_LENGTH, 2)
        address = self.get(BRIDGE_ADDRESS, 3)
        if command == BRIDGE_CMD_READ:
            uc.mem_write(
                BRIDGE_BUFFER, bytes(self.bridge[address:address + length])
            )
        elif command == BRIDGE_CMD_PROGRAM:
            self.bridge[address:address + length] = uc.mem_read(
                BRIDGE_BUFFER, length
            )
        elif command == BRIDGE_CMD_ERASE:
            sector = address & ~0xFFF
            self.bridge[sector:sector + 0x1000] = b'\xff' * 0x1000
        else:
            raise AssertionError(f'unknown bridge command {command:#x}')
        uc.mem_write(BRIDGE_COMMAND, b'\x00')
        self.bridge_ops[command] += 1

    def call(self, address, *args, count=2_000_000):
        for register, value in zip(
            (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args
        ):
            self.uc.reg_write(register, value)
        self.uc.reg_write(UC_ARM_REG_SP, STACK)
        self.uc.reg_write(UC_ARM_REG_LR, RETURN | 1)
        self.uc.emu_start(address | 1, RETURN, count=count)
        assert self.uc.reg_read(UC_ARM_REG_PC) == RETURN, (
            f'unbounded run: stopped at {self.uc.reg_read(UC_ARM_REG_PC):#x} '
            f'instead of returning from {address:#x}'
        )
        assert self.uc.reg_read(UC_ARM_REG_SP) == STACK, hex(address)
        return self.uc.reg_read(UC_ARM_REG_R0)

    def put(self, address, value, width=4):
        self.uc.mem_write(address, value.to_bytes(width, 'little'))

    def get(self, address, width=4):
        return int.from_bytes(self.uc.mem_read(address, width), 'little')

    # Host side: driver behavior from NOTES-vendor-driver.md 5.3-5.4.
    def init_mailbox(self):
        for slot in range(8):
            self.put(TX_STATE + 4 * slot, 0)
            self.put(RX_STATE + 4 * slot, 0)
        for address in (
            TX_WRITE_INDEX,
            TX_READ_INDEX,
            RX_WRITE_INDEX,
            RX_READ_INDEX,
            PSOC_EVENT,
            FPGA_BASE + 0xBE0,
        ):
            self.put(address, 0)

    def connect_host(self):
        # Bit 0: link present. Bits 5:3 give hardware revision 3
        # (FUN_00011b4c computes (reg >> 3 & 7) + 1).
        self.uc.mem_write(FPGA_LINK, b'\x11')
        for event in (3, 2):  # connect, host reset
            self.raise_fpga_event(event)
            self.call(IRQ6_HANDLER)
        for _ in range(16):
            self.call(SERVICE_EVENTS)
            if self.get(HOST_HANDSHAKE_STATE) == 2:
                return
        raise AssertionError('host handshake did not reach protocol-ready')

    def raise_fpga_event(self, bit):
        address = FPGA_EVENT + (bit >> 3)
        self.uc.mem_write(
            address, bytes([self.get(address, 1) | (1 << (bit & 7))])
        )

    def warm_start(self):
        self.call(SCHEDULER_INIT)
        assert self.call(SETTINGS_INIT) == 1, 'settings initialization'
        self.init_mailbox()
        self.connect_host()
        self.call(RESOURCE_RELOAD)  # load the header, set resource validity
        # FUN_00017404 stores the version values into the state pool and
        # flags the 0x40 and 0xD2 descriptors for sending.
        # The refresh computes the whole-resource CRC-8 through the flash
        # bridge, about 22 million instructions, then caches it.
        self.call(VERSION_REFRESH, count=60_000_000)

    def host_write_slot(self, words):
        write = self.get(TX_WRITE_INDEX)
        read = self.get(TX_READ_INDEX)
        assert write <= 8 and read <= 8, 'TX index bounds'
        assert (write + 1) & 7 != read, 'TX ring full'
        data = b''.join(struct.pack('<I', word) for word in words)
        self.uc.mem_write(TX_SLOT_BASE + write * SLOT_STRIDE, data)
        self.put(TX_STATE + 4 * write, (1 << 5) | len(words))
        self.put(TX_WRITE_INDEX, (write + 1) & 7)
        # The driver rings the doorbell in the BAR0 GENERAL register; the
        # FPGA answers by raising event bit 1 to the PSoC (FUN_0001fd84).
        self.raise_fpga_event(1)
        self.call(IRQ6_HANDLER)

    def send_get(self, command, p1):
        self.host_write_slot([1, 0, 3 | command << 8 | p1 << 16])

    def step(self):
        # One pass of the main loop body (FUN_0001f8fc calls both in order).
        self.call(SERVICE_EVENTS)
        self.call(SEND_REPORTS)

    def run_until_report(self, command, p1, attempts=4):
        self.send_get(command, p1)
        for _ in range(attempts):
            self.step()
            for record in self.read_reports():
                if record['cmd'] == command and record['p1'] == p1:
                    return record
        raise AssertionError(f'no report for {command:#x} p1 {p1}')

    def read_reports(self):
        records = []
        write = self.get(RX_WRITE_INDEX)
        read = self.get(RX_READ_INDEX)
        while write != read:
            state = self.get(RX_STATE + 4 * read)
            assert state & 0x20, 'RX slot not full'
            length = min(state & 0x1F, 30)
            data = bytes(
                self.uc.mem_read(
                    RX_SLOT_BASE + read * SLOT_STRIDE, length * 4
                )
            )
            self.put(RX_STATE + 4 * read, 0)
            self.put(RX_READ_INDEX, (read + 1) & 7)
            records.extend(parse_records(data))
            write = self.get(RX_WRITE_INDEX)
            read = self.get(RX_READ_INDEX)
        return records

    def cold_boot(self, count=80_000_000):
        """Run from Reset_Handler until the main loop entry, bounded.

        Emulation stops at the first call of the main loop function,
        0x1F8FC. A return at any other address is a stall.
        """
        self.uc.reg_write(UC_ARM_REG_SP, 0x20008000)
        self.uc.emu_start(RESET_HANDLER | 1, MAIN_LOOP_START, count=count)
        return self.uc.reg_read(UC_ARM_REG_PC)


def parse_records(data):
    """Parse mailbox records the way the vendor host does (NOTES 5.4)."""
    records = []
    offset = 8  # words 0 and 1 are the header
    while offset + 4 <= len(data):
        kind = data[offset]
        if kind == 1:
            records.append(
                {
                    'cmd': data[offset + 1],
                    'p1': data[offset + 2],
                    'p2': 0,
                    'data': data[offset + 3:offset + 4],
                }
            )
            offset += 4
        elif kind == 2:
            length = data[offset + 4]
            words = 2 + (max(length - 3, 0) + 3) // 4
            records.append(
                {
                    'cmd': data[offset + 1],
                    'p1': data[offset + 2],
                    'p2': data[offset + 3],
                    'data': data[offset + 5:offset + 5 + length],
                }
            )
            offset += 4 * words
        else:
            raise AssertionError(f'unknown record type {kind:#x}')
    return records
