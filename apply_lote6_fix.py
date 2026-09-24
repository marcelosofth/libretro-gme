#!/usr/bin/env python3
"""
apply_lote6_fix.py

Corrige o segundo ponto do estouro do YM2151 (Shinobi): o volume do PSG
(SN76489) era multiplicado por fm_gain=3.0 sempre que uses_fm era true,
mesmo quando o chip FM ativo era o YM2151 (que ja sai em escala cheia,
sem precisar do reforço de 3x pensado pro YM2612/YM2413/etc). Isso inflava
o PSG e a soma PSG+YM2151 estourava no Blip_Buffer, mesmo com o fix
anterior (Lote 5) certo.

Fix: introduzir fm_gain_effective, que comeca igual a fm_gain e cai pra
1.0 soh quando quem ligou uses_fm foi o YM2151. O volume do PSG passa a
usar fm_gain_effective em vez de fm_gain direto.
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
        '\tuses_fm = false;\n'
        '\n'
        '\tfm_rate = blip_buf.sample_rate() * oversample_factor;',

        '\tuses_fm = false;\n'
        '\t// Ganho efetivo aplicado ao PSG quando algum chip FM esta ativo.\n'
        '\t// Comeca igual a fm_gain (reforço de 3x, correto pros FM \n'
        '\t// "internamente baixos" como YM2612/YM2413/etc) mas cai pra 1.0\n'
        '\t// quando quem ativa uses_fm e o YM2151, que ja sai em escala\n'
        '\t// cheia -- ver comentario do fix do Lote 5.\n'
        '\tdouble fm_gain_effective = fm_gain;\n'
        '\n'
        '\tfm_rate = blip_buf.sample_rate() * oversample_factor;'
    ),
    (
        '\t\tuses_fm = true;\n'
        '\t\t// Ymfm_Opm_Emu::run() gera amostras na taxa NATIVA do chip,',

        '\t\tuses_fm = true;\n'
        '\t\tfm_gain_effective = 1.0; // YM2151 full-scale -- PSG acompanha, sem reforço de 3x\n'
        '\t\t// Ymfm_Opm_Emu::run() gera amostras na taxa NATIVA do chip,'
    ),
    (
        '\t\tpsg[0].volume( 0.135 * fm_gain * gain() );\n'
        '\t\tif ( psg_dual )\n'
        '\t\t\tpsg[1].volume( 0.135 * fm_gain * gain() );',

        '\t\tpsg[0].volume( 0.135 * fm_gain_effective * gain() );\n'
        '\t\tif ( psg_dual )\n'
        '\t\t\tpsg[1].volume( 0.135 * fm_gain_effective * gain() );'
    ),
])

print("Patch do Lote 6 (fix PSG+YM2151) aplicado com sucesso!")