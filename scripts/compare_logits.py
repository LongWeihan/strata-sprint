"""Compare raw little-endian float32 logits without exporting the vectors."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def compare(a, b):
    x = np.fromfile(a, dtype='<f4'); y = np.fromfile(b, dtype='<f4')
    if x.size == 0 or x.shape != y.shape:
        raise ValueError('Empty vectors or different shapes')
    if np.isnan(x).any() or np.isnan(y).any() or np.isposinf(x).any() or np.isposinf(y).any():
        raise ValueError('NaN or positive infinity in diagnostic logits')
    finite = np.isfinite(x)
    if not np.array_equal(finite, np.isfinite(y)) or not finite.any():
        raise ValueError('Finite masks differ or contain no usable logits')
    u, v = x[finite].astype('f8'), y[finite].astype('f8')
    lp = u - u.max(); lp -= np.log(np.exp(lp).sum())
    lq = v - v.max(); lq -= np.log(np.exp(lq).sum())
    return {'byte_equal': x.tobytes() == y.tobytes(), 'top1_equal': int(x.argmax()) == int(y.argmax()),
            'max_abs_difference': float(np.max(np.abs(u - v))),
            'kl_nats': float(np.sum(np.exp(lp) * (lp - lq))),
            'reference_sha256': hashlib.sha256(x.tobytes()).hexdigest(),
            'candidate_sha256': hashlib.sha256(y.tobytes()).hexdigest()}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference', type=Path); p.add_argument('candidate', type=Path)
    a = p.parse_args(); print(json.dumps(compare(a.reference, a.candidate), indent=2))
