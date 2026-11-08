#!/usr/bin/env python3
"""Build the mobile display provider for caihong.

The provider is the original IOMobileFramebuffer class with its constructor,
destructor and dispatch entry points redirected at our own NativeMobileDisplay.
Producing it needs two things an ordinary archive builder does not have:

* a prelinked image of the ORIGINAL kexts, so the class can be located. Kext
  symbols are stripped from the prelinked kernel, so the class is found by the
  fixed addresses the reference port qualified, and those addresses only hold if
  the same kernelcache and the same kext placement are used. They are, because
  this board pins the same kernelcache as the reference port.
* that image has to exist before the kernel links, so this builder makes one
  itself: prelink the bootstrap kernel against the IPSW kernelcache.

Runs as an archive builder (cwd is the build tree, before the final link).
"""
import hashlib
import json
import os
import pathlib
import struct
import subprocess
import sys

ROOT = pathlib.Path.cwd()
OUT = ROOT / 'build' / 'gop-framebuffer'
DRIVER = ROOT / 'drivers/GopFramebuffer' if (ROOT / 'drivers/GopFramebuffer').is_dir() else ROOT / 'drivers/NativeMobileDisplay'
CANDIDATE = ROOT / 'build' / 'native-prelink' / 'native-owner-mobile-graphics-candidate.macho'
KERNEL = ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped.noctf'
EMIT = ROOT / 'kits/NativePrelink/emit_prelink.py'

# From board.toml [ipsw] and [kernel.prelink]. The tree does not carry board.toml.
IPSW_URL = ('https://updates.cdn-apple.com/2025SpringFCS/fullrestores/122-77166/'
            'DCA6CFE8-90E9-4B92-880D-3DE171798E40/iPad_Pro_HFR_17.7.11_21H461_Restore.ipsw')
KERNELCACHE_SHA256 = 'f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7'
SLIDE = '-0x1000000'
ROOTS = [
    'com.apple.AppleFSCompression.AppleFSCompressionTypeZlib',
    'com.apple.driver.AppleARMPlatform',
    'com.apple.driver.AppleARMWatchdogTimer',
    'com.apple.driver.AppleAudioClockLibs',
    'com.apple.driver.AppleEffaceableStorage',
    'com.apple.driver.AppleIISController',
    'com.apple.driver.AppleM2ScalerCSCDriver',
    'com.apple.driver.AppleMobileFileIntegrity',
    'com.apple.driver.ApplePMGR',
    'com.apple.driver.IODARTFamily',
    'com.apple.filesystems.apfs',
    'com.apple.iokit.CoreAnalyticsFamily',
    'com.apple.iokit.IOAVFamily',
    'com.apple.iokit.IOAudio2Family',
    'com.apple.iokit.IOCECFamily',
    'com.apple.iokit.IOCryptoAcceleratorFamily',
    'com.apple.iokit.IOGPUFamily',
    'com.apple.iokit.IOHDCPFamily',
    'com.apple.iokit.IOMobileGraphicsFamily',
    'com.apple.iokit.IOReportFamily',
    'com.apple.iokit.IOSlowAdaptiveClockingFamily',
    'com.apple.iokit.IOStorageFamily',
    'com.apple.iokit.IOSurface',
    'com.apple.kec.Libm',
    'com.apple.kec.corecrypto',
    'com.apple.kext.AppleMatch',
    'com.apple.kext.CoreTrust',
    'com.apple.security.AppleImage4',
    'com.apple.security.sandbox',
    'com.apple.iokit.IOHIDFamily',
    'com.apple.iokit.IOHIDEventDriver',
]

# Verified against this board's prelinked image: the reference port's addresses
# still hold, because the kext placement is deterministic for a given kernelcache.
IOMFB_C2 = 0xfffffff00577b318
IOMFB_D2 = 0xfffffff00577b364
IOMFB_METACLASS = 0xfffffff006b313d8
IOMFB_TEXT = (0xfffffff00576c000, 0xfffffff00576c000 + 0x36f74)


def run(cmd, **kw):
    """Run and surface the child's output when it fails; the CI log is the only view."""
    options = {'capture_output': True, 'text': True, 'timeout': 1800}
    options.update(kw)
    result = subprocess.run([str(x) for x in cmd], **options)
    if result.returncode:
        print((result.stdout or '')[-4000:])
        print((result.stderr or '')[-4000:])
        raise SystemExit(f'command failed ({result.returncode}): {" ".join(str(x) for x in cmd[:3])} ...')
    return result.stdout


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def fail(message):
    print(f'display: {message}')
    raise SystemExit(message)


