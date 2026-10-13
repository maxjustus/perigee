"""Decode Ensemble format-3 resources offline. The image output requires Pillow."""

import argparse
import hashlib
import struct
from collections import namedtuple
from pathlib import Path

Asset = namedtuple("Asset", "kind width height frames offset")


def main():
    from PIL import Image, ImageDraw

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resource", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    blob = args.resource.read_bytes()
    assets = parse(blob)
    args.output.mkdir(parents=True, exist_ok=True)
    contact = Image.new("RGB", (6 * 168, ((len(assets) + 5) // 6) * 148), "#202020")
    labels = ImageDraw.Draw(contact)
    rows = ["id\ttype\twidth\theight\tframes\tfile_offset\tbytes"]
    for index, asset in enumerate(assets):
        strip = Image.new("RGB", (asset.width * asset.frames, asset.height))
        for frame in range(asset.frames):
            image = render(blob, asset, frame)
            image.save(args.output / f"asset-{index:02x}-{frame:02d}.png")
            strip.paste(image, (frame * asset.width, 0))
            if frame == 0:
                x, y = index % 6 * 168, index // 6 * 148
                labels.text(
                    (x + 4, y + 2),
                    f"{index:02X} {asset.width}x{asset.height} x{asset.frames}",
                    fill="white",
                )
                contact.paste(image, (x + 4, y + 20))
        if asset.frames > 1:
            strip.save(args.output / f"frames-{index:02x}.png")
        rows.append(
            f"{index:02x}\t{asset.kind}\t{asset.width}\t{asset.height}\t{asset.frames}\t"
            f"0x{asset.offset:x}\t{asset.width * asset.height * asset.frames * 2}"
        )
    contact.save(args.output / "contact.png")
    (args.output / "assets.tsv").write_text("\n".join(rows) + "\n")
    print(f"sha256={hashlib.sha256(blob).hexdigest()}")
    print(
        f"assets={len(assets)} frames={sum(asset.frames for asset in assets)} crc8=0x{crc8(blob):02x}"
    )


def parse(blob):
    if len(blob) < 20:
        raise ValueError("Resource header is incomplete")
    magic, version, _resource_version, count, data_offset, size, checksum = (
        struct.unpack_from("<4H3I", blob)
    )
    if magic != 0x4642 or version != 3:
        raise ValueError("Resource magic or format is unsupported")
    if size != len(blob) or data_offset != 20 + count * 8 or data_offset > size:
        raise ValueError("Resource size or index extent is invalid")
    if crc8(blob[:16] + blob[20:data_offset]) != checksum & 255:
        raise ValueError("Resource header and index checksum is invalid")
    assets = []
    expected = data_offset
    for index in range(count):
        kind, width, height, frames, relative = struct.unpack_from(
            "<4BI", blob, 20 + index * 8
        )
        if kind not in (1, 2) or not width or not height:
            raise ValueError(f"Resource {index} type or dimensions are invalid")
        if (kind == 1 and frames != 0) or (kind == 2 and frames == 0):
            raise ValueError(f"Resource {index} frame count is invalid")
        frames = max(1, frames)
        offset = data_offset + relative
        if offset != expected:
            raise ValueError(f"Resource {index} payload is not contiguous")
        expected += width * height * frames * 2
        if expected > size:
            raise ValueError(f"Resource {index} payload exceeds the file")
        assets.append(Asset(kind, width, height, frames, offset))
    if expected != size:
        raise ValueError("Resource payload does not fill the file")
    return assets


def crc8(data):
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ (7 if value & 128 else 0)) & 255
    return value


def render(blob, asset, frame):
    from PIL import Image

    if not 0 <= frame < asset.frames:
        raise ValueError("Frame index is outside the resource")
    size = asset.width * asset.height * 2
    offset = asset.offset + frame * size
    pixels = []
    for (value,) in struct.iter_unpack(">H", blob[offset : offset + size]):
        pixels.append(
            (
                (value >> 11) * 255 // 31,
                ((value >> 5) & 63) * 255 // 63,
                (value & 31) * 255 // 31,
            )
        )
    image = Image.new("RGB", (asset.width, asset.height))
    image.putdata(pixels)
    return image


if __name__ == "__main__":
    main()
