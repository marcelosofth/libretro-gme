#!/usr/bin/env python3
"""apply_volume_l2_r2.py - controle de volume do proprio core no L2/R2.

  L2 = abaixa o volume     R2 = aumenta o volume
  (segurando, repete sozinho; passo de 10%, faixa 0% a 200%, padrao 100%)

- Vale em qualquer tela (player, navegador de zip e creditos); L2/R2 nao
  fecham a janela de creditos.
- So o audio enviado ao RetroArch e' escalado (com limite anti-estouro);
  espectro, onda e LED continuam mostrando o sinal original.
- Ao mudar, aparece um aviso "VOL 100%" com barra no centro da tela por ~1,5 s.

Uso (na raiz do repo):  python3 apply_volume_l2_r2.py
Opcional:               python3 apply_volume_l2_r2.py --root /caminho/do/repo
                        python3 apply_volume_l2_r2.py --file src/libretro.c

Procura o libretro.c automaticamente (fora de deps/), faz backup em
libretro.c.bak_volume e so grava se TODAS as ancoras forem encontradas.
Pode rodar de novo: se ja estiver aplicado, avisa e nao altera nada.
Funciona com ou sem o apply_credits_pause.py aplicado antes.
"""
import os
import sys
import shutil

ROOT = "."
if "--root" in sys.argv:
    ROOT = sys.argv[sys.argv.index("--root") + 1]

TARGET = None
if "--file" in sys.argv:
    TARGET = sys.argv[sys.argv.index("--file") + 1]


def find_libretro_c():
    candidates = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ("deps", ".git", "node_modules", "obj", "build")]
        if "libretro.c" in files:
            candidates.append(os.path.join(base, "libretro.c"))
    candidates.sort(key=lambda p: (0 if os.sep + "src" + os.sep in p else 1, len(p)))
    return candidates[0] if candidates else None


path = TARGET or find_libretro_c()
if not path or not os.path.isfile(path):
    print("ERRO: libretro.c nao encontrado. Use --file caminho/do/libretro.c")
    sys.exit(1)

