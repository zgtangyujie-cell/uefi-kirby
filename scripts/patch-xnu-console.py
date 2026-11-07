#!/usr/bin/env python3
"""Redirect the kernel's printf() to the frame buffer.

The kernel's video console never starts on this board: every printf() goes to a
serial port that does not exist. This patches printf() to branch into
scripts/xnu-console.c, which formats the message with the same stack-based
variadic convention and draws it on the screen.

Must run on the UNPATCHED kernel (the entry probe's own patch changes the entry
sequence this script verifies). Run it before patch-xnu-entry-probe.py.

Usage: patch-xnu-console.py <kernel.macho>
"""
import importlib.util
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("probe", ROOT / "scripts" / "patch-xnu-entry-probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

CAVE_MIN = 0xD00
CAVE_ALIGN = 0x10


def text_segments(data):
    """(vmaddr, filesize, fileoff, name) for segments that hold executable code."""
    _, _, _, _, ncmds = struct.unpack_from("<IiiII", data, 0)
    offset = 32
    found = []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, offset)
        if cmd == 0x19:
            name = data[offset + 8:offset + 24].rstrip(b"\0").decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, offset + 24)
            if filesize and "TEXT" in name:
                found.append((vmaddr, filesize, fileoff, name))
        offset += size
    return found


def find_cave(data, near_va):
    """A zero run big enough for the console code, taken from the END of a text segment.

    Scanning from the start would claim the padding the entry probe keeps for its
    own stage code and the panic screen, so search backwards: the tail padding of
    a segment is the safe place.
    """
    segments = text_segments(data)
    order = [seg for seg in segments if seg[0] <= near_va < seg[0] + seg[1]]
    order += [seg for seg in segments if seg not in order]
    for base, filesize, offset, name in order:
        at = filesize - CAVE_MIN
        while at >= 0:
            at &= ~(CAVE_ALIGN - 1)
            if data[offset + at:offset + at + CAVE_MIN] == bytes(CAVE_MIN):
                return base + at
            at -= CAVE_ALIGN
    raise SystemExit(f"no {CAVE_MIN:#x} byte zero run in an executable segment")


def assemble(source, va, workdir, vinfo_va, machine_idle, page_total, page_free):
    brew = "/opt/homebrew/opt/llvm/bin"
    tools = {}
    for name in ("clang", "ld.lld", "llvm-objcopy", "llvm-nm", "llvm-size", "llvm-objdump"):
        tools[name] = shutil.which(name) or f"{brew}/{name}"
        if not Path(tools[name]).exists():
            raise SystemExit(f"{name} is required (looked in PATH and {brew})")
    clang, lld, objcopy, nm, size, objdump = (tools[n] for n in
        ("clang", "ld.lld", "llvm-objcopy", "llvm-nm", "llvm-size", "llvm-objdump"))

    font_dir = ROOT / "scripts" / "fbconsole"
    obj, elf, binary = (workdir / n for n in ("console.o", "console.elf", "console.bin"))
    subprocess.run([clang, "--target=aarch64-none-elf", "-ffreestanding", "-fno-builtin",
                    "-fno-stack-protector", "-mgeneral-regs-only", "-fno-pic", "-mcmodel=tiny",
                    "-Oz", f"-DVINFO={vinfo_va:#x}UL", f"-DMACHINE_IDLE={machine_idle:#x}UL",
                    f"-DPAGE_TOTAL={page_total:#x}UL", f"-DPAGE_FREE={page_free:#x}UL", f"-I{font_dir}", "-c", source,
                    "-o", obj], check=True)
    sizes = subprocess.run([size, "--format=berkeley", obj], capture_output=True, text=True,
                           check=True).stdout.splitlines()[-1].split()
    if int(sizes[1]) or int(sizes[2]):
        raise SystemExit(f"console code has writable data (data {sizes[1]}, bss {sizes[2]})")

    script = workdir / "console.ld"
    script.write_text("SECTIONS { . = %#x; .text : { *(.text.a_entry) *(.text.b_main) *(.text*) *(.rodata*) } "
                      "/DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.ARM.*) } }\n" % va)
    subprocess.run([lld, "-T", script, "-e", "console_printf", obj, "-o", elf], check=True)
    subprocess.run([objcopy, "-O", "binary", "-j", ".text", elf, binary], check=True)

    load = None
    for line in subprocess.run([objdump, "-h", elf], capture_output=True, text=True, check=True).stdout.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == ".text":
            load = int(parts[3], 16)
    entry = None
    beat = None
    for line in subprocess.run([nm, elf], capture_output=True, text=True, check=True).stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == "console_printf":
            entry = int(parts[0], 16)
        if len(parts) == 3 and parts[2] == "heartbeat_wrapper":
            beat = int(parts[0], 16)
    if load is None or entry != load:
        raise SystemExit(f"console_printf must be the first byte (entry {entry}, load {load})")
    if beat is None:
        raise SystemExit("heartbeat_wrapper is missing")
    return binary.read_bytes(), load, entry, beat


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    kernel = Path(sys.argv[1])
    data = bytearray(kernel.read_bytes())
    probe.load_segments(data)
    # The symbol table already carries final addresses; the entry-probe rebase is
    # not needed here and cannot run once that probe has rewritten the entry.
    names = {name: va for va, name in probe.kernel_symbols(kernel).items()}

    printf_va = names.get("_printf")
    if printf_va is None:
        raise SystemExit("no _printf in the kernel")
    vinfo_va = names.get("_boot_progress_panic_vinfo") or names.get("_vinfo")
    if vinfo_va is None:
        raise SystemExit("no _vinfo in the kernel")
    first = struct.unpack_from("<I", data, probe.file_offset(printf_va))[0]
    if first == 0 or first == 0xFFFFFFFF:
        raise SystemExit("printf() is not where the symbol table says")

    table = probe.kernel_symbols(kernel)          # address -> name, for find_call
    symbols = {name: va for va, name in table.items()}
    for need in ("_machine_idle", "_processor_idle", "_max_mem", "_vm_page_pages", "_vm_page_free_count"):
        if need not in symbols:
            raise SystemExit(f"no {need} in the kernel")
    call_va, callee = probe.find_call(data, table, "_processor_idle", "_machine_idle", 1)

    cave = find_cave(data, printf_va)
    with tempfile.TemporaryDirectory() as tmp:
        code, load, entry, beat = assemble(ROOT / "scripts" / "xnu-console.c", cave, Path(tmp), vinfo_va,
                                           callee, symbols["_vm_page_pages"], symbols["_vm_page_free_count"])
    if load + len(code) > cave + CAVE_MIN:
        raise SystemExit(f"console code is {len(code):#x} bytes, the cave holds {CAVE_MIN:#x}")
    if any(data[probe.file_offset(load):probe.file_offset(load) + len(code)]):
        raise SystemExit("the chosen padding is not empty")

    data[probe.file_offset(load):probe.file_offset(load) + len(code)] = code
    struct.pack_into("<I", data, probe.file_offset(printf_va), probe.branch(printf_va, entry))
    # bl <heartbeat>: keep the call to machine_idle, then tick
    delta = (beat - call_va) >> 2
    struct.pack_into("<I", data, probe.file_offset(call_va), 0x94000000 | (delta & 0x3FFFFFF))
    kernel.write_bytes(data)
    print(f"patched {kernel.name}: printf() at {printf_va:#x} -> console at {entry:#x}; "
          f"idle call at {call_va:#x} -> heartbeat at {beat:#x} ({len(code):#x} bytes)")


if __name__ == "__main__":
    main()
