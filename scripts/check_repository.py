"""Check tracked/public inputs, local documentation links and the upstream pin."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PIN = '7695859aa13afb248bdb4d36f9b2e95707db079d'


def main():
    names = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files'], text=True).splitlines()
    forbidden = {'.gguf', '.safetensors', '.sqlite', '.sqlite3', '.pyc', '.log'}
    for name in names:
        p = ROOT / name
        if not p.is_file(): continue  # gitlink
        assert p.suffix not in forbidden and '.env' != p.name, name
        if p.suffix in {'.json', '.md', '.py', '.yml', '.html'}:
            raw = p.read_text()
            assert not re.search(r'/Users/[A-Za-z0-9_. -]+/', raw), name
            assert not re.search(r'gh[pousr]_[A-Za-z0-9]{25,}|sk-[A-Za-z0-9]{24,}', raw), name
        if p.suffix == '.md':
            for href in re.findall(r'\]\(([^\s)]+)', p.read_text()):
                if href.startswith(('https:', 'http:', '#', 'mailto:')): continue
                dest = (p.parent / href.split('#')[0]).resolve()
                if dest.is_relative_to(ROOT / 'engine'): continue  # optional source checkout in CPU CI
                assert dest.exists(), f'{name}: broken link {href}'
    tree = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '--stage', 'engine'], text=True)
    assert PIN in tree and tree.startswith('160000'), 'Upstream gitlink drift'
    assert json.loads((ROOT / 'model-manifest.json').read_text())['model_weights_in_repository'] is False
    print('Public-file checks, document links and upstream pin verified.')


if __name__ == '__main__': main()
