#!/usr/bin/env python3
"""
apply_res_640x480.py

Escala o core de 320x240 para 640x480, com texto/UI em 2x (fonte bitmap
8x8 desenhada como blocos 2x2, todas as posicoes/larguras dobradas).

O que este script NAO faz: trocar src/background.h pelo fundo de
640x480. Isso e so copiar o arquivo por cima -- veja o passo manual
abaixo.

Usa substituicao por REGIAO DE FUNCAO (regex, do inicio de uma funcao ate
o comeco da proxima), em vez de casar o texto exato caractere-a-caractere.
Isso evita quebrar por causa de espacamento/indentacao, mas presume que a
ASSINATURA de cada funcao abaixo ainda esta identica a atual -- se algo
mudou muito nesse meio tempo, o assert vai avisar em vez de aplicar
errado.
"""
import re
import sys

def replace_region(content, start_pat, end_pat, new_text, label):
    pat = re.compile(re.escape(start_pat) + r'.*?(?=' + re.escape(end_pat) + r')',
                      re.DOTALL)
    new_content, n = pat.subn(new_text.rstrip('\n') + '\n\n', content, count=1)
    if n != 1:
        print(f"AVISO: regiao nao encontrada: {label}")
        sys.exit(1)
    return new_content

def literal(content, old, new, label):
    if content.count(old) != 1:
        print(f"AVISO: ancora '{label}' nao encontrada (ou nao e unica): {old!r}")
        sys.exit(1)
    return content.replace(old, new, 1)


with open('src/libretro.c', 'r') as f:
    lr = f.read()

# ---- put_glyph: fonte 8x8 desenhada como blocos 2x2 (texto 2x) ----
lr = replace_region(lr,
    'static void put_glyph(unsigned char ch, int px, int py, unsigned short color, int cx0, int cx1)',
    '/* colunas realmente usadas pelo glifo',
'''static void put_glyph(unsigned char ch, int px, int py, unsigned short color, int cx0, int cx1)
{
   int x, y, sx, sy;
   int charx = (ch % 16) * 8;
   int chary = (ch >> 4) * 8;
   for (y = 0; y < 8; y++)
   {
      for (x = 0; x < 8; x++)
      {
         if (!is_font_pixel(charx + x, chary + y))
            continue;
         for (sy = 0; sy < 2; sy++)
         {
            int yy = py + y * 2 + sy;
            if (yy < 0 || yy >= 480)
               continue;
            for (sx = 0; sx < 2; sx++)
            {
               int xx = px + x * 2 + sx;
               if (xx < cx0 || xx >= cx1 || xx < 0 || xx >= 640)
                  continue;
               set_pixel(framebuffer, xx, yy, color);
            }
         }
      }
   }
}
''', 'put_glyph')

# ---- text_width_prop: retorna largura ja em espaco de tela (x2) ----
lr = replace_region(lr,
    'static int text_width_prop(const char *text)',
    'static void draw_text_prop(const char *text, int x, int y, unsigned short color)',
'''static int text_width_prop(const char *text)
{
   int w = 0, x0, x1;
   for (; *text; text++)
   {
      glyph_extent((unsigned char)*text, &x0, &x1);
      w += (x1 < 0) ? 4 : (x1 - x0 + 2);
   }
   w = w > 0 ? w - 1 : 0;
   return w * 2;
}
''', 'text_width_prop')

# ---- draw_text_prop: avanco e offset de glifo em espaco de tela (x2) ----
lr = replace_region(lr,
    'static void draw_text_prop(const char *text, int x, int y, unsigned short color)',
    '/* texto monoespacado',
'''static void draw_text_prop(const char *text, int x, int y, unsigned short color)
{
   int x0, x1;
   for (; *text; text++)
   {
      unsigned char ch = (unsigned char)*text;
      glyph_extent(ch, &x0, &x1);
      if (x1 < 0)
      {
         x += 4 * 2;
         continue;
      }
      put_glyph(ch, x - x0 * 2, y, color, 0, 640);
      x += (x1 - x0 + 2) * 2;
   }
}
''', 'draw_text_prop')

# ---- draw_text_scroll: passo de 8px do glifo monoespacado vira 16px ----
lr = replace_region(lr,
    'static void draw_text_scroll(const char *text, int x, int y, int maxw, unsigned short color)',
    '/* texto proporcional cortado em maxx */',
'''static void draw_text_scroll(const char *text, int x, int y, int maxw, unsigned short color)
{
   int len   = (int)strlen(text);
   int textw = len * 8 * 2;
   int off   = 0, i;

   if (textw > maxw)
   {
      int delta  = textw - maxw;
      int delay  = 30;
      int modulo = delta + delay * 2;
      int frames = get_track_elapsed_frames();
      off = (modulo - abs((frames / 2) % (2 * modulo) - modulo)) - delay;
      if (off < 0)     off = 0;
      if (off > delta) off = delta;
   }

   for (i = 0; i < len; i++)
   {
      int gx = x - off + i * 8 * 2;
      if (gx + 8 * 2 <= x || gx >= x + maxw)
         continue;
      put_glyph((unsigned char)text[i], gx, y, color, x, x + maxw);
   }
}
''', 'draw_text_scroll')

# ---- draw_text_prop_clip: mesmo tratamento de draw_text_prop ----
lr = replace_region(lr,
    'static void draw_text_prop_clip(const char *text, int x, int y, unsigned short color, int maxx)',
    '/* LED de atividade',
'''static void draw_text_prop_clip(const char *text, int x, int y, unsigned short color, int maxx)
{
   int x0, x1;
   for (; *text && x < maxx; text++)
   {
      unsigned char ch = (unsigned char)*text;
      glyph_extent(ch, &x0, &x1);
      if (x1 < 0)
      {
         x += 4 * 2;
         continue;
      }
      put_glyph(ch, x - x0 * 2, y, color, 0, maxx);
      x += (x1 - x0 + 2) * 2;
   }
}
''', 'draw_text_prop_clip')

