"""Compare complete, matching portable benchmark runs; print regressions too."""
import argparse
import json
from pathlib import Path
import statistics


def compare(a, b):
    if a.get('phase') != 'complete' or b.get('phase') != 'complete' or a.get('suite') != b.get('suite'):
        raise ValueError('Both runs must be complete and use the same suite')
    def key(c): return c['task'], c.get('repeat'), c.get('tier'), c.get('turn')
    left = {key(c): c for c in a['cases']}; right = {key(c): c for c in b['cases']}
    if len(left) != len(a['cases']) or len(right) != len(b['cases']) or left.keys() != right.keys():
        raise ValueError('Missing, extra or duplicate benchmark cases')
    groups = {}
    for k, original in left.items():
        label = original['task'] + (f' {original["tier"]}' if 'tier' in original else '')
        groups.setdefault(label, []).append((original, right[k]))
    rows = []
    for label, pairs in groups.items():
        first = [statistics.mean(p[i]['ttft_seconds'] for p in pairs) for i in [0, 1]]
        rows.append({'task': label, 'n': len(pairs), 'baseline_ttft': first[0], 'candidate_ttft': first[1],
                     'ttft_speedup': first[0] / first[1],
                     'text_equal': sum(x['answer_sha256'] == y['answer_sha256'] for x, y in pairs),
                     'baseline_check_failures': sum(any(x.get(k) is False for k in ['needle_passed','semantic_passed','retrieval_passed']) for x, _ in pairs),
                     'candidate_check_failures': sum(any(y.get(k) is False for k in ['needle_passed','semantic_passed','retrieval_passed']) for _, y in pairs)})
    return rows


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline', type=Path); p.add_argument('candidate', type=Path)
    a = p.parse_args(); print(json.dumps(compare(json.loads(a.baseline.read_text()), json.loads(a.candidate.read_text())), indent=2))
