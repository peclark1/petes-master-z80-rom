#!/usr/bin/env python3
"""Create one reviewable two-page V5.6 target Z80 source file."""

from __future__ import annotations

from pathlib import Path

import build_imsai_rom as target
import build_merged_z80_source as v55


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "IMSAI_MONITOR_V5.6_TARGET_MERGED.z80"


def replace_span(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[:start] + replacement + text[end:]


def strip_obsolete_definitions(text: str) -> str:
    # Retain RTC access, but remove the unused auxiliary-CPU PIC definitions.
    start = text.index(";-------------- S100Computers MSDOS Support Board PORT ASSIGNMENTS")
    end = text.index(";--------------- PORTS FOR FOR Z80/WD2793 FDC Board", start)
    text = text[:start] + (
        ";-------------- RTC PORT ---------------------------------------------\n"
        "CMOS_PORT\tEQU\t70H\n\n"
    ) + text[end:]

    # Replace all former floppy/processor-switch definitions with only the
    # target CPU bank control, FDC+, and private workspace definitions.
    start = text.index(";--------------- PORTS FOR FOR Z80/WD2793 FDC Board")
    end = text.index(";-------------- S100Computers IDE HARD DISK CONTROLLER COMMANDS ETC.", start)
    replacement = (
        ";-------------- TARGET CPU / ALTAIR FDC+ -----------------------------\n"
        "Z80PORT\tEQU\t0D0H\t\t;V2 CPU memory and ROM-page control\n"
        "ALTAIR_DSTAT\tEQU\t08H\t\t;FDC+ status / drive select\n"
        "ALTAIR_DSECTR\tEQU\t09H\t\t;FDC+ sector / command\n"
        "ALTAIR_DDATA\tEQU\t0AH\t\t;FDC+ data\n"
        "UNSAFE_INPUT_PORT\tEQU\t0EDH\t;Retain legacy port-scan exclusion\n"
        "USE_FRONT_PANEL_SWITCHES EQU 0\t;0=forced console, 1=read port FFH\n"
        "FORCED_CONSOLE_SELECTOR  EQU 0\t;0=Console I/O, 1=Serial A\n"
        "CONSOLE_SELECTOR\tEQU\t5EH\n"
        "BANK_RETURN_FLAG\tEQU\t5FH\n\n"
    )
    text = text[:start] + replacement + text[end:]

    text = text.replace("VERSA\t\tEQU\tBASE+800H \t;<--------<<<<<< LOCATION OF FLOPPY BIOS JMP's (For old CPM V1.2 Software)\n", "")
    text = text.replace("RUN_CPM14\tEQU\tTRUE\t\t;Some of my early old CPM V1.4 programs count on routines being at crertain places \n", "")
    return text


def low_target_source() -> str:
    return r'''
;=============================================================================
; IMSAI V5.6 TARGET ROUTINES - RECLAIMED LOW-PAGE AREA
;=============================================================================
	ORG	0F993H
TARGET_AUTO_BOOT:
	LD	HL,TARGET_AUTO_MSG
	CALL	PRINT_STRING
	LD	B,3
TARGET_COUNTDOWN:
	LD	A,B
	ADD	A,'0'
	LD	C,A
	CALL	CO
	LD	D,3			;Approximately one second at 10 MHz
TARGET_DELAY_OUTER:
	LD	HL,0FFFFH
TARGET_DELAY_INNER:
	CALL	CSTS
	JR	NZ,TARGET_CANCEL_AUTO
	DEC	HL
	LD	A,H
	OR	L
	JR	NZ,TARGET_DELAY_INNER
	DEC	D
	JR	NZ,TARGET_DELAY_OUTER
	LD	C,' '
	CALL	CO
	DJNZ	TARGET_COUNTDOWN
	LD	HL,TARGET_IDE_MSG
	CALL	PRINT_STRING
	LD	HL,START		;Dummy frame expected by HBOOTCPM
	PUSH	HL
	JP	HBOOTCPM

TARGET_CANCEL_AUTO:
	CALL	CI			;Consume the interrupting key
	LD	HL,TARGET_MONITOR_MSG
	CALL	PRINT_STRING
	JP	START

TARGET_BOOT_MENU:
	LD	HL,TARGET_BOOT_MENU_MSG
	CALL	PRINT_STRING
TARGET_BOOT_MENU_WAIT:
	CALL	CI
	AND	5FH
	CP	'I'
	JP	Z,HBOOTCPM
	CP	'F'
	JP	Z,TARGET_FDC_BOOT
	CP	'M'
	RET	Z			;Return through monitor's START frame
	JP	TARGET_BOOT_MENU_WAIT

TARGET_FDC_BOOT:
	LD	HL,TARGET_FDC_MSG
	CALL	PRINT_STRING
	LD	D,3			;High-page service 3 = CDBL at FF00H
	JP	ACTIVATE_HIGH_PAGE

TARGET_HARDWARE_REQUEST:
	LD	D,4			;High-page service 4 = build configuration
	JP	ACTIVATE_HIGH_PAGE

TARGET_AUTO_MSG:
	DB	CR,LF,'IDE/CF AUTO BOOT IN 3 SECONDS - PRESS ANY KEY FOR MONITOR',CR,LF,'$'
TARGET_IDE_MSG:
	DB	CR,LF,'BOOTING CP/M FROM IDE/CF...',CR,LF,'$'
TARGET_MONITOR_MSG:
	DB	CR,LF,'AUTO BOOT CANCELLED - MONITOR ACTIVE',CR,LF,'$'
TARGET_BOOT_MENU_MSG:
	DB	CR,LF,'BOOT: [I] IDE/CF  [F] ALTAIR FDC+  [M] MONITOR : $'
TARGET_FDC_MSG:
	DB	CR,LF,'BOOTING ALTAIR FDC+ WITH CDBL...',CR,LF,'$'
'''


def high_target_source() -> str:
    cdbl = target.parse_cdbl_hex()
    db_lines = []
    for offset in range(0, len(cdbl), 16):
        values = ",".join(f"{value:02X}H" for value in cdbl[offset : offset + 16])
        db_lines.append(f"\tDB\t{values}")
    cdbl_source = "\n".join(db_lines)
    return r'''
	ORG	0F8C0H
IMSAI_HIGH_DISPATCH:
	LD	A,D
	CP	1
	JP	Z,HIGH_XMODEM
	CP	2
	JP	Z,IMSAI_HIGH_BANNER
	CP	3
	JP	Z,0FF00H		;Martin Eberhard CDBL
	CP	4
	JP	Z,IMSAI_HARDWARE_STATUS
	JP	INVALID_MENU_ERROR

	ORG	0F900H
IMSAI_HARDWARE_STATUS:
	LD	HL,IMSAI_CONFIG_MSG
	CALL	HIGH_PRINT_STRING
	LD	A,0A6H
	LD	(BANK_RETURN_FLAG),A
	JP	ACTIVATE_LOW_PAGE

IMSAI_CONFIG_MSG:
	DB	CR,LF,'HARDWARE / BUILD CONFIGURATION',CR,LF
	DB	'  SYSTEM : IMSAI 8080',CR,LF
	DB	'  CPU    : S100 Z80 V2; 8K BANKED ROM @ F000H; P39 7-8',CR,LF
	DB	'  CONSOLE: CONSOLE I/O @ 00H/01H (BUILD SELECTED)',CR,LF
	DB	'  SERIAL : S100 SERIAL I/O PORT A @ A1H/A3H, 38400 8N1',CR,LF
	DB	'  STORAGE: DUAL IDE/CF @ 30H-34H',CR,LF
	DB	'           ALTAIR FDC+ @ 08H-0AH; CDBL @ HIGH-PAGE FF00H',CR,LF
	DB	'  PANEL  : NOT CONNECTED TO CURRENT Z80 CPU',CR,LF
	DB	'  DEFAULT: IDE/CF AUTO BOOT; ANY KEY CANCELS',CR,LF,'$'

; Martin Eberhard CDBL 2.05, assembled image supplied by deramp.com.
; Runs at FF00H, relocates itself to 4C00H, and auto-detects an Altair
; 88-DCDD 8-inch disk or 88-MDS Minidisk through FDC+ ports 08H-0AH.
	ORG	0FF00H
IMSAI_CDBL:
''' + cdbl_source + "\n"


def patch_low_target(text: str) -> str:
    text = v55.patch_low(text)
    text = strip_obsolete_definitions(text)

    # Public vectors whose old implementations were reclaimed.
    replacements = {
        "ZTRAP:\t\tJP\tTRAP\t\t\t;ERROR TRAP ADDRESS": "ZTRAP:\t\tJP\tMENU_ERROR\t\t;Unsupported legacy trap",
        "ZONLIST:\tJP\tONLIST\t\t\t;INITILIZE LIST DEVICE": "ZONLIST:\tJP\tMENU_ERROR",
        "ZOFFLIST:\tJP\tOFLIST\t\t\t;TURN OFF LIST DEVICE": "ZOFFLIST:\tJP\tMENU_ERROR",
        "ZLOADER:\tJP\tLOADER\t\t\t;LOAD IN CPM IMAGE ON TRACKS 0 & 1 (VIA FLOPPY BOOT LOADER ON DISK SECTOR 1) ": "ZLOADER:\tJP\tMENU_ERROR",
        "ZDOS\t\tJP\tDOS\t\t\t;LOAD MSDOS FROM 5\" DRIVE D:": "ZDOS:\t\tJP\tMENU_ERROR",
        "ZVBOOT\t\tJP\tVBOOT\t\t\t;BOOT UP CPM-80 FROM VERSAFLOPPY II FDC": "ZALTAIR_BOOT:\tJP\tTARGET_FDC_BOOT",
        "ZPRDY:\t\tJP\tPRDY\t\t\t;PUNCH READY CHECK": "ZPRDY:\t\tJP\tMENU_ERROR",
        "ZRSTAT:\t\tJP\tRSTAT\t\t\t;READER STATUS": "ZRSTAT:\t\tJP\tMENU_ERROR",
        "ZZBOOT\t\tJP\tZBOOT\t\t\t;BOOT UP CPM-80 FROM ZFDC FDC": "ZALTAIR_BOOT2:\tJP\tTARGET_FDC_BOOT",
    }
    for old, new in replacements.items():
        text = v55.replace_once(text, old, new, "target public vector")

    table_replacements = {
        "\tDW  SWITCH_68K  ; \"B\"  SWITCH CONTROL TO 68000 CPU ": "\tDW  TARGET_BOOT_MENU\t; \"B\" boot menu",
        "\tDW  ZBOOT\t; \"C\"  BOOT IN CP/M FROM 8\" DISK WITH WITH ZFDC FDC ": "\tDW  TARGET_FDC_BOOT\t; \"C\" Altair FDC+",
        "\tDW  SHOW_DATE\t; \"H\"  SHOW CURRENT DATE": "\tDW  TARGET_HARDWARE_REQUEST ; \"H\" hardware/build status",
        "\tDW  ZVBOOT\t; \"L\"  BOOT IN CP/M FROM 8\" DISK WITH VERSAFLOPPY II FDC": "\tDW  MENU_ERROR\t; \"L\" unused",
        "\tDW  UP8086\t; \"O\"  SWITCH CONTROL TO 8088, 8086 or 80286. ": "\tDW  MENU_ERROR\t; \"O\" unused",
        "\tDW  SWITCH_8086 ; \"W\"  INPUT Port ED (switched in 8086/80286)": "\tDW  MENU_ERROR\t; \"W\" unused",
    }
    for old, new in table_replacements.items():
        text = v55.replace_once(text, old, new, "target command table")

    text = v55.replace_once(text, "\tJP\tZ,ZBOOT\n", "\tJP\tZ,HBOOTCPM\t\t;Ctrl-C boots configured IDE/CF\n", "Ctrl-C target")
    text = text.replace(
        "\tCP\tA,SW_TMA0\t\t;Inputting here will switch out the Z80 to 8086/80286\n",
        "\tCP\tA,UNSAFE_INPUT_PORT\t;Preserve exclusion of legacy side-effect port\n",
    )

    # Remove reset-time writes to absent hardware while preserving addresses.
    text = v55.replace_once(text, "\tOUT\t(SW_TMAX),A\t\t;Make sure TMA0*,TMA1*,TMA2* & TMA3* S100 lines are high\n", "\tDB\t0,0\t\t\t;Retired auxiliary-CPU control write\n", "CPU switch startup")
    text = replace_span(text, "\tLD\tA,0FFH\n\tOUT\t(SELECT),A", "\n\tLD\tA,10000000B", "\tDB\t0,0,0,0\t\t;Retired floppy-select write\n")
    text = replace_span(text, "\tLD\tA,0FFH\n\tOUT\t(RSET),A", "\n\n\t\t\t\t\t;We need to clear the 8259A", "\tDB\t0,0,0,0,0,0\t;Retired floppy-reset writes\n")
    pic_start = text.index("\t\t\t\t\t;We need to clear the 8259A")
    pic_end = text.index("\n\tLD\tA,0H\t\t\t;SETUP MEMORY MANAGEMENT", pic_start)
    text = text[:pic_start] + "\tDB\t0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0\t;Retired PIC setup\n" + text[pic_end + 1:]

    text = v55.replace_once(
        text,
        "\tCALL\tINITILIZE_IDE_BOARD\t;initilize first IDE drive (if present)\n\t\n\tLD\tA,11111100B\t\t;FLAG PROGRESS (Initilization done, 6 LED's ON)\n\tOUT\t(DIAG_LEDS),A\n",
        "\tCALL\tINITILIZE_IDE_BOARD\t;Initialize configured IDE/CF\n"
        "\tJP\tTARGET_AUTO_BOOT\n\tNOP\t\t\t\t;Keep START at F178H\n",
        "auto boot startup",
    )

    # Tagged returns: A5=cold banner, A6=hardware-status command.
    start = text.index("\tORG\t0F75CH\nLOW_RETURN_DISPATCH:")
    end = text.index(";---------------------------------------------------------------------------------------------------------\nIF RUN_CPM14", start)
    dispatcher = r'''	ORG	0F75CH
LOW_RETURN_DISPATCH:
	LD	A,(BANK_RETURN_FLAG)
	CP	0A5H
	JP	Z,LOW_COLD_BANNER_RETURN
	CP	0A6H
	JP	NZ,START
	XOR	A
	LD	(BANK_RETURN_FLAG),A
	RET
LOW_COLD_BANNER_RETURN:
	XOR	A
	LD	(BANK_RETURN_FLAG),A
	JP	STARTUP_CONTINUE
'''
    text = text[:start] + dispatcher + text[end:]

    # Remove the F800H compatibility table, retaining RTC code at F842H.
    start = text.index("IF RUN_CPM14\n\tORG\tVERSA")
    end = text.index(";------THIS IS THE MAIN ROUTINE TO GET THE TIME", start)
    text = text[:start] + "\tORG\t0F842H\n\n" + text[end:]

    # Replace processor and obsolete floppy implementations with target code.
    start = text.index(";THIS ROUTINE ACTIVATES THE S100 TMA0* LINE")
    end = text.index("SIGNON_MSG:", start)
    text = text[:start] + low_target_source() + "\n\tORG\t0FC6AH\n" + text[end:]

    # Target menu; the next retained string remains fixed at FD99H.
    start = text.index("MENUMSG:")
    end = text.index("SMSG_SP:", start)
    menu = r'''MENUMSG:
	DB	CR,LF,'A=Memmap B=Boot Menu C=Altair FDC+ D=Disp E=Echo F=Fill G=Goto'
	DB	CR,LF,'H=Hardware I=Time J=Test K=Menu M=Move N=SeqMap P=CP/M IDE/CF'
	DB	CR,LF,'Q=I/O Port R=Ports S=Subs T=Type V=Verify X=XModem Z=Top'
	DB	CR,LF,'@=Flush Printer',CR,LF,LF,'$'
	ORG	0FD99H
'''
    text = text[:start] + menu + text[end:]

    # Remove stale low-page floppy strings, retaining live error messages.
    start = text.index("BOOT_MSG0:")
    end = text.index("Menu_ErrorMsg:", start)
    text = text[:start] + "\tORG\t0FF37H\n" + text[end:]
    return text


def patch_high_target(text: str) -> str:
    text = v55.patch_high(text)
    text = strip_obsolete_definitions(text)
    text = text.replace("D=1 XMODEM, D=2 IMSAI banner", "D=1 XMODEM, D=2 banner, D=3 CDBL, D=4 status")
    start = text.index("\tORG\t0F8C0H\nIMSAI_HIGH_DISPATCH:")
    end = text.index("\n;END", start)
    return text[:start] + high_target_source() + text[end:]


def remove_obsolete_comment_lines(text: str) -> str:
    terms = ("zfdc", "versafloppy", "68000", "68030", "8086", "8088", "80286", "80386", "run_cpm14")
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith(";") and any(term in line.lower() for term in terms):
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


def main() -> None:
    low = patch_low_target(v55.LOW_PATH.read_text(encoding="latin-1").replace("\r\n", "\n"))
    high = patch_high_target(v55.HIGH_PATH.read_text(encoding="latin-1").replace("\r\n", "\n"))
    low = remove_obsolete_comment_lines(low).replace("V5.5G", "V5.6 TARGET")
    high = remove_obsolete_comment_lines(high).replace("V5.5G", "V5.6 TARGET")

    header = r'''; IMSAI 8080 MONITOR V5.6 TARGET - MERGED TWO-PAGE REVIEW SOURCE
;
; Set ROM_PAGE to 0 for the physical lower 4K half or 1 for the upper
; 4K half. Both pages execute at CPU address F000H. The production BIN is
; generated and byte-verified by build_imsai_rom.py and verify_target_rom.py.
;
ROM_PAGE	EQU	0

	IF	ROM_PAGE
;=============================================================================
; ROM PAGE 1 - HIGH 4K
;=============================================================================
'''
    middle = r'''
	ELSE
;=============================================================================
; ROM PAGE 0 - LOW 4K
;=============================================================================
'''
    footer = "\n\tENDIF\n\tEND\n"
    merged = header + high + middle + low + footer
    OUTPUT.write_text(merged, encoding="latin-1", newline="\r\n")
    print(f"Wrote {OUTPUT.name}: {OUTPUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
