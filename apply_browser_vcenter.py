#!/usr/bin/env python3
"""apply_browser_vcenter.py - centraliza verticalmente o texto de cada
linha da janela do navegador dentro da sua celula (BROWSER_ROW_H).

Antes, o texto era desenhado a partir do topo da celula: como o glifo da
fonte (16px) e menor que a altura da celula (26px), sobravam 10px por
linha que ficavam todos embaixo da ultima linha (margem de baixo maior
que a de cima). Agora o texto fica centralizado (5px de folga em cima e
embaixo de cada linha), o que tambem iguala a margem superior e inferior
da janela inteira.

Uso (na raiz do repo):  python3 apply_browser_vcenter.py
Opcional:               python3 apply_browser_vcenter.py --root /caminho/do/repo

Nao altera nenhum arquivo se a ancora nao for encontrada.
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

if "BROWSER_GLYPH_H" in lc:
    print("Ja aplicado (BROWSER_GLYPH_H ja existe em libretro.c). Nada a fazer.")
    sys.exit(0)

# 1) define a altura real do glifo (fonte 8x8 desenhada em escala 2x = 16px)
lc = sub_once(
    lc,
    re.escape('#define BROWSER_BG_ALPHA  190  /* 0 = totalmente transparente, 255 = totalmente solido */'),
    lambda m: (
        '#define BROWSER_BG_ALPHA  190  /* 0 = totalmente transparente, 255 = totalmente solido */\n'
        '#define BROWSER_GLYPH_H   16   /* altura do glifo desenhado (fonte 8x8 em escala 2x) */'
    ),
    "define de BROWSER_BG_ALPHA (para inserir BROWSER_GLYPH_H)",
)

# 2) desloca o texto para o centro vertical de cada celula
lc = sub_once(
    lc,
    re.escape('   y = box_y0 + 20;'),
    lambda m: '   y = box_y0 + 20 + (BROWSER_ROW_H - BROWSER_GLYPH_H) / 2;',
    "posicao vertical inicial do texto do navegador",
)

write("src/libretro.c", lc)
print("OK: src/libretro.c atualizado.")
print("Agora compile: make platform=win -j$(nproc) ... (mesmo comando de sempre)")
