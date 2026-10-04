# Slim build of VerusCoin/verushashpy for a distributable image: links the system libsodium
# and never uses -march=native, so the module runs on CPUs other than the one that built it.
import platform

import pybind11
from setuptools import Extension, setup

machine = platform.machine().lower()
if machine in ('x86_64', 'amd64'):
    # Needed to compile the AES-NI/CLMUL code path; it is only taken when the CPU reports support.
    arch_flags = ['-msse4.2', '-maes', '-mpclmul']
elif machine in ('aarch64', 'arm64'):
    # Same idea for the ARMv8 crypto extensions (checked at runtime through the kernel's hwcaps).
    arch_flags = ['-march=armv8-a+crypto', '-flax-vector-conversions']
else:
    raise SystemExit('unsupported architecture: ' + machine)

setup(
    name='verushash',
    version='0.0.4',
    ext_modules=[Extension(
        'verushash',
        sorted([
            'src/compat/glibc_compat.cpp', 'src/compat/glibc_sanity.cpp',
            'src/compat/glibcxx_sanity.cpp', 'src/compat/strnlen.cpp',
            'src/crypto/haraka.c', 'src/crypto/haraka_portable.c',
            'src/crypto/ripemd160.cpp', 'src/crypto/sha256.cpp',
            'src/crypto/uint256.cpp', 'src/crypto/utilstrencodings.cpp',
            'src/crypto/verus_hash.cpp', 'src/crypto/verus_clhash.cpp',
            'src/crypto/verus_clhash_portable.cpp', 'src/support/cleanse.cpp',
            'src/blockhash.cpp', 'src/solutiondata.cpp', 'src/main.cpp',
        ]),
        include_dirs=[pybind11.get_include(), 'src/include', 'src'],
        libraries=['sodium'],
        define_macros=[('VERSION_INFO', '"0.0.4"')],
        extra_compile_args=['-O3', '-fexceptions', '-w'] + arch_flags,
    )],
    zip_safe=False,
)
