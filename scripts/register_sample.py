#!/usr/bin/env python3
"""Explicitly register the repository's offline protocol sample for the current user."""
import json
from pathlib import Path
import sys
from storyboarder.automation.registry import ScriptRegistry

if __name__ == '__main__':
    script = Path(__file__).resolve().parents[1] / 'examples' / 'sample_adapter.py'
    if not script.is_file():
        raise SystemExit('Run this helper from a complete Storyboarder source checkout.')
    result = ScriptRegistry().register(
        'offline-sample', [sys.executable, str(script)],
        description='Explicitly trusted offline slate generator; no provider or credentials.',
    )
    print(json.dumps(result, indent=2))
