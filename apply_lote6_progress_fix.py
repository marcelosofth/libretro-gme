#!/usr/bin/env python3
import sys

def patch(path, replacements):
    with open(path, 'r') as f:
        content = f.read()
    for old, new in replacements:
        if content.count(old) != 1:
            print(f"AVISO: ancora nao encontrada (ou nao unica) em {path}:\n{old!r}")
            sys.exit(1)
        content = content.replace(old, new, 1)
    with open(path, 'w') as f:
        f.write(content)
    print(f"OK: {path} patchado.")

patch('src/libretro.c', [
    (
        '   /* barra de progresso */\n'
        '   draw_shape(framebuffer, get_color(4, 8, 9), UI_LEFT, 418, UI_W, 12);\n'
        '   prog = get_track_progress_permille();\n'
        '   if (prog > 0)\n'
        '      draw_shape(framebuffer, get_color(12, 25, 28), UI_LEFT, 418, (UI_W * prog) / 1000, 12);',

        '   /* barra de progresso (proxima ao espectro, cuja base fica em y=408) */\n'
        '   draw_shape(framebuffer, get_color(4, 8, 9), UI_LEFT, 410, UI_W, 12);\n'
        '   prog = get_track_progress_permille();\n'
        '   if (prog > 0)\n'
        '      draw_shape(framebuffer, get_color(12, 25, 28), UI_LEFT, 410, (UI_W * prog) / 1000, 12);'
    ),
])

print("Barra de progresso subida (Lote 6).")
