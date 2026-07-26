import io

from PIL import Image


def resize_image(image_bytes: bytes, max_dimension: int = 1024, quality: int = 85) -> bytes:
    """Downscale an image so its longest side is at most `max_dimension` px
    and re-encode it as JPEG.

    Vision model pricing/latency scales with image resolution, so shrinking
    photos before sending them to Mistral meaningfully cuts token usage while
    keeping enough detail for descriptions, keyword extraction and landmark
    recognition.
    """
    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()
