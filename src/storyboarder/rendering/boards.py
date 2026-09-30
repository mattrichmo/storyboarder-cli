"""Presentation boards, not canvas screenshots. HTML, paginated PDF and PNG sheets."""
from pathlib import Path
import hashlib
import html
import json
import math
import os
import shutil
import tempfile
from PIL import Image, ImageOps, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from storyboarder.domain.errors import StoryboardError
from storyboarder.domain.models import dumps
from storyboarder.media.files import FORMATS, safe_path, sha256
from .composer import copy_label, display_title
from .exports import json_file, commit_export

BOARD_CSS = """
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f4f2ec;color:#252923;font:15px/1.5 system-ui,sans-serif}main{max-width:1200px;margin:0 auto;padding:42px}header{display:flex;align-items:end;justify-content:space-between;border-bottom:1px solid #c9cbbf;padding-bottom:24px;margin-bottom:36px}h1{font:44px/1.08 Georgia,serif;margin:8px 0}h2{font:28px Georgia,serif;margin:36px 0 18px}.eyebrow{font-size:11px;letter-spacing:.15em;text-transform:uppercase}.panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:30px 26px}article{break-inside:avoid;min-width:0}.image{aspect-ratio:16/9;background:#e6e7df;display:flex;align-items:center;justify-content:center;overflow:hidden}.image img{width:100%;height:100%;object-fit:contain}.line{display:flex;gap:14px;justify-content:space-between;border-bottom:1px solid #c9cbbf;padding:12px 0}h3{margin:0;font-weight:600;font-size:16px}.number{font:16px monospace}.meta{font-size:12px;color:#4e554b;margin:8px 0}.copy{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;margin:10px 0}.refstrip{display:flex;gap:8px;flex-wrap:wrap}.refstrip img{width:86px;height:55px;object-fit:contain;background:#e6e7df}.refstrip figure{margin:0;max-width:110px}.refstrip figcaption{font-size:10px;overflow-wrap:anywhere}.badge{font:11px monospace;text-transform:uppercase}.checks{border-top:1px solid #c9cbbf;margin-top:36px;padding-top:20px}footer{font-size:11px;margin-top:40px;color:#4e554b}@media(max-width:650px){main{padding:20px}.panels{grid-template-columns:1fr}header{display:block}h1{font-size:34px}}@media print{body{background:white}main{padding:0}h1{font-size:30px}header{margin-bottom:20px}.panels{gap:22px}h2{break-after:avoid}article{break-inside:avoid}a{color:inherit}footer{margin-top:24px}}@page{size:A4 landscape;margin:15mm}
"""


def panel_data(document, approved_only=False):
    panels = []
    for scene in document["scenes"]:
        for shot in scene["shots"]:
            frame = next((f for f in shot["frames"] if f["state"] == "approved" or (not approved_only and f["state"] == "selected")), None)
            references = [a for a in shot["assignments"] if a["media"]]
            image = frame["media"] if frame else (references[0]["media"] if references else None)
            ctx = shot["context"]["scalars"]
            panels.append({"scene": scene["title"], "scene_id": scene["id"], "sequence": scene["sequence"]["title"], "shot": shot, "image": image, "frame": frame, "references": references, "image_label": f"{copy_label(frame['state'])} storyboard image" if frame else "Reference image · not a storyboard image" if image else "No storyboard image added yet", "framing": ctx.get("framing", {}).get("value", "Framing not set"), "camera": ctx.get("camera", {}).get("value", ""), "location": ctx.get("location_id", {}).get("label", ""), "time": ctx.get("time", {}).get("value", "")})
    return panels


