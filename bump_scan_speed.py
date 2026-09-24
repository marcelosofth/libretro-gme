#!/usr/bin/env python3
"""bump_scan_speed.py - dobra (ou multiplica por um fator escolhido) a velocidade
do avanco rapido (R) e do voltar acelerado (L), ajustando a constante SCAN_MULT
em src/player.c (gerada pelo apply_scan.py).

Uso (na raiz do repo):
    python3 bump_scan_speed.py            # dobra (x2) o valor atual
    python3 bump_scan_speed.py --factor 3 # multiplica por 3 o valor atual
    python3 bump_scan_speed.py --set 8    # define o valor absoluto 8
Opcional:
    python3 bump_scan_speed.py --root /caminho/do/repo

Nao altera nada se a ancora nao for encontrada.
"""
import os
import re
import sys

ROOT = "."
if "--root" in sys.argv:
    ROOT = sys.argv[sys.argv.index("--root") + 1]

FACTOR = 2
SET_VAL = None
if "--factor" in sys.argv:
    FACTOR = int(sys.argv[sys.argv.index("--factor") + 1])
if "--set" in sys.argv:
    SET_VAL = int(sys.argv[sys.argv.index("--set") + 1])

P_C = os.path.join(ROOT, "src", "player.c")


def read(path):
    with open(path, "rb") as f:
        raw = f.read().decode("utf-8")
    crlf = "\r\n" in raw
    return raw.replace("\r\n", "\n"), crlf


def write(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def fail(msg):
    print("ERRO: " + msg)
    print("Nenhum arquivo foi alterado.")
    sys.exit(1)


pc, pc_crlf = read(P_C)

pattern = r"(#define\s+SCAN_MULT\s+)(\d+)(\s*/\*[^\n]*\*/)?"
matches = list(re.finditer(pattern, pc))
if len(matches) != 1:
    fail("definicao de SCAN_MULT encontrada %d vez(es), esperado 1" % len(matches))

m = matches[0]
old_val = int(m.group(2))
new_val = SET_VAL if SET_VAL is not None else old_val * FACTOR

if new_val == old_val:
    fail("novo valor (%d) igual ao atual, nada para mudar" % new_val)

pc = pc[:m.start(2)] + str(new_val) + pc[m.end(2):]

write(P_C, pc, pc_crlf)
print("OK: SCAN_MULT alterado de %d para %d em src/player.c" % (old_val, new_val))
print("Agora compile de novo: make platform=win -j$(nproc) ... (mesmo comando de sempre)")
