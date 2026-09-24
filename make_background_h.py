#!/usr/bin/env python3
"""Gera background.h (fundo principal, 640x480, RGB565) a partir de uma imagem.

Uso:
    python3 make_background_h.py fundo.png background.h
"""
import sys
from PIL import Image

W, H = 640, 480

def main():
    if len(sys.argv) < 3:
        print("Uso: python3 make_background_h.py <imagem_entrada> <background.h_saida>")
        sys.exit(1)

    src_path = sys.argv[1]
    out_path = sys.argv[2]

    img = Image.open(src_path).convert("RGB")
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)

    pixels = list(img.getdata())

    lines = []
    lines.append("/* background.h - fundo principal (640x480), gerado automaticamente")
    lines.append("   a partir de %s. RGB565, mesmo formato/uso de credits_bg.h. */" % src_path.split("/")[-1])
    lines.append("#ifndef GME_LIBRETRO_BACKGROUND_H__")
    lines.append("#define GME_LIBRETRO_BACKGROUND_H__")
    lines.append("")
    lines.append("#define BG_W %d" % W)
    lines.append("#define BG_H %d" % H)
    lines.append("")
    lines.append("static const unsigned short bg_pixels[BG_W * BG_H] = {")

    vals = []
    for (r, g, b) in pixels:
        v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        vals.append(v)

    per_line = 16
    for i in range(0, len(vals), per_line):
        chunk = vals[i:i + per_line]
        lines.append("   " + ",".join(str(v) for v in chunk) + ",")

    lines.append("};")
    lines.append("")
    lines.append("#endif")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("OK: %s gerado (%d x %d, %d pixels)" % (out_path, W, H, len(vals)))


if __name__ == "__main__":
    main()