def board_html(document, panels, paths):
    esc = lambda v: html.escape(str(v), quote=True)
    result = ["<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>", f"<title>{esc(display_title(document['owner']['title']))} — Storyboard</title><link rel='stylesheet' href='board.css'><main><header><div><div class='eyebrow'>Storyboard</div><h1>{esc(display_title(document['owner']['title']))}</h1><div>{esc(display_title(document['project']['title']))}</div></div><div class='eyebrow'>For review · {len(panels)} shots</div></header>"]
    active_scene = None
    for p in panels:
        shot = p["shot"]
        if p["scene_id"] != active_scene:
            if active_scene is not None:
                result.append("</div>")
            result.append(f"<h2>{esc(display_title(p['sequence']))} / {esc(display_title(p['scene']))}</h2><div class='panels'>")
            active_scene = p["scene_id"]
        number = shot["fields"].get("number") or f"{shot['position']+1:02}"
        image = f"<img src='{paths[p['image']['id']]}' alt='{esc(p['image_label'])}' loading='lazy'>" if p["image"] else "<span class='eyebrow'>No storyboard image added yet</span>"
        result.append(f"<article><div class='image'>{image}</div><div class='line'><h3><span class='number'>{esc(number)}</span> / {esc(display_title(shot['title']))}</h3><span class='badge'>{esc(p['framing'])}</span></div><p class='meta'>{esc(p['image_label'])} · {esc(p['location'])} {esc(p['time'])}</p>")
        for key in ("action", "dialogue", "camera", "continuity", "notes"):
            value = p["camera"] if key == "camera" else shot["fields"].get(key)
            if value:
                result.append(f"<p class='copy'><strong>{key.title()}</strong><br>{esc(value)}</p>")
        if p["references"]:
            result.append("<div class='refstrip'>")
            for a in p["references"]:
                result.append(f"<figure><img src='{paths[a['media']['id']]}' alt='{esc(display_title(a['asset']['title']))}'><figcaption>{esc(copy_label(a['role']))} / {esc(display_title(a['asset']['title']))}</figcaption></figure>")
            result.append("</div>")
        result.append("</article>")
    if active_scene is not None:
        result.append("</div>")
    if not panels:
        result.append("<p>No shots yet. Add shots to this part of the story to build a board.</p>")
    if document["validation"]:
        result.append("<section class='checks'><h2>Production checks</h2>")
        for issue in document["validation"]:
            result.append(f"<p>{esc(issue['severity'].upper())}: {esc(issue['message'])}</p>")
        result.append("</section>")
    result.append("<footer>Storyboarder · Storyboard images and reference images are shown separately. The project package includes the full shot details and story direction.</footer></main></html>")
    return "".join(result)


def _paragraph(pdf, value, x, y, width, height, size=10, leading=14):
    style = ParagraphStyle("editorial", fontName="Helvetica", fontSize=size, leading=leading, textColor=colors.HexColor("#252923"))
    escaped = html.escape(str(value)).replace("\n", "<br/>")
    paragraph = Paragraph(escaped, style)
    _, needed = paragraph.wrap(width, height)
    truncated = False
    # Respect the panel's text area; the full text is always retained in JSON/HTML.
    if needed > height:
        low, high = 0, len(str(value))
        while low < high:
            mid = (low + high + 1) // 2
            test = Paragraph(html.escape(str(value)[:mid]) + " … (continued in the HTML board)", style)
            if test.wrap(width, height)[1] <= height:
                low = mid
            else:
                high = mid - 1
        paragraph = Paragraph(html.escape(str(value)[:low]) + " … (continued in the HTML board)", style)
        needed = paragraph.wrap(width, height)[1]
        truncated = True
    paragraph.drawOn(pdf, x, y - needed)
    return needed, truncated


