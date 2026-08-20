PYTHON ?= python3
Z80ASM ?= z80asm
BUILD_DIR ?= build
BUILDER := tools/build_from_source.py

.PHONY: all build verify release clean

all: build

build:
	$(PYTHON) $(BUILDER) --assembler "$(Z80ASM)" --build-dir "$(BUILD_DIR)"

verify:
	$(PYTHON) $(BUILDER) --assembler "$(Z80ASM)" --build-dir "$(BUILD_DIR)" --verify-reference

release:
	$(PYTHON) $(BUILDER) --assembler "$(Z80ASM)" --build-dir "$(BUILD_DIR)" --release

clean:
	rm -rf "$(BUILD_DIR)"
