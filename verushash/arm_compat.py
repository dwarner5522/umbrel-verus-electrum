'''Make VerusCoin/verushashpy compile on arm64.

Its sources already contain ARM code paths written against the SSE2NEON.h that the Verus daemon
shipped at the time, but three headers still include x86-only headers unconditionally, haraka.c lacks the
daemon's ARM AES round, and the SSE2NEON.h file itself is missing from the repository. x86 builds are unaffected.
'''
import pathlib
import sys

src = pathlib.Path(sys.argv[1]) / 'src' / 'crypto'

NEON_OR_X86 = '''#if defined(__arm__) || defined(__aarch64__)
#include "crypto/SSE2NEON.h"
#else
#include "immintrin.h"
#endif'''

CLHASH = '''#if defined(__arm__) || defined(__aarch64__)
#include "crypto/SSE2NEON.h"
#include <sys/auxv.h>
#include <asm/hwcap.h>
#else
#include <cpuid.h>
#include <x86intrin.h>
#endif'''

# The AES round the non-portable Haraka code needs, as the Verus daemon defined it for ARM.
HARAKA_C = '''#if defined(__arm__) || defined(__aarch64__)
#include "crypto/SSE2NEON.h"
__m128i _mm_aesenc_si128(__m128i a, __m128i RoundKey)
{
    return vreinterpretq_s32_u8(veorq_u8(vaesmcq_u8(vaeseq_u8(vreinterpretq_u8_s32(a), vdupq_n_u8(0))), vreinterpretq_u8_s32(RoundKey)));
}
#endif
#include "haraka.h"'''


def replace(name, old, new):
    path = src / name
    text = path.read_text()
    if old not in text:
        sys.exit('{}: expected text not found, the upstream source has changed'.format(name))
    path.write_text(text.replace(old, new, 1))


replace('haraka.h', '#include "immintrin.h"', NEON_OR_X86)
replace('haraka_portable.h', '#include "immintrin.h"', NEON_OR_X86)
replace('verus_clhash.h', '#include <cpuid.h>\n#include <x86intrin.h>', CLHASH)
replace('haraka.c', '#include "haraka.h"', HARAKA_C)