def render_pdf(target, document, panels, directory, paths):
    page_w, page_h = landscape(A4)
    pdf = canvas.Canvas(str(target), pagesize=(page_w, page_h), invariant=1)
    pdf.setTitle(display_title(document["owner"]["title"]) + " — Storyboard")
    pdf.setAuthor("Storyboarder")
    page_panels = [panels[i:i+2] for i in range(0, len(panels), 2)] or [[]]
    truncations = []
    for page_number, group in enumerate(page_panels, 1):
        pdf.setFillColor(colors.HexColor("#f5f3ed"))
        pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#252923"))
        pdf.setFont("Helvetica", 9)
        pdf.drawString(32, page_h-29, "STORYBOARD")
        pdf.setFont("Times-Roman", 23)
        _paragraph(pdf, display_title(document["owner"]["title"]), 32, page_h-42, page_w-160, 35, 20, 25)
        pdf.setFont("Helvetica", 9)
        pdf.drawRightString(page_w-32, page_h-29, f"{page_number:02} / {len(page_panels):02}")
        pdf.setStrokeColor(colors.HexColor("#c9cbbf"))
        pdf.line(32, page_h-86, page_w-32, page_h-86)
        width = (page_w - 84) / 2
        for index, p in enumerate(group):
            x, top = 32 + index * (width + 20), page_h - 104
            image_h = width * 9 / 16
            pdf.setFillColor(colors.HexColor("#e5e7df"))
            pdf.rect(x, top-image_h, width, image_h, fill=1, stroke=0)
            if p["image"]:
                pdf.drawImage(ImageReader(str(directory / paths[p["image"]["id"]])), x, top-image_h, width=width, height=image_h, preserveAspectRatio=True, anchor="c", mask="auto")
            else:
                pdf.setFillColor(colors.HexColor("#555e50"))
                pdf.setFont("Helvetica", 10)
                pdf.drawCentredString(x+width/2, top-image_h/2, "NO STORYBOARD IMAGE YET")
            y = top-image_h-12
            shot = p["shot"]
            number = shot["fields"].get("number") or f"{shot['position']+1:02}"
            used, _ = _paragraph(pdf, f"{number} / {display_title(shot['title'])}", x, y, width, 36, 13, 17)
            y -= used+5
            used, _ = _paragraph(pdf, f"{display_title(p['scene'])} · {p['framing']} · {p['image_label']}", x, y, width, 32, 8, 11)
            y -= used+10
            body = "\n\n".join(f"{copy_label(key).upper()}\n{str(shot['fields'][key])}" for key in ("action", "dialogue", "notes") if shot["fields"].get(key))
            _, clipped = _paragraph(pdf, body or "No action described yet.", x, y, width, max(y-95, 28), 9, 12)
            if clipped:
                truncations.append(shot["id"])
            # Compact exact reference strip on every panel, separate from frame candidate.
            refs = p["references"][:5]
            for ref_index, a in enumerate(refs):
                xx = x + ref_index * 69
                pdf.drawImage(ImageReader(str(directory / paths[a["media"]["id"]])), xx, 47, width=62, height=36, preserveAspectRatio=True, anchor="c", mask="auto")
            if len(p["references"]) > 5:
                _paragraph(pdf, f"+{len(p['references'])-5} more references", x, 42, width, 12, 7, 9)
        pdf.setFont("Helvetica", 7)
        pdf.setFillColor(colors.HexColor("#555e50"))
        pdf.drawString(32, 22, "Reference images are separate from storyboard images. The download includes the complete story and shot notes.")
        pdf.showPage()
    pdf.save()
    return {"pages": len(page_panels), "text_abbreviated_for_layout": truncations}


