# Pete's Master Z80 ROM

Custom 8K IMSAI 8080 monitor ROM for the S-100 Z80 CPU Board V2.

This repository is intended to track the verified IMSAI Monitor V5.5G code base used in the physical machine. The monitor occupies a logical 4K window at F000h-FFFFh and uses the V2 CPU board's D3h-controlled EEPROM A12 path to select between two physical 4K pages in a 28C64/27C64.

The current source of truth is `IMSAI_MONITOR_V5.5G_MERGED.z80`, derived from John Monahan's Master Z80 Monitor sources and carrying the IMSAI-specific page-switching, console-selection, menu, and banner changes.
