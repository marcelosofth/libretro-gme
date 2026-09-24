#!/usr/bin/env python3
"""apply_credits_pause.py - na tela de creditos (aberta com B), apertar B
de novo pausa o texto que sobe; apertar B outra vez continua de onde parou.
Qualquer outro botao continua fechando a janela.

Uso (na raiz do repo):  python3 apply_credits_pause.py
Opcional:               python3 apply_credits_pause.py --root /caminho/do/repo
                        python3 apply_credits_pause.py --file src/libretro.c

Procura o libretro.c automaticamente (fora de deps/), faz backup em
libretro.c.bak_credits_pause e so grava se TODAS as ancoras forem
encontradas. Pode rodar de novo sem problema: se ja estiver aplicado, avisa
e nao altera nada.
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
    # prefere src/libretro.c
    candidates.sort(key=lambda p: (0 if os.sep + "src" + os.sep in p else 1, len(p)))
    return candidates[0] if candidates else None


path = TARGET or find_libretro_c()
if not path or not os.path.isfile(path):
    print("ERRO: libretro.c nao encontrado. Use --file caminho/do/libretro.c")
    sys.exit(1)

# le sem converter quebras de linha (preserva CRLF se o arquivo usar)
with open(path, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
    src = f.read()

EOL = "\r\n" if "\r\n" in src else "\n"


def nl(text):
    """Converte o texto das ancoras para o tipo de quebra de linha do arquivo."""
    return text.replace("\n", EOL)


if "credits_paused" in src:
    print("Ja aplicado (credits_paused ja existe em %s). Nada a fazer." % path)
    sys.exit(0)

EDITS = [
    # 1) variavel de estado
    (
        "static int credits_frame      = 0;\n",
        "static int credits_frame      = 0;\n"
        "static int credits_paused     = 0;   /* 1 = texto dos creditos parado (B pausa/continua) */\n",
    ),
    # 2) entrada: B pausa/continua, outros botoes fecham
    (
        "   /* janela de creditos (B, fora do navegador): enquanto aberta, qualquer\n"
        "      botao fecha; nenhum outro controle (transporte, navegador) reage */\n"
        "   if(credits_open_state)\n"
        "   {\n"
        "      if(input)\n"
        "         credits_open_state = 0;\n"
        "   }",
        "   /* janela de creditos (B, fora do navegador): enquanto aberta, B pausa/continua\n"
        "      o texto subindo; qualquer outro botao fecha; nenhum outro controle\n"
        "      (transporte, navegador) reage */\n"
        "   if(credits_open_state)\n"
        "   {\n"
        "      if(input & (1<<RETRO_DEVICE_ID_JOYPAD_B))\n"
        "         credits_paused = !credits_paused;\n"
        "      if(input & ~(1<<RETRO_DEVICE_ID_JOYPAD_B))\n"
        "         credits_open_state = 0;\n"
        "   }",
    ),
    # 3) ao abrir, comeca rodando
    (
        "         credits_open_state = 1;\n"
        "         credits_frame      = 0;\n"
        "      }",
        "         credits_open_state = 1;\n"
        "         credits_frame      = 0;\n"
        "         credits_paused     = 0;\n"
        "      }",
    ),
    # 4) so avanca o frame dos creditos quando nao esta pausado
    (
        "      draw_credits();\n"
        "      credits_frame++;",
        "      draw_credits();\n"
        "      if(!credits_paused)\n"
        "         credits_frame++;",
    ),
]

new_src = src
for i, (old, new) in enumerate(EDITS, 1):
    old, new = nl(old), nl(new)
    n = new_src.count(old)
    if n != 1:
        print("ERRO: ancora %d encontrada %d vez(es) (esperado 1). Nada foi alterado." % (i, n))
        print("O libretro.c pode ser diferente da versao esperada; mande o arquivo atual.")
        sys.exit(1)
    new_src = new_src.replace(old, new)

bak = path + ".bak_credits_pause"
if not os.path.exists(bak):
    shutil.copy2(path, bak)

with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
    f.write(new_src)

print("OK: pausa dos creditos aplicada em %s" % path)
print("Backup: %s" % bak)
