#!/usr/bin/env python3
"""apply_wave_freq.py - osciloscopio mostra uma janela maior de audio (mais oscilacoes).

Uso (na raiz do repo):  python3 apply_wave_freq.py [src/libretro.c]
Antes: cada quadro desenhava so as 735 amostras do quadro atual (~16,7 ms).
Depois: guarda as ultimas amostras num buffer circular e desenha as ultimas
WAVE_SPAN (padrao 1470 = 2 quadros, ~33 ms) => o dobro de oscilacoes na tela.
Ajuste fino: mude WAVE_SPAN no codigo (735 = como era, 1470 = 2x, 2205 = 3x; max 8000).
"""
import re, sys, shutil

NEW = r'''/* Janela do osciloscopio: WAVE_SPAN amostras (por canal) mais recentes.
 * 735 = 1 quadro (~16,7 ms); maior = mais oscilacoes visiveis na tela.
 * WAVE_RING deve ser potencia de 2 e maior que WAVE_SPAN. */
#define WAVE_SPAN 1470
#define WAVE_RING 8192

static short wave_ring[WAVE_RING * 2];
static short wave_lin[WAVE_SPAN * 2];
static unsigned wave_pos = 0;

static void draw_waveform(const short *audio, int frames)
{
   int i;
   unsigned start;

   for (i = 0; i < frames; i++)
   {
      unsigned p = wave_pos & (WAVE_RING - 1);
      wave_ring[p * 2]     = audio[i * 2];
      wave_ring[p * 2 + 1] = audio[i * 2 + 1];
      wave_pos++;
   }

   start = wave_pos - WAVE_SPAN;
   for (i = 0; i < WAVE_SPAN; i++)
   {
      unsigned p = (start + (unsigned)i) & (WAVE_RING - 1);
      wave_lin[i * 2]     = wave_ring[p * 2];
      wave_lin[i * 2 + 1] = wave_ring[p * 2 + 1];
   }

   draw_wave_channel(wave_lin, WAVE_SPAN, 0, WAVE_TOP, WAVE_H, get_color(10, 28, 31));
   draw_wave_channel(wave_lin, WAVE_SPAN, 1, WAVE_TOP + WAVE_H + WAVE_GAP, WAVE_H, get_color(28, 12, 27));
}'''

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "src/libretro.c"
    raw = open(path, "rb").read().decode("utf-8", "surrogateescape")
    crlf = "\r\n" in raw
    src = raw.replace("\r\n", "\n")
    if "#define WAVE_SPAN" in src:
        sys.exit("Ja aplicado (WAVE_SPAN existe). Para ajustar, edite o #define WAVE_SPAN.")
    pat = re.compile(r"static void draw_waveform\(const short \*audio, int frames\)\n\{.*?\n\}", re.S)
    ms = pat.findall(src)
    if len(ms) != 1 or "draw_wave_channel" not in ms[0]:
        sys.exit("ERRO: nao achei draw_waveform no formato esperado; nada alterado.")
    out = pat.sub(lambda m: NEW, src, count=1)
    shutil.copyfile(path, path + ".bak_wave")
    if crlf: out = out.replace("\n", "\r\n")
    open(path, "wb").write(out.encode("utf-8", "surrogateescape"))
    print("OK: osciloscopio atualizado em", path, "(backup:", path + ".bak_wave)")

if __name__ == "__main__":
    main()
