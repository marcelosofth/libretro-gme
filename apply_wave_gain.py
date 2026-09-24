#!/usr/bin/env python3
"""apply_wave_gain.py - ondas do osciloscopio com mais movimento (ganho automatico).

Uso (na raiz do repo, DEPOIS do apply_wave_freq.py):  python3 apply_wave_gain.py [src/libretro.c]
Cada canal ganha um ganho automatico: mede o pico recente (decai devagar) e amplia
a onda para ocupar ~85% da altura, com ganho maximo limitado. Sons baixos ficam bem
mais animados; sons altos continuam iguais (ganho minimo 1x).
Ajuste no codigo: WAVE_TARGET (pico alvo, max 32767), WAVE_MAX_GAIN (x), WAVE_MIN_PEAK.
"""
import re, sys, shutil

NEW_FUNC = r'''/* Ganho automatico do osciloscopio (mais movimento nas ondas) */
#define WAVE_TARGET   28000   /* pico alvo (max 32767) */
#define WAVE_MAX_GAIN 12      /* ganho maximo (x) */
#define WAVE_MIN_PEAK 1500    /* abaixo disso nao amplia mais (evita ruido) */

static int wave_peak[2] = { 0, 0 };

static void draw_waveform(const short *audio, int frames)
{
   int i, ch;
   int gain[2];
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

   for (ch = 0; ch < 2; ch++)
   {
      int pk = 0;
      for (i = 0; i < WAVE_SPAN; i++)
      {
         int s = wave_lin[i * 2 + ch];
         if (s < 0) s = -s;
         if (s > pk) pk = s;
      }
      wave_peak[ch] -= wave_peak[ch] / 32;      /* decai devagar */
      if (pk > wave_peak[ch]) wave_peak[ch] = pk;
      pk = wave_peak[ch];
      if (pk < WAVE_MIN_PEAK) pk = WAVE_MIN_PEAK;
      gain[ch] = (WAVE_TARGET * 256) / pk;      /* ponto fixo 8.8 */
      if (gain[ch] > WAVE_MAX_GAIN * 256) gain[ch] = WAVE_MAX_GAIN * 256;
      if (gain[ch] < 256) gain[ch] = 256;
   }

   draw_wave_channel(wave_lin, WAVE_SPAN, 0, WAVE_TOP, WAVE_H, get_color(10, 28, 31), gain[0]);
   draw_wave_channel(wave_lin, WAVE_SPAN, 1, WAVE_TOP + WAVE_H + WAVE_GAP, WAVE_H, get_color(28, 12, 27), gain[1]);
}'''

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "src/libretro.c"
    raw = open(path, "rb").read().decode("utf-8", "surrogateescape")
    crlf = "\r\n" in raw
    src = raw.replace("\r\n", "\n")
    if "#define WAVE_MAX_GAIN" in src:
        sys.exit("Ja aplicado. Para ajustar, edite WAVE_TARGET / WAVE_MAX_GAIN no codigo.")
    if "#define WAVE_SPAN" not in src:
        sys.exit("ERRO: rode antes o apply_wave_freq.py. Nada alterado.")

    sig = re.compile(r"(static void draw_wave_channel\([^)]*?unsigned short color)\)")
    line = re.compile(r"int y(\s*)=\s*mid - \(s \* \(h / 2\)\) / 32768;")
    func = re.compile(r"static void draw_waveform\(const short \*audio, int frames\)\n\{.*?\n\}", re.S)
    for name, pat in (("assinatura", sig), ("linha do y", line), ("draw_waveform", func)):
        if len(pat.findall(src)) != 1:
            sys.exit("ERRO: nao achei %s no formato esperado; nada alterado." % name)

    out = sig.sub(lambda m: m.group(1) + ", int gain_q8)", src, count=1)
    out = line.sub(lambda m: "int v = (s * gain_q8) >> 8;\n      int y = mid - (v * (h / 2)) / 32768;", out, count=1)
    out = func.sub(lambda m: NEW_FUNC, out, count=1)

    shutil.copyfile(path, path + ".bak_wave_gain")
    if crlf: out = out.replace("\n", "\r\n")
    open(path, "wb").write(out.encode("utf-8", "surrogateescape"))
    print("OK: ganho automatico aplicado em", path, "(backup:", path + ".bak_wave_gain)")

if __name__ == "__main__":
    main()
