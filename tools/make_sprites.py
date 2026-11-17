# /// script
# requires-python = ">=3.12"
# dependencies = ["pillow"]
# ///
"""Generates the mood sprites for the dashboard card and the brand icon.

Run with: uv run tools/make_sprites.py
"""

from pathlib import Path

from PIL import Image

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "shanagotchi"
SPRITES = COMPONENT / "www" / "sprites"
PAPER = (244, 241, 234, 255)

base = [
    ".....######.....",
    "...##......##...",
    "..#..........#..",
    ".#............#.",
    "#..............#",
    "#..............#",
    "#..............#",
    "#..............#",
    "#..............#",
    ".#............#.",
    "..############..",
    "..#.#......#.#..",
]
eyes = {
    "open": [(4, 4), (4, 5), (5, 4), (5, 5), (4, 10), (4, 11), (5, 10), (5, 11)],
    "happy": [(4, 5), (5, 4), (5, 6), (4, 10), (5, 9), (5, 11)],
    "flat": [(5, 4), (5, 5), (5, 10), (5, 11)],
    "sad": [(5, 4), (5, 5), (5, 10), (5, 11), (4, 6), (4, 9)],
    "sleep": [(5, 4), (5, 5), (5, 6), (5, 9), (5, 10), (5, 11)],
    "wide": [
        (3, 4),
        (3, 5),
        (4, 4),
        (4, 5),
        (5, 4),
        (5, 5),
        (3, 10),
        (3, 11),
        (4, 10),
        (4, 11),
        (5, 10),
        (5, 11),
    ],
}
mouths = {
    "smile": [(7, 5), (7, 10), (8, 6), (8, 7), (8, 8), (8, 9)],
    "grin": [
        (7, 5),
        (7, 6),
        (7, 7),
        (7, 8),
        (7, 9),
        (7, 10),
        (8, 6),
        (8, 7),
        (8, 8),
        (8, 9),
    ],
    "flat": [(8, 6), (8, 7), (8, 8), (8, 9)],
    "frown": [(7, 6), (7, 7), (7, 8), (7, 9), (8, 5), (8, 10)],
    "o": [(7, 7), (7, 8), (8, 6), (8, 9)],
    "small": [(8, 7), (8, 8)],
}
extra = {"blush": [(6, 2), (6, 13)], "tear": [(6, 11), (7, 11)]}
moods = {
    "hungry": ("wide", "o", []),
    "proud": ("happy", "grin", ["blush"]),
    "happy": ("happy", "smile", ["blush"]),
    "okay": ("open", "flat", []),
    "low": ("flat", "frown", []),
    "sad": ("sad", "frown", ["tear"]),
    "sleep": ("sleep", "small", []),
    "ask": ("open", "small", []),
}

P = 10
cols = {"#": (0, 0, 0, 255), "blush": (255, 0, 0, 255), "tear": (0, 0, 255, 255)}


def put(px, cells, c):
    for r, cc in cells:
        for y in range(r * P, r * P + P):
            for x in range(cc * P, cc * P + P):
                px[x, y] = c


for mood, (e, mo, ex) in moods.items():
    im = Image.new("RGBA", (16 * P, 12 * P), (0, 0, 0, 0))
    px = im.load()
    outline = [
        (r, c) for r, row in enumerate(base) for c, ch in enumerate(row) if ch == "#"
    ]
    put(px, outline + eyes[e] + mouths[mo], cols["#"])
    for k in ex:
        put(px, extra[k], cols[k])
    im.save(SPRITES / f"{mood}.png")
star = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
sp = star.load()
for y, row in enumerate(["..#..", ".###.", "#####", ".###.", ".#.#."]):
    for x, ch in enumerate(row):
        if ch == "#":
            for yy in range(y * 4, y * 4 + 4):
                for xx in range(x * 4, x * 4 + 4):
                    sp[xx, yy] = (230, 170, 0, 255)
star.save(SPRITES / "star.png")

icon = Image.new("RGBA", (256, 256), PAPER)
happy = Image.open(SPRITES / "happy.png").resize((224, 168), Image.NEAREST)
icon.paste(happy, (16, 44), happy)
icon.save(COMPONENT / "brand" / "icon.png")
