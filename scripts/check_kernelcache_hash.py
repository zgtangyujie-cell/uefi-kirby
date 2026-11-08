"""Compare our kernelcache against the one caihong's mobile-display builder pins.

`caihong/scripts/build-native-mobile-display.py:36` hardcodes

    KERNELCACHE_SHA256 = 'f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7'

because the (IOMobileFramebuffer) class is located by *fixed addresses* that
only hold for that exact kernelcache with that exact kext placement.  If our
kernelcache hash differs, those addresses are meaningless and the mobile-display
route cannot be copied straight across.

Usage: check_kernelcache_hash.py
"""

import glob
import hashlib
import os

CAIHONG = "f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7"

CANDIDATES = [
    r"D:\WorkBuddy AI\Y700-UNIXNU\work\UniXNU\out\ipsw\21H461\kernelcache.decompressed",
    r"D:\WorkBuddy AI\Y700-UNIXNU\work\UniXNU\out\ipsw\21H461\kernelcache.lzfse",
    r"D:\WorkBuddy AI\Y700-UNIXNU\work\ipsw\kernelcache.release.ipad7",
]


def main() -> int:
    print("caihong pins  " + CAIHONG)
    print()
    found = False
    for path in CANDIDATES:
        if os.path.exists(path):
            data = open(path, "rb").read()
            digest = hashlib.sha256(data).hexdigest()
            same = digest == CAIHONG
            print("%s" % path)
            print("  %d bytes  sha256=%s  %s"
                  % (len(data), digest, "★ MATCHES caihong" if same else "(differs)"))
            if same:
                found = True
        else:
            print("%s : absent" % path)

    # Also look for any kernelcache* file in the UniXNU out tree.
    for path in glob.glob(r"D:\WorkBuddy AI\Y700-UNIXNU\work\UniXNU\out\**\kernelcache*", recursive=True):
        if path in CANDIDATES:
            continue
        data = open(path, "rb").read()
        digest = hashlib.sha256(data).hexdigest()
        same = digest == CAIHONG
        print("%s" % path)
        print("  %d bytes  sha256=%s  %s"
              % (len(data), digest, "★ MATCHES caihong" if same else "(differs)"))
        if same:
            found = True

    print()
    if found:
        print("RESULT: at least one local kernelcache matches caihong's, so the")
        print("        hardcoded IOMobileFramebuffer addresses are valid for us.")
        return 0
    print("RESULT: no local kernelcache matches caihong's hash.")
    print("        The mobile-display builder's fixed addresses do not apply as-is.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
