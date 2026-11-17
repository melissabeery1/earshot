"""Makes your own menu bar icons: in your colours, or from a photo of you.

    .venv/bin/python make_icons.py --color "#2B1626"
    .venv/bin/python make_icons.py --photo ~/Pictures/me.jpg --ring "#E57BA6"
    .venv/bin/python make_icons.py --photo me.jpg --tint "#F4C6D6" --ring "#E57BA6" --dot "#D62828"

Writes three files to icons/:
  idle.png       the everyday icon, also used on review notifications
  listening.png  while you dictate: the idle icon with a coloured ring
  recording.png  while a call is recording: a dark ring and a red dot

Each is 104 pixels square with a transparent background. The menu bar shows it at 26 points, so 104 stays sharp
on Retina screens. The colours show because the code tells macOS this isn't a template image (template images
are turned black and white to match the menu bar). Needs Pillow: .venv/bin/pip install pillow
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageOps

S = 104
HERE = os.path.dirname(os.path.abspath(__file__))


def rgba(hex_colour, alpha=255):
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def circle_mask(inset):
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).ellipse((inset, inset, S - inset, S - inset), fill=255)
    return m


def from_colour(colour, mark):
    """A disc in your colour with two sound waves, the default look."""
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((14, 14, S - 14, S - 14), fill=rgba(colour))
    for r in (18, 30):
        d.arc((S / 2 - r, S / 2 - r, S / 2 + r, S / 2 + r), start=-50, end=50, fill=rgba(mark), width=7)
    d.ellipse((S / 2 - 26, S / 2 - 6, S / 2 - 14, S / 2 + 6), fill=rgba(mark))
    return im


def from_photo(path, tint=None):
    """Your photo, cropped to a circle from its centre. With --tint, turned into shades of one colour, which reads
    better at 26 points than a full-colour photo."""
    photo = ImageOps.exif_transpose(Image.open(os.path.expanduser(path))).convert("RGB")
    photo = ImageOps.fit(photo, (S - 28, S - 28), centering=(0.5, 0.4))      # a little above centre, for a face
    if tint:
        grey = ImageOps.autocontrast(photo.convert("L"))
        photo = ImageOps.colorize(grey, black=(40, 20, 34), white=rgba(tint)[:3], mid=None).convert("RGB")
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    im.paste(photo, (14, 14), circle_mask(0).resize((S - 28, S - 28)))
    return im


def with_ring(base, colour):
    im = base.copy()
    ImageDraw.Draw(im).ellipse((4, 4, S - 4, S - 4), outline=rgba(colour), width=8)
    return im


def with_dot(base, ring, dot):
    im = with_ring(base, ring)
    ImageDraw.Draw(im).ellipse((S - 34, 4, S - 4, 34), fill=rgba(dot))
    return im


def main():
    p = argparse.ArgumentParser(description="Make your own menu bar icons.")
    p.add_argument("--color", default="#2B1626", help="disc colour when there's no photo")
    p.add_argument("--mark", default="#FBE1E7", help="colour of the sound waves on the disc")
    p.add_argument("--photo", help="a photo to crop into a circle instead of the disc")
    p.add_argument("--tint", help="turn the photo into shades of this colour")
    p.add_argument("--ring", default="#E57BA6", help="ring colour while you dictate")
    p.add_argument("--rec-ring", default="#2B1626", help="ring colour while a call records")
    p.add_argument("--dot", default="#D62828", help="dot colour while a call records")
    a = p.parse_args()

    base = from_photo(a.photo, a.tint) if a.photo else from_colour(a.color, a.mark)
    out = os.path.join(HERE, "icons")
    os.makedirs(out, exist_ok=True)
    base.save(os.path.join(out, "idle.png"))
    with_ring(base, a.ring).save(os.path.join(out, "listening.png"))
    with_dot(base, a.rec_ring, a.dot).save(os.path.join(out, "recording.png"))
    print("Made icons/idle.png, listening.png and recording.png. In the menu bar: Restart dictation.")


if __name__ == "__main__":
    main()
