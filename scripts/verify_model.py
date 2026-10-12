"""Stream-check the two existing model shards. Downloads nothing."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    a = p.parse_args()
    manifest = json.loads((Path(__file__).resolve().parents[1] / 'model-manifest.json').read_text())
    for item in manifest['files']:
        path = a.directory / item['file']
        if not path.is_file() or path.stat().st_size != item['bytes']:
            raise SystemExit('Missing shard or incorrect size: ' + item['file'])
        digest = hashlib.sha256(); read = 0; last = -1
        with path.open('rb') as stream:
            while block := stream.read(16 * 1024 * 1024):
                digest.update(block); read += len(block); percent = int(read * 100 / item['bytes'])
                if percent // 10 != last:
                    print(f'{item["file"]}: {percent}% verified', flush=True); last = percent // 10
        if digest.hexdigest() != item['sha256']:
            raise SystemExit('SHA256 mismatch: ' + item['file'])
    print('Both shards match the frozen model manifest.')


if __name__ == '__main__': main()
