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
    # Funcoes do osciloscopio, logo depois de draw_ui()
    (
        '/*\n * Tell libretro about this core, it\'s name, version and which rom files it supports.\n */',

        '''/* ---- osciloscopio estereo (espaco entre o cabecalho e o espectro) ---- */
#define WAVE_TOP  154
#define WAVE_H    48
#define WAVE_GAP  10

static void draw_wave_channel(const short *audio, int frames, int offset,
                               int y0, int h, unsigned short color)
{
   int x, px = -1, py = 0;
   int mid = y0 + h / 2;

   draw_line(framebuffer, get_color(4, 7, 8), UI_LEFT, mid, UI_RIGHT, mid);

   for (x = 0; x < UI_W; x++)
   {
      int idx = (x * frames) / UI_W;
      int s   = audio[idx * 2 + offset];
      int y   = mid - (s * (h / 2)) / 32768;
      if (y < y0)         y = y0;
      if (y >= y0 + h)     y = y0 + h - 1;
      if (px >= 0)
         draw_line(framebuffer, color, UI_LEFT + px, py, UI_LEFT + x, y);
      px = x;
      py = y;
   }
}

static void draw_waveform(const short *audio, int frames)
{
   draw_wave_channel(audio, frames, 0, WAVE_TOP, WAVE_H, get_color(10, 28, 31));
   draw_wave_channel(audio, frames, 1, WAVE_TOP + WAVE_H + WAVE_GAP, WAVE_H, get_color(28, 12, 27));
}

/*
 * Tell libretro about this core, it's name, version and which rom files it supports.
 */'''
    ),
    # Chamada no retro_run, logo apos draw_ui()
    (
        '   //graphic handling\n'
        '   spectrum_draw_background(framebuffer);\n'
        '   draw_ui();\n'
        '   spectrum_draw_bars(framebuffer);',

        '   //graphic handling\n'
        '   spectrum_draw_background(framebuffer);\n'
        '   draw_ui();\n'
        '   draw_waveform(audio, 735);\n'
        '   spectrum_draw_bars(framebuffer);'
    ),
])

print("Osciloscopio estereo adicionado.")
