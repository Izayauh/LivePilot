"""Draw the Live Pilot icon in the window's own palette: python studio/make_icon.py

Writes studio/static/icon.png (512) and icon.ico (16..256) for the desktop shortcut and the tab.
"""

from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
BG = (20, 21, 23)        # --bg
PANEL = (27, 29, 32)     # --panel
ACCENT = (224, 163, 58)  # --accent
OK = (76, 183, 130)      # --ok
TEXT = (232, 230, 225)   # --text

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([0, 0, S, S], radius=220, fill=BG)

# A waveform of five bars, the middle one taller: sound coming in.
bar_w, gap = 92, 54
heights = [260, 420, 620, 420, 260]
total = 5 * bar_w + 4 * gap
x = (S - total) / 2
cy = S / 2 + 40
for i, h in enumerate(heights):
    color = ACCENT if i == 2 else PANEL
    d.rounded_rectangle([x, cy - h / 2, x + bar_w, cy + h / 2], radius=bar_w / 2, fill=color,
                        outline=(42, 45, 49), width=6)
    x += bar_w + gap

# The listening light, top right, same green as the window's pill.
d.ellipse([S - 300, 150, S - 160, 290], fill=OK)

out = Path(__file__).parent / "static"
img.resize((512, 512), Image.LANCZOS).save(out / "icon.png")
img.resize((256, 256), Image.LANCZOS).save(out / "icon.ico",
                                           sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", out / "icon.png", out / "icon.ico")
