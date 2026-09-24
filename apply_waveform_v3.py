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
    # Recentraliza o osciloscopio dentro da caixa (medido: caixa vai de y~153.5
    # a y~286.5, centro y=220; conteudo antigo ia de 154 a 260, centro y=207 -> +13px)
    (
        '#define WAVE_TOP  154',
        '#define WAVE_TOP  167'
    ),
    # Recentraliza a barra de progresso dentro da caixa (medido: caixa vai de
    # y~400.8 a y~438.1, centro y~419.5; barra antiga ia de 410 a 422, centro
    # y=416 -> +3px)
    (
        '   draw_shape(framebuffer, get_color(4, 8, 9), UI_LEFT, 410, UI_W, 12);\n'
        '   prog = get_track_progress_permille();\n'
        '   if (prog > 0)\n'
        '      draw_shape(framebuffer, get_color(12, 25, 28), UI_LEFT, 410, (UI_W * prog) / 1000, 12);',

        '   draw_shape(framebuffer, get_color(4, 8, 9), UI_LEFT, 413, UI_W, 12);\n'
        '   prog = get_track_progress_permille();\n'
        '   if (prog > 0)\n'
        '      draw_shape(framebuffer, get_color(12, 25, 28), UI_LEFT, 413, (UI_W * prog) / 1000, 12);'
    ),
])

print("Waveform e barra de progresso recentralizados.")
