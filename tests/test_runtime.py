import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

from strata_sprint.profile import MODEL, clean_environment, option, tune, validate_profile, write_config, validate_access
from strata_sprint.supervisor import native_state, should_restart, stop_owned


def base():
    return {'exe': 'build/strata', 'cwd': 'engine', 'tokenizer': 'pack/tokenizer',
        'args': ['--native', 'models/' + MODEL, '--pack', 'pack', '--ple-gguf', 'models/part2.gguf',
                 '--expert-profile', 'data/expert-profile.bin', '--mtp', 'mtp',
                 '--kv', 'fp16', '--spec', '4', '--max-context', '131072', '--prefill', 'auto',
                 '--spec-min-p', '0.5', '--expert-cache', 'auto', '--resident-budget-gib', '8',
                 '--pool-workers', '3', '--pcie-frac', '0'],
        'sampling': {'temperature': 1, 'top_p': .95, 'top_k': 20}, 'api_key': 'fixture-secret',
        'reasoning_effort': 'high', 'reasoning_budget_tokens': 16384}


class ProfileTests(unittest.TestCase):
    def test_native_child_env_does_not_authenticate_public_http_server(self):
        config = {'host': '0.0.0.0', 'env': {'STRATA_API_KEY': 'child-only'}}
        with self.assertRaises(ValueError): validate_access(config, {})
        validate_access(config, {'STRATA_API_KEY': 'server-key'})
        validate_access({**config, 'api_key': ['one', 'two']}, {})

    def test_empty_public_credentials_do_not_pass_preflight(self):
        for key in ['', '  ', ',,', [''], []]:
            with self.assertRaises(ValueError): validate_access({'host': '0.0.0.0', 'api_key': key}, {})

    def test_preserves_model_sampling_auth_and_thinking_without_mutating_input(self):
        original = base(); saved = copy.deepcopy(original)
        result = tune(original, '/tmp')
        self.assertEqual(original, saved)
        for key in ('sampling', 'api_key', 'reasoning_effort', 'reasoning_budget_tokens'):
            self.assertEqual(result[key], original[key])
        self.assertEqual(Path(option(result['args'], '--native')).name, MODEL)
        self.assertEqual(option(result['args'], '--kv'), 'fp16')
        validate_profile(result)

    def test_relative_paths_keep_same_assets_after_moving_config(self):
        result = tune(base(), '/tmp/example')
        self.assertEqual(result['exe'], str(Path('/tmp/example/engine/build/strata').resolve()))
        self.assertEqual(option(result['args'], '--pack'), str(Path('/tmp/example/engine/pack').resolve()))

    def test_duplicate_tuning_cannot_override_selected_values(self):
        config = base(); config['args'] += ['--prefill', '16384', '--conversation-cache-mib', '0']
        result = tune(config, '/tmp')
        self.assertEqual(option(result['args'], '--prefill'), '8192')
        self.assertEqual(option(result['args'], '--conversation-cache-mib'), '16384')

    def test_malformed_or_duplicate_precision_is_rejected(self):
        for suffix in [['--kv', 'q8'], ['--prefill']]:
            config = base(); config['args'] += suffix
            with self.assertRaises(ValueError): tune(config, '/tmp')

    def test_lower_precision_and_wrong_model_are_not_silently_changed(self):
        for key, value in [('--kv', 'q8'), ('--native', 'another.gguf'), ('--spec', '8')]:
            config = base(); config['args'][config['args'].index(key) + 1] = value
            with self.assertRaises(ValueError): tune(config, '/tmp')

    def test_inherited_kernel_flags_removed_but_auth_and_cuda_retained(self):
        env = {'STRATA_QFUSE': '1', 'STRATA_DUMP_FIRST_LOGITS': '/private',
               'STRATA_API_KEY': 'fixture', 'STRATA_ALLOWED_HOSTS': 'host', 'LD_LIBRARY_PATH': '/cuda'}
        cleaned = clean_environment(env)
        self.assertEqual(set(cleaned), {'STRATA_API_KEY', 'STRATA_ALLOWED_HOSTS', 'LD_LIBRARY_PATH'})

    def test_low_memory_rejected_and_operator_cap_recorded(self):
        for amount in [32, 64, 159, True]:
            with self.assertRaises(ValueError): tune(base(), '/tmp', amount)
        config = tune(base(), '/tmp', 192)
        self.assertEqual(option(config['args'], '--memory-limit-mib'), str(192 * 1024))

    def test_private_config_atomic_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'config.json'; write_config(p, base())
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(p.read_text())['api_key'], 'fixture-secret')
            self.assertEqual(len(list(Path(d).iterdir())), 1)

    def test_profile_drift_and_hidden_kernel_switch_fail(self):
        config = tune(base(), '/tmp'); config['env']['STRATA_LFUSE'] = '1'
        with self.assertRaises(ValueError): validate_profile(config)
        config = tune(base(), '/tmp'); config['args'][config['args'].index('--prefill') + 1] = '16384'
        with self.assertRaises(ValueError): validate_profile(config)


