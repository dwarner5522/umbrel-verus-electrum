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
