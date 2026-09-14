"""Derive every Petralysis brand asset from one master image.

Offline and deterministic. The master is a square PNG of the faceted crystal
on its pale alice-blue ground, committed as assets/brand/petralysis-master.png.
Every file the site references is cut from it here, so replacing the master
and re-running this script is the whole procedure for a brand refresh:

    pip install -r tools/requirements-brand.txt
    python tools/make_brand_assets.py

Outputs (all under assets/img/):

    favicon.ico            16, 32 and 48 px in one container
    icon-192.png           192 x 192, maskable-safe
    icon-512.png           512 x 512, maskable-safe
    apple-touch-icon.png   180 x 180
    brand-32.png           header mark, 32 x 32
    brand-64.png           the same mark for high-DPI screens (srcset 2x)
    ogp.png                1200 x 630 Open Graph card with the wordmark

Framing: the crystal is found by its difference from the background colour
(sampled at the master's corners), then re-centred so that it fills a fixed
share of each square. Icons keep the crystal inside the central 80% that
maskable icons are guaranteed to show; the header mark is framed tighter
because nothing crops it. The background colour of every output is the one
measured from the master, not a constant, so the tint on the site always
matches the artwork.

--synthesize writes a stand-in master first. It exists so the pipeline can be
exercised before the owner's artwork is available; the stand-in follows the
same brief (facets, silver-to-black, thin light seams, alice-blue ground) but
is not the brand. Drop the real PNG over it and re-run without the flag.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
MASTER = REPO_ROOT / "assets" / "brand" / "petralysis-master.png"
OUT = REPO_ROOT / "assets" / "img"

WORDMARK = "Petralysis"
TAGLINE = "Supply concentration in critical minerals, from open data"

# Share of the square the crystal's longer side occupies. 0.80 is the
# maskable-icon safe zone; the header mark can sit closer to its edges.
ICON_FILL = 0.80
MARK_FILL = 0.92

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


# ------------------------------------------------------------------ master

def synthesize_master(size: int = 1024) -> Image.Image:
    """A stand-in crystal that follows the brief, for use before the real one.

    A cut-gem silhouette split into flat facets. Tone comes from a fake light
    at the upper left: facets facing it are near-white silver, facets turned
    away run to near-black, and every seam is drawn as a thin pale line so the
    facets read at 16 px as well as at 512.
    """
    ground = (240, 248, 255)  # alice blue
    scale = 4  # draw large, then downsample for clean edges
    big = size * scale
    image = Image.new("RGB", (big, big), ground)
    draw = ImageDraw.Draw(image)

    def pt(x: float, y: float) -> tuple[float, float]:
        return (x * big, y * big)

    # Outer silhouette (an elongated hexagon) and an inner ring of four points
    # that forms the table. Coordinates are fractions of the canvas; the whole
    # shape stays inside the central 80% so the master itself is maskable-safe.
    top, bottom = pt(0.50, 0.11), pt(0.50, 0.89)
    ur, ul = pt(0.79, 0.35), pt(0.21, 0.35)
    lr, ll = pt(0.74, 0.65), pt(0.26, 0.65)
    it, ib = pt(0.50, 0.36), pt(0.50, 0.64)
    ir, il = pt(0.63, 0.50), pt(0.37, 0.50)

    def grey(v: int) -> tuple[int, int, int]:
        return (v, v + 2, v + 5) if v < 250 else (v, v, v)

    facets = [
        # crown, lit side
        ([top, ur, it], grey(214)),
        ([top, it, ul], grey(238)),
        ([ul, it, il], grey(226)),
        ([ur, ir, it], grey(170)),
        # girdle facets
        ([ul, il, ll], grey(196)),
        ([ur, lr, ir], grey(96)),
        # table
        ([it, ir, ib, il], grey(154)),
        # pavilion, shadow side
        ([ll, il, ib], grey(128)),
        ([ib, ir, lr], grey(52)),
        ([ll, ib, bottom], grey(74)),
        ([bottom, ib, lr], grey(26)),
    ]
    for polygon, fill in facets:
        draw.polygon(polygon, fill=fill)

    seam = (232, 238, 244)
    width = max(2, scale * 2)
    edges = {
        (top, ur), (ur, lr), (lr, bottom), (bottom, ll), (ll, ul), (ul, top),
        (top, it), (ur, it), (ur, ir), (ul, it), (ul, il), (ll, il), (ll, ib),
        (lr, ir), (lr, ib), (bottom, ib), (it, ir), (ir, ib), (ib, il), (il, it),
    }
    for a, b in edges:
        draw.line([a, b], fill=seam, width=width)

    return image.resize((size, size), Image.LANCZOS)


# --------------------------------------------------------------- framing

def background_of(image: Image.Image) -> tuple[int, int, int]:
    """The ground colour, read from the four corners of the master."""
    rgb = image.convert("RGB")
    w, h = rgb.size
    corners = [rgb.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    return tuple(round(sum(c[i] for c in corners) / 4) for i in range(3))  # type: ignore[return-value]


def subject_box(image: Image.Image, ground: tuple[int, int, int], tolerance: int = 18):
    """Bounding box of everything that is not the ground colour."""
    rgb = image.convert("RGB")
    diff = Image.eval(
        Image.merge("RGB", [
            Image.eval(band, lambda v, g=g: abs(v - g)) for band, g in zip(rgb.split(), ground)
        ]).convert("L"),
        lambda v: 255 if v > tolerance else 0,
    )
    box = diff.getbbox()
    return box or (0, 0, rgb.width, rgb.height)


def framed_square(master: Image.Image, side: int, fill: float, ground) -> Image.Image:
    """The crystal re-centred on a fresh square of the ground colour."""
    left, top, right, bottom = subject_box(master, ground)
    crystal = master.convert("RGB").crop((left, top, right, bottom))
    longest = max(crystal.size)
    target = int(round(side * fill))
    # Downsample in one high-quality step from the master's resolution.
    ratio = target / longest
    crystal = crystal.resize(
        (max(1, int(round(crystal.width * ratio))), max(1, int(round(crystal.height * ratio)))),
        Image.LANCZOS,
    )
    canvas = Image.new("RGB", (side, side), ground)
    canvas.paste(crystal, ((side - crystal.width) // 2, (side - crystal.height) // 2))
    return canvas


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def ogp_card(master: Image.Image, ground) -> Image.Image:
    """1200 x 630: crystal on the left, wordmark and one line beside it."""
    width, height = 1200, 630
    margin = 88
    card = Image.new("RGB", (width, height), ground)
    crystal = framed_square(master, 440, 0.86, ground)
    card.paste(crystal, (margin, (height - crystal.height) // 2))

    draw = ImageDraw.Draw(card)
    ink = (20, 24, 29)
    muted = (87, 96, 106)
    x = margin + crystal.width + 44
    room = width - margin - x

    word = font(92)
    # The tagline wraps at its comma and shrinks until the longer line fits
    # the room beside the crystal, so a longer tagline never runs off the card.
    lines = [part.strip() for part in TAGLINE.split(",")]
    lines = [lines[0] + ","] + lines[1:] if len(lines) > 1 else lines
    size = 30
    while size > 16:
        line = font(size)
        if max(draw.textlength(text, font=line) for text in lines) <= room:
            break
        size -= 1
    line = font(size)

    word_box = draw.textbbox((0, 0), WORDMARK, font=word)
    word_h = word_box[3] - word_box[1]
    line_h = int(size * 1.35)
    block = word_h + 22 + line_h * len(lines)
    y = (height - block) // 2
    draw.text((x, y - word_box[1]), WORDMARK, font=word, fill=ink)
    y += word_h + 22
    for text in lines:
        draw.text((x, y), text, font=line, fill=muted)
        y += line_h
    return card


# ------------------------------------------------------------------ main

def build(master_path: Path = MASTER, out: Path = OUT) -> dict[str, Path]:
    master = Image.open(master_path)
    ground = background_of(master)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    def save(name: str, image: Image.Image, **kwargs) -> None:
        path = out / name
        image.save(path, optimize=True, **kwargs)
        written[name] = path

    save("icon-512.png", framed_square(master, 512, ICON_FILL, ground))
    save("icon-192.png", framed_square(master, 192, ICON_FILL, ground))
    save("apple-touch-icon.png", framed_square(master, 180, ICON_FILL, ground))
    save("brand-64.png", framed_square(master, 64, MARK_FILL, ground))
    save("brand-32.png", framed_square(master, 32, MARK_FILL, ground))
    save("ogp.png", ogp_card(master, ground))

    # One ICO holding three sizes. Pillow writes the sizes it is given from
    # the image passed, so the largest is rendered and the rest derived from it
    # with the same framing.
    ico = framed_square(master, 48, MARK_FILL, ground)
    save("favicon.ico", ico, sizes=[(16, 16), (32, 32), (48, 48)])

    print(f"master {master_path.relative_to(REPO_ROOT)} {master.size[0]}x{master.size[1]}")
    print(f"ground colour #{ground[0]:02X}{ground[1]:02X}{ground[2]:02X} (use as --brand-tint)")
    for name, path in written.items():
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--master", type=Path, default=MASTER, help="master PNG (default: assets/brand/petralysis-master.png)")
    parser.add_argument("--out", type=Path, default=OUT, help="output directory (default: assets/img)")
    parser.add_argument("--synthesize", action="store_true",
                        help="write a stand-in master before deriving (only until the real artwork exists)")
    args = parser.parse_args()
    if args.synthesize:
        args.master.parent.mkdir(parents=True, exist_ok=True)
        synthesize_master().save(args.master, optimize=True)
        print(f"synthesized stand-in master at {args.master}")
    build(args.master, args.out)


if __name__ == "__main__":
    main()
