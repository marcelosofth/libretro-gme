#!/usr/bin/env python3
"""apply_chip_font.py - linha do CHIP com a fonte Press Start 2P (maiuscula) e degrade vertical.

Uso (na raiz do repo):  python3 apply_chip_font.py [src/libretro.c]
Requer o apply_header_order.py ja aplicado (HDR_Y1 no codigo).
- Cria src/font_chip.h (atlas 128x128, mesmo formato da fonte principal)
- Adiciona funcoes chip_* em libretro.c (fonte propria, nao mexe no put_glyph/glyph_extent)
- Linha 1 (CHIP: + texto do chip) usa a fonte nova com degrade da imagem de referencia:
  azul -> branco (metade de cima), dourado -> creme (metade de baixo). O led continua igual.
- Corrige tambem o limite direito da linha do sistema (maxx absoluto = HDR_TEXT_MAX_X)
Backup: libretro.c.bak_chip
"""
import re, sys, os, shutil

ATLAS_HEX = [
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00386c6c106270300c60000000000002",
    "00386cfe7ca4d83018306c1800000004",
    "00386c6cd0c8d8303018381800000008",
    "0030006c7c1070003018fe7e007e0010",
    "0030006c1626da003018381800000020",
    "000000fefc4acc0018306c1830003040",
    "0030006c108c7e000c60000030003080",
    "00000000000000000000000060000000",
    "38187c7e1cfc3cfe787c00000c00607c",
    "4c38c60c3cc060c6c4c63030180030fe",
    "c6180e186cfcc00ce4c6303030fe18c6",
    "c6183c3ccc06fc18787e000060000c0c",
    "c6187806fe06c6309e06303030fe1838",
    "6418e0c60cc6c630860c303018003000",
    "387efe7c0c7c7c307c7800600c006038",
    "00000000000000000000000000000000",
    "7c38fc3cf8fefe3ec67e06c660c6c67c",
    "826cc666ccc0c060c61806cc60eee6c6",
    "bac6c6c0c6c0c0c0c61806d860fef6c6",
    "aac6fcc0c6fcfccefe1806f060d6dec6",
    "befec6c0c6c0c0c6c61806f860d6cec6",
    "80c6c666ccc0c066c618c6dc60c6c6c6",
    "7cc6fc3cf8fec03ec67e7cce7ec6c67c",
    "00000000000000000000000000000000",
    "fc7cfc7c7ec6c6d6c666fe3c80783800",
    "c6c6c6c618c6c6d6c6660e3040186c00",
    "c6c6c6c018c6c6d66c661c3020180000",
    "c6c6ce7c18c6eed6383c383010180000",
    "fcdef80618c67cfe6c18703008180000",
    "c0ccdcc618c638eec618e03004180000",
    "c07ace7c187c1044c618fe3c02780000",
    "000000000000000000000000000000fe",
    "1038fc3cf8fefe3ec67e06c660c6c67c",
    "086cc666ccc0c060c61806cc60eee6c6",
    "00c6c6c0c6c0c0c0c61806d860fef6c6",
    "00c6fcc0c6fcfccefe1806f060d6dec6",
    "00fec6c0c6c0c0c6c61806f860d6cec6",
    "00c6c666ccc0c066c618c6dc60c6c6c6",
    "00c6fc3cf8fec03ec67e7cce7ec6c67c",
    "00000000000000000000000000000000",
    "fc7cfc7c7ec6c6d6c666fe0c18600000",
    "c6c6c6c618c6c6d6c6660e1818300000",
    "c6c6c6c018c6c6d66c661c1818307000",
    "c6c6ce7c18c6eed6383c38301818ba00",
    "fcdef80618c67cfe6c18701818301c00",
    "c0ccdcc618c638eec618e01818300000",
    "c07ace7c187c1044c618fe0c18600000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
]

FONT_H_HEAD = """#ifndef GME_LIBRETRO_FONT_CHIP_H__
#define GME_LIBRETRO_FONT_CHIP_H__

/* Fonte Press Start 2P (OFL), 8x8, so maiusculas (minusculas usam glifos maiusculos).
 * Mesmo formato da fonte principal: 128x128, 2 bytes/pixel, preto = pixel aceso. */
static const surface font_chip = {
  128, 128, 2,
"""