class RecoveryTests(unittest.TestCase):
    def test_loading_active_and_unknown_are_never_forcibly_restarted(self):
        for loaded, native in [(None, True), (False, True), (None, False), (False, None), (True, True)]:
            _, restart = should_restart(loaded, native, 10, 900, True, 300)
            self.assertFalse(restart)

    def test_confirmed_exit_requires_three_observations(self):
        streak = 0
        for expected in [False, False, True]:
            streak, restart = should_restart(False, False, streak, 20, True, 300)
            self.assertEqual(restart, expected)

    def test_startup_failure_respects_grace_and_observation_uncertainty_resets_streak(self):
        self.assertFalse(should_restart(False, False, 5, 10, False, 300)[1])
        self.assertTrue(should_restart(False, False, 5, 301, False, 300)[1])
        self.assertEqual(should_restart(None, False, 5, 900, True, 300), (0, False))

    def test_exited_wrapper_still_cleans_its_group_once(self):
        process = types.SimpleNamespace(pid=12345, poll=lambda: 1, wait=lambda **_: 1)
        with patch('strata_sprint.supervisor.os.killpg', side_effect=ProcessLookupError) as kill:
            stop_owned(process); stop_owned(process)
        kill.assert_called_once_with(12345, signal.SIGTERM)

    @unittest.skipUnless(sys.platform == 'linux', 'Live orphan-process recovery targets Linux')
    def test_owned_group_stops_child_even_after_wrapper_exit(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / 'child.pid'
            program = ("import subprocess,sys,pathlib; "
                       "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); "
                       f"pathlib.Path({str(marker)!r}).write_text(str(p.pid))")
            proc = subprocess.Popen([sys.executable, '-c', program], start_new_session=True)
            proc.wait(timeout=10); child = int(marker.read_text())
            try:
                # Limit the zombie-reaping wait in a fixture; TERM still reaches the orphan.
                with patch('strata_sprint.supervisor.time.monotonic', side_effect=[0, 21]):
                    stop_owned(proc)
                stop_owned(proc)  # Idempotent: no signal sent twice after PID reuse.
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    result = subprocess.run(['ps', '-o', 'stat=', '-p', str(child)], capture_output=True, text=True)
                    if not result.stdout.strip() or result.stdout.strip().startswith('Z'):
                        break
                    time.sleep(.05)
                else: self.fail('Owned orphan child survived cleanup')
            finally:
                try: os.kill(child, signal.SIGKILL)
                except ProcessLookupError: pass

    def test_unknown_proc_is_not_reported_absent(self):
        self.assertIsNone(native_state(99999999, '/missing'))


class StreamingTests(unittest.TestCase):
    def run_fixture(self, complete):
        from strata_sprint import bench_io
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                calls.append(1); self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                events = [{'choices': [{'delta': {'content': 'OK'}, 'finish_reason': None}]}]
                if complete:
                    events.append({'choices': [{'delta': {}, 'finish_reason': 'stop'}],
                                   'usage': {'completion_tokens': 1}})
                for event in events:
                    self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
                if complete: self.wfile.write(b'data: [DONE]\n\n')
            def log_message(self, *_): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with patch.object(bench_io, 'resources', return_value={}):
                if complete:
                    row, raw = bench_io.call(f'http://127.0.0.1:{server.server_port}', {}, None)
                    self.assertEqual(raw['answer'], 'OK'); self.assertEqual(row['finish'], 'stop')
                else:
                    with self.assertRaisesRegex(RuntimeError, 'outcome unknown'):
                        bench_io.call(f'http://127.0.0.1:{server.server_port}', {}, None)
            self.assertEqual(len(calls), 1)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_complete_sse(self): self.run_fixture(True)
    def test_truncated_sse_is_not_a_success_or_replayed(self): self.run_fixture(False)


if __name__ == '__main__': unittest.main()