def render_png(directory, document, panels, paths):
    # Contact sheets are paginated to cap peak memory and keep labels readable.
    groups = [panels[i:i+6] for i in range(0, len(panels), 6)] or [[]]
    filenames = []
    for page, group in enumerate(groups, 1):
        sheet = Image.new("RGB", (1800, 1960), "#f5f3ed")
        draw = ImageDraw.Draw(sheet)
        header_font = ImageFont.load_default(size=38)
        font = ImageFont.load_default(size=22)
        small = ImageFont.load_default(size=18)
        def fit(line, maximum, chosen_font):
            line = str(line).replace("\n", " ")
            while draw.textlength(line, font=chosen_font) > maximum and line:
                line = line[:-1]
            return line
        draw.text((60, 40), "STORYBOARD", fill="#58604f", font=small)
        draw.text((60, 83), fit(display_title(document["owner"]["title"]), 1500, header_font), fill="#252923", font=header_font)
        draw.text((1600, 48), f"{page}/{len(groups)}", fill="#252923", font=font)
        for index, panel in enumerate(group):
            x, y = 60 + (index % 2) * 860, 175 + (index // 2) * 565
            draw.rectangle((x, y, x+820, y+460), fill="#e5e7df")
            if panel["image"]:
                with Image.open(directory / paths[panel["image"]["id"]]) as source:
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    image.thumbnail((820, 460), Image.Resampling.LANCZOS)
                    sheet.paste(image, (x+(820-image.width)//2, y+(460-image.height)//2))
            else:
                draw.text((x+240, y+215), "NO STORYBOARD IMAGE YET", fill="#58604f", font=font)
            shot = panel["shot"]
            number = shot["fields"].get("number") or f"{shot['position']+1:02}"
            draw.text((x, y+475), fit(f"{number} / {display_title(shot['title'])}", 815, font), fill="#252923", font=font)
            draw.text((x, y+508), fit(f"{panel['framing']} · {panel['image_label']}", 815, small), fill="#58604f", font=small)
        draw.text((60, 1895), "Contact sheet · Full shot notes and references are included in the accompanying download.", fill="#58604f", font=small)
        filename = f"board-{page:03}.png"
        sheet.save(directory / filename, "PNG", optimize=True)
        filenames.append(filename)
    return filenames


def export_board(service, owner_id, format="html", approved_only=False):
    if format not in ("html", "pdf", "png", "all"):
        raise StoryboardError("Choose HTML, PDF, PNG, or all three formats.")
    document = service.compose(owner_id)
    if not document["valid"]:
        raise StoryboardError("One or more chosen images are missing. Review the project health report before exporting.", {"validation": document["validation"]})
    panels = panel_data(document, approved_only)
    digest = hashlib.sha256(dumps({"document": document, "format": format, "approved_only": approved_only, "renderer": 2}).encode()).hexdigest()[:16]
    relative = f"exports/boards/{owner_id[:8]}-{digest}"
    target = safe_path(service.root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".board-", dir=target.parent))
    try:
        records = {r["id"]: r for r in service.repo.snapshot()["media"]}
        (temp / "media").mkdir()
        paths, display_paths = {}, {}
        for media in document["media"]:
            path = f"media/{media['id']}{FORMATS[media['format']]}"
            source = safe_path(service.root, records[media["id"]]["path"], must_exist=True)
            shutil.copyfile(source, temp / path)
            if sha256(temp / path) != media["sha256"]:
                raise StoryboardError("A reference image changed while the board was being created. Restore the original from backup or import it again.")
            paths[media["id"]] = path
            display_paths[media["id"]] = path
            if media["format"] in ("TIFF", "BMP"):
                # Preserve the exact original in media/, add a browser-safe preview.
                (temp / "previews").mkdir(exist_ok=True)
                preview = f"previews/{media['id']}.jpg"
                with Image.open(source) as image:
                    view = ImageOps.exif_transpose(image).convert("RGB")
                    view.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
                    view.save(temp / preview, "JPEG", quality=92, optimize=True)
                display_paths[media["id"]] = preview
        # Include the same bundle-relative paths throughout the JSON snapshot.
        def mark(value):
            if isinstance(value, dict):
                if "sha256" in value and value.get("id") in paths:
                    value["bundle_path"] = paths[value["id"]]
                for v in value.values():
                    mark(v)
            elif isinstance(value, list):
                for v in value:
                    mark(v)
        mark(document)
        document["self_contained"] = True
        json_file(temp / "scene.json", document)
        (temp / "board.css").write_text(BOARD_CSS)
        (temp / "board.html").write_text(board_html(document, panels, display_paths), encoding="utf-8")
        extra = {}
        if format in ("pdf", "all"):
            extra = render_pdf(temp / "board.pdf", document, panels, temp, paths)
        if format in ("png", "all"):
            extra["contact_sheets"] = render_png(temp, document, panels, paths)
        files = [{"path": p.relative_to(temp).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)} for p in sorted(temp.rglob("*")) if p.is_file()]
        manifest = {"schema": document["schema"], "kind": "visual-board", "owner_id": owner_id, "format": format, "approved_only": approved_only, "self_contained": True, "files": files, **extra}
        json_file(temp / "manifest.json", manifest)
        archive = safe_path(service.root, relative + ".zip")
        commit_export(temp, target, archive)
        view_file = "board.pdf" if format == "pdf" else "board-001.png" if format == "png" else "board.html"
        return {"path": relative, "archive": relative + ".zip", "view": relative + "/" + view_file, "files": [relative + "/" + f["path"] for f in files if not f["path"].startswith("media/")] + [relative + ".zip"], "manifest": manifest, "validation": document["validation"]}
    finally:
        if temp.exists():
            shutil.rmtree(temp)
