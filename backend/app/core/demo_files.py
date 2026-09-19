"""Pembuat berkas contoh (PNG & PDF) tanpa dependensi tambahan.

Dipakai seeder untuk menyiapkan dokumen demo yang benar-benar dapat dipratinjau.
"""
import struct
import zlib
from typing import List, Tuple


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def png_bytes(
    width: int = 480,
    height: int = 300,
    background: Tuple[int, int, int] = (222, 235, 232),
    band: Tuple[int, int, int] = (17, 94, 89),
) -> bytes:
    """PNG valid sederhana: latar lembut dengan garis aksen di bagian atas."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0
        color = band if 24 <= y <= 72 else background
        raw.extend(bytes(color) * width)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _chunk(b"IEND", b"")
    )


def pdf_bytes(title: str, lines: List[str]) -> bytes:
    """PDF 1 halaman dengan xref yang benar agar bisa dibuka semua viewer."""
    text_lines = [title] + list(lines)
    content_parts = ["BT", "/F1 16 Tf", "60 720 Td", "20 TL"]
    for index, line in enumerate(text_lines):
        safe = line.replace("\\", "").replace("(", "").replace(")", "")
        if index == 1:
            content_parts.append("/F1 11 Tf")
        content_parts.append(f"({safe}) Tj")
        content_parts.append("T*")
    content_parts.append("ET")
    content = "\n".join(content_parts).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + body + b"\nendobj\n"

    xref_at = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_at).encode()
        + b"\n%%EOF\n"
    )
    return bytes(out)
