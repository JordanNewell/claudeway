"""Claudeway OG image generator.

Terminal-screen aesthetic, NEWELL brand tokens, honest framing.
Replaces the prior "BUZZ PUNTED ON" thesis with "VERIFIABLE CONSENSUS".

Reads canonical tokens from the vaulted brand-system; no hardcoded hex.

Usage:
    py scripts/generate_og.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TOKENS_PATH = Path("e:/vaults/anything.xyz/50_Projects/brand-system/tokens.json")
SPACE_GROTESK_DIR = Path.home() / "AppData/Local/Microsoft/Windows/Fonts"
JETBRAINS_DIR = Path.home() / "AppData/Local/Microsoft/Windows/Fonts"

SPACE_GROTESK = {
    "Medium":   SPACE_GROTESK_DIR / "SpaceGrotesk-variable.ttf",  # variable font
    "SemiBold": SPACE_GROTESK_DIR / "SpaceGrotesk-variable.ttf",
    "Bold":     SPACE_GROTESK_DIR / "SpaceGrotesk-Bold.ttf",
}
JETBRAINS = {
    "Regular": JETBRAINS_DIR / "JetBrainsMono-Regular.ttf",
    "Medium":  JETBRAINS_DIR / "JetBrainsMono-Medium.ttf",
    "Bold":    JETBRAINS_DIR / "JetBrainsMono-Bold.ttf",
}

CANVAS_W = 1280
CANVAS_H = 640

EVENT_ID = "3974ebfe688f1639a8534b46bbbfeddf354d18efcd190352da877756d1bac60b"


def parse_hex(s: str) -> tuple[int, int, int]:
    s = s.strip().lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def load_tokens() -> dict:
    return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def grid(n: int) -> int:
    return int(n * 8)


def main() -> int:
    tokens = load_tokens()
    bg = parse_hex(tokens["colors"]["background"])
    text = parse_hex(tokens["colors"]["text"])
    primary = parse_hex(tokens["colors"]["primary"])
    muted = parse_hex(tokens["colors"]["muted"])
    surface = parse_hex(tokens["colors"]["surface"])
    border = parse_hex(tokens["colors"]["border"])

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), bg)
    draw = ImageDraw.Draw(canvas)

    # Scanline texture (subtle material depth)
    scanline_overlay = (
        min(surface[0] + 6, 255),
        min(surface[1] + 6, 255),
        min(surface[2] + 6, 255),
    )
    for y in range(0, CANVAS_H, 4):
        draw.line([(0, y), (CANVAS_W, y)], fill=scanline_overlay, width=1)

    # Hairline border frame
    inset = grid(2)
    draw.rectangle(
        [inset, inset, CANVAS_W - inset, CANVAS_H - inset],
        outline=border,
        width=1,
    )

    margin_x = grid(8)  # 64px

    # 1. Receipt chip (top-left)
    chip_text = "claudeway v0.3.2"
    chip_font = font(JETBRAINS["Medium"], 18)
    chip_pad_x = grid(2)
    chip_pad_y = grid(1)
    chip_bbox = draw.textbbox((0, 0), chip_text, font=chip_font)
    chip_w = chip_bbox[2] - chip_bbox[0] + chip_pad_x * 2
    chip_h = chip_bbox[3] - chip_bbox[1] + chip_pad_y * 2
    chip_x, chip_y = margin_x, grid(8)
    draw.rounded_rectangle(
        [chip_x, chip_y, chip_x + chip_w, chip_y + chip_h],
        radius=4,
        fill=surface,
        outline=border,
        width=1,
    )
    draw.text(
        (chip_x + chip_pad_x - chip_bbox[0], chip_y + chip_pad_y - chip_bbox[1]),
        chip_text,
        font=chip_font,
        fill=muted,
    )

    # 2. Terminal session (left-aligned, below chip)
    term_font = font(JETBRAINS["Regular"], 20)
    term_lines = [
        ("$ reach_consensus --sign=ed25519 --publish=nostr", primary),
        ("> three agents · debate (round 2)", muted),
        ("> agreement: 34%", muted),
        ("> signing... ✓", text),
        ("> publishing to wss://nos.lol ... ✓", text),
        ("[ok] kind:30078 ed25519 4/7 relays nak verify: 0", primary),
    ]
    term_y = chip_y + chip_h + grid(4)
    line_height = 28
    for line, color in term_lines:
        draw.text((margin_x, term_y), line, font=term_font, fill=color)
        term_y += line_height

    # 3. Hero title — Space Grotesk SemiBold, centered
    title_text = "VERIFIABLE CONSENSUS"
    title_font = font(SPACE_GROTESK["SemiBold"], 84)
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]
    title_x = (CANVAS_W - title_w) // 2 - title_bbox[0]
    title_y = grid(40)  # 320px — lower half, hero position
    draw.text((title_x, title_y), title_text, font=title_font, fill=text)

    # Blinking cursor block immediately after title
    cursor_w, cursor_h = 24, title_h - 12
    cursor_x = title_x + title_w + 12
    cursor_y = title_y + 12
    draw.rectangle([cursor_x, cursor_y, cursor_x + cursor_w, cursor_y + cursor_h], fill=primary)

    # 4. Subtitle
    subtitle_text = "signed agreement, on the open wire"
    subtitle_font = font(SPACE_GROTESK["Medium"], 32)
    sub_bbox = draw.textbbox((0, 0), subtitle_text, font=subtitle_font)
    sub_w = sub_bbox[2] - sub_bbox[0]
    sub_x = (CANVAS_W - sub_w) // 2 - sub_bbox[0]
    sub_y = title_y + title_h + grid(3)
    draw.text((sub_x, sub_y), subtitle_text, font=subtitle_font, fill=muted)

    # 5. Footer — event ID hash, bottom-right (tiny mono)
    footer_font = font(JETBRAINS["Regular"], 14)
    footer_text = EVENT_ID
    foot_bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
    foot_w = foot_bbox[2] - foot_bbox[0]
    foot_x = CANVAS_W - margin_x - foot_w - foot_bbox[0]
    foot_y = CANVAS_H - grid(8) - (foot_bbox[3] - foot_bbox[1])
    draw.text((foot_x, foot_y), footer_text, font=footer_font, fill=muted)

    # 6. NEWELL signature — bottom-left
    sig_font = font(JETBRAINS["Bold"], 14)
    sig_text = "NEWELL  /  BUILD. CONNECT. GROW."
    sig_y = CANVAS_H - grid(8) - 14
    draw.text((margin_x, sig_y), sig_text, font=sig_font, fill=primary)

    out_path = Path("assets/og/claudeway-og.png").resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG", optimize=True)
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
