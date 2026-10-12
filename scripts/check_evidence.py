"""Recompute release claims and verify the sanitized evidence manifests."""
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'benchmarks/pro6000-2026-10-12'


def main():
    read = lambda n: json.loads((DATA / n).read_text())
    for file in read('provenance.json')['files']:
        assert hashlib.sha256((DATA / file['file']).read_bytes()).hexdigest() == file['export_sha256'], file['file']
    summary = read('summary.json')
    total = sum(sum(len(v['cases']) for v in read(name)['variants'])
                for name in ['screen.json', 'long.json', 'precision.json', 'validation.json'])
    assert total == 449
    baseline, sprint = read('validation.json')['variants'][:2]
    def mean(v, task, tier=None):
        return statistics.mean(c['ttft_seconds'] for c in v['cases']
                               if c['task'] == task and (tier is None or c.get('tier') == tier))
    a, b = [mean(v, 'interleaved') for v in [baseline, sprint]]
    assert abs(a / b - summary['main_conversation_resume_ttft_seconds']['speedup']) < 1e-10
    assert round(a / b, 1) == 38.3
    assert mean(sprint, 'context', 4096) > mean(baseline, 'context', 4096)
    numbers = read('validation-logits-summary.json')['validation_selected']
    assert numbers['answer_equal'] == numbers['answer_total'] == 70
    assert numbers['byte_equal_rows'] == 49 and numbers['rows'] == 61
    assert read('cache-parity.json')['passed'] is True
    assert read('math-supplement.json')['passed'] is True
    # Preserve the original output-cap failures rather than relabel them.
    for v in [baseline, sprint]:
        assert sum(c.get('needle_passed') is False for c in v['cases'] if c['task'] == 'reasoning') == 3
    assert summary['engine']['source_changes'] is False
    print('Evidence verified: 449 records; 38.3x resume; regression and truncated checks retained.')


if __name__ == '__main__': main()
