#!/usr/bin/env python3
"""
apply_lote5_fix.py

Corrige clipping/estouro no YM2151 (via ymfm).

Causa: fm_gain = 3.0 foi calibrado para os sintetizadores classicos do gme
(Ym2612_Emu, Ym2413_Emu), que sao "internamente mais baixos de proposito"
(comentario original no codigo) e por isso precisam desse reforço de 3x
antes de chegar em escala cheia.

Ymfm_Opm_Emu::run() ja satura cada canal em escala cheia via
output.clamp16() antes de devolver a amostra -- nao tem esse headroom
interno. Aplicar fm_gain*gain() em cima disso multiplica um sinal que ja
esta no talo, e satura de verdade (corte/distorcao), mais perceptivel nos
transientes fortes (batidas/percussao do FM).

Fix: para o setup() do YM2151, usar so gain() (o ganho geral do usuario),
sem o reforço de 3x pensado pros emuladores classicos.
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
        '\t\tfm_rate = ym2151.sample_rate( ym2151_rate );\n'
        '\t\tDual_Resampler::setup( fm_rate / blip_buf.sample_rate(), rolloff, fm_gain * gain() );',

        '\t\tfm_rate = ym2151.sample_rate( ym2151_rate );\n'
        '\t\t// Ymfm_Opm_Emu ja satura cada canal em escala cheia\n'
        '\t\t// (clamp16()) antes de sair do chip -- diferente dos\n'
        '\t\t// sintetizadores classicos do gme (Ym2612_Emu/Ym2413_Emu),\n'
        '\t\t// que sao "internamente mais baixos de proposito" (ver\n'
        '\t\t// comentario de fm_gain acima) e por isso precisam do\n'
        '\t\t// reforço de 3x. Aplicar fm_gain aqui estoura um sinal\n'
        '\t\t// que ja esta em escala cheia.\n'
        '\t\tDual_Resampler::setup( fm_rate / blip_buf.sample_rate(), rolloff, gain() );'
    ),
])

print("Patch do Lote 5 (fix ganho/clipping do YM2151) aplicado com sucesso!")
