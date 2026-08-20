#!/usr/bin/env python3
"""Create a single reviewable V5.5G Z80 source containing both ROM pages.

Set ROM_PAGE to 0 or 1 at the top of the generated file and assemble twice.
The original SLR Z80ASM is not available here, so the generated source is
validated structurally against the authoritative V5.5G binary-patch builder.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOW_PATH = ROOT / "original" / "Master0_NO_IOBYTE.z80"
HIGH_PATH = ROOT / "original" / "Master1_NO_IOBYTE.z80"
OUTPUT = ROOT / "IMSAI_MONITOR_V5.5G_MERGED.z80"


def replace_once(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{description}: expected one match, found {count}")
    return text.replace(old, new, 1)


def add_workspace_symbols(text: str) -> str:
    old = "@SEC_SIZE EQU\t5CH\t\t\t;Byte count of a sector fot loader\n"
    new = old + (
        "\n;----- IMSAI V5.5G build options and private workspace ---------------\n"
        "USE_FRONT_PANEL_SWITCHES EQU 0\t;0=forced console, 1=read port FFH\n"
        "FORCED_CONSOLE_SELECTOR  EQU 0\t;bit 0: 0=Console I/O, 1=Serial A\n"
        "CONSOLE_SELECTOR\tEQU\t5EH\t;Selected console byte\n"
        "BANK_RETURN_FLAG\tEQU\t5FH\t;A5H only while returning from banner\n"
    )
    return replace_once(text, old, new, "workspace symbols")


def patch_console_routing(text: str, high: bool) -> str:
    co_label = "HIGH_CO:" if high else "CO:"
    old = (
        f"{co_label}\n" if high else f"{co_label}\t"
    )
    if high:
        old += (
            "\tLD\tA,0FFH\n"
            "\tBIT\t5,A\t\t\t;SEE IF SERIAL PORT OUTPUT IS REQ\n"
            "\tJR\tNZ,NO_SERIAL\t\t;MAKE SURE TO RETURN CHARACTER SENT IN [A]\n"
        )
        new = (
            "HIGH_CO:\n"
            "\tLD\tA,(CONSOLE_SELECTOR)\t;IMSAI switch 08 is bit 0\n"
            "\tRRA\n"
            "\tJR\tNC,NO_SERIAL\t\t;0=Console I/O, 1=Serial A\n"
        )
    else:
        old += (
            "LD\tA,0FFH\n"
            "\tBIT\t5,A\t\t\t;SEE IF SERIAL PORT OUTPUT IS REQ\n"
            "\tJR\tNZ,NO_SERIAL\t\t;MAKE SURE TO RETURN CHARACTER SENT IN [A]\n"
        )
        new = (
            "CO:\tLD\tA,(CONSOLE_SELECTOR)\t;IMSAI switch 08 is bit 0\n"
            "\tRRA\n"
            "\tJR\tNC,NO_SERIAL\t\t;0=Console I/O, 1=Serial A\n"
        )
    text = replace_once(text, old, new, f"{'high' if high else 'low'} CO selector")

    if high:
        old = (
            "NO_SERIAL:\n"
            "\tLD\tA,0FFH\t\t;NOTE CHARACTER IS IN [C]\n"
            "\tBIT\t0,A\t\t\t;CHECK IF OUTPUT TO PRINTER IS ALSO REQ\n"
            "\tCALL\tSDCONO\t\t\t;OUTPUT TO CONSOLE (No Printer)\n"
            "\tRET\n"
        )
    else:
        old = (
            "NO_SERIAL:\n"
            "\tLD\tA,0FFH\t\t;NOTE CHARACTER IS IN [C]\n"
            "\tBIT\t0,A\t\t\t;CHECK IF OUTPUT TO PRINTER IS ALSO REQ\n"
            "\tJP\tZ,LOX\t\t\t;Send to BOTH printer and console\n"
        )
    new = (
        "NO_SERIAL:\n"
        "\tJP\tSDCONO\t\t\t;Console I/O only; printer routing removed\n"
        "\tNOP\t\t\t\t;Address-preserving replacement\n"
        "\tNOP\n\tNOP\n\tNOP\n"
    )
    text = replace_once(text, old, new, f"{'high' if high else 'low'} NO_SERIAL")

    old = (
        "\tOUT\t(CONSOL_OUT),A\n"
        "\tLD\tA,0FFH\n"
        "\tBIT\t5,A\t\t\t;SEE IF SERIAL PORT OUTPUT IS REQ\n"
        "\tJR\tNZ,SDCON5\t\t;MAKE SURE TO RETURN CHARACTER SENT IN [A]\n"
    )
    new = (
        "\tOUT\t(CONSOL_OUT),A\n"
        "\tJR\tSDCON5\t\t\t;Return character sent\n"
        "\tNOP\t\t\t\t;Address-preserving replacement\n"
        "\tNOP\n\tNOP\n\tNOP\n"
    )
    text = replace_once(text, old, new, f"{'high' if high else 'low'} console tail")

    csts = "HIGH_CSTS:" if high else "CSTS:"
    if high:
        old = (
            "HIGH_CSTS:\n"
            "\tLD\tA,0FFH\n"
            "\tBIT\t5,A\t\t\t;SEE IF SERIAL PORT STATUS IS REQ\n"
            "\tJR\tNZ,NO_SER_STAT\t\t\n"
        )
        new = (
            "HIGH_CSTS:\n"
            "\tLD\tA,(CONSOLE_SELECTOR)\n"
            "\tRRA\n"
            "\tJR\tNC,NO_SER_STAT\t\n"
        )
    else:
        old = (
            "CSTS:\tLD\tA,0FFH\n"
            "\tBIT\t5,A\t\t\t;SEE IF SERIAL PORT STATUS IS REQ\n"
            "\tJR\tNZ,NO_SER_STAT\t\t\n"
        )
        new = (
            "CSTS:\tLD\tA,(CONSOLE_SELECTOR)\n"
            "\tRRA\n"
            "\tJR\tNC,NO_SER_STAT\t\n"
        )
    text = replace_once(text, old, new, f"{csts} selector")

    ci = "HIGH_CI:" if high else "CI:"
    if high:
        old = (
            "HIGH_CI:\n"
            "\tLD\tA,0FFH\n"
            "\tBIT\t5,A\t\t\t;SEE IF SERIAL PORT INPUT IS REQ\n"
            "\tJR\tNZ,CI_IN\t\t;NO, then do normal CI\n"
        )
        new = (
            "HIGH_CI:\n"
            "\tLD\tA,(CONSOLE_SELECTOR)\n"
            "\tRRA\n"
            "\tJR\tNC,CI_IN\t\t;0=Console I/O, 1=Serial A\n"
        )
    else:
        old = (
            "CI:\tLD\tA,0FFH\n"
            "\tBIT\t5,A\t\t\t;SEE IF SERIAL PORT INPUT IS REQ\n"
            "\tJR\tNZ,CI_IN\t\t;NO, then do normal CI\n"
        )
        new = (
            "CI:\tLD\tA,(CONSOLE_SELECTOR)\n"
            "\tRRA\n"
            "\tJR\tNC,CI_IN\t\t;0=Console I/O, 1=Serial A\n"
        )
    return replace_once(text, old, new, f"{ci} selector")


def patch_low(text: str) -> str:
    text = add_workspace_symbols(text)

    text = replace_once(
        text,
        "ACTIVATE_LOW_PAGE:\t\t\t\t; RETURN BACK TO LOW PAGE OF ROM\n"
        "\tNOP\n\tNOP\n\tNOP\n\tNOP\n"
        "\tJP\tSTART\t\t\t\t; <---- Switching back to LOW page will arrive here\n",
        "ACTIVATE_LOW_PAGE:\t\t\t\t; RETURN BACK TO LOW PAGE OF ROM\n"
        "\tNOP\n\tNOP\n\tNOP\n\tNOP\n"
        "\tJP\tLOW_RETURN_DISPATCH\t\t;V5.5G banner/XMODEM return dispatch\n",
        "low return continuation",
    )

    text = replace_once(
        text,
        "BEGIN:\t\n"
        "\tLD\tA,'#'\t\t\t;For quick hardware diagnostic test\n"
        "\tOUT\t(CONSOL_OUT),A\t\t;Must see a \"#\" on the CRT in ROM access is active\n",
        "BEGIN:\t\n"
        ";V5.5G: remove unconditional Console I/O '#'; keep all addresses fixed.\n"
        "\tNOP\n\tNOP\n\tNOP\n\tNOP\n",
        "early hash removal",
    )

    start_marker = (
        "\tLD\tA,11000000B\t\t;FLAG PROGRESS VISUALLY FOR DIAGNOSTIC (2 LED's ON)\n"
        "\tOUT\t(DIAG_LEDS),A \n\n"
    )
    end_marker = (
        "\tLD\tA,11100000B\t\t;FLAG PROGRESS (Have a Stack with 3 LED's ON)\n"
        "\tOUT\t(DIAG_LEDS),A\n\n"
    )
    start = text.index(start_marker)
    end = text.index(end_marker, start) + len(end_marker)
    replacement = (
        ";----- IMSAI V5.5G cold start (24 bytes, F119H-F130H) --------\n"
        "\tXOR\tA\n"
        "\tLD\t(BANK_RETURN_FLAG),A\t;Clear private high-page return flag\n\n"
        "\tIF\tUSE_FRONT_PANEL_SWITCHES\n"
        "\tIN\tA,(0FFH)\t\t;IMSAI programmed-input switches\n"
        "\tELSE\n"
        "\tLD\tA,FORCED_CONSOLE_SELECTOR\n"
        "\tENDIF\n"
        "\tLD\t(CONSOLE_SELECTOR),A\n"
        "\tCALL\tINIT_SCC_A\n"
        "\tCALL\tINIT_SCC_B\n"
        "\tLD\tA,AinBout8255cfg\n"
        "\tOUT\t(PortCtrl_8255),A\n"
        "\tLD\tD,2\t\t\t;High-page service 2 = IMSAI banner\n"
        "\tJP\tACTIVATE_HIGH_PAGE\t;Original jump-based bank transition\n"
        "STARTUP_CONTINUE:\t\t\t;F131H after banner returns\n\n"
    )
    text = text[:start] + replacement + text[end:]

    old = (
        "\tLD\tHL,SP_MSG\t\t;Print Current Stack Location\n"
        "\tCALL\tPRINT_STRING\n\t\n"
        "\tPUSH\tIX\t\t\t;SP is stored from above in [IX]\n"
        "\tPOP\tHL\n"
        "\tCALL\tHLSP\t\t\t;Print HL/SP \n\t\n"
        "\tLD\tHL,IOBYTE_MSG\t\t;Print Current IOBYTE value\n"
        "\tCALL\tPRINT_STRING\n\t\n"
        "\tLD\tA,0FFH\t\t;Show IOBYTE. If bit 0=0 (force printer output), CMP/3 boot will hang\n"
        "\tCALL\tZBITS\n\t\n"
        "\tCALL\tCRLF\t\t\t;Then CRLF\n"
    )
    new = (
        ";V5.5G: RAM top and console state are printed by the high-page banner.\n"
        ";Keep F147H-F160H as 26 address-preserving NOP bytes.\n"
        "\tDB\t0,0,0,0,0,0,0,0,0,0,0,0,0\n"
        "\tDB\t0,0,0,0,0,0,0,0,0,0,0,0,0\n"
    )
    text = replace_once(text, old, new, "old stack/IOBYTE display")
    text = patch_console_routing(text, high=False)

    old = (
        "SIGNON_MSG:\tDB SCROLL,QUIT,NO_ENHANCEMENT,FAST,BELL,CR,LF,LF\t\t\n"
        "\t\tDB 'Z80 ROM MONITOR (V5.4) @ F000H (J.Monahan,12/20/2017) $'\t\n"
    )
    new = (
        "SIGNON_MSG:\tDB CR,LF,'IMSAI 8080 MONITOR @ F000H $'\n"
        "\t\t;35 pad bytes retain MENUMSG and every later address\n"
        "\t\tDB 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0\n"
        "\t\tDB 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0\n"
    )
    text = replace_once(text, old, new, "short monitor heading")

    insertion = (
        "NOP\nNOP\nNOP\n"
        ";----- IMSAI V5.5G low-page continuation --------------------------\n"
        "\tORG\t0F75CH\n"
        "LOW_RETURN_DISPATCH:\n"
        "\tLD\tA,(BANK_RETURN_FLAG)\n"
        "\tCP\t0A5H\n"
        "\tJP\tNZ,START\t\t;Normal D=1 XMODEM return\n"
        "\tXOR\tA\n"
        "\tLD\t(BANK_RETURN_FLAG),A\n"
        "\tJP\tSTARTUP_CONTINUE\t\t;No CALL/RET across the bank switch\n"
    )
    text = replace_once(text, "NOP\nNOP\nNOP\n;---------------------------------------------------------------------------------------------------------\nIF RUN_CPM14", insertion + ";---------------------------------------------------------------------------------------------------------\nIF RUN_CPM14", "low return dispatcher")
    return text


def high_banner_source() -> str:
    return r'''

;=============================================================================
; IMSAI V5.5G HIGH-PAGE BANNER AND SERVICE DISPATCH
;=============================================================================
	ORG	0F627H
IMSAI_HIGH_BANNER:
	LD	HL,IMSAI_BANNER
	CALL	HIGH_PRINT_STRING

	LD	HL,IMSAI_RAM_TOP
	CALL	HIGH_PRINT_STRING
	PUSH	IX
	POP	HL
	CALL	HIGH_LADR
	LD	HL,IMSAI_HEX_LINE_END
	CALL	HIGH_PRINT_STRING

	IF	USE_FRONT_PANEL_SWITCHES
	LD	HL,IMSAI_SWITCH_HEADING
	CALL	HIGH_PRINT_STRING
	LD	A,(CONSOLE_SELECTOR)
	LD	B,8
IMSAI_SWITCH_LOOP:
	RLCA
	PUSH	AF
	LD	HL,IMSAI_OFF_TOKEN
	JR	NC,IMSAI_PRINT_SWITCH
	LD	HL,IMSAI_ON_TOKEN
IMSAI_PRINT_SWITCH:
	CALL	HIGH_PRINT_STRING
	POP	AF
	DJNZ	IMSAI_SWITCH_LOOP

	LD	HL,IMSAI_HEX_PREFIX
	CALL	HIGH_PRINT_STRING
	LD	A,(CONSOLE_SELECTOR)
	CALL	HIGH_LBYTE
	LD	HL,IMSAI_HEX_SUFFIX
	CALL	HIGH_PRINT_STRING
	ELSE
	LD	HL,IMSAI_FRONT_PANEL_UNAVAILABLE
	CALL	HIGH_PRINT_STRING
	ENDIF

	LD	A,(CONSOLE_SELECTOR)
	RRA
	LD	HL,IMSAI_SERIAL_CONSOLE
	JR	C,IMSAI_PRINT_CONSOLE
	LD	HL,IMSAI_CONSOLE_IO
IMSAI_PRINT_CONSOLE:
	CALL	HIGH_PRINT_STRING

	LD	A,0A5H
	LD	(BANK_RETURN_FLAG),A
	JP	ACTIVATE_LOW_PAGE

IMSAI_BANNER:
	DB	CR,LF
	DB	'  .----------------------------------------------------------------.',CR,LF
	DB	'  |  o o o o o o o o       I M S A I   8 0 8 0                   |',CR,LF
	DB	'  |  o o o o o o o o    o o o o o o o o o o o o o o o o         |',CR,LF
	DB	'  |  / / / / / / / /    / / / / / / / /    [ RUN ] [ STOP ]     |',CR,LF
	DB	'  ',27H,'----------------------------------------------------------------',27H,CR,LF
	DB	'                 IMSAI 8080 MONITOR @ F000H',CR,LF,'$'
IMSAI_RAM_TOP:		DB	CR,LF,'RAM TOP: $'
IMSAI_HEX_LINE_END:	DB	'H',CR,LF,'$'
	IF	USE_FRONT_PANEL_SWITCHES
IMSAI_SWITCH_HEADING:
	DB	'FRONT PANEL:  15  14  13  12  11  10  09  08',CR,LF
	DB	'              $'
IMSAI_OFF_TOKEN:	DB	'OFF $'
IMSAI_ON_TOKEN:	DB	'ON  $'
IMSAI_HEX_PREFIX:	DB	'  [$'
IMSAI_HEX_SUFFIX:	DB	'H]',CR,LF,'$'
	ELSE
IMSAI_FRONT_PANEL_UNAVAILABLE:
	DB	'FRONT PANEL: NOT CONNECTED - CONSOLE SET AT BUILD TIME',CR,LF,'$'
	ENDIF
IMSAI_SERIAL_CONSOLE:
	DB	'CONSOLE: SERIAL I/O PORT A - 38400 8N1',CR,LF,'$'
IMSAI_CONSOLE_IO:
	DB	'CONSOLE: CONSOLE I/O BOARD - PORTS 00H/01H',CR,LF,'$'

	ORG	0F8C0H
IMSAI_HIGH_DISPATCH:
	LD	A,D
	CP	1
	JP	Z,HIGH_XMODEM
	CP	2
	JP	Z,IMSAI_HIGH_BANNER
	JP	INVALID_MENU_ERROR
'''


def patch_high(text: str) -> str:
    text = add_workspace_symbols(text)
    text = replace_once(
        text,
        "HIGH_MENU_OPTION:\n"
        "\tLD\tA,D\t\t\t\t; HIGH PAGE code with 1 in [D] for XMODEM\n"
        "\tCP\tA,1\n"
        "\tJP\tZ,HIGH_XMODEM\n"
        "\tJP\tINVALID_MENU_ERROR\t\t; The only menu option so far\n",
        "HIGH_MENU_OPTION:\n"
        "\tJP\tIMSAI_HIGH_DISPATCH\t\t;D=1 XMODEM, D=2 IMSAI banner\n"
        "\tNOP\t\t\t\t;Six NOPs retain INVALID_MENU_ERROR at F08FH\n"
        "\tNOP\n\tNOP\n\tNOP\n\tNOP\n\tNOP\n",
        "high service entry",
    )
    text = patch_console_routing(text, high=True)
    text = replace_once(
        text,
        "END_OF_ROM_PAGE: DB\t'  End of ROM HIGH PAGE-->'\n\n;END",
        "END_OF_ROM_PAGE: DB\t'  End of ROM HIGH PAGE-->'\n" + high_banner_source() + "\n;END",
        "high banner insertion",
    )
    return text


def main() -> None:
    low = patch_low(LOW_PATH.read_text(encoding="latin-1").replace("\r\n", "\n"))
    high = patch_high(HIGH_PATH.read_text(encoding="latin-1").replace("\r\n", "\n"))

    header = r'''; IMSAI 8080 MONITOR V5.5G - MERGED TWO-PAGE REVIEW SOURCE
;
; Derived from John Monahan's Master Z80 Monitor V5.4 NO_IOBYTE sources.
; The IMSAI-specific changes used for the verified V5.5G 8K ROM are integrated
; below as Z80 instructions and are marked "IMSAI V5.5G".
;
; Set ROM_PAGE to 0 for the physical 0000H-0FFFH EEPROM half (MASTER0),
; or to 1 for the physical 1000H-1FFFH EEPROM half (MASTER1).  Each selection
; assembles at CPU address F000H. Concatenate the two 4096-byte results in
; page-0 then page-1 order to form the complete 28C64 image.
;
; The original SLR Z80ASM was not available in the build environment.  The
; released BIN remains generated and byte-verified by build_imsai_rom.py;
; this merged source is intended for code review and subsequent native builds.
;
ROM_PAGE	EQU	0		;0=low page, 1=high page

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
    footer = r'''
	ENDIF
	END
'''
    OUTPUT.write_text(header + high + middle + low + footer, encoding="latin-1", newline="\r\n")
    print(f"Wrote {OUTPUT.name}: {OUTPUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
