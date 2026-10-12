"""Run the published 70-record request sequence against an already running engine."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

CHECKS = [
    ('arithmetic', 'Return only the integer: 137 * 29.', '3973'),
    ('chinese', '只输出下列记录的编号，不要解释：设备=PRO6000，编号=海鸥-8392，状态=正常。', '海鸥-8392'),
    ('json', 'Extract as compact JSON with exactly keys name,count,enabled: name is Pelican, count is 17, enabled is true.', None),
    ('sort', 'Return only a JSON array containing these numbers in ascending order: 7, -3, 2, 7, 0, 19, -12.', None),
    ('code', 'Write Python stable merge_sort(xs) without external libraries. Return only the function in a fenced Python code block.', None),
    ('sql', 'Write SQL selecting user_id and COUNT(*) as total from events, where event_type equals login, grouped by user_id, ordered by total descending then user_id ascending. Return SQL only.', None),
    ('unicode', 'Reverse this list of strings; return JSON only: ["鹈鹕", "🚲", "café", "GPU"].', None),
    ('reasoning', 'Find the smallest positive integer divisible by all integers from 1 to 12. Explain briefly.', '27720'),
    ('constraints', 'Output exactly three bullet points in Chinese explaining why sorted data is required for binary search.', None),
]


def payload(model, kind, prompt, rep, thinking=False):
    return {'model': model, 'messages': [
        {'role': 'system', 'content': f'Precision benchmark {kind} trial {rep}.'},
        {'role': 'user', 'content': prompt}], 'max_tokens': 768, 'temperature': 0, 'seed': 6273,
        'timings': True, 'reasoning_budget_tokens': 256 if thinking else 0,
        'reasoning_effort': 'xhigh' if thinking else 'none',
        'chat_template_kwargs': {'enable_thinking': thinking}}


def main(argv=None):
    try:
        from . import bench_io as io
    except ImportError:
        raise SystemExit('Install benchmark dependencies: pip install -e ".[bench]"')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://127.0.0.1:8080')
    p.add_argument('--model', default=io.MODEL)
    p.add_argument('--label', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--fixtures', type=Path, default=Path('results/local/fixtures'))
    p.add_argument('--pid', type=int, help='Optional upstream server PID for RSS sampling')
    p.add_argument('--suite', choices=['validation', 'decode', 'context', 'resume'], default='validation')
    a = p.parse_args(argv)
    if a.output.exists():
        p.error('Output already exists; use a new path to preserve previous measurements')
    io.ROOT = a.fixtures; io.MODEL = a.model
    if os.environ.get('SPRINT_BENCH_API_KEY'):
        io.HTTP.headers['Authorization'] = 'Bearer ' + os.environ['SPRINT_BENCH_API_KEY']
    data = {'label': a.label, 'started_at': time.time(), 'suite': a.suite, 'cases': [],
            'method': 'request-side streaming TTFT; server-side decode timings; 1-second GPU samples'}
    def save(phase):
        data.update(phase=phase, updated_at=time.time())
        a.output.parent.mkdir(parents=True, exist_ok=True)
        temp = a.output.with_suffix('.tmp'); temp.write_text(json.dumps(data, indent=2)); temp.replace(a.output)
        print(phase, flush=True)
    def call(request):
        return io.call(a.url.rstrip('/'), request, a.pid)
    def make(kind, prompt, rep, thinking=False):
        return payload(a.model, kind, prompt, rep, thinking)
    try:
        save('warmup'); call(make('warmup', 'Reply OK.', 0))
        if a.suite == 'validation':
            for rep in range(3):
                for name, prompt, needle in CHECKS:
                    save(f'correctness {name} {rep}')
                    request = make(name, prompt, rep); request['max_tokens'] = 512
                    if rep == 2:
                        request.update(temperature=.7, top_p=.95, top_k=20, seed=3841)
                    row, raw = call(request)
                    row.update(task=name, repeat=rep, needle_passed=needle in raw['answer'] if needle else None)
                    if name in {'json', 'sort', 'unicode'}:
                        text = raw['answer'].strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
                        expected = {'json': {'name': 'Pelican', 'count': 17, 'enabled': True},
                                    'sort': [-12, -3, 0, 2, 7, 7, 19], 'unicode': ['GPU', 'café', '🚲', '鹈鹕']}[name]
                        try: row['semantic_passed'] = json.loads(text) == expected
                        except ValueError: row['semantic_passed'] = False
                    data['cases'].append(row)
        if a.suite in {'validation', 'decode'}:
            for rep in range(3):
                for name, prompt, thinking in io.TASKS:
                    save(f'decode {name} {rep}'); row, raw = call(make(name, prompt, rep, thinking))
                    row.update(task='decode_' + name, repeat=rep,
                               full_output_sha256=hashlib.sha256((raw['reasoning'] + '\0' + raw['answer']).encode()).hexdigest())
                    data['cases'].append(row)
        if a.suite in {'validation', 'context', 'resume'}:
            contexts = io.prepare_cases(a.url.rstrip('/'))
        if a.suite in {'validation', 'context'}:
            for rep in range(3):
                for case in contexts:
                    request = json.loads(json.dumps(case['payload']))
                    request['model'] = a.model
                    request['messages'][0]['content'] = f'Validation repeat {rep}. ' + request['messages'][0]['content']
                    save(f'context {case["tier"]} {rep}'); row, raw = call(request)
                    row.update(task='context', tier=case['tier'], repeat=rep,
                               retrieval_passed='PELICAN-STRATA-74931' in raw['answer'])
                    data['cases'].append(row)
        if a.suite in {'validation', 'resume'}:
            request = json.loads(json.dumps(contexts[1]['payload'])); request['model'] = a.model
            request['messages'][0]['content'] = 'Parked exact prefix. ' + request['messages'][0]['content']
            _, raw = call(request)
            request['messages'] += [{'role': 'assistant', 'content': raw['answer']},
                {'role': 'user', 'content': 'Write five sentences about the value of this exact checkpoint: ' + raw['answer']}]
            row, raw = call(request); row.update(task='warm_followup'); data['cases'].append(row)
            request['messages'] += [{'role': 'assistant', 'content': raw['answer']},
                                   {'role': 'user', 'content': 'State the checkpoint only.'}]
            for turn in range(12):
                save(f'interleaved {turn}')
                side, _ = call(make('interrupting_' + str(turn), 'Return only ' + str(turn + 137 * 29) + '.', turn))
                side.update(task='side_request', turn=turn); data['cases'].append(side)
                row, raw = call(request); row.update(task='interleaved', turn=turn,
                    retrieval_passed='PELICAN-STRATA-74931' in raw['answer']); data['cases'].append(row)
                request['messages'] += [{'role': 'assistant', 'content': raw['answer']},
                                       {'role': 'user', 'content': 'Repeat the checkpoint only.'}]
        data['completed_at'] = time.time(); save('complete')
        return 0
    except Exception as exc:
        data['error_type'] = type(exc).__name__; save('failed')
        raise


if __name__ == '__main__':
    raise SystemExit(main())
