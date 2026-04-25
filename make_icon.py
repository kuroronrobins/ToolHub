from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


BACKGROUND = (24, 96, 72, 255)
FOREGROUND = (255, 255, 255, 255)
SIZES = (16, 32, 48, 64, 128, 256)


def fill_rect(
    pixels: bytearray,
    size: int,
    left: int,
    top: int,
    right: int,
    bottom: int,
    color: tuple[int, int, int, int],
) -> None:
    left = max(0, min(size, left))
    right = max(0, min(size, right))
    top = max(0, min(size, top))
    bottom = max(0, min(size, bottom))
    if left >= right or top >= bottom:
        return

    red, green, blue, alpha = color
    for row in range(top, bottom):
        row_offset = row * size * 4
        for column in range(left, right):
            offset = row_offset + column * 4
            pixels[offset : offset + 4] = bytes((red, green, blue, alpha))


def render_icon(size: int) -> bytearray:
    pixels = bytearray(bytes(BACKGROUND) * size * size)

    border = max(1, size // 24)
    margin = max(1, size // 8)
    fill_rect(pixels, size, margin, margin, size - margin, margin + border, FOREGROUND)
    fill_rect(pixels, size, margin, size - margin - border, size - margin, size - margin, FOREGROUND)
    fill_rect(pixels, size, margin, margin, margin + border, size - margin, FOREGROUND)
    fill_rect(pixels, size, size - margin - border, margin, size - margin, size - margin, FOREGROUND)

    stroke = max(1, size // 10)
    top = size // 3
    bottom = size * 2 // 3
    t_left = size // 4
    t_right = size // 2 - max(1, size // 20)
    h_left = size // 2 + max(1, size // 20)
    h_right = size * 3 // 4

    fill_rect(pixels, size, t_left, top, t_right, top + stroke, FOREGROUND)
    t_center = (t_left + t_right) // 2
    fill_rect(pixels, size, t_center - stroke // 2, top, t_center + (stroke + 1) // 2, bottom, FOREGROUND)

    fill_rect(pixels, size, h_left, top, h_left + stroke, bottom, FOREGROUND)
    fill_rect(pixels, size, h_right - stroke, top, h_right, bottom, FOREGROUND)
    h_middle = (top + bottom) // 2
    fill_rect(pixels, size, h_left, h_middle - stroke // 2, h_right, h_middle + (stroke + 1) // 2, FOREGROUND)

    return pixels


def png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def encode_png(size: int, pixels: bytearray) -> bytes:
    raw_rows = bytearray()
    row_length = size * 4
    for row in range(size):
        raw_rows.append(0)
        start = row * row_length
        raw_rows.extend(pixels[start : start + row_length])

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            png_chunk(b"IHDR", header),
            png_chunk(b"IDAT", zlib.compress(bytes(raw_rows), level=9)),
            png_chunk(b"IEND", b""),
        ]
    )


def encode_ico(images: list[tuple[int, bytes]]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(images))
    directory = bytearray()
    image_offset = 6 + len(images) * 16

    for size, image_data in images:
        size_byte = 0 if size >= 256 else size
        directory.extend(
            struct.pack(
                "<BBBBHHII",
                size_byte,
                size_byte,
                0,
                0,
                1,
                32,
                len(image_data),
                image_offset,
            )
        )
        image_offset += len(image_data)

    return header + bytes(directory) + b"".join(image_data for _, image_data in images)


def generate_icons(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    images = [(size, encode_png(size, render_icon(size))) for size in SIZES]
    (output_dir / "icon.png").write_bytes(images[-1][1])
    (output_dir / "icon.ico").write_bytes(encode_ico(images))


def main() -> int:
    default_output = Path(__file__).resolve().parent / "launcher" / "src-tauri" / "icons"
    parser = argparse.ArgumentParser(description="Generate ToolHub Tauri icon assets.")
    parser.add_argument("--output-dir", type=Path, default=default_output)
    args = parser.parse_args()

    generate_icons(args.output_dir)
    print(args.output_dir / "icon.ico")
    print(args.output_dir / "icon.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
