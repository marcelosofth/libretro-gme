#!/usr/bin/env python3
"""apply_dpad_repeat.py - dentro do navegador de zip, segurar CIMA/BAIXO
agora repete o movimento (igual segurar uma tecla em qualquer menu),
em vez de só mover um item por toque.

Uso (na raiz do repo):  python3 apply_dpad_repeat.py
Opcional:               python3 apply_dpad_repeat.py --root /caminho/do/repo

Nao altera nenhum arquivo se qualquer ancora nao for encontrada.
"""
import os
import re
import sys

ROOT = "."
if "--root" in sys.argv:
    ROOT = sys.argv[sys.argv.index("--root") + 1]

def read(rel):
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8", newline="") as f:
        return f.read()

def write(rel, content):
    with open(os.path.join(ROOT, rel), "w", encoding="utf-8", newline="") as f:
        f.write(content)

def sub_once(text, pattern, repl, label):
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        print(f"ERRO: ancora '{label}' encontrada {len(matches)} vez(es), esperado 1")
        sys.exit(1)
    return text[:matches[0].start()] + repl(matches[0]) + text[matches[0].end():]

lc = read("src/libretro.c")

if "down_hold_frames" in lc:
    print("Ja aplicado (down_hold_frames ja existe em libretro.c). Nada a fazer.")
    sys.exit(0)

# 1) contadores de hold para UP/DOWN, junto dos contadores do L/R
OLD_COUNTERS = '''#define SCAN_HOLD_FRAMES 18
static int l_hold_frames = 0;
static int r_hold_frames = 0;'''

NEW_COUNTERS = '''#define SCAN_HOLD_FRAMES 18
static int l_hold_frames = 0;
static int r_hold_frames = 0;

/* repeticao ao segurar CIMA/BAIXO dentro do navegador de zip */
#define BROWSER_REPEAT_DELAY 20   /* frames antes de comecar a repetir (~0,33s a 60fps) */
#define BROWSER_REPEAT_RATE   6   /* frames entre repeticoes depois disso (~0,1s) */
static int down_hold_frames = 0;
static int up_hold_frames   = 0;'''

lc = sub_once(
    lc,
    re.escape(OLD_COUNTERS),
    lambda m: NEW_COUNTERS,
    "contadores de hold do L/R (topo de retro_run)",
)

# 2) logica de UP/DOWN dentro do navegador: edge + hold-repeat
OLD_UPDOWN = '''      if(input & (1<<RETRO_DEVICE_ID_JOYPAD_DOWN))
      {
         browser_cursor++;
         if(browser_cursor >= browser_count_ui)
            browser_cursor = 0;
      }
      if(input & (1<<RETRO_DEVICE_ID_JOYPAD_UP))
      {
         browser_cursor--;
         if(browser_cursor < 0)
            browser_cursor = browser_count_ui - 1;
      }'''

NEW_UPDOWN = '''      {
         int move_down = 0, move_up = 0;

         if(input & (1<<RETRO_DEVICE_ID_JOYPAD_DOWN))
         {
            move_down = 1;
            down_hold_frames = 0;
         }
         else if(realinput & (1<<RETRO_DEVICE_ID_JOYPAD_DOWN))
         {
            down_hold_frames++;
            if(down_hold_frames >= BROWSER_REPEAT_DELAY &&
               (down_hold_frames - BROWSER_REPEAT_DELAY) % BROWSER_REPEAT_RATE == 0)
               move_down = 1;
         }
         else
            down_hold_frames = 0;

         if(input & (1<<RETRO_DEVICE_ID_JOYPAD_UP))
         {
            move_up = 1;
            up_hold_frames = 0;
         }
         else if(realinput & (1<<RETRO_DEVICE_ID_JOYPAD_UP))
         {
            up_hold_frames++;
            if(up_hold_frames >= BROWSER_REPEAT_DELAY &&
               (up_hold_frames - BROWSER_REPEAT_DELAY) % BROWSER_REPEAT_RATE == 0)
               move_up = 1;
         }
         else
            up_hold_frames = 0;

         if(move_down)
         {
            browser_cursor++;
            if(browser_cursor >= browser_count_ui)
               browser_cursor = 0;
         }
         if(move_up)
         {
            browser_cursor--;
            if(browser_cursor < 0)
               browser_cursor = browser_count_ui - 1;
         }
      }'''

lc = sub_once(
    lc,
    re.escape(OLD_UPDOWN),
    lambda m: NEW_UPDOWN,
    "bloco UP/DOWN do navegador (em retro_run)",
)

# 3) zera os contadores de hold sempre que o navegador fecha ou abre,
#    para nao herdar um "hold" que comecou antes de abrir/fechar
lc = sub_once(
    lc,
    re.escape('''      if(!browser_open_state)
      {
         int n = browser_open();
         if(n > 0)
         {
            browser_open_state = 1;
            browser_cursor     = browser_last_cursor();
            browser_count_ui   = n;
         }
      }
      else
      {
         browser_close();
         browser_open_state = 0;
      }'''),
    lambda m: '''      if(!browser_open_state)
      {
         int n = browser_open();
         if(n > 0)
         {
            browser_open_state = 1;
            browser_cursor     = browser_last_cursor();
            browser_count_ui   = n;
            down_hold_frames   = 0;
            up_hold_frames     = 0;
         }
      }
      else
      {
         browser_close();
         browser_open_state = 0;
         down_hold_frames   = 0;
         up_hold_frames     = 0;
      }''',
    "abre/fecha navegador com SELECT (para zerar hold de UP/DOWN)",
)

write("src/libretro.c", lc)
print("OK: src/libretro.c atualizado.")
print("Agora compile: make platform=win -j$(nproc) ... (mesmo comando de sempre)")
