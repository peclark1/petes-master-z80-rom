#!/usr/bin/env python3
"""Native Ubuntu entry point for the IMSAI V5.6 source build.

The merged review source intentionally preserves a few historical/transcription
quirks from the byte-verified V5.6 package.  This wrapper applies only those
known compatibility corrections to a temporary source copy, then delegates all
assembly, ROM reconstruction, verification, and release work to
build_from_source.py.  z80asm remains the program that emits the Z80 machine
code.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import build_from_source as core


ORIGINAL_SOURCE = core.SOURCE


def prepare_source() -> str:
    """Return the merged source with the three verified V5.6 layout fixes."""
    text = ORIGINAL_SOURCE.read_text(encoding="latin-1")

    # HIGH page: the released image contains a RET immediately before the first
    # SDCONO body.  The merged review source omitted that one byte.
    needles = (
        "SDCONO:\tIN\tA,(CONSOL_STATUS)",
        "SDCONO:\tIN\tA,CONSOL_STATUS",
    )
    pos = next((text.find(needle) for needle in needles if text.find(needle) >= 0), -1)
    if pos < 0:
        raise RuntimeError("Could not locate the first high-page SDCONO routine")
    before = text[max(0, pos - 8) : pos].replace("\r\n", "\n")
    if not before.endswith("\tRET\n"):
        text = text[:pos] + "\tRET\n" + text[pos:]

    # LOW page: the review source has two surplus zero bytes in the menu pad.
    old_pad = "\t\tDB 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0\n\nMENUMSG:"
    new_pad = "\t\tDB 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0\n\nMENUMSG:"
    normalized = text.replace("\r\n", "\n")
    if old_pad in normalized:
        normalized = normalized.replace(old_pad, new_pad, 1)
    elif new_pad not in normalized:
        raise RuntimeError("Could not locate the low-page menu padding")

    # LOW page: the released menu terminator is CR,LF,CR,LF,'$'.
    old_tail = "DB\tCR,LF,'@=Flush Printer',CR,LF,LF,'$'"
    new_tail = "DB\tCR,LF,'@=Flush Printer',CR,LF,CR,LF,'$'"
    if old_tail in normalized:
        normalized = normalized.replace(old_tail, new_tail, 1)
    elif new_tail not in normalized:
        raise RuntimeError("Could not locate the low-page menu tail")

    return normalized


def install_assembler_compatibility() -> None:
    """Add the two Ubuntu-z80asm syntax rules proven by CI."""
    original_segment_normalizer = core.normalize_unquoted_segment

    def normalize_unquoted_segment(segment: str) -> str:
        segment = original_segment_normalizer(segment)
        # z80asm parses a hex literal beginning A-F as an identifier unless it
        # has a leading zero (for example D3H -> 0D3H).
        return re.sub(r"(?<![A-Z0-9_])([A-F][0-9A-F]*H)\b", r"0\1", segment)

    core.normalize_unquoted_segment = normalize_unquoted_segment

    original_page_normalizer = core.normalize_page

    def normalize_page(lines: list[str]):
        source, targets, markers = original_page_normalizer(lines)
        # z80asm requires a colon on this synthetic compatibility EQU label.
        source = source.replace(
            f"ERROR\tEQU\t0{core.LEGACY_ERROR_TARGET:04X}H",
            f"ERROR:\tEQU\t0{core.LEGACY_ERROR_TARGET:04X}H",
            1,
        )
        return source, targets, markers

    core.normalize_page = normalize_page


def main() -> int:
    install_assembler_compatibility()
    corrected = prepare_source()

    with tempfile.TemporaryDirectory(prefix="imsai-v56-native-") as temp_dir:
        temp_source = Path(temp_dir) / ORIGINAL_SOURCE.name
        temp_source.write_text(corrected, encoding="latin-1")
        core.SOURCE = temp_source
        return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