def kernelcache():
    """The decompressed arm64 kernelcache, via the driver's own IPSW reader."""
    # The tree carries the device scripts; the driver package lives above it.
    for candidate in (ROOT.parents[2] / 'scripts', ROOT.parent / 'scripts', ROOT / 'scripts'):
        if (candidate / 'unixnu' / 'ipsw.py').is_file():
            sys.path.insert(0, str(candidate))
            break
    else:
        fail('cannot find the unixnu driver package to read the IPSW')
    from unixnu import ipsw as ipsw_mod

    class Context:
        """Just enough of the driver's context for its IPSW reader."""
        board = {
            'ipsw': {
                'url': IPSW_URL, 'product': 'iPad7,1', 'version': '17.7.11', 'build': '21H461',
                'device_class': 'j120ap', 'chip_id': 0x8011, 'board_id': 12,
            },
            'kernel': {'prelink': {'kernelcache_sha256': KERNELCACHE_SHA256}},
        }
        out_root = ROOT.parent

    source = ipsw_mod.Ipsw(Context(), IPSW_URL)
    path = ipsw_mod.kernelcache(Context(), source)
    print(f'display: kernelcache {path} {path.stat().st_size} bytes')
    return path


def make_candidate(cache):
    CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
    if CANDIDATE.is_file():
        CANDIDATE.unlink()
    command = [sys.executable, EMIT, '--kernel', KERNEL, '--prelinked', cache,
               '--slide', SLIDE, '--output', CANDIDATE]
    for root in ROOTS:
        command += ['--root', root]
    print('display: prelink candidate')
    run(command, text=True)
    print(f'display: candidate {sha(CANDIDATE)}')
    return CANDIDATE


def check_candidate(candidate):
    """The addresses are only usable if the class really sits where the port expects."""
    data = candidate.read_bytes()
    sys.path.insert(0, str(ROOT / 'kits/NativePrelink'))
    from native_prelink import macho, backed_offset

    segments = macho(data)['segments']

    def read(va, size):
        at = backed_offset(segments, va, size, len(data))
        return data[at:at + size]

    first = struct.unpack('<I', read(IOMFB_C2, 4))[0]
    if first & 0xFFC00000 != 0xD1000000:      # sub sp, sp, #imm
        fail(f'IOMobileFramebuffer C2 at {IOMFB_C2:#x} does not start with a frame setup ({first:#010x})')
    for site, label in ((IOMFB_C2, 'C2'), (IOMFB_D2, 'D2')):
        word = struct.unpack('<I', read(site + 0x30 if label == 'C2' else site + 0x18, 4))[0]
        if word >> 26 != 0b100101:
            fail(f'the constructor/destructor call inside {label} is not a bl ({word:#010x})')
    print('display: candidate carries the expected IOMobileFramebuffer layout')


def compile_probe():
    """Build the provider probe with the kernel's own flags for this tree.

    The probe includes kernel headers, so it is compiled with the argument list
    the kernel build recorded for IOPlatformExpert, with only the source and the
    output swapped.
    """
    recipe = ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json'
    if not recipe.is_file():
        fail(f'no compile recipe to borrow: {recipe}')
    record = json.loads(recipe.read_text().strip().rstrip(','))
    command, skip = [], False
    for argument in record['arguments']:
        if skip:
            skip = False
            continue
        if argument == record['file']:
            # Ported from caihong: the file moved to this board's own kit
            command.append(str(ROOT / 'kits/tb321fu/MobileDisplayProviderProbe.cpp'))
        elif argument == '-o':
            command.extend(['-o', str(OUT / 'MobileDisplayProviderProbe.o')])
            skip = True
        elif (argument == '-Xclang' or argument.startswith('-W')
              or argument.startswith(('-clang-vendor-feature=', '-fno-odr-hash-protocols'))):
            # Apple-internal switches the kernel build passes through -Xclang; the
            # Xcode clang rejects them written out, so drop them with their pair.
            continue
        else:
            command.append(argument)
    command += ['-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                '-Wno-unnecessary-virtual-specifier', '-Wno-c99-designator',
                '-Wno-reorder-init-list', '-Wno-deprecated-enum-enum-conversion',
                '-I', str(ROOT / '.cache/xnu-work/osfmk')]
    run(command, cwd=record['directory'])
    return OUT / 'MobileDisplayProviderProbe.o'


