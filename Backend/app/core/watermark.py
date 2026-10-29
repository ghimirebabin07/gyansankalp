from PIL import Image, ImageDraw, ImageFont


def stamp(img: Image.Image, text: str, footer: str) -> Image.Image:
    """Return a copy of the page with a tiled diagonal watermark and a footer line.

    Uses Pillow's built-in font, so keep the text ASCII (phone number, user id).
    Nepali names would need a Devanagari .ttf file.
    """
    base = img.convert("RGBA")
    w, h = base.size
    font = ImageFont.load_default(size=max(14, w // 32))

    probe = ImageDraw.Draw(base)
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
    tw, th = right - left, bottom - top

    # Draw on a square as large as the page diagonal, rotate it, then crop the
    # middle. This way the rotated pattern has no empty corners.
    side = int((w ** 2 + h ** 2) ** 0.5) + 2
    layer = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    step_x, step_y = tw + th * 3, th * 5
    for row, y in enumerate(range(0, side, step_y)):
        offset = (row % 2) * (step_x // 2)
        for x in range(-step_x, side, step_x):
            draw.text((x + offset, y), text, font=font, fill=(90, 90, 90, 70))
    layer = layer.rotate(30, resample=Image.BICUBIC)
    left_c, top_c = (side - w) // 2, (side - h) // 2
    layer = layer.crop((left_c, top_c, left_c + w, top_c + h))

    out = Image.alpha_composite(base, layer)

    small = ImageFont.load_default(size=max(10, w // 60))
    ImageDraw.Draw(out).text((10, h - small.size - 8), footer, font=small, fill=(110, 110, 110, 255))
    return out.convert("RGB")
