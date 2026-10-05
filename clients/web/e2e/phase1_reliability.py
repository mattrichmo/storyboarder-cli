#!/usr/bin/env python3
"""Focused browser regressions for the confirmed phase-one UI failures.

Run against a normally served loopback Storyboarder origin.  The image tool
fixture is cancelled while queued and is never executed.
"""
from pathlib import Path
import argparse
import asyncio
import json
import re
import sys
import uuid

import httpx
from playwright.async_api import async_playwright


async def main(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "transport": "normal loopback navigation",
        "url": args.url,
        "passed": [],
        "failed": [],
        "never_run": [],
        "responsive": [],
        "expected_http_errors": [],
        "expected_conflicts": [],
        "console_errors": [],
        "page_errors": [],
    }
    cases = [
        "canvas_space_enter_parity",
        "inspector_tabs_and_responsive_focus",
        "context_failure_retry",
        "context_stale_owner_response",
        "usage_failure_retry_preserves_target",
        "stable_layout_id_conflict_and_save_as_new",
        "queued_cancel_outcome_notice",
    ]
    async with async_playwright() as playwright:
        options = {"headless": True}
        if args.chromium:
            options["executable_path"] = args.chromium
        browser = await playwright.chromium.launch(**options)
        page = await browser.new_page(viewport={"width": 1440, "height": 1024}, device_scale_factor=1)
        page.set_default_timeout(8000)
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))

        def console_error(message):
            if message.type != "error":
                return
            if "503 (Service Unavailable)" in message.text:
                report["expected_http_errors"].append(message.text)
            elif "409 (Conflict)" in message.text:
                report["expected_conflicts"].append(message.text)
            else:
                report["console_errors"].append(message.text)

        page.on("console", console_error)
        client = httpx.AsyncClient(base_url=args.url, timeout=30)
        try:
            await page.goto(args.url, wait_until="networkidle")
            await page.get_by_role("button", name="Storyboarder workspace", exact=True).wait_for()
            session = (await client.get("/api/v1/session")).json()
            project_id = session["active_project_id"]
            launch_headers = {"X-Storyboarder-Token": session["token"]}
            assert project_id, "The isolated browser fixture has no active project."
            state_path = f"/api/v1/projects/{project_id}/state"

            async def canvas():
                await page.get_by_role("button", name="Story canvas", exact=True).click()
                await page.locator(".graph-node").first.wait_for()

            async def context_tab():
                return page.get_by_role("tab", name="Story direction", exact=True)

            async def check_space_enter():
                await canvas()
                nodes = page.locator(".graph-node")
                assert await nodes.count() >= 2, "Fixture must include at least two Canvas cards."
                space_node = nodes.nth(0)
                enter_node = nodes.nth(1)
                space_id = await space_node.get_attribute("data-node-id")
                enter_id = await enter_node.get_attribute("data-node-id")
                assert space_id != enter_id
                await space_node.focus()
                await space_node.press("Space")
                assert await space_node.get_attribute("aria-pressed") == "true", "Space did not select the focused card."
                await page.locator(".inspector").wait_for()
                assert await page.locator(".inspector").count() == 1, "Space did not open the item inspector."
                space_title = (await page.locator(".inspector h2").inner_text()).strip()
                assert space_title, "Space opened an empty inspector."
                await page.get_by_role("button", name="Close inspector", exact=True).click()
                await enter_node.focus()
                await enter_node.press("Enter")
                assert await enter_node.get_attribute("aria-pressed") == "true", "Enter did not select the focused card."
                await page.locator(".inspector").wait_for()
                enter_title = (await page.locator(".inspector h2").inner_text()).strip()
                assert enter_title, "Enter opened an empty inspector."
                assert await page.locator(".inspector").count() == 1
                report["canvas_activation"] = {
                    "space_id": space_id,
                    "space_inspector_title": space_title,
                    "enter_id": enter_id,
                    "enter_inspector_title": enter_title,
                }

            async def check_tabs_and_responsive():
                tabs = page.get_by_role("tab")
                tab_data = await tabs.evaluate_all("els => els.map(e => ({id:e.id,controls:e.getAttribute('aria-controls'),selected:e.getAttribute('aria-selected'),tabindex:e.getAttribute('tabindex')}))")
                assert len(tab_data) >= 2
                assert all(item["id"] for item in tab_data), tab_data
                assert len({item["id"] for item in tab_data}) == len(tab_data), tab_data
                assert all(item["controls"] for item in tab_data), tab_data
                links = await page.locator("[role=tab]").evaluate_all("els => els.map(tab => {const panel=document.getElementById(tab.getAttribute('aria-controls'));return {tab:tab.id,panel:panel?.id,labelledBy:panel?.getAttribute('aria-labelledby'),hidden:panel?.hidden};})")
                assert all(link["panel"] == link["tab"].replace("-tab-", "-panel-") and link["labelledBy"] == link["tab"] for link in links), links
                async def press_and_check(key, expected):
                    active = page.get_by_role("tab", name=expected, exact=True)
                    current = await page.evaluate("document.activeElement.getAttribute('aria-controls')")
                    target = await active.get_attribute("aria-controls")
                    await page.keyboard.press(key)
                    assert await page.evaluate("document.activeElement.getAttribute('aria-controls')") == target, f"{key} did not move focus to {expected}."
                    assert await active.get_attribute("aria-selected") == "true", f"{key} did not activate {expected}."
                    roving = await page.locator("[role=tab][tabindex='0']").count()
                    assert roving == 1, f"Expected one tab stop after {key}; got {roving}."
                    assert current != target or key in ("Home", "End")

                first = tabs.first
                await first.focus()
                await press_and_check("ArrowRight", "References")
                await press_and_check("End", "Story direction")
                await press_and_check("Home", "Details")
                await press_and_check("ArrowLeft", "Story direction")
                snapshots = []
                for width in (1440, 1050, 801, 800, 521, 520, 390):
                    await page.set_viewport_size({"width": width, "height": 900})
                    await page.wait_for_timeout(80)
                    snapshot = await page.locator(".inspector").evaluate("e => ({width:innerWidth,role:e.getAttribute('role'),modal:e.getAttribute('aria-modal'),mainInert:document.getElementById('main-content').inert,activeInside:e.contains(document.activeElement),overflow:document.documentElement.scrollWidth>innerWidth})")
                    assert snapshot["overflow"] is False, snapshot
                    assert snapshot["role"] == ("dialog" if width <= 800 else "complementary"), snapshot
                    assert snapshot["mainInert"] is (width <= 800), snapshot
                    first = page.get_by_role("tab").first
                    await first.focus()
                    await first.press("ArrowRight")
                    assert await page.evaluate("document.activeElement.getAttribute('role')") == "tab", f"Tab focus was lost at {width}px."
                    assert await page.evaluate("document.activeElement.getAttribute('aria-selected')") == "true", f"Keyboard tab activation failed at {width}px."
                    assert await page.locator(".inspector").evaluate("e => e.contains(document.activeElement)"), snapshot
                    snapshots.append(snapshot)
                report["responsive"] = snapshots
                await page.set_viewport_size({"width": 1440, "height": 1024})

            async def check_context_retry():
                await canvas()
                scenes = page.locator('.graph-node[aria-label^="Scene:"]')
                sequences = page.locator('.graph-node[aria-label^="Sequence:"]')
                assert await scenes.count() and await sequences.count(), "Context retry fixture needs a sequence and scene."
                scene_id = await scenes.first.get_attribute("data-node-id")
                failures = {"count": 0}

                async def fail_once(route):
                    data = route.request.post_data_json or {}
                    if route.request.url.endswith("/commands/context.resolve") and data.get("owner_id") == scene_id and failures["count"] == 0:
                        failures["count"] += 1
                        await route.fulfill(status=503, content_type="application/json", body=json.dumps({"error": {"code": "injected_failure", "message": "Injected local recovery failure", "details": {}}}))
                    else:
                        await route.continue_()

                await page.route("**/commands/context.resolve", fail_once)
                await sequences.first.press("Enter")
                await scenes.first.press("Enter")
                await (await context_tab()).click()
                alert = page.locator(".inspector [role=alert]")
                await alert.wait_for()
                assert await alert.get_by_role("button", name="Retry loading direction", exact=True).count() == 1
                assert await page.locator(".inspector [role=status]").count() == 0, "Failed resolution left a permanent loading state."
                await alert.get_by_role("button", name="Retry loading direction", exact=True).click()
                await page.locator(".inspector .context-view").wait_for()
                assert await page.locator(".inspector [role=alert]").count() == 0
                assert failures["count"] == 1
                await page.unroute("**/commands/context.resolve", fail_once)

            async def check_context_race():
                await canvas()
                sequence = page.locator('.graph-node[aria-label^="Sequence:"]').first
                scene = page.locator('.graph-node[aria-label^="Scene:"]').first
                sequence_id = await sequence.get_attribute("data-node-id")
                scene_title = (await scene.locator("h3").inner_text()).strip()
                gate, started, released = asyncio.Event(), asyncio.Event(), asyncio.Event()

                async def delay_sequence(route):
                    data = route.request.post_data_json or {}
                    if route.request.url.endswith("/commands/context.resolve") and data.get("owner_id") == sequence_id:
                        response = await route.fetch()
                        started.set()
                        await gate.wait()
                        await route.fulfill(response=response)
                        released.set()
                    else:
                        await route.continue_()

                await page.route("**/commands/context.resolve", delay_sequence)
                await sequence.press("Enter")
                await asyncio.wait_for(started.wait(), timeout=8)
                await scene.press("Enter")
                await page.get_by_role("tab", name="Story direction", exact=True).click()
                await page.locator(".inspector .context-view .scope-chain").wait_for()
                await page.wait_for_function("title => document.querySelector('.inspector .context-view .scope-chain')?.textContent.includes(title)", arg=scene_title)
                before = (await page.locator(".inspector .context-view").inner_text()).strip()
                assert scene_title in before
                gate.set()
                await asyncio.wait_for(released.wait(), timeout=8)
                await page.wait_for_timeout(150)
                after = (await page.locator(".inspector .context-view").inner_text()).strip()
                assert scene_title in after, "A stale sequence response replaced the currently selected scene context."
                assert after == before, "Stale context changed the resolved owner details."
                await page.unroute("**/commands/context.resolve", delay_sequence)
                report["context_race"] = {"owner": scene_title, "preserved_text_length": len(after)}

            async def check_usage_retry():
                await canvas()
                scene = page.locator('.graph-node[aria-label^="Scene:"]').first
                target_id = await scene.get_attribute("data-node-id")
                attempts = []

                async def fail_first_usage(route):
                    data = route.request.post_data_json or {}
                    if route.request.url.endswith("/commands/entity.usage"):
                        attempts.append(data.get("id"))
                        if len(attempts) == 1:
                            await route.fulfill(status=503, content_type="application/json", body=json.dumps({"error": {"code": "injected_failure", "message": "Injected usage preflight failure", "details": {}}}))
                            return
                    await route.continue_()

                await page.route("**/commands/entity.usage", fail_first_usage)
                await scene.focus()
                await scene.press("Delete")
                dialog = page.get_by_role("dialog", name="Remove this card?", exact=True)
                await dialog.get_by_role("alert").wait_for()
                assert await dialog.locator(".modal-body").get_attribute("data-removal-id") == target_id
                assert "Checking where this item is used" not in await dialog.inner_text()
                retry = dialog.get_by_role("button", name="Retry usage check", exact=True)
                assert await retry.count() == 1
                await retry.click()
                await dialog.locator(".usage-summary").wait_for()
                assert attempts == [target_id, target_id], attempts
                assert await dialog.locator(".modal-body").get_attribute("data-removal-id") == target_id
                assert await dialog.get_by_role("button", name="Archive item…", exact=True).is_enabled()
                assert "Injected usage preflight failure" not in await dialog.inner_text()
                await dialog.get_by_role("button", name="Close dialog", exact=True).click()
                await page.unroute("**/commands/entity.usage", fail_first_usage)

            async def check_layout_id_recovery():
                name = f"Phase-one identity recovery {uuid.uuid4().hex[:7]}"

                async def command(command_name, payload):
                    response = await client.post(f"/api/v1/projects/{project_id}/commands/{command_name}", json=payload, headers=launch_headers)
                    assert response.status_code == 200, f"{command_name} returned {response.status_code}: {response.text}"
                    return response.json()

                original = await command("canvas.save", {"name": name, "mode": "story", "positions": {}, "settings": {}})
                original_id = original["id"]
                await page.reload(wait_until="networkidle")
                await canvas()
                await page.get_by_label("Saved arrangement", exact=True).select_option(original_id)
                name_input = page.get_by_label("Arrangement name", exact=True)
                renamed = f"{name} renamed"
                await name_input.fill(renamed)
                await page.get_by_role("button", name="Save arrangement", exact=True).click()
                await page.wait_for_function("id => document.querySelector('.canvas-layout-bar select[aria-label=\"Saved arrangement\"]')?.value === id", arg=original_id)
                state = (await client.get(state_path)).json()
                saved_rename = next(layout for layout in state["layouts"] if layout["id"] == original_id)
                assert saved_rename["name"] == renamed, saved_rename

                node = page.locator(".graph-node").first
                node_id = await node.get_attribute("data-node-id")
                await node.focus()
                await node.press("ArrowRight")
                before = await node.get_attribute("style")
                latest_original = next(layout for layout in state["layouts"] if layout["id"] == original_id)
                await command("canvas.remove", {"id": original_id, "revision": latest_original["revision"]})
                replacement = await command("canvas.save", {"name": renamed, "mode": "story", "positions": {"replacement-sentinel": {"x": 919, "y": 717}}, "settings": {}})
                replacement_id = replacement["id"]
                assert replacement_id != original_id

                await page.get_by_role("button", name="Save arrangement", exact=True).click()
                conflict = page.get_by_role("button", name="Refresh latest saved revision", exact=True)
                await conflict.wait_for()
                await conflict.click()
                await page.get_by_role("status").filter(has_text="This saved arrangement is no longer available").wait_for()
                assert await page.get_by_role("button", name="Reapply merged arrangement", exact=True).count() == 0
                fresh = (await client.get(state_path)).json()
                replacement_after = next(layout for layout in fresh["layouts"] if layout["id"] == replacement_id)
                assert replacement_after["revision"] == replacement["revision"]
                assert replacement_after["positions"] == replacement["positions"]

                await page.get_by_role("button", name="Save as new arrangement", exact=True).last.click()
                new_name = await page.get_by_label("Arrangement name", exact=True).input_value()
                assert new_name != renamed
                await page.get_by_role("button", name="Save arrangement", exact=True).click()
                await page.wait_for_function("name => Array.from(document.querySelectorAll('.canvas-layout-bar select option')).some(option => option.textContent === name)", arg=new_name)
                after_save = (await client.get(state_path)).json()
                new_layout = next(layout for layout in after_save["layouts"] if layout["name"] == new_name)
                replacement_after = next(layout for layout in after_save["layouts"] if layout["id"] == replacement_id)
                assert new_layout["id"] not in (original_id, replacement_id)
                assert replacement_after["revision"] == replacement["revision"]
                assert replacement_after["positions"] == replacement["positions"]
                assert node_id and before
                report["layout_recovery"] = {"old_id": original_id, "replacement_id": replacement_id, "new_id": new_layout["id"], "replacement_revision": replacement_after["revision"]}

            async def check_queued_cancel():
                state = (await client.get(state_path)).json()
                title = f"Phase-one queued cancellation {uuid.uuid4().hex[:8]}"
                jobs = state.get("jobs", [])
                queued = next((job for job in jobs if job.get("status") == "queued"), None)
                if queued is None:
                    meta = (await client.get("/api/v1/meta")).json()
                    scripts = meta.get("scripts", [])
                    assert scripts, "No trusted script fixture is registered for queued cancellation."
                    payload = {"script": scripts[0]["name"], "target": "asset", "title": title, "asset_type": "reference", "prompt": "Never run; cancellation UI regression fixture."}
                    created = await client.post(f"/api/v1/projects/{project_id}/commands/job.create", json=payload, headers=launch_headers)
                    assert created.status_code == 200, created.text
                else:
                    title = queued["title"]
                await page.reload(wait_until="networkidle")
                await page.get_by_role("button", name="Image tools", exact=True).click()
                row = page.get_by_role("button", name=re.compile(re.escape(title)))
                await row.wait_for()
                await row.click()
                await page.get_by_role("button", name="Cancel…", exact=True).click()
                cancel_dialog = page.get_by_role("dialog", name="Stop image tool", exact=True)
                await cancel_dialog.get_by_role("checkbox").check()

                recovery = {"cancel_posts": 0, "state_gets": 0}

                async def count_cancel(route):
                    recovery["cancel_posts"] += 1
                    await route.continue_()

                async def fail_refresh_once(route):
                    if route.request.method == "GET" and route.request.url.endswith("/state"):
                        recovery["state_gets"] += 1
                        if recovery["state_gets"] == 1:
                            await route.fulfill(status=503, content_type="application/json", body=json.dumps({"error": {"code": "injected_failure", "message": "Injected post-cancel refresh failure", "details": {}}}))
                            return
                    await route.continue_()

                await page.route("**/commands/job.cancel", count_cancel)
                await page.route(f"**/projects/{project_id}/state", fail_refresh_once)
                await cancel_dialog.get_by_role("button", name="Stop image tool", exact=True).click()
                toast = page.locator(".toast")
                await toast.wait_for()
                assert await toast.get_attribute("data-outcome") == "cancelled"
                assert "run was stopped" in (await toast.inner_text()).lower()
                assert "could not refresh" in (await toast.inner_text()).lower()
                await page.get_by_role("button", name="Retry project refresh", exact=True).wait_for()
                assert recovery == {"cancel_posts": 1, "state_gets": 1}, recovery
                await page.get_by_role("button", name="Retry project refresh", exact=True).click()
                await page.wait_for_function("title => Array.from(document.querySelectorAll('.job-row')).some(row => row.textContent.includes(title) && row.textContent.includes('Stopped'))", arg=title)
                assert recovery == {"cancel_posts": 1, "state_gets": 2}, recovery
                await page.unroute("**/commands/job.cancel", count_cancel)
                await page.unroute(f"**/projects/{project_id}/state", fail_refresh_once)
                icon = await toast.locator(":scope > svg").evaluate("e => e.innerHTML")
                assert "rect" in icon and "m4 12 5 5L20 6" not in icon, icon
                report["cancel_notice"] = {"title": title, "outcome": await toast.get_attribute("data-outcome"), "icon": icon}

            functions = [check_space_enter, check_tabs_and_responsive, check_context_retry, check_context_race, check_usage_retry, check_layout_id_recovery, check_queued_cancel]
            for index, (name, function) in enumerate(zip(cases, functions)):
                try:
                    await function()
                    report["passed"].append(name)
                except Exception as error:
                    report["failed"].append({"case": name, "error": f"{type(error).__name__}: {error}"})
                    await page.screenshot(path=str(output / "failure.png"), full_page=True)
                    (output / "failure.txt").write_text(await page.locator("body").inner_text())
                    report["never_run"].extend(cases[index + 1 :])
                    break
            assert not report["page_errors"], report["page_errors"]
            assert not report["console_errors"], report["console_errors"]
            report["passed_all"] = not report["failed"] and not report["never_run"]
        except Exception as error:
            report["failed"].append({"case": "setup_or_browser", "error": f"{type(error).__name__}: {error}"})
            report["never_run"] = [case for case in cases if case not in report["passed"]]
            report["passed_all"] = False
        finally:
            await client.aclose()
            await browser.close()
            (output / "phase1-browser-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report.get("passed_all") else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--chromium")
    sys.exit(asyncio.run(main(parser.parse_args())))
