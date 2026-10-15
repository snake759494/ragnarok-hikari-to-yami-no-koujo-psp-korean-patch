"""Read and rewrite the GIM textures that hold the game's UI wording.

The yes/no choice, the LOAD and SAVE title bars and the button hints are not
drawn from the font -- they are small pre-rendered images stored as GIM chunks
inside ``pack/static.dat``.  Translating them means editing pixels, so this
module decodes a GIM to a plain 8-bit indexed bitmap and writes one back into
the same bytes it came from.

GIM is a tree of ``(u16 type, u16 unused, u32 size, u32 next, u32 data)``
chunks: 0x02 root, 0x03 picture, 0x04 image, 0x05 palette.  PSP textures are
usually stored swizzled -- rearranged into 16-byte by 8-row blocks for the GPU --
so the pixels have to be put back in raster order before anything can be drawn.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


MAGIC = b"MIG.00.1PSP\x00"

# The magic is followed by four reserved bytes, so chunks start at 0x10.
HEADER = 16

ROOT, PICTURE, IMAGE, PALETTE = 0x02, 0x03, 0x04, 0x05

FORMAT_BPP = {0: 16, 1: 16, 2: 16, 3: 32, 4: 4, 5: 8, 6: 16, 7: 32}


@dataclass
class Chunk:
    kind: int
    start: int
    size: int
    data_offset: int


def chunks(blob: bytes, start: int, end: int):
    position = start
    while position + 16 <= end:
        kind, _pad, size, _next, data = struct.unpack_from("<HHIII", blob, position)
        if size < 16 or position + size > end:
            return
        yield Chunk(kind, position, size, data)
        position += size


def find_chunk(blob: bytes, kind: int) -> Chunk | None:
    """Depth-first search for the first chunk of ``kind``."""
    stack = [(HEADER, len(blob))]
    while stack:
        start, end = stack.pop()
        for chunk in chunks(blob, start, end):
            if chunk.kind == kind:
                return chunk
            if chunk.kind in (ROOT, PICTURE):
                stack.append((chunk.start + 16, chunk.start + chunk.size))
    return None


@dataclass
class Image:
    width: int
    height: int
    pitch: int
    rows: int
    bpp: int
    swizzled: bool
    pixel_offset: int
    pixels: bytearray          # raster order, one byte per pixel (INDEX8 only)
    palette: bytes


def unswizzle(data: bytes, pitch: int, rows: int) -> bytearray:
    """Undo the GPU's 16x8 block interleave."""
    out = bytearray(pitch * rows)
    blocks_per_row = pitch // 16
    for index in range(len(data) // 16):
        block = index // 8
        line = index % 8
        column = block % blocks_per_row
        band = block // blocks_per_row
        y = band * 8 + line
        if y >= rows:
            continue
        out[y * pitch + column * 16 : y * pitch + column * 16 + 16] = data[
            index * 16 : index * 16 + 16
        ]
    return out


def swizzle(raster: bytes, pitch: int, rows: int) -> bytearray:
    out = bytearray(pitch * rows)
    blocks_per_row = pitch // 16
    for index in range(len(out) // 16):
        block = index // 8
        line = index % 8
        column = block % blocks_per_row
        band = block // blocks_per_row
        y = band * 8 + line
        if y >= rows:
            continue
        out[index * 16 : index * 16 + 16] = raster[
            y * pitch + column * 16 : y * pitch + column * 16 + 16
        ]
    return out


def read(blob: bytes) -> Image:
    if not blob.startswith(MAGIC):
        raise ValueError("not a GIM texture")
    image = find_chunk(blob, IMAGE)
    if image is None:
        raise ValueError("GIM has no image chunk")
    header = image.start + 16
    (
        _header_size,
        _unused,
        image_format,
        pixel_order,
        width,
        height,
        bpp,
        pitch_align,
        height_align,
    ) = struct.unpack_from("<HHHHHHHHH", blob, header)
    if image_format != 5:
        raise ValueError(f"unsupported GIM format {image_format}; only INDEX8 is handled")

    pitch = (width * bpp // 8 + pitch_align - 1) // pitch_align * pitch_align
    rows = (height + height_align - 1) // height_align * height_align
    # The chunk's data field points at the image header, and the header carries
    # its own offset to the pixels at +0x1C.  That is 16 bytes past the end of
    # the header proper -- using the header size instead shifts every read and
    # write by one swizzle block, which scrambles one row in every eight.
    pixel_offset = image.start + image.data_offset + struct.unpack_from("<I", blob, header + 0x1C)[0]
    raw = blob[pixel_offset : pixel_offset + pitch * rows]
    pixels = unswizzle(raw, pitch, rows) if pixel_order else bytearray(raw)

    palette = b""
    chunk = find_chunk(blob, PALETTE)
    if chunk is not None:
        palette_offset = (
            chunk.start
            + chunk.data_offset
            + struct.unpack_from("<I", blob, chunk.start + 16 + 0x1C)[0]
        )
        palette = blob[palette_offset : chunk.start + chunk.size]

    return Image(width, height, pitch, rows, bpp, bool(pixel_order), pixel_offset, pixels, palette)


def write(blob: bytes, image: Image) -> bytes:
    """Put ``image.pixels`` back, keeping every byte of layout identical."""
    raw = swizzle(image.pixels, image.pitch, image.rows) if image.swizzled else image.pixels
    if len(raw) != image.pitch * image.rows:
        raise ValueError("pixel buffer has the wrong size")
    return blob[: image.pixel_offset] + bytes(raw) + blob[image.pixel_offset + len(raw) :]


def rgba(palette: bytes, index: int) -> tuple[int, int, int, int]:
    """Palette entries are straight RGBA8888.

    Alpha really does span 0-255 here -- the game's own palettes reach 255 and
    fill the range smoothly.  Treating it as the 0-128 scale some PSP formats
    use doubles every partial value and clips the top half flat, which quietly
    wrecks both previews and any nearest-colour matching done against them.
    """
    if (index + 1) * 4 > len(palette):
        return (0, 0, 0, 0)
    r, g, b, a = palette[index * 4 : index * 4 + 4]
    return r, g, b, a


def texture_names(container: bytes) -> list[tuple[int, str]]:
    """Every GIM in a pack file, as ``(offset, name)``."""
    found: list[tuple[int, str]] = []
    position = container.find(MAGIC)
    while position >= 0:
        end = position
        while end > 0 and container[end - 1] == 0:
            end -= 1
        start = end
        while start > 0 and container[start - 1] != 0:
            start -= 1
        try:
            name = container[start:end].decode("shift_jis")
        except UnicodeDecodeError:
            name = ""
        found.append((position, name))
        position = container.find(MAGIC, position + 1)
    return found


@dataclass
class Placement:
    start: int      # first byte of the record
    across: int     # position along the axis the texture's rows run down
    along: int      # position along the axis the texture's columns run across
    size: int       # the GIM's byte length, as the record claims it


PLACEMENT_FLAG = 0x10


def placement(container: bytes, offset: int) -> Placement:
    """The screen position recorded for the GIM at ``offset``.

    Each texture in a packed file is introduced by a 32-byte record: two
    placement coordinates, a constant 0x10, the GIM's byte length, then the
    name the GIM is stored under.  The length is what makes the record
    self-checking -- read it at the wrong place and it will not match the
    texture, so a caller that moves artwork around cannot silently corrupt the
    file instead.
    """
    end = offset
    while end > 0 and container[end - 1] == 0:
        end -= 1
    start = end
    while start > 0 and container[start - 1] != 0:
        start -= 1
    start -= 16
    if start < 0:
        raise ValueError(f"@{offset:07X}: no room for a placement record")
    across, along, flag, size = struct.unpack_from("<IIII", container, start)
    if flag != PLACEMENT_FLAG:
        raise ValueError(f"@{offset:07X}: placement record has flag {flag:#x}")
    return Placement(start, across, along, size)


def check_placement(container: bytes, offset: int, image: Image) -> Placement:
    """``placement`` plus the length check the record exists to make possible."""
    found = placement(container, offset)
    expected = image.pitch * image.rows + len(image.palette) + 208
    if found.size != expected:
        raise ValueError(
            f"@{offset:07X}: record claims {found.size} bytes, texture is {expected}"
        )
    return found


def move(buffer: bytearray, record_start: int, along: int) -> None:
    """Rewrite one placement record's along-axis coordinate, in place.

    ``record_start`` is the record's position in ``buffer``, which need not be
    the packed file the record was read from -- callers usually hold the whole
    ISO and add the file's own offset.
    """
    if along < 0:
        raise ValueError("placement coordinates are unsigned")
    struct.pack_into("<I", buffer, record_start + 4, along)


def extent(blob: bytes, start: int) -> int:
    """Total byte length of the GIM beginning at ``start``."""
    kind, _pad, size, _next, _data = struct.unpack_from("<HHIII", blob, start + HEADER)
    if kind != ROOT:
        raise ValueError("GIM does not start with a root chunk")
    return HEADER + size
