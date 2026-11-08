#!/usr/bin/env python3
"""Build the QcomXnuUsbDebug kernel archive with the selected XNU's compile record.

This lives in the device repository on purpose: tree.py copies <device>/scripts/
into the build tree, so both this script and the module next to it land where
archive_plan() and build-xnu-4k-baseline.sh look for them.  Module sources are
under scripts/qcom-xnu-usb-debug; its own scripts/build.py does the compilation
and the import/export audit, using the real pe_kprintf.o record so the archive
matches the kernel it will be linked into.

Run from the kernel archive stage: the bootstrap pass has already left
build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/pexpert/DEVELOPMENT/pe_kprintf.o.json.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'scripts/qcom-xnu-usb-debug'
RECORD = ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/pexpert/DEVELOPMENT/pe_kprintf.o.json'
OUT = ROOT / 'build/qcom-xnu-usb-debug'
ARCHIVE = OUT / 'libQcomXnuUsbDebug.a'
# build.py refuses to write inside its source tree, so it builds under .cache and
# this script copies the audited archive to the path the kernel link consumes.
WORK = ROOT / '.cache/qcom-xnu-usb-debug-build'
SOC = 'soc/Sm8650.h'


def xcrun(tool):
    return subprocess.check_output(['xcrun', '-f', tool], text=True).strip()


def main():
    if not (MODULE / 'scripts/build.py').is_file():
        raise SystemExit(f'missing module sources: {MODULE}')
    if not (MODULE / SOC).is_file():
        raise SystemExit(f'missing SoC profile: {MODULE / SOC}')
    if not RECORD.is_file():
        raise SystemExit(f'missing compile record: {RECORD}; the bootstrap pass must run first')
    OUT.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-B', str(MODULE / 'scripts/build.py'),
               '--compile-record', str(RECORD),
               '--soc', SOC,
               '--ar', xcrun('ar'),
               '--nm', xcrun('nm'),
               '--output', str(WORK),
               '--replace']
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise SystemExit('QcomXnuUsbDebug module build failed')
    built = WORK / 'libQcomXnuUsbDebug.a'
    if not built.is_file():
        raise SystemExit(f'module build produced no archive: {built}')
    shutil.copy2(built, ARCHIVE)
    report = json.loads((WORK / 'build-report.json').read_text())
    report['soc'] = SOC
    report['archive'] = str(ARCHIVE)
    (OUT / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('QcomXnuUsbDebug: %s sha256 %s' % (ARCHIVE, report.get('archive_sha256', '')[:16]))


if __name__ == '__main__':
    main()
