#!/usr/bin/env python3
"""
apply_paula_label.py

Troca o texto exibido na tela para .mod com Mix. Paula ativo:
de "PAULA" para "AMIGA: MIX. PAULA".

Uso: rodar na raiz do repo (/workspaces/libretro-gme)
    python3 apply_paula_label.py
"""
import os
import sys

PLAYER_C = "src/player.c"

OLD_LINE = '      strcpy(chip_text, is_mod ? "PAULA" : "TRACKER");\n'
NEW_LINE = '      strcpy(chip_text, is_mod ? "AMIGA: MIX. PAULA" : "TRACKER");\n'


def rd(p):
    with open(p, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.read()


def wr(p, s):
    with open(p, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(s)


def fail(msg):
    print("ABORTADO: " + msg)
    sys.exit(1)


def main():
    if not os.path.isfile(PLAYER_C):
        fail("nao encontrei %s" % PLAYER_C)

    txt = rd(PLAYER_C)

    if "AMIGA: MIX. PAULA" in txt:
        fail("%s ja tem o texto novo -- patch parece ja aplicado" % PLAYER_C)

    n = txt.count(OLD_LINE)
    if n == 0:
        fail("nao encontrei a linha exata esperada em %s "
             "(rode: grep -n 'PAULA' %s e me mande a saida)" % (PLAYER_C, PLAYER_C))
    if n > 1:
        fail("a linha esperada aparece %d vezes em %s (esperava 1) -- preciso conferir manualmente" % (n, PLAYER_C))

    new_txt = txt.replace(OLD_LINE, NEW_LINE, 1)
    wr(PLAYER_C, new_txt)

    print("OK: texto trocado com sucesso em %s." % PLAYER_C)
    print('Agora .mod com Mix. Paula ativo mostra "AMIGA: MIX. PAULA" na tela.')
    print("")
    print("Proximo passo: recompilar o core e substituir o .dll/.so de teste.")


if __name__ == "__main__":
    main()
