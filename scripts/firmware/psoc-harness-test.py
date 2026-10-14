"""Tests for the PSoC harness. Red first, then green.

Run: uv run --with unicorn==2.1.4 python scripts/firmware/psoc-harness-test.py
"""

if not __debug__:
    raise SystemExit('Run without -O or PYTHONOPTIMIZE. Assertions are required.')

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'psoc_harness', Path(__file__).with_name('psoc-harness.py')
)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def main():
    image = h.firmware_image()
    resource = h.RESOURCE.read_bytes()
    config = h.CONFIG.read_bytes()

    machine = h.PSoCMachine(image, resource=resource, config=config)
    machine.warm_start()
    print('PASS warm start: settings init, mailbox init, handshake state 2')

    check(
        machine.get(h.TX_WRITE_INDEX) == 0
        and machine.get(h.TX_READ_INDEX) == 0,
        'mailbox indices start at zero',
    )

    record = machine.run_until_report(0x40, 0)
    check(record['data'] == bytes.fromhex('010503'), 'version 0x40 p1 0 data')
    check(
        machine.get(h.TX_READ_INDEX) == 1
        and machine.get(h.TX_WRITE_INDEX) == 1,
        'TX indices advance together',
    )
    check(machine.get(h.TX_STATE) == 0, 'consumed TX slot state clears')
    check(
        machine.get(h.RX_WRITE_INDEX) == machine.get(h.RX_READ_INDEX),
        'RX indices match after the host read drains every slot',
    )
    check(machine.get(h.RX_STATE) == 0, 'read RX slot state clears')
    print('PASS get 0x40 p1 0: report 01 05 03, indices and state cleared')

    record = machine.run_until_report(0x40, 3)
    check(record['data'] == bytes.fromhex('00061b'), 'version 0x40 p1 3 data')
    check(
        machine.get(h.TX_WRITE_INDEX) == 2 and machine.get(h.TX_READ_INDEX) == 2,
        'second command uses the next slot',
    )
    print('PASS get 0x40 p1 3: report 00 06 1b')

    refused = False
    try:
        machine.call(h.RESET_HANDLER, count=100)
    except AssertionError:
        refused = True
    check(refused, 'unbounded run is refused')
    print('PASS refusal: bounded call stops with PC check')

    stall = machine.cold_boot()
    check(stall == h.MAIN_LOOP_START, 'cold boot reaches the main loop entry')
    print('PASS cold boot: reached the main loop from Reset_Handler')
    exercised = (h.TICKER_READ, h.FPGA_WRITE_WORD32)
    for address in exercised:
        check(machine.hits[address] > 0, f'substitution at {address:#x} never fired')
    check(machine.bridge_ops[0x12] > 0, 'flash bridge read never ran')
    quiet = sorted(hex(a) for a, n in machine.hits.items() if n == 0)
    print(f'PASS substitution accounting: exercised-path substitutes fired')
    print(f'path-conditional, not exercised here: {", ".join(quiet)}')

    machine = h.PSoCMachine(image, resource=resource, config=config)
    machine.warm_start()
    record = machine.run_until_report(0x40, 1)
    check(len(record['data']) == 3, 'version 0x40 p1 1 is a three-byte value')
    print('PASS fresh machine: get 0x40 p1 1 returns a version record')


def check(condition, label):
    if not condition:
        raise AssertionError(label)


if __name__ == '__main__':
    main()