with open(path, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
    src = f.read()

EOL = "\r\n" if "\r\n" in src else "\n"


def nl(text):
    return text.replace("\n", EOL)


if "volume_pct" in src:
    print("Ja aplicado (volume_pct ja existe em %s). Nada a fazer." % path)
    sys.exit(0)

# ---------------------------------------------------------------------------
# Bloco novo 1: estado + funcoes (entra logo antes do retro_run)
# ---------------------------------------------------------------------------
BLOCK_FUNCS = r'''
/* ---- volume do core (L2 abaixa, R2 aumenta) ----
 * Escala so o audio enviado ao RetroArch; espectro/onda/LED usam o sinal original. */
#define VOL_MAX           200   /* % (100 = volume original; acima disso amplifica com limite) */
#define VOL_STEP           10   /* % por toque */
#define VOL_REPEAT_DELAY   20   /* frames segurando antes de repetir (~0,33 s a 60 fps) */
#define VOL_REPEAT_RATE    4    /* frames entre repeticoes */
#define VOL_OSD_FRAMES     90   /* tempo do aviso na tela (~1,5 s a 60 fps) */
static int volume_pct      = 100;
static int vol_osd_frames  = 0;
static int vol_up_hold     = 0;
static int vol_down_hold   = 0;

static void volume_update(uint16_t pressed, uint16_t held)
{
   int up = 0, down = 0;

   if(pressed & (1<<RETRO_DEVICE_ID_JOYPAD_L2))
   {
      down = 1;
      vol_down_hold = 0;
   }
   else if(held & (1<<RETRO_DEVICE_ID_JOYPAD_L2))
   {
      vol_down_hold++;
      if(vol_down_hold >= VOL_REPEAT_DELAY &&
         (vol_down_hold - VOL_REPEAT_DELAY) % VOL_REPEAT_RATE == 0)
         down = 1;
   }
   else
      vol_down_hold = 0;

   if(pressed & (1<<RETRO_DEVICE_ID_JOYPAD_R2))
   {
      up = 1;
      vol_up_hold = 0;
   }
   else if(held & (1<<RETRO_DEVICE_ID_JOYPAD_R2))
   {
      vol_up_hold++;
      if(vol_up_hold >= VOL_REPEAT_DELAY &&
         (vol_up_hold - VOL_REPEAT_DELAY) % VOL_REPEAT_RATE == 0)
         up = 1;
   }
   else
      vol_up_hold = 0;

   if(up && !down)
      volume_pct += VOL_STEP;
   else if(down && !up)
      volume_pct -= VOL_STEP;
   else
      return;

   if(volume_pct > VOL_MAX) volume_pct = VOL_MAX;
   if(volume_pct < 0)       volume_pct = 0;
   vol_osd_frames = VOL_OSD_FRAMES;
}

/* devolve o buffer a enviar ao frontend (o original se o volume for 100%) */
static short *volume_apply(short *audio, int frames)
{
   static short vol_buf[2048 * 2];
   int i, n = frames * 2;

   if(volume_pct == 100 || n > (int)(sizeof(vol_buf) / sizeof(vol_buf[0])))
      return audio;

   for(i = 0; i < n; i++)
   {
      int v = ((int)audio[i] * volume_pct) / 100;
      if(v >  32767) v =  32767;
      if(v < -32768) v = -32768;
      vol_buf[i] = (short)v;
   }
   return vol_buf;
}

/* aviso "VOL xxx%" com barra, no centro da tela, por alguns instantes */
static void volume_osd_draw(void)
{
   char txt[24];
   int bw = 208, bh = 48;
   int bx = (640 - bw) / 2, by = (480 - bh) / 2;
   int tw, fill, tick;

   if(vol_osd_frames <= 0)
      return;
   vol_osd_frames--;

   snprintf(txt, sizeof(txt), "VOL %d%%", volume_pct);
   tw = text_width_prop(txt);

   draw_shape_alpha(framebuffer, get_color(2, 4, 5),   215, bx,     by,     bw,     bh);
   draw_shape_alpha(framebuffer, get_color(6, 12, 14), 215, bx + 2, by + 2, bw - 4, bh - 4);
   draw_text_prop(txt, bx + (bw - tw) / 2, by + 7, get_color(30, 58, 25));

   /* barra: cheia = VOL_MAX; marca branca = 100% (volume original) */
   draw_shape(framebuffer, get_color(4, 8, 9), bx + 12, by + bh - 16, bw - 24, 8);
   fill = ((bw - 24) * volume_pct) / VOL_MAX;
   if(fill > 0)
      draw_shape(framebuffer, get_color(8, 56, 17), bx + 12, by + bh - 16, fill, 8);
   tick = ((bw - 24) * 100) / VOL_MAX;
   draw_shape(framebuffer, get_color(31, 63, 31), bx + 12 + tick, by + bh - 18, 2, 12);
}
'''

# Bloco novo 2: leitura dos botoes (entra antes da janela de creditos)
BLOCK_INPUT = '''   /* L2/R2 = volume (vale em qualquer tela); depois some do "input" para nao
      fechar a janela de creditos nem disparar outras acoes */
   volume_update(input, realinput);
   input &= ~((1<<RETRO_DEVICE_ID_JOYPAD_L2) | (1<<RETRO_DEVICE_ID_JOYPAD_R2));

'''

EDITS = [
    # (ancora, novo_texto, onde)   onde: "after" = depois da ancora, "before" = antes,
    #                              "replace" = troca a ancora
    ("static int up_hold_frames   = 0;\n", BLOCK_FUNCS, "after"),
    ("   /* janela de creditos (B, fora do navegador): enquanto aberta,", BLOCK_INPUT, "before"),
    ("   audio_batch_cb(audio,735);",
     "   audio_batch_cb(volume_apply(audio, 735), 735);", "replace"),
    ("   video_cb(framebuffer->pixel_data",
     "   volume_osd_draw();\n", "before"),
]

new_src = src
for i, (anchor, text, where) in enumerate(EDITS, 1):
    a = nl(anchor)
    t = nl(text)
    n = new_src.count(a)
    if n != 1:
        print("ERRO: ancora %d encontrada %d vez(es) (esperado 1). Nada foi alterado." % (i, n))
        print("O libretro.c pode ser diferente da versao esperada; mande o arquivo atual.")
        sys.exit(1)
    if where == "after":
        new_src = new_src.replace(a, a + t)
    elif where == "before":
        new_src = new_src.replace(a, t + a)
    else:
        new_src = new_src.replace(a, t)

bak = path + ".bak_volume"
if not os.path.exists(bak):
    shutil.copy2(path, bak)

with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
    f.write(new_src)

print("OK: volume L2/R2 aplicado em %s" % path)
print("Backup: %s" % bak)
