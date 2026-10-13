"""Check vendor bytes and address arithmetic. No firmware or device execution.

Run: python3 scripts/firmware/verify-recovery.py [image.cyacd]
"""

import hashlib
import runpy
import sys
from pathlib import Path

DEFAULT = Path(
    "/Applications/Utilities/Apogee Firmware Updater.app/Contents/Resources/EnsemblePSoC.cyacd"
)
SHA256 = "7dd0ab0a7e7d1637309d48684b250c4f8a69a1cafa215b5a9c682ad4673a3a24"


def main():
    if not __debug__:
        sys.exit("Verification requires assertions. Disable Python optimization.")
    image = load_image(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT)
    anchors = {
        "mode-one interval": {
            0x1838C: "4ff46013",
            0x18394: "03f59003",
            0x183A2: "07d3",
            0x183AC: "02d2",
        },
        "mode-two interval": {
            0x183B6: "4ff4e013",
            0x183BE: "03f5e013",
            0x183CC: "07d3",
            0x183D6: "02d2",
        },
        "next address and completion check": {
            0x18140: "faf780f9",
            0x18148: "03f58073",
            0x181E8: "00f0c0f8",
            0x181F0: "5ad0",
            0x182A8: "244b0222da60",
        },
        "program timeout and exact byte count": {
            0x12450: "fff78eff",
            0x12458: "05d1",
            0x1245A: "1c4b01221a601b4b02221a60",
            0x12468: "b3f5807f",
            0x1246C: "2bd8",
            0x1248C: "1b780b70",
            0x1249A: "9a42edd3",
            0x124A0: "fff748ff",
            0x124A6: "0a221a70",
            0x124B4: "054b02221a60054b02221a60",
            0x124CC: "f88eff1ffc8eff1f340080602e008060",
        },
        "completion status from separate global": {
            0x18278: "faf730f9",
            0x18288: "09f030fb",
            0x182C0: "1e4bdb68dbb287f87b30",
            0x1833C: "248fff1f",
        },
        "mode-zero marker and reset": {
            0x17FCC: "fff794fb",
            0x17FD0: "2f4b00221a70",
            0x17FE2: "0bf08bf9",
            0x18090: "2d008060",
            0x176FC: "012000f029f8",
            0x1775E: "cd233b73ab237b73",
            0x1776C: "01230023dbb2bb730023fb73",
            0x1777C: "4ff4fe6019460422fbf700fd",
            0x23300: "024b40221a7000f0d5fb",
            0x2330C: "fa460040",
            0x23AC0: "43f00103dbb21370",
            0x23AD0: "f6460040",
        },
        "command 0x63 state five": {
            0x18360: "fff7bef9",
            0x176E4: "034b05221a60",
            0x176F4: "1c8fff1f",
            0x175E8: "09760100",
            0x17608: "012000f0a3f8",
        },
    }
    for claim, checks in anchors.items():
        for address, expected in checks.items():
            value = bytes.fromhex(expected)
            assert image[address : address + len(value)] == value, (
                f"{claim}: {address:#x}"
            )
        print(f"PASS bytes: {claim}")
    for mode, lower, upper in [(1, 0x380000, 0x800000), (2, 0x1C0000, 0x380000)]:
        assert lower <= upper - 256 < upper
        next_address = (upper - 256) + 256
        assert not lower <= next_address < upper
        assert lower + ((upper - lower - 1) // 256) * 256 == upper - 256
        print(f"PASS arithmetic: mode {mode}, exact fill ends at excluded {upper:#x}")


def load_image(path):
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SHA256, "Unexpected vendor image"
    rows, _ = runpy.run_path(str(Path(__file__).with_name("image-format-inspect.py")))["parse"](raw)
    assert list(rows) == [256 + n for n in range(256)] + [512 + n for n in range(98)] + [1023]
    image = bytearray(b"\xff" * 0x40000)
    for index, data in rows.items():
        image[index * 256 : (index + 1) * 256] = data[:256]
    print("PASS vendor hash and 355 rows, no array-zero payload")
    return image


if __name__ == "__main__":
    main()
