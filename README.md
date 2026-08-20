# IMSAI 8080 Monitor V5.6 Target ROM

This is the target-state 8K ROM for the present IMSAI 8080 configuration:

- S100Computers Z80 V2 CPU board
- P39 on pins 7-8 for software-controlled 4K ROM paging
- Console I/O board at ports 00H/01H, selected at build time
- S100Computers Serial I/O board, port A at A1H/A3H
- Dual IDE/CF interface at ports 30H-34H
- Altair FDC+ at its default ports 08H-0AH
- No DSI FDS code
- No auxiliary processor support

## Important hardware settings

1. Keep the Z80 V2 CPU board's P39 jumper on pins 7-8. This is the setting
   already proven with the V5.5G ROM and allows port D3H bit 1 to select the
   lower or upper 4K half of the 28C64.
2. Keep the FDC+ onboard PROM disabled. The CPU ROM supplies CDBL at CPU
   address FF00H when its high page is selected. Enabling both ROMs at the
   same address can cause bus contention.
3. CDBL supports an FDC+ configured to appear as an original Altair 8-inch
   drive or an Altair Minidisk. For a directly connected Shugart 8-inch drive,
   use FDC+ drive type 1. CDBL is not the boot loader for the FDC+ 1.5 MB or
   iCOM/IBM-3740 modes.

## Boot behavior

After reset, the ROM displays the IMSAI banner and starts an approximately
three-second IDE/CF countdown. Press any key to cancel automatic boot and enter
the monitor. If no key is received, the existing IDE/CF CP/M loader runs.

Monitor boot commands:

- `B` - boot menu: IDE/CF, Altair FDC+, or monitor
- `C` - boot the Altair FDC+ through CDBL
- `P` - boot CP/M from IDE/CF immediately
- `H` - display the build-time hardware/configuration table
- `Ctrl-C` - boot the configured IDE/CF device

The `L`, `O`, and `W` command slots are disabled. Versafloppy, ZFDC,
CP/M 1.4 compatibility-table, auxiliary-processor, and DSI code are absent.
The reset path no longer writes to the retired floppy, auxiliary-CPU, or PIC
ports.

## Why CDBL instead of DBL or MBL

The attached `DBL.ASM` is the original 256-byte Altair 8-inch disk boot loader
and would work through an FDC+ in Altair 8-inch mode. Martin Eberhard's CDBL is
also 256 bytes at FF00H, but automatically supports both the Altair 8-inch and
Minidisk formats. Mike Douglas ships CDBL in the FDC+ PROM for this reason.
MBL is a cassette/paper-tape loader, not a multi-floppy loader.

The unmodified published CDBL 2.05 image is included under `third_party/` with
its source. CDBL relocates itself to RAM at 4C00H, reads the boot file through
ports 08H-0AH, loads it at 0000H, and jumps to 0000H. On error it emits its
single-letter code to several original Altair terminal ports; port 01H reaches
the configured Console I/O board.

Sources:

- https://deramp.com/downloads/altair/hardware/fdc%2B/FDC%2B%20Manual.pdf
- https://deramp.com/downloads/altair/software/roms/custom_roms/M%20Eberhard%20Improved%20ROMs/

## Native Ubuntu build

The preferred development path now assembles
`IMSAI_MONITOR_V5.6_TARGET_MERGED.z80` with the Ubuntu `z80asm` package and
then constructs the complete 8K device image from the two assembled 4K banks.

Install the build prerequisites once:

```sh
sudo apt update
sudo apt install make python3 z80asm
```

Then, after pulling source changes:

```sh
git pull
make
```

The programmer-ready image is:

```text
build/IMSAI_MONITOR_V5.6_TARGET_28C64_8K.BIN
```

It is exactly 8192 bytes: the physical lower 4K bank followed by the physical
upper 4K bank. This is the complete image for an 8K x 8 28C64 or 27C64.

Useful targets:

```sh
make          # assemble both ROM pages and create BIN/HEX/checksums
make verify   # also require an exact match with the checked-in release BINs
make release  # copy the newly assembled BIN/HEX/checksums to the repo root
make clean
```

`make verify` is especially useful before changing the source: it proves that
the native assembler path reproduces the known V5.6 release byte-for-byte.
After an intentional source change, use `make`, test the result, and use
`make release` when that build should become the new checked-in release image.

### Historical SLR source compatibility

The monitor source originated with SLR Z80ASM and retains a few SLR-specific
syntax conveniences. `tools/build_from_source.py` converts only those source
syntax details to the stricter syntax accepted by Ubuntu `z80asm` (for example,
case-insensitive symbols, accumulator shorthand, and physical padding between
later `ORG` locations). The actual Z80 opcodes are emitted by `z80asm`; the
Python tool does not synthesize the monitor machine code.

The generated strict-source files, assembler listings, and labels are retained
under `build/` for inspection.

## Programming

With `minipro`, program the freshly built AT28C64 image with:

```sh
minipro -p AT28C64 -w build/IMSAI_MONITOR_V5.6_TARGET_28C64_8K.BIN
```

For a 27C64, select the exact 27C64 device supported by your programmer and
write the same 8192-byte BIN file.

## Legacy patch builder and verification

`build_imsai_rom.py` remains in the repository as the address-checked builder
used to create the first V5.6 target image from the known V5.4 bank binaries.
`verify_target_rom.py` retains the detailed static assertions for that build.
They are useful as historical/reference tooling, but normal source development
should now use `make` so changes flow from Z80 source to the burnable ROM image.

The V5.5G bank-switch and Console I/O base was previously tested in the IMSAI
hardware; the V5.6 automatic boot, menu, hardware status, and FDC+ CDBL path
still require their first hardware test.
