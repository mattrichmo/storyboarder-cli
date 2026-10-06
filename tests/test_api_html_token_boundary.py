import os
import shutil
import socket
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager

import pytest
import uvicorn

from storyboarder.api.server import create_app


@contextmanager
def loopback_server(service):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(project=service.root, port=port),
            host="127.0.0.1",
            port=port,
            log_level="error",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(base + "/api/v1/session", timeout=0.2):
                    break
            except (OSError, urllib.error.URLError):
                if not thread.is_alive():
                    raise RuntimeError("local API server exited before becoming ready")
                time.sleep(0.05)
        else:
            raise RuntimeError("local API server did not become ready")
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _export_url(base, project_id, relative):
    return f"{base}/api/v1/projects/{project_id}/files/{relative}"


def _assert_isolated(headers):
    policy = headers.get("content-security-policy") or headers["Content-Security-Policy"]
    assert "sandbox allow-same-origin" in policy
    assert "script-src 'none'" in policy
    assert "default-src 'none'" in policy
    assert "connect-src" not in policy
    assert "form-action 'none'" in policy


def test_export_documents_are_isolated_and_board_preview_still_works(service, story):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    chromium = (
        os.environ.get("STORYBOARDER_CHROMIUM")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if not chromium:
        pytest.skip("a local Chromium executable is required for the browser regression")

    project_id = service.project.id
    attack_dir = service.root / "exports" / "boards" / "token-boundary"
    attack_dir.mkdir(parents=True, exist_ok=True)
    (attack_dir / "attack.js").write_text(
        "fetch('/api/v1/session').then(r=>r.json()).then(s=>{"
        "window.__tokenReadable=typeof s.token==='string'&&s.token.length>0;"
        f"return fetch('/api/v1/projects/{project_id}/commands/asset.create',{{"
        "method:'POST',headers:{'Content-Type':'application/json',"
        "'X-Storyboarder-Token':s.token},"
        "body:JSON.stringify({title:location.pathname.endsWith('.svg')?"
        "'Unauthorized SVG token write':'Unauthorized HTML token write',type:'character'})"
        "});}).then(r=>window.__writeStatus=r.status).catch(()=>{});",
        encoding="utf-8",
    )
    (attack_dir / "attack.html").write_text(
        "<!doctype html><script src='attack.js'></script>", encoding="utf-8"
    )
    (attack_dir / "attack.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' "
        "xmlns:xlink='http://www.w3.org/1999/xlink'>"
        "<script type='application/ecmascript' xlink:href='attack.js'></script></svg>",
        encoding="utf-8",
    )
    board = service.export_board(story["sequence"]["id"], "html")

    with loopback_server(service) as base:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, executable_path=chromium, args=["--no-sandbox"]
            )
            page = browser.new_page()
            try:
                for extension, mime, title in (
                    ("html", "text/html", "Unauthorized HTML token write"),
                    ("svg", "image/svg+xml", "Unauthorized SVG token write"),
                ):
                    url = _export_url(
                        base,
                        project_id,
                        f"exports/boards/token-boundary/attack.{extension}",
                    )
                    response = page.goto(url, wait_until="load", timeout=10000)
                    assert response is not None and response.status == 200
                    assert response.headers["content-type"].startswith(mime)
                    page.wait_for_timeout(250)
                    observed = page.evaluate(
                        "({tokenReadable:window.__tokenReadable||false,"
                        "writeStatus:window.__writeStatus||null})"
                    )
                    assert observed == {"tokenReadable": False, "writeStatus": None}, (
                        f"{extension} document reached the local API write path: {observed}"
                    )
                    assert service.list_entities(query=title)["total"] == 0
                    _assert_isolated(response.headers)

                with urllib.request.urlopen(
                    _export_url(
                        base,
                        project_id,
                        "exports/boards/token-boundary/attack.html?download=true",
                    )
                ) as attack_download:
                    assert "attachment" in attack_download.headers["Content-Disposition"]
                    _assert_isolated(attack_download.headers)

                board_url = _export_url(base, project_id, board["view"])
                preview = page.goto(board_url, wait_until="load", timeout=10000)
                assert preview is not None and preview.status == 200
                assert preview.headers["content-type"].startswith("text/html")
                assert "Content-Disposition" not in preview.headers
                _assert_isolated(preview.headers)
                rendered = page.evaluate(
                    "({background:getComputedStyle(document.body).backgroundColor,"
                    "images:[...document.images].map(i=>({loaded:i.complete,width:i.naturalWidth}))})"
                )
                assert rendered["background"] == "rgb(244, 242, 236)"
                assert rendered["images"]
                assert all(image["loaded"] and image["width"] > 0 for image in rendered["images"])
                assert service.list_entities(query="Unauthorized HTML token write")["total"] == 0
                assert service.list_entities(query="Unauthorized SVG token write")["total"] == 0
            finally:
                browser.close()
