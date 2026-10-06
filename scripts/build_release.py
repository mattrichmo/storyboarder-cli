#!/usr/bin/env python3
"""Build and verify wheel/sdist using setuptools; frontend must already be built."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from storyboarder import SCHEMA_VERSION

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rebuild-web', action='store_true')
    args = parser.parse_args()
    if args.rebuild_web:
        subprocess.run(['node', 'build.mjs'], cwd=ROOT/'clients/web', check=True)
    static = ROOT/'src/storyboarder/static'
    if not (static/'index.html').is_file() or not (static/'build.json').is_file():
        raise SystemExit('Build clients/web first; a release cannot contain an empty frontend.')
    build = json.loads((static/'build.json').read_text())
    entry = Path(build['entry'])
    style = Path(build['style']) if build.get('style') else None
    if entry.is_absolute() or '..' in entry.parts or not build['entry'].startswith('assets/app-'):
        raise SystemExit('Frontend build manifest contains an unsafe application path.')
    if not (static/entry).is_file():
        raise SystemExit('Frontend build manifest points to a missing asset.')
    import hashlib
    if hashlib.sha256((static/entry).read_bytes()).hexdigest() != build['sha256']:
        raise SystemExit('Frontend build hash does not match its manifest. Rebuild clients/web/.')
    index = (static/'index.html').read_text()
    if f'/{build["entry"]}' not in index:
        raise SystemExit('Frontend index and build manifest point to different application bundles.')
    if style:
        if style.is_absolute() or '..' in style.parts or not build['style'].startswith('assets/app-') or not (static/style).is_file():
            raise SystemExit('Frontend build manifest points to an invalid stylesheet.')
        if hashlib.sha256((static/style).read_bytes()).hexdigest() != build.get('style_sha256') or f'/{build["style"]}' not in index:
            raise SystemExit('Frontend stylesheet hash or index reference does not match its manifest.')
    migration_dir = ROOT/'src/storyboarder/storage/migrations'
    migration_files = sorted(migration_dir.glob('*.sql'))
    try:
        migration_versions = [int(path.name.split('_', 1)[0]) for path in migration_files]
    except ValueError:
        raise SystemExit('Migration files must begin with their numeric schema version.')
    if sorted(migration_versions) != list(range(1, SCHEMA_VERSION + 1)) or len(set(migration_versions)) != len(migration_versions):
        raise SystemExit(f'Incomplete migration set: release schema {SCHEMA_VERSION} requires migrations 1 through {SCHEMA_VERSION}.')
    os.chdir(ROOT)
    destination = ROOT/'dist'
    destination.mkdir(exist_ok=True)
    from setuptools.build_meta import build_wheel, build_sdist
    wheel = destination / build_wheel(str(destination))
    sdist = destination / build_sdist(str(destination))
    required = {'storyboarder/static/index.html', 'storyboarder/static/'+build['entry'],
                'storyboarder/static/assets/react-runtime.js',
                'storyboarder/static/THIRD_PARTY_LICENSES.txt',
                *{'storyboarder/storage/migrations/'+path.name for path in migration_files}}
    if style:
        required.add('storyboarder/static/'+build['style'])
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        missing = required - names
        if missing:
            raise SystemExit('Incomplete wheel: '+', '.join(sorted(missing)))
        if any(name.lower().endswith(('.ttf','.otf','.woff','.woff2')) for name in names):
            raise SystemExit('Do not package font files.')
    print(json.dumps({'wheel':str(wheel),'sdist':str(sdist),'packaged_frontend':build['entry']},indent=2))

if __name__ == '__main__':
    main()
