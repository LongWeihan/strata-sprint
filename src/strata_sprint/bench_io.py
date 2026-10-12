"""Streaming timing and deterministic fixtures adapted from the recorded GPU experiment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import threading
import time

import psutil
import requests

ROOT = Path('results/local')
MODEL = 'Qwen3.8-Flash-Next-GSQ-RCO-abliterated-IQ3_S-00001-of-00002.gguf'
HTTP = requests.Session()
HTTP.trust_env = False
TASKS = [
    ('code', 'Write a Python module containing a stable merge sort, binary search, and a heap-based merge of sorted iterators, with type hints and doctests. Return code only.', False),
    ('reasoning', 'Find the number of binary strings of length 40 with no three consecutive 1s. Derive a recurrence and calculate the exact integer. Explain why the recurrence is correct.', True),
    ('prose', 'Explain how a compiler turns source code into an executable, in six detailed paragraphs, including parsing, type checking, optimization, linking, and debugging information.', False),
]


def resources(pid):
    output = {}
    try:
        gpu = subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu,power.draw',
                              '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3)
        vals = gpu.stdout.strip().split(',')
        output.update(gpu_mib=float(vals[0]), gpu_util=float(vals[1]), power_w=float(vals[2]))
        p = psutil.Process(pid) if pid else None
        output['process_rss_bytes'] = sum(x.memory_info().rss for x in ([p,*p.children(recursive=True)] if p else []) if x.is_running())
    except (ValueError, OSError, psutil.Error, subprocess.SubprocessError):
        pass
    for suffix,key in [('usage_in_bytes','cgroup_memory_bytes'),('limit_in_bytes','cgroup_limit_bytes')]:
        p = Path('/sys/fs/cgroup/memory/memory.'+suffix)
        if p.exists(): output[key] = int(p.read_text())
    output['system_available_bytes'] = psutil.virtual_memory().available
    return output


def call(base, payload, pid):
    samples = []
    stop = threading.Event()
    def monitor():
        while not stop.is_set():
            samples.append(resources(pid))
            stop.wait(1)
    thread = threading.Thread(target=monitor,daemon=True)
    thread.start()
    start = time.monotonic()
    first = None
    answer = ''
    reasoning = ''
    usage = timings = None
    finish = None
    done = False
    chunks = 0
    try:
        with HTTP.post(base+'/v1/chat/completions',json={**payload,'stream':True,
                'stream_options':{'include_usage':True}},stream=True,timeout=(10,900)) as r:
            r.raise_for_status()
            for line in r.iter_lines(chunk_size=1):
                if not line.startswith(b'data: '): continue
                if line[6:] == b'[DONE]':
                    done = True
                    break
                event = json.loads(line[6:])
                if event.get('error'): raise RuntimeError(str(event['error']))
                for choice in event.get('choices',[]):
                    delta = choice.get('delta',{})
                    text = delta.get('content') or ''
                    think = delta.get('reasoning_content') or delta.get('reasoning') or ''
                    if text or think:
                        if first is None: first = time.monotonic()-start
                        chunks += 1
                    answer += text
                    reasoning += think
                    finish = choice.get('finish_reason') or finish
                usage = event.get('usage') or usage
                timings = event.get('timings') or timings
        if not done or finish is None:
            raise RuntimeError('Incomplete inference stream; outcome unknown; no request was replayed')
        elapsed = time.monotonic()-start
    finally:
        stop.set();thread.join(timeout=5)
    summary = dict(seconds=round(elapsed,4),ttft_seconds=round(first,4) if first else None,
                   usage=usage,timings=timings,finish=finish,answer_chars=len(answer),
                   reasoning_chars=len(reasoning),stream_content_events=chunks,
                   answer_sha256=hashlib.sha256(answer.encode()).hexdigest())
    for key in ['gpu_mib','process_rss_bytes','cgroup_memory_bytes','power_w']:
        values=[s[key] for s in samples if key in s]
        if values: summary['peak_'+key]=max(values)
    if usage and first and elapsed>first:
        summary['wall_output_tokens_per_second']=round(max(0,usage.get('completion_tokens',0)-1)/(elapsed-first),2)
    return summary,dict(answer=answer,reasoning=reasoning,samples=samples)


def prepare_cases(base):
    ROOT.mkdir(parents=True, exist_ok=True)
    path=ROOT/'context-fixtures.json'
    if path.exists(): return json.loads(path.read_text())
    cases=[]
    for target in [4096,32768,122880]:
        prefix=f'Benchmark context tier {target}. Return only the exact value assigned to SECRET_CODE. Do not explain.'
        def payload(n):
            lines=[f'Entry {i:06d}: ordinary test data for a deterministic retrieval benchmark.' for i in range(n)]
            lines.insert(len(lines)//2,'SECRET_CODE = PELICAN-STRATA-74931')
            return {'model':MODEL,'messages':[{'role':'system','content':prefix},
                {'role':'user','content':'\n'.join(lines)+'\nWhat is SECRET_CODE?'}],
                'temperature':0,'seed':6273,'max_tokens':64,'cache_prompt':False,'timings':True,
                'reasoning_effort':'none','chat_template_kwargs':{'enable_thinking':False}}
        low,high=0,target//5
        for _ in range(18):
            mid=(low+high+1)//2
            p=payload(mid)
            cr=HTTP.post(base+'/v1/messages/count_tokens',json={'model':p['model'],
                 'system':prefix,'messages':p['messages'][1:],'thinking':{'type':'disabled'}},timeout=60)
            cr.raise_for_status()
            if cr.json()['input_tokens']<=target:low=mid
            else:high=mid-1
            if low>=high:break
        cases.append({'tier':target,'payload':payload(low)})
    path.write_text(json.dumps(cases))
    return cases
