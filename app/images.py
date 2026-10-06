"""Meal image storage. Uploads are normalised to WebP inside UPLOAD_DIR."""

import io
import shutil
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from . import config

MAX_DIMENSION = 1600


class ImageError(ValueError):
    pass


def _new_name() -> str:
    return f"{uuid.uuid4().hex}.webp"


def save_image(data: bytes) -> str:
    """Validate, auto-rotate, resize and store an uploaded image. Returns the file name."""
    if not data:
        raise ImageError("The uploaded image is empty.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ImageError(f"Image is too large (max {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)  # phone photos carry their rotation in EXIF
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
            name = _new_name()
            config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            img.save(config.UPLOAD_DIR / name, "WEBP", quality=84, method=4)
            return name
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageError("That file doesn't look like a supported image (JPEG, PNG, WebP, GIF).") from exc


def copy_image(name: str | None) -> str | None:
    """Duplicate a stored image so each meal owns its own file."""
    if not name:
        return None
    src = path_for(name)
    if not src or not src.exists():
        return None
    new = _new_name()
    shutil.copyfile(src, config.UPLOAD_DIR / new)
    return new


def delete_image(name: str | None) -> None:
    path = path_for(name)
    if path and path.exists():
        path.unlink(missing_ok=True)


def path_for(name: str | None) -> Path | None:
    if not name:
        return None
    # Never allow path traversal – image names are always bare file names.
    if Path(name).name != name:
        return None
    return config.UPLOAD_DIR / name


def url_for(name: str | None) -> str | None:
    return f"/uploads/{name}" if name else None
