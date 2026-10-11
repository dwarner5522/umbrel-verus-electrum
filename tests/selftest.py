'''Build-time check: block hashes and txids computed by this image must match Verus mainnet.

Covers every header generation (VerusHash 1.0, 2.0, 2.1, 2.2 and PBaaS headers with
variable-length solutions), so a miscompiled hash module fails the image build
instead of failing weeks into a sync.
'''
import json
import os
import sys

sys.path.insert(0, sys.argv[1])
from electrumx.lib.coins import Verus
from electrumx.lib.hash import hash_to_hex_str

vectors = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'blocks.json')))
failures = 0
for height, vector in sorted(vectors.items(), key=lambda item: int(item[0])):
    raw = bytes.fromhex(vector['block'])
    header = Verus.block_header(raw, int(height))
    deserializer = Verus.DESERIALIZER(raw, start=len(header))
    txids = [hash_to_hex_str(tx_hash) for _tx, tx_hash in deserializer.read_tx_block()]
    ok = (hash_to_hex_str(Verus.header_hash(header)) == vector['hash']
          and txids == vector['txids']
          and deserializer.cursor == len(raw))
    failures += not ok
    print('{:>8} {}'.format(height, 'ok' if ok else 'MISMATCH'))

if failures:
    sys.exit('{} of {} test blocks failed'.format(failures, len(vectors)))
print('all {} test blocks match mainnet'.format(len(vectors)))


# The header merkle cache hashes every header on the chain in one call. That call must work in
# batches (the unbatched version needs many gigabytes on mainnet) and still return the same hashes.
import asyncio
import hashlib

from electrumx.server.db import DB


class FakeCoin:
    header_hash = staticmethod(lambda header: hashlib.sha256(header).digest())


def batched_hashes(lengths, batch, height, count):
    headers = [bytes([n % 251]) * length for n, length in enumerate(lengths)]
    largest_read = 0

    async def read_headers(start, wanted):
        nonlocal largest_read
        largest_read = max(largest_read, wanted)
        found = headers[start:start + wanted]
        return b''.join(found), len(found)

    db = DB.__new__(DB)
    db.HEADER_HASH_BATCH = batch
    db.coin = FakeCoin
    db.read_headers = read_headers
    db.header_len = lambda n: lengths[n]
    hashes = asyncio.get_event_loop().run_until_complete(db.fs_block_hashes(height, count))
    assert hashes == [FakeCoin.header_hash(header) for header in headers[height:height + count]], (batch, height, count)
    assert largest_read <= batch, (largest_read, batch)


lengths = [140 + (n * 37) % 1400 for n in range(1000)]
for batch, height, count in [(64, 0, 1000), (64, 3, 640), (1000, 0, 1000), (7, 990, 10), (64, 5, 0), (64, 0, 1)]:
    batched_hashes(lengths, batch, height, count)
try:
    batched_hashes(lengths, 64, 990, 20)
except DB.DBError:
    pass
else:
    sys.exit('reading past the last header did not fail')
print('header hashes are read in batches')
