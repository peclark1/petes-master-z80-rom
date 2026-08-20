#!/usr/bin/env python3
"""Static verification for the IMSAI Monitor V5.6 target ROM."""

from __future__ import annotations

import hashlib
from pathlib import Path

import build_imsai_rom as build


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"


def parse_intel_hex(text: str) -> bytes:
    memory: dict[int, int] = {}
    upper = 0
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        record = bytes.fromhex(line[1:])
        assert sum(record) & 0xFF == 0, f"HEX checksum failure line {line_number}"
        count = record[0]
        address = (record[1] << 8) | record[2]
        kind = record[3]
        payload = record[4 : 4 + count]
        if kind == 0:
            for index, value in enumerate(payload):
                memory[upper + address + index] = value
        elif kind == 1:
            break
        elif kind == 4:
            upper = int.from_bytes(payload, "big") << 16
        else:
            raise AssertionError(f"Unsupported HEX record type {kind:02X}")
    return bytes(memory[index] for index in range(max(memory) + 1))


def main() -> None:
    low = (OUTPUT / "IMSAI_MONITOR_V5.6_TARGET_LOW_4K.BIN").read_bytes()
    high = (OUTPUT / "IMSAI_MONITOR_V5.6_TARGET_HIGH_4K.BIN").read_bytes()
    combined = (OUTPUT / "IMSAI_MONITOR_V5.6_TARGET_28C64_8K.BIN").read_bytes()
    hex_bytes = parse_intel_hex(
        (OUTPUT / "IMSAI_MONITOR_V5.6_TARGET_28C64_8K.HEX").read_text(encoding="ascii")
    )

    assert len(low) == len(high) == 4096
    assert len(combined) == 8192
    assert combined == low + high == hex_bytes

    # Validated V2 CPU banking mechanism and forced Console I/O selection.
    assert low[0x078:0x07C] == bytes.fromhex("3E 06 D3 D3")
    assert high[0x07C:0x07F] == bytes.fromhex("C3 86 F0")
    assert high[0x07F:0x083] == bytes.fromhex("3E 04 D3 D3")
    assert low[0x11D:0x123] == bytes.fromhex("3E 00 32 5E 00 CD")
    assert low[0x2CD:0x2D3] == bytes.fromhex("3A 5E 00 1F 30 05")
    assert high[0x0AA:0x0B0] == bytes.fromhex("3A 5E 00 1F 30 05")

    # Startup now enters the automatic boot countdown after IDE init.
    assert low[0x174:0x178] == bytes.fromhex("C3 93 F9 00")
    assert b"IDE/CF AUTO BOOT IN 3 SECONDS" in low
    assert b"PRESS ANY KEY FOR MONITOR" in low

    target_code, labels = build.build_low_target_routines()
    assert low[0x993 : 0x993 + len(target_code)] == target_code
    table = {
        0x08A: labels["boot_menu"],
        0x08C: labels["fdc_boot"],
        0x096: labels["hardware_request"],
        0x09E: build.LOW_MENU_ERROR,
        0x0A4: build.LOW_MENU_ERROR,
        0x0B4: build.LOW_MENU_ERROR,
    }
    for offset, target in table.items():
        assert int.from_bytes(low[offset : offset + 2], "little") == target
    assert low[0x2A0:0x2A3] == bytes.fromhex("CA 7D F3")  # Ctrl-C -> IDE/CF
    for vector_offset in (0x067, 0x076):
        assert int.from_bytes(low[vector_offset : vector_offset + 2], "little") == labels["fdc_boot"]

    # The retired CP/M 1.4 table and old boot implementation are absent.
    assert low[0x800:0x842] == bytes(0x42)
    assert low[0x0DD:0x0DF] == bytes(2)      # no auxiliary CPU switch write
    assert low[0x0F3:0x0F7] == bytes(4)      # no Versafloppy select write
    assert low[0x0FB:0x101] == bytes(6)      # no VF/ZFDC reset writes
    assert low[0x101:0x111] == bytes(16)     # no old 8259/8086 PIC setup
    for obsolete in (b"ZFDC", b"VERSAFLOPPY", b"68000", b"8086"):
        assert obsolete not in low.upper()

    menu = low[0xCA9:0xD99]
    for required in (b"B=Boot Menu", b"C=Altair FDC+", b"H=Hardware", b"P=CP/M IDE/CF"):
        assert required in menu
    for obsolete in (b"CPM(V)", b"ZFDC", b"68000", b"8086"):
        assert obsolete not in menu.upper()

    # High-page service dispatch: XMODEM, banner, CDBL, hardware status.
    assert high[0x8C0:0x8D8] == bytes.fromhex(
        "7A FE 01 CA 53 F2 FE 02 CA 27 F6 FE 03 CA 00 FF FE 04 CA 00 F9 C3 8F F0"
    )
    config = build.build_high_config_status()
    assert high[0x900 : 0x900 + len(config)] == config
    assert b"HARDWARE / BUILD CONFIGURATION" in high
    assert b"ALTAIR FDC+ @ 08H-0AH" in high
    assert b"P39 7-8" in high

    # Exact published CDBL bytes occupy the high-page FF00H boot address.
    cdbl = build.parse_cdbl_hex()
    assert len(cdbl) == 256
    assert high[0xF00:0x1000] == cdbl
    assert cdbl[:4] == bytes.fromhex("F3 11 F5 FF")
    assert cdbl[0xDF:0xE2] == bytes.fromhex("D2 00 00")  # JNC 0000H
    assert cdbl[0xF2:0xF5] == bytes.fromhex("C3 D6 4C")

    merged_source = (ROOT / "IMSAI_MONITOR_V5.6_TARGET_MERGED.z80").read_text(
        encoding="latin-1"
    )
    for required in (
        "TARGET_AUTO_BOOT",
        "TARGET_FDC_BOOT",
        "IMSAI_HARDWARE_STATUS",
        "IMSAI_CDBL",
    ):
        assert required in merged_source
    for obsolete in ("ZFDC", "VERSAFLOPPY", "SWITCH_8086", "SWITCH_68K", "RUN_CPM14"):
        assert obsolete not in merged_source.upper()

    digest = hashlib.sha256(combined).hexdigest()
    print("IMSAI Monitor V5.6 target verification passed")
    print("  bank switching: validated F078H/F07FH mechanism")
    print("  console: forced Console I/O ports 00H/01H")
    print("  auto boot: IDE/CF, three-second cancelable countdown")
    print("  boot menu: IDE/CF, Altair FDC+, monitor")
    print("  CDBL: exact 256-byte high-page image at FF00H")
    print("  removed: DSI, CP/M 1.4 table, Versafloppy, ZFDC, 8086, 68000")
    print(f"  combined SHA-256: {digest}")


if __name__ == "__main__":
    main()
