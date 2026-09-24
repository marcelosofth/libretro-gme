#!/usr/bin/env python3
"""
apply_lote4_fix.py

Corrige desafinacao/aliasing (ouvido como ruido nas batidas/transientes) no
YM2151 via ymfm.

Causa: Ymfm_Opm_Emu::set_rate() ignora o sample_rate pedido -- run() sempre
gera 1 amostra na taxa NATIVA do chip (clock/64) por chamada, sem decimar
internamente (diferente do wrapper do YM2203, que decima).

Em Vgm_Emu.cpp, fm_rate so era ajustado para a taxa nativa quando
disable_oversampling_ == true. Como nada no core chama
disable_oversampling(true), fm_rate ficava com o valor generico
"blip_rate * oversample_factor", que nao bate com a taxa real gerada pelo
ymfm. O Dual_Resampler entao reamostra com a proporcao errada -> aliasing,
mais perceptivel em transientes ricos em harmonicos (ataques percussivos).

Fix: para o YM2151 (backend ymfm sem decimacao propria), sempre usar a taxa
nativa do chip, independente de disable_oversampling_.
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
        '\tlong ym2151_rate = get_le32( header().ym2151_rate );\n'
        '\tif ( !uses_fm && ym2151_rate )\n'
        '\t{\n'
        '\t\tuses_fm = true;\n'
        '\t\tif ( disable_oversampling_ )\n'
        '\t\t\tfm_rate = ym2151.sample_rate( ym2151_rate );\n'
        '\t\tDual_Resampler::setup( fm_rate / blip_buf.sample_rate(), rolloff, fm_gain * gain() );',

        '\tlong ym2151_rate = get_le32( header().ym2151_rate );\n'
        '\tif ( !uses_fm && ym2151_rate )\n'
        '\t{\n'
        '\t\tuses_fm = true;\n'
        '\t\t// Ymfm_Opm_Emu::run() gera amostras na taxa NATIVA do chip,\n'
        '\t\t// sem decimar/reamostrar internamente (diferente do wrapper\n'
        '\t\t// do YM2203). fm_rate precisa bater com essa taxa nativa\n'
        '\t\t// sempre, nao so quando disable_oversampling_ esta ligado --\n'
        '\t\t// caso contrario o Dual_Resampler reamostra com a proporcao\n'
        '\t\t// errada, causando desafinacao/aliasing (mais audivel em\n'
        '\t\t// transientes percussivos do FM).\n'
        '\t\tfm_rate = ym2151.sample_rate( ym2151_rate );\n'
        '\t\tDual_Resampler::setup( fm_rate / blip_buf.sample_rate(), rolloff, fm_gain * gain() );'
    ),
])

print("Patch do Lote 4 (fix taxa nativa do YM2151/ymfm) aplicado com sucesso!")