def build_archive():
    OUT.mkdir(parents=True, exist_ok=True)
    print('display: compile NativeMobileDisplay')
    run([sys.executable, ROOT / 'scripts/build-arm-driver.py', 'NativeMobileDisplay'], text=True)

    obj = OUT / 'NativeMobileDisplay.o'
    if not obj.is_file():
        fail(f'{obj} was not produced')

    # The three symbols the driver imports from the original family. They are
    # bound to the addresses the original image uses, which is why the class has
    # to be located first.
    asm = OUT / 'original-bindings.S'
    asm.write_text(''.join(f'.globl {name}\n.set {name}, {value:#x}\n' for name, value in (
        ('__ZN19IOMobileFramebufferC2EPK11OSMetaClass', IOMFB_C2),
        ('__ZN19IOMobileFramebufferD2Ev', IOMFB_D2),
        ('__ZN19IOMobileFramebuffer10gMetaClassE', IOMFB_METACLASS),
    )))
    sdk = run(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    run(['xcrun', 'clang', '-target', 'arm64-apple-ios17.0', '-isysroot', sdk, '-Werror',
         '-c', asm, '-o', OUT / 'original-bindings.o'])

    llvm = pathlib.Path(run(['brew', '--prefix', 'llvm'], text=True).strip()) / 'bin'
    late = OUT / 'NativeMobileDisplay.late.o'
    run([llvm / 'llvm-objcopy', '--remove-section=__DATA,__mod_init_func',
         '--globalize-symbol=__GLOBAL__sub_I_NativeMobileDisplay.cpp', obj, late])

    probe = compile_probe()
    archive = OUT / 'libGopFramebuffer.late.a'
    archive.unlink(missing_ok=True)
    run(['xcrun', 'ar', 'rcs', archive, late, OUT / 'original-bindings.o', probe])
    return archive


def report(archive, candidate):
    sources = sorted({p.name for p in OUT.iterdir() if p.is_file()})
    document = {
        'kit_revision': subprocess.check_output(
            ['git', '-C', str(DRIVER), 'rev-parse', 'HEAD'],
            text=True).strip(),
        'archive_sha256': sha(archive),
        'candidate_sha256': sha(candidate),
        'source_sha256': {f'drivers/NativeMobileDisplay/{name}': sha(DRIVER / name)
                          for name in ('NativeMobileDisplay.cpp', 'OriginalMobileFramebufferABI.h')
                          if (DRIVER / name).is_file()},
        'objects': sources,
        'addresses': {'c2': IOMFB_C2, 'd2': IOMFB_D2, 'metaclass': IOMFB_METACLASS},
    }
    (OUT / 'build-report.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    print(f'display: {archive} {archive.stat().st_size} bytes')


def stub_archive():
    """A placeholder archive that only satisfies the probe call.

    The XNU source patch calls native_mobile_display_provider_probe() without a
    config guard, so a link without a display archive fails. Publish a stub at
    the path the kernel build expects, so it can produce the image the candidate
    is made from; the real archive replaces it afterwards.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    source = OUT / 'stub.c'
    source.write_text('/* placeholder: the real provider replaces this archive */\n'
                      'void native_mobile_display_provider_probe(void) {}\n')
    sdk = run(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    run(['xcrun', 'clang', '-target', 'arm64-apple-ios17.0', '-isysroot', sdk, '-Werror',
         '-c', source, '-o', OUT / 'stub.o'])
    archive = OUT / 'libGopFramebuffer.late.a'
    archive.unlink(missing_ok=True)
    run(['xcrun', 'ar', 'rcs', archive, OUT / 'stub.o'])
    (OUT / 'build-report.json').write_text(json.dumps({'archive_sha256': sha(archive)}, indent=2) + '\n')
    print('display: placeholder archive published for the parent build')


def ensure_kernel():
    """The bootstrap pass stops before the link, so there is no image to prelink.

    Build one with the display switched off: the kext placement depends on the
    kernelcache and the root set, not on this driver, so that image is a valid
    parent for the candidate. The outer build then relinks with the archive.
    """
    if KERNEL.is_file():
        return
    print('display: building a kernel image to prelink against')
    stub_archive()
    # The parent image only has to exist so the candidate can be made. Storage,
    # mockfs and the owner checks all need archives that this step builds later,
    # so they stay off here.
    env = {**os.environ, 'XNU_NATIVE_MOBILE_DISPLAY': '1', 'XNU_NATIVE_UFS': '0', 'XNU_SOURCE_MOCKFS': '0',
           'XNU_NATIVE_AES': '0', 'XNU_NATIVE_VIRTIO_BLOCK': '0', 'XNU_VERIFIED_ROOT_PROBE': '0',
           'XNU_OWNER_ROOT_AUDIT': '0', 'XNU_OWNER_ROOT_TRUST': '0',
           'XNU_BUILD_ARCHIVES': '1', 'XNU_BOOTSTRAP': '0'}
    result = subprocess.run(['bash', ROOT / 'scripts/build-xnu-4k-baseline.sh'],
                            cwd=ROOT, env=env, capture_output=True, text=True)
    if not KERNEL.is_file():
        stdout_tail = '\n'.join((result.stdout or '').splitlines()[-25:])
        stderr_tail = '\n'.join((result.stderr or '').splitlines()[-25:])
        fail(f'no kernel image to prelink against ({KERNEL}); '
             f'build exited {result.returncode}\n--- stdout ---\n{stdout_tail}\n--- stderr ---\n{stderr_tail}')


def main():
    ensure_kernel()
    if not EMIT.is_file():
        fail(f'{EMIT} is missing')
    cache = kernelcache()
    candidate = make_candidate(cache)
    check_candidate(candidate)
    archive = build_archive()
    report(archive, candidate)


if __name__ == '__main__':
    main()
