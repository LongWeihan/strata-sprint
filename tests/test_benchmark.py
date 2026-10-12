import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from strata_sprint import benchmark, bench_io


def script(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


class BenchmarkTests(unittest.TestCase):
    def test_portable_sequence_has_the_same_record_keys_as_published_validation(self):
        original = json.loads((Path(__file__).resolve().parents[1] / 'benchmarks/pro6000-2026-10-12/validation.json').read_text())
        def key(row): return row['task'], row.get('repeat'), row.get('tier'), row.get('turn')
        expected = [key(c) for c in original['variants'][0]['cases']]
        fixtures = [{'tier': tier, 'payload': benchmark.payload('fixture', 'context', 'PELICAN-STRATA-74931', 0)}
                    for tier in [4096, 32768, 122880]]
        def call(*_):
            return ({'ttft_seconds': .1, 'answer_sha256': 'fixture', 'finish': 'stop'},
                    {'answer': 'PELICAN-STRATA-74931', 'reasoning': ''})
        with tempfile.TemporaryDirectory() as d, patch.object(bench_io, 'prepare_cases', return_value=fixtures), \
             patch.object(bench_io, 'call', side_effect=call) as run, patch('builtins.print'):
            out = Path(d) / 'result.json'
            self.assertEqual(benchmark.main(['--label', 'fixture', '--output', str(out)]), 0)
            data = json.loads(out.read_text())
            self.assertEqual([key(c) for c in data['cases']], expected)
            self.assertEqual(run.call_count, 72)
            self.assertEqual(data['phase'], 'complete')

    def test_partial_run_is_refused_by_comparator(self):
        with self.assertRaises(ValueError):
            script('compare_runs').compare({'phase': 'failed'}, {'phase': 'complete'})

    def test_logit_comparison_rejects_mask_changes_and_detects_small_errors(self):
        import numpy as np
        compare = script('compare_logits').compare
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a', Path(d) / 'b'
            np.array([1, 2, -np.inf], dtype='<f4').tofile(a)
            np.array([1, 2, -np.inf], dtype='<f4').tofile(b)
            self.assertTrue(compare(a, b)['byte_equal'])
            np.array([1, 2.01, -np.inf], dtype='<f4').tofile(b)
            self.assertFalse(compare(a, b)['byte_equal'])
            self.assertGreater(compare(a, b)['kl_nats'], 0)
            np.array([1, 2, 0], dtype='<f4').tofile(b)
            with self.assertRaises(ValueError): compare(a, b)


if __name__ == '__main__': unittest.main()
