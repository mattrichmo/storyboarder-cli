#!/usr/bin/env python3
"""Offline protocol demonstration; makes a labelled slate, not a generated film still.

Usage: python sample_adapter.py /path/to/request.json /path/to/output-directory
It receives no database handle, project path or provider credentials.
"""
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: sample_adapter.py REQUEST_JSON OUTPUT_DIRECTORY")
    request_file, output = Path(sys.argv[1]), Path(sys.argv[2])
    request = json.loads(request_file.read_text())
    if request.get("schema") != "storyboarder.job/v1":
        raise SystemExit("Unsupported request version")
    output.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 720), "#edece5")
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 70, 1210, 650), outline="#77836f", width=2)
    draw.text((100, 112), "STORYBOARDER / ADAPTER TEST", fill="#45533e", font=ImageFont.load_default(size=22))
    draw.text((100, 282), request["target"]["title"][:48], fill="#283024", font=ImageFont.load_default(size=35))
    draw.text((100, 550), "Protocol demonstration only. Replace with your own trusted asset script.", fill="#45533e", font=ImageFont.load_default(size=20))
    path = output / "candidate.png"
    image.save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"schema": "storyboarder.result/v1", "provider": "offline-sample", "model": "labelled-slate-v1", "outputs": [{"key": "candidate-01", "path": "candidate.png", "title": request["target"]["title"], "notes": "Demonstration slate produced by the offline adapter; not a photorealistic or approved production frame.", "sha256": digest}]}
    (output / "result.json").write_text(json.dumps(manifest, indent=2))
    print("One candidate written. Review it in Storyboarder before importing.")


if __name__ == "__main__":
    main()
