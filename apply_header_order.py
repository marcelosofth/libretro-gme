#!/usr/bin/env python3
"""apply_header_order.py - reordena as 4 linhas do cabecalho do player.

Uso (na raiz do repo):  python3 apply_header_order.py [src/libretro.c]
Nova ordem (uma linha por faixa do fundo):
  1) CHIP: (led) chip     2) sistema     3) jogo     4) faixa (esq) + Track N/M (dir)
Linhas 1-3 param em x=416 (antes do logo; nas funcoes *_clip o limite e um x absoluto). A linha 4 ajusta a largura da faixa
a partir do tamanho do texto "Track N/M" (nunca passa por cima dele).
Backup: libretro.c.bak_hdr
"""
import re, sys, shutil

DEFS = r'''/* Cabecalho: 4 linhas, uma por faixa do fundo (y = topo do texto).
 * 1) chip  2) sistema  3) jogo  4) faixa + Track N/M.
 * HDR_TEXT_MAX_X: limite direito das linhas 1-3 (o logo comeca depois). */
#define HDR_Y1 24
#define HDR_Y2 60
#define HDR_Y3 96
#define HDR_Y4 132
#define HDR_TEXT_MAX_X 416

'''

NEW_BLOCK = r'''   /* cabecalho: linha 4 = faixa (esq) + Track N/M (dir) */
   get_track_label(message);
   w = text_width_prop(message);
   draw_text_prop(message, UI_RIGHT - w, HDR_Y4, get_color(28, 56, 28));
   draw_text_scroll(get_song_name(message), UI_LEFT, HDR_Y4, UI_W - w - 16, get_color(30, 58, 25));

   /* linha 3 = jogo */
   draw_text_scroll(get_game_name(message), UI_LEFT, HDR_Y3, HDR_TEXT_MAX_X - UI_LEFT, get_color(19, 36, 27));  /* 3o parametro = largura */

   /* linha 2 = sistema */
   get_system_line(message);
   draw_text_prop_clip(message, UI_LEFT, HDR_Y2, get_color(15, 33, 21), HDR_TEXT_MAX_X);

   /* linha 1 = CHIP: (led) chip de audio */
   {
      int lx = UI_LEFT + text_width_prop("CHIP:") + 16;
      draw_text_prop("CHIP:", UI_LEFT, HDR_Y1, get_color(15, 33, 21));
      draw_led(lx + 6, HDR_Y1 + 6);
      draw_text_prop_clip(get_chip_text(message), lx + 24, HDR_Y1, get_color(27, 54, 29), HDR_TEXT_MAX_X);
   }
'''

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "src/libretro.c"
    raw = open(path, "rb").read().decode("utf-8", "surrogateescape")
    crlf = "\r\n" in raw
    src = raw.replace("\r\n", "\n")
    if "#define HDR_Y1" in src:
        sys.exit("Ja aplicado (HDR_Y1 existe). Para ajustar, edite os #define HDR_Y*.")
    blk = re.compile(r"[ ]*/\* cabecalho \*/\n.*?draw_text_prop_clip\(get_chip_text\(message\)[^\n]*\n[ ]*\}\n", re.S)
    sig = re.compile(r"static void draw_ui\(void\)")
    if len(blk.findall(src)) != 1 or len(sig.findall(src)) != 1:
        sys.exit("ERRO: nao achei o cabecalho de draw_ui no formato esperado; nada alterado.")
    m = blk.search(src)
    old = m.group(0)
    for needle in ("get_song_name", "get_track_label", "get_game_name", "get_system_line", "get_chip_text", "draw_led"):
        if needle not in old:
            sys.exit("ERRO: bloco inesperado (falta %s); nada alterado." % needle)
    out = blk.sub(lambda mm: NEW_BLOCK, src, count=1)
    out = sig.sub(lambda mm: DEFS + "static void draw_ui(void)", out, count=1)
    shutil.copyfile(path, path + ".bak_hdr")
    if crlf: out = out.replace("\n", "\r\n")
    open(path, "wb").write(out.encode("utf-8", "surrogateescape"))
    print("OK: cabecalho reordenado em", path, "(backup:", path + ".bak_hdr)")

if __name__ == "__main__":
    main()
