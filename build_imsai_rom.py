#!/usr/bin/env python3
"""Build the IMSAI 8080 Monitor V5.6 target ROM images.

This applies verified patches to the supplied V5.4 4K bank images.  The
validated V5.5G paging and Console I/O work is retained, obsolete processor
and floppy boot paths are reclaimed, and the high page gains Martin
Eberhard's 256-byte CDBL Altair floppy boot loader at FF00H.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT / "original"
OUTPUT = ROOT / "output"
THIRD_PARTY = ROOT / "third_party"

LOW_INPUT = ORIGINAL / "MASTER0_V5.4_NO_IOBYTE_4K.BIN"
HIGH_INPUT = ORIGINAL / "MASTER1_V5.4_NO_IOBYTE_4K.BIN"

EXPECTED_LOW_SHA256 = "3868bb5818b69f8ee04a50c0b3bf10229c71c7eba616e8d8341856df6a7d92f6"
EXPECTED_HIGH_SHA256 = "4439a858a883224ce10040656fa2b8d31d1a885672cbd51553d680f1d63775b0"

ROM_BASE = 0xF000
CONSOLE_SELECTOR = 0x005E
BANK_RETURN_FLAG = 0x005F

# Console-selection build options.  The current Z80 CPU has no IMSAI CP-A
# ribbon connector, so this release deliberately does not sample port FFH.
# Set USE_FRONT_PANEL_SWITCHES to True after installing a CPU board that
# provides the original IMSAI programmed-input path.
USE_FRONT_PANEL_SWITCHES = False
FORCED_CONSOLE_SELECTOR = 0x00  # bit 0: 0=Console I/O, 1=Serial I/O port A

HIGH_PRINT_STRING = 0xF21F
HIGH_LADR = 0xF237
HIGH_LBYTE = 0xF23C
HIGH_ROUTINE = 0xF627
HIGH_DISPATCH = 0xF8C0
HIGH_CONFIG_STATUS = 0xF900
HIGH_CDBL = 0xFF00
ORIGINAL_HIGH_ENTRY = 0xF078
ORIGINAL_LOW_RETURN = 0xF07F
LOW_RETURN_DISPATCH = 0xF75C

LOW_TARGET_ROUTINES = 0xF993
LOW_TARGET_END = 0xFC69

LOW_PRINT_STRING = 0xF1B0
LOW_CI = 0xF333
LOW_CO = 0xF2CD
LOW_CSTS = 0xF31E
LOW_START = 0xF178
LOW_IDE_BOOT = 0xF37D
LOW_MENU_ERROR = 0xF0C1


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def addr_offset(address: int) -> int:
    if not ROM_BASE <= address <= 0xFFFF:
        raise ValueError(f"Address outside ROM window: {address:04X}H")
    return address - ROM_BASE


def patch(image: bytearray, address: int, expected: bytes, replacement: bytes) -> None:
    if len(expected) != len(replacement):
        raise ValueError(f"Patch length mismatch at {address:04X}H")
    offset = addr_offset(address)
    actual = bytes(image[offset : offset + len(expected)])
    if actual != expected:
        raise RuntimeError(
            f"Unexpected bytes at {address:04X}H: "
            f"expected {expected.hex(' ')}, found {actual.hex(' ')}"
        )
    image[offset : offset + len(replacement)] = replacement


class Code:
    def __init__(self, origin: int):
        self.origin = origin
        self.data = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[str, int, str]] = []

    @property
    def pc(self) -> int:
        return self.origin + len(self.data)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"Duplicate label: {name}")
        self.labels[name] = self.pc

    def emit(self, *values: int) -> None:
        self.data.extend(v & 0xFF for v in values)

    def word(self, value: int) -> None:
        self.emit(value, value >> 8)

    def abs16(self, opcode: int, target: int | str) -> None:
        self.emit(opcode)
        if isinstance(target, str):
            self.fixups.append(("abs16", len(self.data), target))
            self.word(0)
        else:
            self.word(target)

    def jr(self, opcode: int, target: str) -> None:
        self.emit(opcode)
        self.fixups.append(("rel8", len(self.data), target))
        self.emit(0)

    def string(self, name: str, value: str) -> None:
        self.label(name)
        self.data.extend(value.encode("ascii"))

    def resolve(self) -> bytes:
        for kind, position, label in self.fixups:
            if label not in self.labels:
                raise ValueError(f"Undefined label: {label}")
            target = self.labels[label]
            if kind == "abs16":
                self.data[position] = target & 0xFF
                self.data[position + 1] = target >> 8
            else:
                instruction_end = self.origin + position + 1
                displacement = target - instruction_end
                if not -128 <= displacement <= 127:
                    raise ValueError(f"Relative branch out of range: {label}")
                self.data[position] = displacement & 0xFF
        return bytes(self.data)


def parse_cdbl_hex() -> bytes:
    """Return the FF00H-FFFFH CDBL image, zero-filling its unused tail."""
    memory = bytearray(256)
    for raw in (THIRD_PARTY / "CDBL.HEX").read_text(encoding="ascii").splitlines():
        line = raw.strip()
        if not line:
            continue
        record = bytes.fromhex(line[1:])
        if sum(record) & 0xFF:
            raise RuntimeError("CDBL.HEX checksum failure")
        count = record[0]
        address = (record[1] << 8) | record[2]
        kind = record[3]
        if kind != 0 or count == 0:
            continue
        if not 0xFF00 <= address <= 0xFFFF:
            raise RuntimeError(f"CDBL record outside FF00H page: {address:04X}H")
        start = address - 0xFF00
        memory[start : start + count] = record[4 : 4 + count]
    if memory[:4] != bytes.fromhex("F3 11 F5 FF"):
        raise RuntimeError("Unexpected CDBL entry bytes")
    if memory[0xF2:0xF5] != bytes.fromhex("C3 D6 4C"):
        raise RuntimeError("Unexpected CDBL error-loop bytes")
    return bytes(memory)


def build_low_target_routines() -> tuple[bytes, dict[str, int]]:
    """Build auto boot, boot menu, and high-page service request stubs."""
    c = Code(LOW_TARGET_ROUTINES)

    c.label("auto_boot")
    c.abs16(0x21, "auto_msg")              # LD HL,auto_msg
    c.abs16(0xCD, LOW_PRINT_STRING)
    c.emit(0x06, 0x03)                     # LD B,3
    c.label("countdown")
    c.emit(0x78, 0xC6, ord("0"), 0x4F)    # LD A,B / ADD A,'0' / LD C,A
    c.abs16(0xCD, LOW_CO)
    c.emit(0x16, 0x03)                     # LD D,3; ~one second at 10 MHz
    c.label("delay_outer")
    c.emit(0x21, 0xFF, 0xFF)               # LD HL,FFFFH
    c.label("delay_inner")
    c.abs16(0xCD, LOW_CSTS)
    c.jr(0x20, "cancel")                  # JR NZ,cancel
    c.emit(0x2B, 0x7C, 0xB5)               # DEC HL / LD A,H / OR L
    c.jr(0x20, "delay_inner")
    c.emit(0x15)                           # DEC D
    c.jr(0x20, "delay_outer")
    c.emit(0x0E, ord(" "))                # LD C,' '
    c.abs16(0xCD, LOW_CO)
    c.jr(0x10, "countdown")               # DJNZ countdown
    c.abs16(0x21, "ide_msg")
    c.abs16(0xCD, LOW_PRINT_STRING)
    c.emit(0x21, LOW_START & 0xFF, LOW_START >> 8, 0xE5)  # dummy PUSH
    c.abs16(0xC3, LOW_IDE_BOOT)

    c.label("cancel")
    c.abs16(0xCD, LOW_CI)                  # consume interrupting key
    c.abs16(0x21, "monitor_msg")
    c.abs16(0xCD, LOW_PRINT_STRING)
    c.abs16(0xC3, LOW_START)

    c.label("boot_menu")
    c.abs16(0x21, "boot_menu_msg")
    c.abs16(0xCD, LOW_PRINT_STRING)
    c.label("boot_menu_wait")
    c.abs16(0xCD, LOW_CI)
    c.emit(0xE6, 0x5F)                     # AND 5FH (uppercase)
    c.emit(0xFE, ord("I"))
    c.abs16(0xCA, LOW_IDE_BOOT)            # JP Z,IDE
    c.emit(0xFE, ord("F"))
    c.abs16(0xCA, "fdc_boot")
    c.emit(0xFE, ord("M"))
    c.emit(0xC8)                           # RET Z through monitor's START frame
    c.abs16(0xC3, "boot_menu_wait")

    c.label("fdc_boot")
    c.abs16(0x21, "fdc_msg")
    c.abs16(0xCD, LOW_PRINT_STRING)
    c.emit(0x16, 0x03)                     # D=3: CDBL service
    c.abs16(0xC3, ORIGINAL_HIGH_ENTRY)

    c.label("hardware_request")
    c.emit(0x16, 0x04)                     # D=4: config/status service
    c.abs16(0xC3, ORIGINAL_HIGH_ENTRY)

    c.string(
        "auto_msg",
        "\r\nIDE/CF AUTO BOOT IN 3 SECONDS - PRESS ANY KEY FOR MONITOR\r\n$",
    )
    c.string("ide_msg", "\r\nBOOTING CP/M FROM IDE/CF...\r\n$")
    c.string("monitor_msg", "\r\nAUTO BOOT CANCELLED - MONITOR ACTIVE\r\n$")
    c.string(
        "boot_menu_msg",
        "\r\nBOOT: [I] IDE/CF  [F] ALTAIR FDC+  [M] MONITOR : $",
    )
    c.string("fdc_msg", "\r\nBOOTING ALTAIR FDC+ WITH CDBL...\r\n$")

    result = c.resolve()
    if LOW_TARGET_ROUTINES + len(result) > LOW_TARGET_END + 1:
        raise RuntimeError("Target routines exceed reclaimed low-page region")
    return result, dict(c.labels)


def build_high_config_status() -> bytes:
    """Build the high-page, build-time hardware configuration/status block."""
    c = Code(HIGH_CONFIG_STATUS)
    c.abs16(0x21, "config_msg")
    c.abs16(0xCD, HIGH_PRINT_STRING)
    c.emit(0x3E, 0xA6)                     # tagged return to command caller
    c.emit(0x32, BANK_RETURN_FLAG & 0xFF, BANK_RETURN_FLAG >> 8)
    c.abs16(0xC3, ORIGINAL_LOW_RETURN)
    c.string(
        "config_msg",
        "\r\nHARDWARE / BUILD CONFIGURATION\r\n"
        "  SYSTEM : IMSAI 8080\r\n"
        "  CPU    : S100 Z80 V2; 8K BANKED ROM @ F000H; P39 7-8\r\n"
        "  CONSOLE: CONSOLE I/O @ 00H/01H (BUILD SELECTED)\r\n"
        "  SERIAL : S100 SERIAL I/O PORT A @ A1H/A3H, 38400 8N1\r\n"
        "  STORAGE: DUAL IDE/CF @ 30H-34H\r\n"
        "           ALTAIR FDC+ @ 08H-0AH; CDBL @ HIGH-PAGE FF00H\r\n"
        "  PANEL  : NOT CONNECTED TO CURRENT Z80 CPU\r\n"
        "  DEFAULT: IDE/CF AUTO BOOT; ANY KEY CANCELS\r\n$",
    )
    return c.resolve()


def build_high_banner() -> bytes:
    c = Code(HIGH_ROUTINE)

    # Decorative cold-start banner.
    c.abs16(0x21, "banner")          # LD HL,banner
    c.abs16(0xCD, HIGH_PRINT_STRING)  # CALL HIGH_PRINT_STRING

    # Detected RAM top, retained in IX by the low-bank startup probe.
    c.abs16(0x21, "ram_top")
    c.abs16(0xCD, HIGH_PRINT_STRING)
    c.emit(0xDD, 0xE5)                # PUSH IX
    c.emit(0xE1)                      # POP HL
    c.abs16(0xCD, HIGH_LADR)
    c.abs16(0x21, "hex_line_end")
    c.abs16(0xCD, HIGH_PRINT_STRING)

    if USE_FRONT_PANEL_SWITCHES:
        # Front-panel switch headings and the programmed-input byte.
        c.abs16(0x21, "switch_heading")
        c.abs16(0xCD, HIGH_PRINT_STRING)
        c.emit(0x3A, CONSOLE_SELECTOR & 0xFF, CONSOLE_SELECTOR >> 8)
        c.emit(0x06, 0x08)            # LD B,8

        c.label("switch_loop")
        c.emit(0x07)                  # RLCA: switch 15 first, switch 08 last
        c.emit(0xF5)                  # PUSH AF
        c.abs16(0x21, "off_token")
        c.jr(0x30, "print_switch")   # JR NC,print_switch
        c.abs16(0x21, "on_token")
        c.label("print_switch")
        c.abs16(0xCD, HIGH_PRINT_STRING)
        c.emit(0xF1)                  # POP AF
        c.jr(0x10, "switch_loop")    # DJNZ switch_loop

        c.abs16(0x21, "hex_prefix")
        c.abs16(0xCD, HIGH_PRINT_STRING)
        c.emit(0x3A, CONSOLE_SELECTOR & 0xFF, CONSOLE_SELECTOR >> 8)
        c.abs16(0xCD, HIGH_LBYTE)
        c.abs16(0x21, "hex_suffix")
        c.abs16(0xCD, HIGH_PRINT_STRING)
    else:
        c.abs16(0x21, "front_panel_unavailable")
        c.abs16(0xCD, HIGH_PRINT_STRING)

    # Bit 0 / physical switch 08 selects the console.
    c.emit(0x3A, CONSOLE_SELECTOR & 0xFF, CONSOLE_SELECTOR >> 8)
    c.emit(0x1F)                      # RRA: bit 0 -> carry
    c.abs16(0x21, "serial_console")
    c.jr(0x38, "print_console")      # JR C,print_console
    c.abs16(0x21, "console_io")
    c.label("print_console")
    c.abs16(0xCD, HIGH_PRINT_STRING)

    # Mark this as the cold-banner return before using the original switch.
    # The normal XMODEM service may freely alter D, so return dispatch must not
    # depend on D still containing its request number.
    c.emit(0x3E, 0xA5)                # LD A,A5H
    c.emit(0x32, BANK_RETURN_FLAG & 0xFF, BANK_RETURN_FLAG >> 8)
    c.abs16(0xC3, ORIGINAL_LOW_RETURN)  # JP original high-to-low switch

    c.string(
        "banner",
        "\r\n"
        "  .----------------------------------------------------------------.\r\n"
        "  |  o o o o o o o o       I M S A I   8 0 8 0                   |\r\n"
        "  |  o o o o o o o o    o o o o o o o o o o o o o o o o         |\r\n"
        "  |  / / / / / / / /    / / / / / / / /    [ RUN ] [ STOP ]     |\r\n"
        "  '----------------------------------------------------------------'\r\n"
        "                 IMSAI 8080 MONITOR @ F000H\r\n$",
    )
    c.string("ram_top", "\r\nRAM TOP: $")
    c.string("hex_line_end", "H\r\n$")
    if USE_FRONT_PANEL_SWITCHES:
        c.string(
            "switch_heading",
            "FRONT PANEL:  15  14  13  12  11  10  09  08\r\n"
            "              $",
        )
        c.string("off_token", "OFF $")
        c.string("on_token", "ON  $")
        c.string("hex_prefix", "  [$")
        c.string("hex_suffix", "H]\r\n$")
    else:
        c.string(
            "front_panel_unavailable",
            "FRONT PANEL: NOT CONNECTED - CONSOLE SET AT BUILD TIME\r\n$",
        )
    c.string("serial_console", "CONSOLE: SERIAL I/O PORT A - 38400 8N1\r\n$")
    c.string("console_io", "CONSOLE: CONSOLE I/O BOARD - PORTS 00H/01H\r\n$")

    result = c.resolve()
    if HIGH_ROUTINE + len(result) > HIGH_DISPATCH:
        raise RuntimeError("High-bank banner overlaps its request dispatcher")
    return result


def intel_hex(data: bytes, record_size: int = 16) -> str:
    lines: list[str] = []
    for address in range(0, len(data), record_size):
        chunk = data[address : address + record_size]
        record = bytearray([len(chunk), address >> 8, address & 0xFF, 0x00])
        record.extend(chunk)
        checksum = (-sum(record)) & 0xFF
        lines.append(":" + record.hex().upper() + f"{checksum:02X}")
    lines.append(":00000001FF")
    return "\n".join(lines) + "\n"


def main() -> None:
    low = bytearray(LOW_INPUT.read_bytes())
    high = bytearray(HIGH_INPUT.read_bytes())
    if len(low) != 4096 or len(high) != 4096:
        raise RuntimeError("Expected two 4096-byte ROM bank images")

    # Verify that this builder is operating on the exact supplied images.
    # The hashes are updated by --initialize-hashes during project creation.
    if EXPECTED_LOW_SHA256 != "INITIALIZE" and sha256(low) != EXPECTED_LOW_SHA256:
        raise RuntimeError(f"Unexpected low-bank SHA-256: {sha256(low)}")
    if EXPECTED_HIGH_SHA256 != "INITIALIZE" and sha256(high) != EXPECTED_HIGH_SHA256:
        raise RuntimeError(f"Unexpected high-bank SHA-256: {sha256(high)}")

    # Remove the pre-console direct '#': output must follow switch 08 selection.
    patch(low, 0xF0D3, bytes.fromhex("3E 23 D3 01"), bytes.fromhex("00 00 00 00"))

    # Retire startup side effects for hardware that is not in the target:
    # auxiliary CPU bus switching, Versafloppy, ZFDC, and the 8259 PIC used by
    # the old 8086 arrangement.  Address-preserving NOPs keep all later code
    # and the matched bank-switch locations stable.
    patch(low, 0xF0DD, bytes.fromhex("D3 EE"), bytes(2))
    patch(low, 0xF0F3, bytes.fromhex("3E FF D3 53"), bytes(4))
    patch(low, 0xF0FB, bytes.fromhex("3E FF D3 50 D3 13"), bytes(6))
    patch(
        low,
        0xF101,
        bytes.fromhex("3E 17 D3 20 3E 08 D3 21 3E 03 D3 21 3E FF D3 21"),
        bytes(16),
    )

    # Initialize the private bank-return flag using an otherwise cosmetic LED
    # progress write immediately before the customized startup block.
    patch(low, 0xF119, bytes.fromhex("3E C0 D3 05"), bytes.fromhex("AF 32 5F 00"))

    # Cold-start setup: load the build-selected console byte (or, on a future
    # compatible CPU, latch port FFH), initialize both SCC channels and the
    # 8255, then jump to banner service D=2 through the exact F078H/F07FH
    # switching path used by the original V5.4 XMODEM service.  The low-bank
    # dispatcher resumes explicitly at F131H; no CALL/RET crosses a ROM bank.
    selector_load = (
        bytes.fromhex("DB FF")
        if USE_FRONT_PANEL_SWITCHES
        else bytes((0x3E, FORCED_CONSOLE_SELECTOR & 0x01))
    )
    patch(
        low,
        0xF11D,
        bytes.fromhex(
            "21 6A FC CD B0 F1 CD 27 F7 CD 32 F7 3E 98 D3 AB 3E E0 D3 05"
        ),
        selector_load
        + bytes.fromhex(
            "32 5E 00 CD 27 F7 CD 32 F7 3E 98 D3 AB 16 02 C3 78 F0"
        ),
    )

    # The original upper-to-lower transition fetches its next opcode at F083H.
    # Route that through a tiny low-bank dispatcher.  Only the A5H flag set by
    # the banner continues at F131H; original services such as
    # XMODEM go to monitor START regardless of how they changed register D.
    patch(low, 0xF083, bytes.fromhex("C3 78 F1"), bytes.fromhex("C3 5C F7"))
    low_return_dispatch = bytes.fromhex(
        "3A 5F 00"      # LD A,(BANK_RETURN_FLAG)
        " FE A5"        # CP A5H (cold banner return)
        " CA 6E F7"     # JP Z,cold_banner_return
        " FE A6"        # CP A6H (hardware-status command return)
        " C2 78 F1"     # JP NZ,START for original high-bank services
        " AF"           # XOR A
        " 32 5F 00"     # Clear BANK_RETURN_FLAG
        " C9"           # RET through monitor's START frame
        " AF"           # cold_banner_return: XOR A
        " 32 5F 00"     # Clear BANK_RETURN_FLAG
        " C3 31 F1"     # JP F131H, cold-start continuation
    )
    patch(
        low,
        LOW_RETURN_DISPATCH,
        bytes(len(low_return_dispatch)),
        low_return_dispatch,
    )

    # RAM top and switch state are now printed by the new banner routine.
    patch(low, 0xF147, bytes(low[addr_offset(0xF147):addr_offset(0xF161)]), bytes(26))

    # Low-bank console routing: bit 0 clear = Console I/O, set = Serial A.
    patch(low, 0xF2CD, bytes.fromhex("3E FF CB 6F 20 05"), bytes.fromhex("3A 5E 00 1F 30 05"))
    patch(low, 0xF2D8, bytes.fromhex("3E FF CB 47 CA F7 F2"), bytes.fromhex("C3 DF F2 00 00 00 00"))
    patch(low, 0xF2EF, bytes.fromhex("3E FF CB 6F 20 00"), bytes.fromhex("18 04 00 00 00 00"))
    patch(low, 0xF31E, bytes.fromhex("3E FF CB 6F 20 03"), bytes.fromhex("3A 5E 00 1F 30 03"))
    patch(low, 0xF333, bytes.fromhex("3E FF CB 6F 20 09"), bytes.fromhex("3A 5E 00 1F 30 09"))

    # Replace the obsolete command entries with the target boot/status paths.
    # B=boot menu, C=Altair FDC+, H=hardware status.  L/O/W are deliberately
    # invalid because Versafloppy, auxiliary processors, and Port ED switching
    # are not part of this IMSAI's target configuration.
    target_code, target_labels = build_low_target_routines()

    # Retire or repurpose legacy public jump vectors whose implementations
    # were reclaimed.  Both historical floppy vectors now enter the Altair
    # FDC+ path; unsupported DOS/list/loader helpers fail safely at MENU_ERROR.
    vector_patches = {
        0xF018: (0xFC60, LOW_MENU_ERROR),
        0xF02A: (0xFC61, LOW_MENU_ERROR),
        0xF02D: (0xFC5F, LOW_MENU_ERROR),
        0xF042: (0xFB06, LOW_MENU_ERROR),
        0xF060: (0xFC61, LOW_MENU_ERROR),
        0xF066: (0xF9D6, target_labels["fdc_boot"]),
        0xF06C: (0xFC61, LOW_MENU_ERROR),
        0xF06F: (0xFC61, LOW_MENU_ERROR),
        0xF075: (0xF9D9, target_labels["fdc_boot"]),
    }
    for vector_address, (old_target, new_target) in vector_patches.items():
        patch(
            low,
            vector_address + 1,
            old_target.to_bytes(2, "little"),
            new_target.to_bytes(2, "little"),
        )

    command_patches = {
        0xF08A: (0xF9A7, target_labels["boot_menu"]),
        0xF08C: (0xF9D9, target_labels["fdc_boot"]),
        0xF096: (0xF84C, target_labels["hardware_request"]),
        0xF09E: (0xF066, LOW_MENU_ERROR),
        0xF0A4: (0xF9B8, LOW_MENU_ERROR),
        0xF0B4: (0xF993, LOW_MENU_ERROR),
    }
    for table_address, (old_target, new_target) in command_patches.items():
        patch(
            low,
            table_address,
            old_target.to_bytes(2, "little"),
            new_target.to_bytes(2, "little"),
        )

    # The monitor's historical Ctrl-C shortcut booted the removed ZFDC path.
    # Keep the shortcut, but make it boot the configured IDE/CF device.
    patch(low, 0xF2A0, bytes.fromhex("CA D9 F9"), bytes.fromhex("CA 7D F3"))

    # After the IDE interface is initialized, enter the cancelable automatic
    # boot countdown.  A trailing NOP preserves the four-byte startup slot.
    patch(low, 0xF174, bytes.fromhex("3E FC D3 05"), bytes((0xC3, 0x93, 0xF9, 0x00)))

    # The fixed F800H CP/M 1.4/Versafloppy table is intentionally retired.
    # RTC code begins at F842H and is retained.
    low[addr_offset(0xF800) : addr_offset(0xF842)] = bytes(0x42)

    # Reclaim the former 8086/68000 and Versafloppy/ZFDC implementation area.
    # No DSI code is present.  Install only the target routines above.
    target_start = addr_offset(LOW_TARGET_ROUTINES)
    target_end = addr_offset(LOW_TARGET_END) + 1
    low[target_start:target_end] = bytes(target_end - target_start)
    low[target_start : target_start + len(target_code)] = target_code

    # Short header and target-state menu. Keep all following strings at their
    # original addresses so the retained IDE, RTC, and monitor code is stable.
    signon_start = addr_offset(0xFC6A)
    signon_end = low.index(ord("$"), signon_start) + 1
    short_signon = b"\r\nIMSAI 8080 MONITOR @ F000H $"
    if len(short_signon) > signon_end - signon_start:
        raise RuntimeError("Short menu heading does not fit original signon slot")
    low[signon_start:signon_end] = short_signon.ljust(signon_end - signon_start, b"\x00")

    menu_start = addr_offset(0xFCA9)
    menu_end = addr_offset(0xFD99)
    target_menu = (
        b"\r\nA=Memmap B=Boot Menu C=Altair FDC+ D=Disp E=Echo F=Fill G=Goto"
        b"\r\nH=Hardware I=Time J=Test K=Menu M=Move N=SeqMap P=CP/M IDE/CF"
        b"\r\nQ=I/O Port R=Ports S=Subs T=Type V=Verify X=XModem Z=Top"
        b"\r\n@=Flush Printer\r\n\r\n$"
    )
    if len(target_menu) > menu_end - menu_start:
        raise RuntimeError("Target menu does not fit original menu-string area")
    low[menu_start:menu_end] = target_menu.ljust(menu_end - menu_start, b"\x00")

    # Remove stale strings for the reclaimed floppy implementations while
    # preserving Menu_ErrorMsg at FF37H and NoHighPageMsg at FF45H.
    low[addr_offset(0xFF0D) : addr_offset(0xFF37)] = bytes(0x2A)

    # High-bank console routing uses the same latched switch byte.
    patch(high, 0xF0AA, bytes.fromhex("3E FF CB 6F 20 05"), bytes.fromhex("3A 5E 00 1F 30 05"))
    patch(high, 0xF0B5, bytes.fromhex("3E FF CB 47 CD BD F0"), bytes.fromhex("C3 BD F0 00 00 00 00"))
    patch(high, 0xF0CD, bytes.fromhex("3E FF CB 6F 20 00"), bytes.fromhex("18 04 00 00 00 00"))
    patch(high, 0xF121, bytes.fromhex("3E FF CB 6F 20 03"), bytes.fromhex("3A 5E 00 1F 30 03"))
    patch(high, 0xF136, bytes.fromhex("3E FF CB 6F 20 09"), bytes.fromhex("3A 5E 00 1F 30 09"))

    banner_code = build_high_banner()
    patch(high, HIGH_ROUTINE, bytes(len(banner_code)), banner_code)

    config_code = build_high_config_status()
    patch(high, HIGH_CONFIG_STATUS, bytes(len(config_code)), config_code)

    cdbl = parse_cdbl_hex()
    high[addr_offset(HIGH_CDBL) : addr_offset(HIGH_CDBL) + 256] = cdbl

    # Preserve the original high-page entry at F07CH and extend its D-register
    # service dispatch without moving the original invalid-request handler.
    # F086H now jumps to free space immediately after the new banner.
    patch(
        high,
        0xF086,
        bytes.fromhex("7A FE 01 CA 53 F2 C3 8F F0"),
        bytes.fromhex("C3 C0 F8 00 00 00 00 00 00"),
    )
    high_dispatch = bytes.fromhex(
        "7A"            # LD A,D
        " FE 01"        # CP 01H
        " CA 53 F2"     # JP Z,HIGH_XMODEM
        " FE 02"        # CP 02H
        " CA 27 F6"     # JP Z,HIGH_ROUTINE
        " FE 03"        # CP 03H
        " CA 00 FF"     # JP Z,CDBL
        " FE 04"        # CP 04H
        " CA 00 F9"     # JP Z,HIGH_CONFIG_STATUS
        " C3 8F F0"     # JP INVALID_MENU_ERROR
    )
    patch(high, HIGH_DISPATCH, bytes(len(high_dispatch)), high_dispatch)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    low_path = OUTPUT / "IMSAI_MONITOR_V5.6_TARGET_LOW_4K.BIN"
    high_path = OUTPUT / "IMSAI_MONITOR_V5.6_TARGET_HIGH_4K.BIN"
    combined_path = OUTPUT / "IMSAI_MONITOR_V5.6_TARGET_28C64_8K.BIN"
    hex_path = OUTPUT / "IMSAI_MONITOR_V5.6_TARGET_28C64_8K.HEX"

    low_path.write_bytes(low)
    high_path.write_bytes(high)
    combined = bytes(low + high)
    combined_path.write_bytes(combined)
    hex_path.write_text(intel_hex(combined), encoding="ascii")

    checksums = {
        low_path.name: sha256(low),
        high_path.name: sha256(high),
        combined_path.name: sha256(combined),
        hex_path.name: sha256(hex_path.read_bytes()),
    }
    checksum_text = "".join(f"{digest}  {name}\n" for name, digest in checksums.items())
    (OUTPUT / "SHA256SUMS.txt").write_text(checksum_text, encoding="ascii")

    print(f"High banner routine: {HIGH_ROUTINE:04X}H-{HIGH_ROUTINE + len(banner_code) - 1:04X}H")
    print(f"High banner bytes:   {len(banner_code)}")
    print(f"Target low routines: {LOW_TARGET_ROUTINES:04X}H-{LOW_TARGET_ROUTINES + len(target_code) - 1:04X}H")
    print(f"High config status:  {HIGH_CONFIG_STATUS:04X}H-{HIGH_CONFIG_STATUS + len(config_code) - 1:04X}H")
    print(f"Altair CDBL:         FF00H-FFFFH ({len(cdbl)} bytes)")
    print(f"Combined SHA-256:    {checksums[combined_path.name]}")


if __name__ == "__main__":
    main()
