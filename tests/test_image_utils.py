import io

from PIL import Image

from pp_mistral.image_utils import resize_image


def _make_png(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(120, 30, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_resize_image_shrinks_large_image_and_converts_to_jpeg():
    original = _make_png(3000, 2000)
    resized = resize_image(original, max_dimension=500, quality=85)

    with Image.open(io.BytesIO(resized)) as img:
        assert img.format == "JPEG"
        assert max(img.size) <= 500
        assert abs(img.size[0] / img.size[1] - 3000 / 2000) < 0.01

    assert len(resized) < len(original)


def test_resize_image_does_not_upscale_small_image():
    original = _make_png(200, 100)
    resized = resize_image(original, max_dimension=1024, quality=85)

    with Image.open(io.BytesIO(resized)) as img:
        assert img.size == (200, 100)