HELPERS = r"""/* ---- fonte do CHIP: Press Start 2P (src/font_chip.h) com degrade vertical ---- */
#include "font_chip.h"

#define CHIP_SPACE 5   /* largura do espaco (px do atlas) */

static unsigned short chip_grad[8];

static void chip_grad_init(void)
{
   /* degrade da imagem de referencia: azul -> branco (topo), dourado -> creme (base) */
   static const unsigned char rgb[8][3] = {
      { 69, 149, 204}, {135, 190, 231}, {212, 237, 253}, {255, 255, 255},
      {183, 129,  41}, {229, 185,  87}, {252, 245, 232}, {252, 245, 232}
   };
   int i;
   for (i = 0; i < 8; i++)
      chip_grad[i] = get_color(rgb[i][0] >> 3, rgb[i][1] >> 2, rgb[i][2] >> 3);
}

static int chip_pixel(unsigned char ch, int x, int y)
{
   const unsigned short *p = (const unsigned short *)font_chip.pixel_data;
   return p[(ch % 16) * 8 + x + ((ch >> 4) * 8 + y) * 128] == 0;
}

static void chip_extent(unsigned char ch, int *x0, int *x1)
{
   int x, y;
   *x0 = 8;
   *x1 = -1;
   for (x = 0; x < 8; x++)
      for (y = 0; y < 8; y++)
         if (chip_pixel(ch, x, y))
         {
            if (x < *x0) *x0 = x;
            if (x > *x1) *x1 = x;
         }
}

static void chip_put_glyph(unsigned char ch, int px, int py, int cx1)
{
   int x, y, sx, sy;
   for (y = 0; y < 8; y++)
      for (x = 0; x < 8; x++)
      {
         if (!chip_pixel(ch, x, y))
            continue;
         for (sy = 0; sy < 2; sy++)
         {
            int yy = py + y * 2 + sy;
            if (yy < 0 || yy >= 480)
               continue;
            for (sx = 0; sx < 2; sx++)
            {
               int xx = px + x * 2 + sx;
               if (xx < 0 || xx >= 640 || xx >= cx1)
                  continue;
               set_pixel(framebuffer, xx, yy, chip_grad[y]);
            }
         }
      }
}

static int chip_text_width(const char *text)
{
   int w = 0, x0, x1;
   for (; *text; text++)
   {
      chip_extent((unsigned char)*text, &x0, &x1);
      w += (x1 < 0) ? CHIP_SPACE : (x1 - x0 + 2);
   }
   w = w > 0 ? w - 1 : 0;
   return w * 2;
}

/* maxx = limite direito absoluto (x) */
static void chip_draw_text(const char *text, int x, int y, int maxx)
{
   int x0, x1;
   chip_grad_init();
   for (; *text && x < maxx; text++)
   {
      unsigned char ch = (unsigned char)*text;
      chip_extent(ch, &x0, &x1);
      if (x1 < 0)
      {
         x += CHIP_SPACE * 2;
         continue;
      }
      chip_put_glyph(ch, x - x0 * 2, y, maxx);
      x += (x1 - x0 + 2) * 2;
   }
}

""".replace("%%", "%")

NEW_CHIP = r"""   /* linha 1 = CHIP: (led) chip de audio - Press Start 2P com degrade */
   {
      int lx = UI_LEFT + chip_text_width("CHIP:") + 16;
      chip_draw_text("CHIP:", UI_LEFT, HDR_Y1, HDR_TEXT_MAX_X);
      draw_led(lx + 6, HDR_Y1 + 6);
      chip_draw_text(get_chip_text(message), lx + 24, HDR_Y1, HDR_TEXT_MAX_X);
   }
"""

def font_h_text():
    out = bytearray()
    for h in ATLAS_HEX:
        for b in bin(int(h, 16))[2:].zfill(128):
            out += b"\x00\x00" if b == "1" else b"\xff\xff"
    lines = []
    for y in range(128):
        row = out[y * 256:(y + 1) * 256]
        lines.append('  "' + "".join("\\%03o" % v for v in row) + '"')
    return FONT_H_HEAD + "\n".join(lines) + "\n};\n\n#endif\n"

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "src/libretro.c"
    raw = open(path, "rb").read().decode("utf-8", "surrogateescape")
    crlf = "\r\n" in raw
    src = raw.replace("\r\n", "\n")
    if "font_chip.h" in src:
        sys.exit("Ja aplicado (font_chip.h ja incluido).")
    if "#define HDR_Y1" not in src:
        sys.exit("ERRO: rode antes o apply_header_order.py. Nada alterado.")
    blk = re.compile(r"[ ]*/\* linha 1 = CHIP.*?draw_text_prop_clip\(get_chip_text\(message\)[^\n]*\n[ ]*\}\n", re.S)
    sig = re.compile(r"static void draw_ui\(void\)")
    sysline = re.compile(r"(draw_text_prop_clip\(message, UI_LEFT, HDR_Y2, get_color\(15, 33, 21\), )HDR_TEXT_MAX_X - UI_LEFT\)")
    if len(blk.findall(src)) != 1 or len(sig.findall(src)) != 1:
        sys.exit("ERRO: nao achei o bloco da linha 1 / draw_ui no formato esperado; nada alterado.")
    out = blk.sub(lambda m: NEW_CHIP, src, count=1)
    out = sysline.sub(lambda m: m.group(1) + "HDR_TEXT_MAX_X)", out, count=1)
    out = sig.sub(lambda m: HELPERS + "static void draw_ui(void)", out, count=1)
    d = os.path.dirname(os.path.abspath(path))
    shutil.copyfile(path, path + ".bak_chip")
    open(os.path.join(d, "font_chip.h"), "w").write(font_h_text())
    if crlf: out = out.replace("\n", "\r\n")
    open(path, "wb").write(out.encode("utf-8", "surrogateescape"))
    print("OK: linha do CHIP atualizada em", path, "(backup:", path + ".bak_chip) e criado", os.path.join(d, "font_chip.h"))

if __name__ == "__main__":
    main()
