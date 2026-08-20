PYTHON ?= python3
Z80ASM ?= z80asm
BUILD_DIR ?= build
BUILDER := tools/native_build.py

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
