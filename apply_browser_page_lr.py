#!/usr/bin/env python3
"""apply_browser_page_lr.py - no navegador do .zip (aberto com SELECT):

  R = desce 5 linhas       L = sobe 5 linhas
  Segurando, repete rapido (mesma cadencia do CIMA/BAIXO segurado).

Ao passar do fim da lista, o cursor da a volta e reaparece no inicio (e vice-versa),
como o CIMA/BAIXO. A e B continuam como antes. Dentro do navegador, L/R nao
trocam de faixa.

Uso (na raiz do repo):  python3 apply_browser_page_lr.py
Opcional:               python3 apply_browser_page_lr.py --root /caminho/do/repo
                        python3 apply_browser_page_lr.py --file src/libretro.c
                        python3 apply_browser_page_lr.py --step 10   (linhas por pulo)

Procura o libretro.c automaticamente (fora de deps/), faz backup em
libretro.c.bak_page_lr e so grava se a ancora for encontrada. Pode rodar de
novo: se ja estiver aplicado, avisa e nao altera nada. Se a versao antiga
(que parava no fim da lista) ja estiver aplicada, ele ATUALIZA para a que da a volta. Funciona com ou sem os
outros apply_*.py (pausa dos creditos, volume L2/R2) aplicados antes.
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

STEP = 5
if "--step" in sys.argv:
    STEP = int(sys.argv[sys.argv.index("--step") + 1])


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


OLD_TAIL = """         if(browser_count_ui <= 0)
            ;   /* lista vazia: nada a mover */
         else if(page_r && !page_l)
         {
            browser_cursor += BROWSER_PAGE_STEP;
            if(browser_cursor > browser_count_ui - 1)
               browser_cursor = browser_count_ui - 1;
         }
         else if(page_l && !page_r)
         {
            browser_cursor -= BROWSER_PAGE_STEP;
            if(browser_cursor < 0)
               browser_cursor = 0;
         }
"""
OLD_COMMENT = "segurando, repete rapido. Para no inicio/fim da lista (nao da a volta). */"
NEW_COMMENT = "segurando, repete rapido. Passando do fim/inicio da lista, da a volta. */"
NEW_TAIL = """         if(browser_count_ui <= 0)
            ;   /* lista vazia: nada a mover */
         else if(page_r && !page_l)
            browser_cursor = (browser_cursor + BROWSER_PAGE_STEP) % browser_count_ui;
         else if(page_l && !page_r)
         {
            browser_cursor = (browser_cursor - BROWSER_PAGE_STEP) % browser_count_ui;
            if(browser_cursor < 0)
               browser_cursor += browser_count_ui;
         }
"""

if "BROWSER_PAGE_STEP" in src:
    if nl(OLD_TAIL) in src:
        # versao antiga (parava no fim da lista) -> atualiza para a que da a volta
        up = src.replace(nl(OLD_TAIL), nl(NEW_TAIL)).replace(OLD_COMMENT, NEW_COMMENT)
        bak = path + ".bak_page_lr"
        if not os.path.exists(bak):
            shutil.copy2(path, bak)
        with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(up)
        print("OK: versao antiga atualizada - agora L/R dao a volta na lista (%s)" % path)
        print("Backup: %s" % bak)
    else:
        print("Ja aplicado (BROWSER_PAGE_STEP ja existe em %s). Nada a fazer." % path)
    sys.exit(0)

BLOCK = '''      /* L/R no navegador: pula BROWSER_PAGE_STEP linhas (R desce, L sobe);
         segurando, repete rapido. Passando do fim/inicio da lista, da a volta. */
      {
#define BROWSER_PAGE_STEP __STEP__
         static int page_r_hold = 0, page_l_hold = 0;
         int page_r = 0, page_l = 0;

         if(input & (1<<RETRO_DEVICE_ID_JOYPAD_R))
         {
            page_r = 1;
            page_r_hold = 0;
         }
         else if(realinput & (1<<RETRO_DEVICE_ID_JOYPAD_R))
         {
            page_r_hold++;
            if(page_r_hold >= BROWSER_REPEAT_DELAY &&
               (page_r_hold - BROWSER_REPEAT_DELAY) % BROWSER_REPEAT_RATE == 0)
               page_r = 1;
         }
         else
            page_r_hold = 0;

         if(input & (1<<RETRO_DEVICE_ID_JOYPAD_L))
         {
            page_l = 1;
            page_l_hold = 0;
         }
         else if(realinput & (1<<RETRO_DEVICE_ID_JOYPAD_L))
         {
            page_l_hold++;
            if(page_l_hold >= BROWSER_REPEAT_DELAY &&
               (page_l_hold - BROWSER_REPEAT_DELAY) % BROWSER_REPEAT_RATE == 0)
               page_l = 1;
         }
         else
            page_l_hold = 0;

         if(browser_count_ui <= 0)
            ;   /* lista vazia: nada a mover */
         else if(page_r && !page_l)
            browser_cursor = (browser_cursor + BROWSER_PAGE_STEP) % browser_count_ui;
         else if(page_l && !page_r)
         {
            browser_cursor = (browser_cursor - BROWSER_PAGE_STEP) % browser_count_ui;
            if(browser_cursor < 0)
               browser_cursor += browser_count_ui;
         }
      }
'''.replace("__STEP__", str(STEP))

ANCHOR = '''      if(input & (1<<RETRO_DEVICE_ID_JOYPAD_B))
      {
         /* dentro de uma pasta: B sobe um nivel. na raiz: B fecha o navegador */
'''

a = nl(ANCHOR)
n = src.count(a)
if n != 1:
    print("ERRO: ancora encontrada %d vez(es) (esperado 1). Nada foi alterado." % n)
    print("O libretro.c pode ser diferente da versao esperada; mande o arquivo atual.")
    sys.exit(1)

new_src = src.replace(a, nl(BLOCK) + a)

bak = path + ".bak_page_lr"
if not os.path.exists(bak):
    shutil.copy2(path, bak)

with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
    f.write(new_src)

print("OK: L/R pulam %d linhas no navegador, dando a volta na lista (aplicado em %s)" % (STEP, path))
print("Backup: %s" % bak)