# ---- draw_led: raio e limiar dobrados (area escala ao quadrado) ----
lr = replace_region(lr,
    'static void draw_led(int cx, int cy)',
    '/* ---- layout: cabecalho',
'''static void draw_led(int cx, int cy)
{
   int dx, dy;
   int t = led_level;
   int r = 8 + (23 * t) / 255, g = 3 + (9 * t) / 255, b = 2 + (5 * t) / 255;
   unsigned short col;
   if (t < 48) /* em repouso/fraco: escurece; acima disso fica igual */
   {
      r = 3 + ((r - 3) * t) / 48;
      g = 1 + ((g - 1) * t) / 48;
      b = 1 + ((b - 1) * t) / 48;
   }
   col = get_color(r, g, b);
   for (dy = -6; dy <= 6; dy++)
      for (dx = -6; dx <= 6; dx++)
         if (dx * dx + dy * dy <= 40)
            set_pixel(framebuffer, cx + dx, cy + dy, col);
   if (t > 200)
      set_pixel(framebuffer, cx - 2, cy - 2, get_color(31, 40, 30));
}
''', 'draw_led')

# ---- UI_LEFT/UI_RIGHT dobrados ----
lr = replace_region(lr,
    '#define UI_LEFT   16',
    'static void draw_ui(void)',
'''#define UI_LEFT   32
#define UI_RIGHT  608
#define UI_W      (UI_RIGHT - UI_LEFT)

''', 'UI_LEFT/UI_RIGHT')

# ---- draw_ui: todas as posicoes/larguras dobradas ----
lr = replace_region(lr,
    'static void draw_ui(void)',
    'void retro_get_system_info(struct retro_system_info *info)',
'''static void draw_ui(void)
{
   char message[512];
   int w, prog;

   /* cabecalho */
   draw_text_scroll(get_song_name(message), UI_LEFT, 24, 416, get_color(30, 58, 25));

   get_track_label(message);
   w = text_width_prop(message);
   draw_text_prop(message, UI_RIGHT - w, 24, get_color(28, 56, 28));

   draw_text_scroll(get_game_name(message), UI_LEFT, 60, 384, get_color(19, 36, 27));

   get_system_line(message);
   draw_text_prop_clip(message, UI_LEFT, 96, get_color(15, 33, 21), 416);

   /* SYSTEM: (led) chip de audio */
   {
      int lx = UI_LEFT + text_width_prop("CHIP:") + 16;
      draw_text_prop("CHIP:", UI_LEFT, 132, get_color(15, 33, 21));
      draw_led(lx + 6, 138);
      draw_text_prop_clip(get_chip_text(message), lx + 24, 132, get_color(27, 54, 29), 416);
   }

   /* barra de progresso */
   draw_shape(framebuffer, get_color(4, 8, 9), UI_LEFT, 418, UI_W, 12);
   prog = get_track_progress_permille();
   if (prog > 0)
      draw_shape(framebuffer, get_color(12, 25, 28), UI_LEFT, 418, (UI_W * prog) / 1000, 12);

   /* tempo (esquerda) e taxa de amostragem (direita) */
   draw_text_prop(get_time_text(message), UI_LEFT, 442, get_color(27, 54, 29));

   get_rate_text(message);
   w = text_width_prop(message);
   draw_text_prop(message, UI_RIGHT - w, 442, get_color(15, 33, 21));
}
''', 'draw_ui')

# ---- av_info e create_surface: 640x480 ----
lr = literal(lr,
    'info->geometry.base_width   = 320;\n   info->geometry.base_height  = 240;\n   info->geometry.max_width    = 320;\n   info->geometry.max_height   = 240;\n   info->geometry.aspect_ratio = 320.0f / 240.0f;',
    'info->geometry.base_width   = 640;\n   info->geometry.base_height  = 480;\n   info->geometry.max_width    = 640;\n   info->geometry.max_height   = 480;\n   info->geometry.aspect_ratio = 640.0f / 480.0f;',
    'av_info dimensoes')

lr = literal(lr,
    'framebuffer = create_surface(320,240,2);',
    'framebuffer = create_surface(640,480,2);',
    'create_surface')

with open('src/libretro.c', 'w') as f:
    f.write(lr)
print("OK: src/libretro.c patchado (UI em 2x, resolucao 640x480).")


with open('src/spectrum.c', 'r') as f:
    sp = f.read()

for name, old_val, new_val in (
    ('BAR_W',     6,   12),
    ('BAR_PITCH', 8,   16),
    ('BAR_X0',    16,  32),
    ('BAR_BASE',  204, 408),
    ('SEG_H',     3,   6),
    ('SEG_PITCH', 4,   8),
):
    pat = re.compile(r'(#define\s+%s\s+)%d\b' % (name, old_val))
    sp, n = pat.subn(r'\g<1>%d' % new_val, sp, count=1)
    if n != 1:
        print(f"AVISO: #define {name} {old_val} nao encontrado")
        sys.exit(1)

with open('src/spectrum.c', 'w') as f:
    f.write(sp)
print("OK: src/spectrum.c patchado (geometria do espectro em 2x).")

print("\nFalta so um passo manual: sobrescreva src/background.h com o")
print("background.h de 640x480 (o mesmo que voce ja tem, gerado do fundo.png).")
