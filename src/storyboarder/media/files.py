"""Managed still-image files, staging, safe paths and rebuildable previews."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from storyboarder.domain.errors import StoryboardError, UnsafePath

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_PIXELS = 50_000_000
MAX_IMPORT_FILES = 2000
FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "TIFF": ".tif", "BMP": ".bmp"}
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def safe_path(root: Path, relative: str, *, must_exist=False) -> Path:
    root = root.resolve()
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts or "\\" in relative or "\x00" in relative:
        raise UnsafePath("The requested path is outside the project.")
    result = root.joinpath(raw)
    # Reject symlinks even if their final target happens to be inside the project.
    current = root
    for part in raw.parts:
        current = current / part
        if current.is_symlink():
            raise UnsafePath("Symbolic links are not permitted in managed project storage.")
    try:
        result.resolve().relative_to(root)
    except ValueError as exc:
        raise UnsafePath("The requested path is outside the project.") from exc
    if must_exist and not result.is_file():
        raise StoryboardError(f"Missing managed file: {relative}. Restore it from a project backup.")
    return result


def safe_name(name: str) -> str:
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^\w.() -]", "_", name, flags=re.UNICODE).strip(" .")
    return (name[:160] or "image")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_image(path):
    path = Path(path)
    size = path.stat().st_size
    if size == 0 or size > MAX_FILE_BYTES:
        raise StoryboardError("Image must be non-empty and no larger than 50 MiB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                fmt = image.format
                if fmt not in FORMATS:
                    raise StoryboardError("Supported still images: JPEG, PNG, WebP, TIFF and BMP. SVG, GIF, RAW, audio and video are not imported.")
                if getattr(image, "n_frames", 1) != 1:
                    raise StoryboardError("Animated and multi-page images are not supported. Export a single still frame first.")
                if image.width * image.height > MAX_PIXELS:
                    raise StoryboardError("Image exceeds the 50-megapixel limit. Export a smaller reference.")
                image.verify()
            # verify() does not fully decode every format; load to reject truncated images.
            with Image.open(path) as image:
                image.load()
                width, height = image.size
        return {"format": fmt, "width": width, "height": height, "size": size, "sha256": sha256(path)}
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise StoryboardError(f"This file could not be decoded as a safe still image: {exc}") from exc


def stage_file(source, staging: Path):
    source = Path(source).expanduser()
    if source.is_symlink() or not source.is_file():
        raise StoryboardError("Choose a regular image file, not a symbolic link or directory.")
    if source.stat().st_size > MAX_FILE_BYTES:
        raise StoryboardError("Image exceeds 50 MiB.")
    staging.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, staging.open("xb") as dst:
        total = 0
        while chunk := src.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise StoryboardError("Image exceeds 50 MiB.")
            dst.write(chunk)
        dst.flush()
        os.fsync(dst.fileno())
    return inspect_image(staging)


def thumbnail(root, media, size=480):
    if size not in (160, 480, 960):
        raise StoryboardError("Thumbnail size must be 160, 480 or 960.")
    source = safe_path(root, media["path"], must_exist=True)
    relative = f".storyboarder/cache/{media['id']}-{size}.jpg"
    output = safe_path(root, relative)
    if not output.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
            # Unique temporary path avoids simultaneous preview races.
            import tempfile
            fd, temporary = tempfile.mkstemp(dir=output.parent, suffix=".jpg")
            os.close(fd)
            try:
                image.save(temporary, "JPEG", quality=86, optimize=True)
                os.replace(temporary, output)
            finally:
                Path(temporary).unlink(missing_ok=True)
    return output


def clear_cache(root):
    directory = safe_path(root, ".storyboarder/cache")
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True, exist_ok=True)
