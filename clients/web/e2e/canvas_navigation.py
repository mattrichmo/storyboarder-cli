#!/usr/bin/env python3
"""Issue #19 regression against the compiled client and a disposable live API.

Build clients/web first. Requires the optional Playwright dependency and Chromium.
Creates its own temporary workspace; never reads or modifies production projects.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time

import httpx
from playwright.async_api import async_playwright
import uvicorn

from storyboarder.api.server import create_app
from storyboarder.application.projects import Workspace
from storyboarder.application.service import Service

from browser_acceptance import load_bridge


async def check_navigation(url, projects, args, report):
    async with async_playwright() as playwright, httpx.AsyncClient(base_url=url, trust_env=False) as api:
        options = {"headless": True}
        if args.chromium:
            options["executable_path"] = args.chromium
        browser = await playwright.chromium.launch(**options)
        page = await browser.new_page(viewport={"width": 1440, "height": 1024})
        page.set_default_timeout(7000)
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        bridge = None
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        try:
            if args.transport_bridge:
                bridge = await load_bridge(page, url)
            else:
                await page.goto(url, wait_until="networkidle")
            await page.get_by_role("button", name="Story canvas", exact=True).wait_for()
            await page.wait_for_function("() => !document.querySelector('.loading-state')")
            await page.screenshot(path=str(output / "shell.png"), full_page=True)
            assert await page.get_by_role("heading", level=1).count() == 1
            report["checks"].append("Compiled app shell loads from the live loopback server.")

            async def state(pid):
                response = await api.get(f"/api/v1/projects/{pid}/state")
                response.raise_for_status()
                return response.json()

            async def canvas():
                await page.get_by_role("button", name="Story canvas", exact=True).click()
                await page.wait_for_selector(".graph-node")
                await page.wait_for_function(
                    "() => !document.querySelector('.canvas-status').textContent.includes('Loading…')"
                )

            async def position(node):
                return await node.evaluate(
                    "node => {const m=new DOMMatrix(node.style.transform);return {x:m.e,y:m.f};}"
                )

            async def warns_on_unload():
                return await page.evaluate("""() => {
                    const event=new Event('beforeunload',{cancelable:true});
                    window.dispatchEvent(event);return event.defaultPrevented;
                }""")

            async def open_project(title):
                await page.get_by_role("button", name="Storyboarder workspace", exact=True).click()
                await page.locator(".project-row").filter(
                    has=page.get_by_role("heading", name=title, exact=True)
                ).click()
                await page.get_by_role("heading", name=title, exact=True).wait_for()
                await canvas()

            a, b = projects
            original = await state(a["id"])
            await canvas()
            await page.get_by_label("Saved arrangement", exact=True).select_option(a["layout"])
            node = page.locator(f'[data-node-id="{a["sequence"]}"]')
            assert await position(node) == {"x": 0, "y": 0}
            await node.focus()
            await node.press("ArrowRight")
            assert await position(node) == {"x": 10, "y": 0}
            # Reproduction: navigate immediately after the keyboard edit.
            await page.get_by_role("button", name="Story outline", exact=True).click()
            await page.locator(".canvas-page").wait_for(state="detached")
            protected_away = await warns_on_unload()
            await canvas()
            assert await position(node) == {"x": 10, "y": 0}, "Navigation discarded the dirty position"
            assert protected_away, "Dirty draft must warn even away from Canvas"
            await page.get_by_text("Unsaved arrangement · kept while you navigate", exact=True).wait_for()
            assert await page.get_by_label("Saved arrangement", exact=True).input_value() == a["layout"]
            unchanged = await state(a["id"])
            assert unchanged["entities"] == original["entities"]
            assert unchanged["layouts"] == original["layouts"]
            report["checks"].append("ArrowRight → outline → Canvas retains x=10 without canonical writes.")

            # Browser/hash routes bypass App.go; drafts must survive these too.
            await page.evaluate("location.hash='outline'")
            await page.locator(".canvas-page").wait_for(state="detached")
            await page.go_back()
            await node.wait_for()
            assert await position(node) == {"x": 10, "y": 0}
            await page.go_forward()
            await page.locator(".canvas-page").wait_for(state="detached")
            await canvas()
            assert await position(node) == {"x": 10, "y": 0}
            report["checks"].append("Hash navigation and browser back/forward preserve the draft.")

            # A restored filter must not auto-fit away the user's draft viewport.
            await page.get_by_role("button", name="Collapse Sequence A", exact=True).click()
            await page.get_by_label("Search canvas cards", exact=True).fill("Sequence A")
            await page.wait_for_function(
                "() => !document.querySelector('.canvas-status').textContent.includes('Loading…')"
                " && document.querySelectorAll('.graph-node').length===1"
            )
            await page.get_by_role("button", name="Zoom in", exact=True).click()
            view = await page.locator(".canvas-world").get_attribute("style")
            await page.get_by_role("button", name="Project overview", exact=True).click()
            await canvas()
            assert await page.get_by_label("Search canvas cards", exact=True).input_value() == "Sequence A"
            assert await page.locator(".canvas-world").get_attribute("style") == view
            await page.get_by_role("button", name="Expand Sequence A", exact=True).wait_for()
            report["checks"].append("Filters, collapsed cards and the zoomed viewport survive unmount.")

            # Failed saves must retain the dirty draft for a later retry.
            async def reject_save(route):
                await route.fulfill(status=409, json={"error": {"code": "revision_conflict"}})
            await page.route("**/commands/canvas.save", reject_save)
            await page.get_by_role("button", name="Save arrangement", exact=True).click()
            await page.get_by_text("This item changed elsewhere.", exact=False).wait_for()
            await page.unroute("**/commands/canvas.save", reject_save)
            await page.get_by_role("button", name="Story outline", exact=True).click()
            await canvas()
            assert await position(node) == {"x": 10, "y": 0}
            assert await warns_on_unload()
            report["checks"].append("Failed save leaves the draft dirty and intact across navigation.")

            # Each project owns its draft; opening another project never resets it.
            await open_project("Navigation B")
            await page.get_by_label("Saved arrangement", exact=True).select_option(b["layout"])
            other = page.locator(f'[data-node-id="{b["sequence"]}"]')
            assert await position(other) == {"x": 0, "y": 0}
            await other.focus()
            await other.press("Shift+ArrowRight")
            await open_project("Navigation A")
            assert await position(node) == {"x": 10, "y": 0}
            assert await page.get_by_label("Saved arrangement", exact=True).input_value() == a["layout"]
            report["checks"].append("Switching projects isolates drafts and restores the original arrangement.")

            async def save():
                # A restored conflict stays locked until the user compares/reapplies it.
                button = page.get_by_role("button", name="Save arrangement", exact=True)
                if await button.is_disabled():
                    await page.get_by_role("button", name="Refresh latest saved revision", exact=True).click()
                    await page.locator(".layout-conflict-review").wait_for()
                    button = page.get_by_role("button", name="Reapply merged arrangement", exact=True)
                async with page.expect_response(lambda response: response.url.endswith("/commands/canvas.save")) as pending:
                    await button.click()
                response = await pending.value
                assert response.ok, await response.text()
                await page.get_by_text("Unsaved arrangement · kept while you navigate", exact=True).wait_for(state="hidden")
                return await response.json()

            saved = await save()
            assert saved["id"] == a["layout"] and saved["revision"] == 2
            after = await state(a["id"])
            layout = next(item for item in after["layouts"] if item["id"] == a["layout"])
            assert layout["positions"][a["sequence"]] == {"x": 10, "y": 0}
            assert after["entities"] == original["entities"]
            await page.get_by_role("button", name="Story outline", exact=True).click()
            assert await warns_on_unload(), "Inactive project's dirty draft must still warn"
            await canvas()
            assert await position(node) == {"x": 10, "y": 0}
            assert not await page.get_by_text("Unsaved arrangement · kept while you navigate", exact=True).count()
            await node.focus()
            await node.press("ArrowRight")
            await page.get_by_role("button", name="Story outline", exact=True).click()
            await canvas()
            saved = await save()
            assert saved["id"] == a["layout"] and saved["revision"] == 3
            assert saved["positions"][a["sequence"]] == {"x": 20, "y": 0}
            report["checks"].append("Save after return updates the same layout at revisions 2 and 3.")

            # A genuine same-field conflict must retain its baseline and explicit choice on return.
            current_session = (await api.get("/api/v1/session")).json()
            external_positions = dict(saved["positions"])
            external_positions[a["sequence"]] = {"x": 90, "y": 0}
            external = await api.post(
                f'/api/v1/projects/{a["id"]}/commands/canvas.save',
                headers={"X-Storyboarder-Token": current_session["token"]},
                json={"name": saved["name"], "mode": saved["mode"], "positions": external_positions,
                      "settings": saved["settings"], "layout_id": saved["id"], "revision": saved["revision"]},
            )
            assert external.status_code == 200, external.text
            await node.focus()
            await node.press("ArrowRight")
            await page.get_by_role("button", name="Save arrangement", exact=True).click()
            await page.get_by_role("button", name="Refresh latest saved revision", exact=True).click()
            choice = page.locator(".layout-conflict-review").get_by_role("button", name="Keep local", exact=True)
            await choice.click()
            await page.get_by_role("button", name="Story outline", exact=True).click()
            await canvas()
            assert await position(node) == {"x": 30, "y": 0}
            assert await choice.get_attribute("aria-pressed") == "true"
            assert await page.get_by_role("button", name="Save arrangement", exact=True).is_disabled()
            async with page.expect_response(lambda response: response.url.endswith("/commands/canvas.save")) as pending:
                await page.get_by_role("button", name="Reapply merged arrangement", exact=True).click()
            recovered = await (await pending.value).json()
            assert recovered["revision"] == 5
            assert recovered["positions"][a["sequence"]] == {"x": 30, "y": 0}
            await page.get_by_text("Unsaved changes", exact=True).wait_for(state="hidden")
            report["checks"].append("Real same-field conflict and Keep local choice survive unmount and reapply under CAS.")

            await node.focus()
            await node.press("ArrowRight")
            await page.get_by_role("button", name="Scene board", exact=True).click()
            gate = page.get_by_role("dialog", name="Unsaved canvas arrangement")
            await gate.get_by_role("button", name="Stay", exact=True).click()
            assert await position(node) == {"x": 40, "y": 0}
            await page.get_by_role("button", name="Scene board", exact=True).click()
            await gate.get_by_role("button", name="Discard changes", exact=True).click()
            await page.get_by_role("button", name="Story flow", exact=True).click()
            await node.wait_for()
            assert await position(node) == {"x": 30, "y": 0}
            report["checks"].append("Mode replacement offers Stay and Discard; discarded geometry returns to the saved layout.")

            await open_project("Navigation B")
            assert await position(other) == {"x": 50, "y": 0}
            await save()
            await page.get_by_role("button", name="Story outline", exact=True).click()
            assert not await warns_on_unload(), "No dirty drafts remain after both saves"
            report["checks"].append("Unload protection covers inactive drafts and clears once all are saved.")
            await page.screenshot(path=str(output / "passed.png"), full_page=True)
            assert not report["page_errors"], report["page_errors"]
            report["passed"] = True
        except Exception as error:
            report["failure"] = str(error)
            await page.screenshot(path=str(output / "failure.png"), full_page=True)
            raise
        finally:
            (output / "canvas-navigation-report.json").write_text(json.dumps(report, indent=2) + "\n")
            if bridge:
                await bridge.aclose()
            await browser.close()


def main(args):
    report = {"checks": [], "page_errors": [], "transport": "bridge" if args.transport_bridge else "loopback"}
    with tempfile.TemporaryDirectory(prefix="storyboarder-canvas-navigation-") as temporary:
        workspace = Workspace(Path(temporary) / "workspace")
        workspace.init()
        projects = []
        for suffix in ("A", "B"):
            project = workspace.create("Navigation " + suffix, "navigation-" + suffix.lower())
            service = Service(project)
            sequence = service.create_entity("sequence", "Sequence " + suffix)
            service.create_entity("scene", "Scene " + suffix, sequence["id"])
            layout = service.save_layout("Working arrangement", "story", {sequence["id"]: {"x": 0, "y": 0}}, {})
            projects.append({"id": project.id, "sequence": sequence["id"], "layout": layout["id"]})
        workspace.switch(projects[0]["id"])
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(create_app(workspace=workspace, port=port), host="127.0.0.1", port=port, log_level="error"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if not thread.is_alive() or time.monotonic() >= deadline:
                    raise RuntimeError("Disposable acceptance server failed to start")
                time.sleep(.02)
            asyncio.run(check_navigation(f"http://127.0.0.1:{port}", projects, args, report))
        finally:
            server.should_exit = True
            thread.join(timeout=10)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium", default=os.environ.get("CHROMIUM_EXECUTABLE"))
    parser.add_argument("--output", default="artifacts/canvas-navigation")
    parser.add_argument("--transport-bridge", action="store_true")
    print(json.dumps(main(parser.parse_args()), indent=2))
