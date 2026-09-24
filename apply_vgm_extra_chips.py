#!/usr/bin/env python3
"""
apply_vgm_extra_chips.py

Acrescenta 7 chips a mais na tabela chip_tab de src/player.c, para que a
tela mostre o nome correto quando um VGM usa: Mikey, K007232, K005289,
MSM5205, MSM5232, BSMT2000 ou ICS2115.

IMPORTANTE: o audio desses chips ja funciona hoje (a libvgm ja despacha e
toca todos eles via VGMPlayer). Este patch e' puramente cosmetico: ele so
ensina a deteccao de chip (chip_tab) do player.c a reconhecer esses 7
offsets no cabecalho do VGM, para exibir o nome certo na tela, igual ja
acontece com SN76489, YM2612 etc.

Offsets confirmados na propria libvgm (deps/libvgm/player/vgmplayer.cpp,
tabela _CHIPCLK_OFS), que sao os offsets realmente lidos pelo motor de
audio para obter o clock de cada chip:
    Mikey    = 0xE4
    K007232  = 0xE8
    K005289  = 0xEC
    MSM5205  = 0xF0
    MSM5232  = 0xF4
    BSMT2000 = 0xF8
    ICS2115  = 0xFC

Uso: rodar na raiz do repo (/workspaces/libretro-gme)
    python3 apply_vgm_extra_chips.py
"""
import os
import sys

PLAYER_C = "src/player.c"

OLD_LINE = (
    '   {0xD8,0x171,"C352"},{0xDC,0x171,"GA20"}\n'
)
NEW_LINE = (
    '   {0xD8,0x171,"C352"},{0xDC,0x171,"GA20"},\n'
    '   {0xE4,0x171,"Mikey"},{0xE8,0x171,"K007232"},{0xEC,0x171,"K005289"},\n'
    '   {0xF0,0x171,"MSM5205"},{0xF4,0x171,"MSM5232"},{0xF8,0x171,"BSMT2000"},\n'
    '   {0xFC,0x171,"ICS2115"}\n'
)


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

    if '"Mikey"' in txt or '"ICS2115"' in txt:
        fail("%s ja parece ter algum dos 7 chips novos -- patch parece ja aplicado" % PLAYER_C)

    n = txt.count(OLD_LINE)
    if n == 0:
        fail("nao encontrei a linha exata esperada (final da chip_tab, com C352 e GA20) em %s "
             "(rode: grep -n 'GA20' %s e me mande a saida)" % (PLAYER_C, PLAYER_C))
    if n > 1:
        fail("a linha esperada aparece %d vezes em %s (esperava 1) -- preciso conferir manualmente" % (n, PLAYER_C))

    new_txt = txt.replace(OLD_LINE, NEW_LINE, 1)
    wr(PLAYER_C, new_txt)

    print("OK: 7 novos chips adicionados a chip_tab em %s." % PLAYER_C)
    print("Mikey, K007232, K005289, MSM5205, MSM5232, BSMT2000, ICS2115")
    print("")
    print("Proximo passo: recompilar o core e substituir o .dll/.so de teste.")
    print("O audio ja funcionava antes; agora a tela tambem deve mostrar o nome certo.")


if __name__ == "__main__":
    main()
