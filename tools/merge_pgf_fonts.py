"""Merge selected glyphs from one PSP PGF font into another.

The target font's tables and existing glyph data are preserved.  Added glyphs
are re-encoded with inline metrics and a simple valid PGF bitmap stream, so
they do not depend on the source font's metric tables.
"""

from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path


def aligned_table_bytes(count: int, bits_per_entry: int) -> int:
    return ((count * bits_per_entry + 31) // 32) * 4


def read_bits(data: bytes, bit_pos: int, count: int) -> tuple[int, int]:
    value = 0
    for i in range(count):
        value |= ((data[(bit_pos + i) // 8] >> ((bit_pos + i) % 8)) & 1) << i
    return value, bit_pos + count


def read_bit_table(data: bytes, offset: int, count: int, bits_per_entry: int) -> list[int]:
    table = data[offset : offset + aligned_table_bytes(count, bits_per_entry)]
    values: list[int] = []
    bit_pos = 0
    for _ in range(count):
        value, bit_pos = read_bits(table, bit_pos, bits_per_entry)
        values.append(value)
    return values


def write_bits(values: list[tuple[int, int]]) -> bytes:
    bit_count = sum(width for _value, width in values)
    output = bytearray((bit_count + 7) // 8)
    bit_pos = 0
    for value, width in values:
        for i in range(width):
            output[(bit_pos + i) // 8] |= ((value >> i) & 1) << ((bit_pos + i) % 8)
        bit_pos += width
    return bytes(output)


def write_bit_table(values: list[int], bits_per_entry: int) -> bytes:
    raw = bytearray(aligned_table_bytes(len(values), bits_per_entry))
    bit_pos = 0
    for value in values:
        if value < 0 or value >= (1 << bits_per_entry):
            raise ValueError(f"table value {value} does not fit in {bits_per_entry} bits")
        for i in range(bits_per_entry):
            raw[(bit_pos + i) // 8] |= ((value >> i) & 1) << ((bit_pos + i) % 8)
        bit_pos += bits_per_entry
    return bytes(raw)


def signed32(value: int) -> int:
    return value - (1 << 32) if value & (1 << 31) else value


def signed7(value: int) -> int:
    return value - 0x80 if value & 0x40 else value


@dataclass(frozen=True)
class GlyphRecord:
    size: int
    width: int
    height: int
    left: int
    top: int
    flags: int
    dimension: tuple[int, int]
    bearing_x: tuple[int, int]
    bearing_y: tuple[int, int]
    advance: tuple[int, int]
    pixels: tuple[int, ...]


class PGF:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        if len(self.data) < 0x188 or self.data[4:8] != b"PGF0":
            raise ValueError(f"not a PGF0 font: {path}")

        self.header_size = struct.unpack_from("<H", self.data, 2)[0]
        self.charmap_length, self.charptr_length, self.charmap_bpe, self.charptr_bpe = struct.unpack_from(
            "<iiii", self.data, 0x10
        )
        self.charmap_min, self.charmap_max = struct.unpack_from("<HH", self.data, 0xB6)
        self.charptr_scale = struct.unpack_from("<H", self.data, 0x100)[0]
        self.dimension_length = self.data[0x102]
        self.bearing_x_length = self.data[0x103]
        self.bearing_y_length = self.data[0x104]
        self.advance_length = self.data[0x105]
        self.shadowmap_length, self.shadowmap_bpe = struct.unpack_from("<ii", self.data, 0x16C)

        offset = self.header_size
        self.dimensions, offset = self._read_pairs(offset, self.dimension_length)
        self.bearing_x, offset = self._read_pairs(offset, self.bearing_x_length)
        self.bearing_y, offset = self._read_pairs(offset, self.bearing_y_length)
        self.advance, offset = self._read_pairs(offset, self.advance_length)
        offset += aligned_table_bytes(self.shadowmap_length, self.shadowmap_bpe)
        self.charmap_offset = offset
        self.charmap = read_bit_table(self.data, offset, self.charmap_length, self.charmap_bpe)
        offset += aligned_table_bytes(self.charmap_length, self.charmap_bpe)
        self.charptr_offset = offset
        self.charptr = read_bit_table(self.data, offset, self.charptr_length, self.charptr_bpe)
        offset += aligned_table_bytes(self.charptr_length, self.charptr_bpe)
        self.glyph_data_offset = offset
        self._glyph_cache: dict[int, GlyphRecord] = {}

    def _read_pairs(self, offset: int, count: int) -> tuple[list[tuple[int, int]], int]:
        pairs = [struct.unpack_from("<ii", self.data, offset + i * 8) for i in range(count)]
        return pairs, offset + count * 8

    def glyph_index(self, codepoint: int) -> int | None:
        pos = codepoint - self.charmap_min
        if pos < 0 or pos >= len(self.charmap):
            return None
        index = self.charmap[pos]
        if index >= len(self.charptr):
            return None
        return index

    def glyph(self, index: int) -> GlyphRecord:
        cached = self._glyph_cache.get(index)
        if cached is not None:
            return cached

        pointer = self.glyph_data_offset + self.charptr[index] * self.charptr_scale
        data = self.data[pointer:]
        bit_pos = 0
        fields: list[int] = []
        for width in (14, 7, 7, 7, 7, 6, 7, 9):
            value, bit_pos = read_bits(data, bit_pos, width)
            fields.append(value)

        size, glyph_width, glyph_height, left, top, flags, _shadow_flags, _shadow_id = fields
        left = signed7(left)
        top = signed7(top)

        metrics: list[tuple[int, int]] = []
        for flag, table in (
            (0x04, self.dimensions),
            (0x08, self.bearing_x),
            (0x10, self.bearing_y),
            (0x20, self.advance),
        ):
            if flags & flag:
                table_index, bit_pos = read_bits(data, bit_pos, 8)
                if table_index >= len(table):
                    raise ValueError(f"invalid metric table index {table_index} in {self.path}")
                metrics.append(table[table_index])
            else:
                first, bit_pos = read_bits(data, bit_pos, 32)
                second, bit_pos = read_bits(data, bit_pos, 32)
                metrics.append((signed32(first), signed32(second)))

        pixel_count = glyph_width * glyph_height
        stream: list[int] = []
        while len(stream) < pixel_count:
            run_code, bit_pos = read_bits(data, bit_pos, 4)
            if run_code < 8:
                value, bit_pos = read_bits(data, bit_pos, 4)
                stream.extend([value] * (run_code + 1))
            else:
                for _ in range(16 - run_code):
                    value, bit_pos = read_bits(data, bit_pos, 4)
                    stream.append(value)
        stream = stream[:pixel_count]

        if (flags & 3) == 2 and glyph_width and glyph_height:
            pixels = [0] * pixel_count
            pos = 0
            for x in range(glyph_width):
                for y in range(glyph_height):
                    pixels[y * glyph_width + x] = stream[pos]
                    pos += 1
        else:
            pixels = stream

        result = GlyphRecord(
            size,
            glyph_width,
            glyph_height,
            left,
            top,
            flags,
            metrics[0],
            metrics[1],
            metrics[2],
            metrics[3],
            tuple(pixels),
        )
        self._glyph_cache[index] = result
        return result


def encode_glyph(glyph: GlyphRecord) -> bytes:
    if not (-64 <= glyph.left <= 63 and -64 <= glyph.top <= 63):
        raise ValueError("glyph bearing does not fit in the PGF 7-bit signed field")

    # Use horizontal-row bitmap order and inline all four metric pairs.  This
    # makes the appended record independent of the source font's metric tables.
    fields: list[tuple[int, int]] = [
        (0, 14),  # size, filled below once the record length is known
        (glyph.width, 7),
        (glyph.height, 7),
        (glyph.left & 0x7F, 7),
        (glyph.top & 0x7F, 7),
        (1, 6),  # FONT_PGF_BMP_H_ROWS, all metrics inline
        (0, 7),  # no shadow
        (0, 9),  # no shadow
    ]
    for first, second in (glyph.dimension, glyph.bearing_x, glyph.bearing_y, glyph.advance):
        fields.extend(((first & 0xFFFFFFFF, 32), (second & 0xFFFFFFFF, 32)))

    # Find the shortest valid stream of four-bit PGF bitmap tokens.  A run
    # token (code 0..7) repeats one value 1..8 times; a literal token (code
    # 8..15) stores 8..1 individual pixels.  Dynamic programming matters for
    # in-place replacements because the original records have tight sizes.
    pixels = glyph.pixels
    infinity = 1 << 30
    best = [infinity] * (len(pixels) + 1)
    choice: list[tuple[str, int] | None] = [None] * (len(pixels) + 1)
    best[-1] = 0
    for position in range(len(pixels) - 1, -1, -1):
        run_limit = 1
        while (
            position + run_limit < len(pixels)
            and run_limit < 8
            and (pixels[position + run_limit] & 0xF) == (pixels[position] & 0xF)
        ):
            run_limit += 1
        for length in range(1, run_limit + 1):
            cost = 8 + best[position + length]
            if cost < best[position]:
                best[position] = cost
                choice[position] = ("run", length)
        for length in range(1, min(8, len(pixels) - position) + 1):
            cost = 4 + length * 4 + best[position + length]
            if cost < best[position]:
                best[position] = cost
                choice[position] = ("literal", length)

    position = 0
    while position < len(pixels):
        token_type, length = choice[position]  # type: ignore[misc]
        if token_type == "run":
            fields.append((length - 1, 4))
            fields.append((pixels[position] & 0xF, 4))
        else:
            fields.append((16 - length, 4))
            fields.extend((value & 0xF, 4) for value in pixels[position : position + length])
        position += length

    bit_count = sum(width for _value, width in fields)
    fields.extend(((0, 1),) * ((-bit_count) % 32))
    size_bytes = (sum(width for _value, width in fields) // 8)
    if size_bytes >= (1 << 14):
        raise ValueError(f"encoded glyph is too large: {size_bytes} bytes")
    fields[0] = (size_bytes, 14)
    return write_bits(fields)


def select_additions(
    target: PGF,
    source: PGF,
    codepoints: list[int] | None = None,
) -> list[tuple[int, int, GlyphRecord]]:
    additions: list[tuple[int, int, GlyphRecord]] = []
    if codepoints is None:
        codepoints = [
            codepoint
            for start, end in ((0x3130, 0x318F), (0xAC00, 0xD7A3))
            for codepoint in range(start, end + 1)
        ]
    for codepoint in sorted(set(codepoints)):
        source_index = source.glyph_index(codepoint)
        if source_index is None:
            continue
        glyph = source.glyph(source_index)
        if not glyph.width or not glyph.height:
            continue

        target_index = target.glyph_index(codepoint)
        if target_index is not None:
            existing = target.glyph(target_index)
            if existing.width and existing.height:
                continue
        additions.append((codepoint, source_index, glyph))
    return additions


def merge(
    target: PGF,
    source: PGF,
    output: Path,
    mapping_output: Path,
    codepoints: list[int] | None = None,
) -> tuple[int, int, int]:
    additions = select_additions(target, source, codepoints)
    if not additions:
        raise ValueError("no new non-empty glyphs selected")

    new_charmap = target.charmap[:]
    new_charptr = target.charptr[:]
    appended = bytearray()
    base_units = len(target.data) - target.glyph_data_offset
    if base_units % target.charptr_scale:
        raise ValueError("target glyph data is not aligned to charptr scale")
    cursor_units = base_units // target.charptr_scale

    mapping_lines = [
        "codepoint\tcharacter\ttarget_glyph_index\tsource_glyph_index\twidth\theight\tleft\ttop"
    ]
    for codepoint, source_index, glyph in additions:
        record = encode_glyph(glyph)
        if len(record) % target.charptr_scale:
            raise ValueError("encoded glyph is not aligned to target charptr scale")

        target_index = len(new_charptr)
        if cursor_units >= (1 << target.charptr_bpe):
            raise ValueError("new glyph data does not fit in the target charptr bit width")
        new_charptr.append(cursor_units)
        new_charmap[codepoint - target.charmap_min] = target_index
        appended.extend(record)
        cursor_units += len(record) // target.charptr_scale

        mapping_lines.append(
            f"U+{codepoint:04X}\t{chr(codepoint)}\t{target_index}\t{source_index}\t"
            f"{glyph.width}\t{glyph.height}\t{glyph.left}\t{glyph.top}"
        )

    new_charptr_bpe = max(target.charptr_bpe, max(new_charptr).bit_length())
    if new_charptr_bpe >= 31:
        raise ValueError("unsupported charptr bit width")
    if new_charptr_bpe != target.charptr_bpe:
        # Rebuilding the table is supported, but normal fonts stay at 19 bits.
        pass

    header = bytearray(target.data[: target.header_size])
    struct.pack_into("<i", header, 0x14, len(new_charptr))
    struct.pack_into("<i", header, 0x1C, new_charptr_bpe)
    metric_and_tables = target.data[target.header_size : target.charmap_offset]
    new_file = bytes(header)
    new_file += metric_and_tables
    new_file += write_bit_table(new_charmap, target.charmap_bpe)
    new_file += write_bit_table(new_charptr, new_charptr_bpe)
    new_file += target.data[target.glyph_data_offset :]
    new_file += appended

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(new_file)
    mapping_output.parent.mkdir(parents=True, exist_ok=True)
    mapping_output.write_text("\n".join(mapping_lines) + "\n", encoding="utf-8")

    return len(additions), len(new_charptr), len(new_file)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="original Japanese PGF")
    parser.add_argument("source", type=Path, help="Korean PGF providing Hangul glyphs")
    parser.add_argument("output", type=Path, help="merged PGF output")
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument(
        "--codepoint",
        action="append",
        type=lambda value: int(value, 0),
        help="add only this Unicode code point; repeat for a minimal test font",
    )
    parser.add_argument("--pack-input", type=Path)
    parser.add_argument("--pack-output", type=Path)
    args = parser.parse_args()

    target = PGF(args.target)
    source = PGF(args.source)
    added, glyph_count, file_size = merge(target, source, args.output, args.mapping, args.codepoint)

    if (args.pack_input is None) != (args.pack_output is None):
        parser.error("--pack-input and --pack-output must be specified together")
    if args.pack_input is not None and args.pack_output is not None:
        pack = args.pack_input.read_bytes()
        payload_start = pack.find(target.data[:8])
        if payload_start < 0 or pack[payload_start:] != target.data:
            raise ValueError("pack input does not contain the exact target PGF payload")
        merged_payload = args.output.read_bytes()
        args.pack_output.parent.mkdir(parents=True, exist_ok=True)
        args.pack_output.write_bytes(pack[:payload_start] + merged_payload)

    print(f"target: {args.target}")
    print(f"source: {args.source}")
    print(f"added non-empty glyphs: {added}")
    print(f"new glyph pointer count: {glyph_count}")
    print(f"merged PGF size: {file_size} bytes")
    print(f"output: {args.output}")
    print(f"mapping: {args.mapping}")
    if args.pack_output is not None:
        print(f"pack output: {args.pack_output}")


if __name__ == "__main__":
    main()
