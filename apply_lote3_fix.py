#!/usr/bin/env python3
"""
apply_lote3_fix.py

Corrige um bug introduzido pelo apply_lote2.py: os campos ym3812_rate (0x50)
e ym3526_rate (0x54) do header VGM so sao validos se o header do arquivo
realmente se estende ate la. Muitos VGMs (ex.: trilha do Shinobi) declaram
version = 0x151 mas tem data_offset apontando para logo depois do campo
ym2151_rate (header "curto", estilo v1.50). Nesses casos, os bytes lidos
como ym3812_rate/ym3526_rate sao na verdade o inicio do stream de comandos,
e viram valores de clock absurdos -> chips OPL habilitados por engano ->
ruido/distorcao no audio.

A correcao: antes de ler cada campo, calcular o fim real do header a partir
de data_offset (relativo ao byte 0x34) e só confiar no campo se ele couber
dentro desse tamanho.
"""
import sys

def patch(path, replacements):
    with open(path, 'r') as f:
        content = f.read()
    for old, new in replacements:
        if old not in content:
            print(f"AVISO: ancora nao encontrada em {path}:\n{old!r}")
            sys.exit(1)
        content = content.replace(old, new, 1)
    with open(path, 'w') as f:
        f.write(content)
    print(f"OK: {path} patchado.")

patch('deps/game-music-emu/gme/Vgm_Emu.cpp', [
    (
        '\tlong vgm_version = get_le32( header().version );\n'
        '\tlong ym3812_rate = vgm_version >= 0x151 ? get_le32( header().ym3812_rate ) : 0;',

        '\t// data_offset e relativo ao proprio byte 0x34; o fim real do header\n'
        '\t// (em bytes, a partir do inicio do arquivo) e 0x34 + data_offset.\n'
        '\t// So confiamos em campos de clock que caibam dentro desse tamanho --\n'
        '\t// caso contrario estariamos lendo bytes do stream de comandos como\n'
        '\t// se fossem clock (bug visto nas trilhas do Shinobi, header curto\n'
        '\t// mas version = 0x151).\n'
        '\tlong vgm_version     = get_le32( header().version );\n'
        '\tlong vgm_data_offset = get_le32( header().data_offset ) + 0x34;\n'
        '\tlong ym3812_rate = ( vgm_version >= 0x151 && vgm_data_offset >= 0x54 )\n'
        '\t                    ? get_le32( header().ym3812_rate ) : 0;'
    ),
    (
        '\tlong ym3526_rate = vgm_version >= 0x151 ? get_le32( header().ym3526_rate ) : 0;',

        '\tlong ym3526_rate = ( vgm_version >= 0x151 && vgm_data_offset >= 0x58 )\n'
        '\t                    ? get_le32( header().ym3526_rate ) : 0;'
    ),
])

print("Patch do Lote 3 (fix header curto YM3812/YM3526) aplicado com sucesso!")
