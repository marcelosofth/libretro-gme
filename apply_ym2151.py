#!/usr/bin/env python3
import sys

def patch(path, replacements):
    with open(path, 'r') as f:
        content = f.read()
    for old, new in replacements:
        if old not in content:
            print(f"AVISO: âncora não encontrada em {path}:\n{old!r}")
            sys.exit(1)
        content = content.replace(old, new, 1)
    with open(path, 'w') as f:
        f.write(content)
    print(f"OK: {path} patchado.")

# 1. Vgm_Emu_Impl.h
patch('deps/game-music-emu/gme/Vgm_Emu_Impl.h', [
    (
        '#include "Ym2413_Emu.h"\n#include "Ym2612_Emu.h"\n#include "Sms_Apu.h"',
        '#include "Ym2413_Emu.h"\n#include "Ym2612_Emu.h"\n#include "Ymfm_Opm_Emu.h"\n#include "Sms_Apu.h"'
    ),
    (
        'Ym_Emu<Ym2612_Emu> ym2612[2];\n\tYm_Emu<Ym2413_Emu> ym2413[2];',
        'Ym_Emu<Ym2612_Emu> ym2612[2];\n\tYm_Emu<Ym2413_Emu> ym2413[2];\n\tYm_Emu<Ymfm_Opm_Emu> ym2151;'
    ),
])

# 2. Vgm_Emu_Impl.cpp
patch('deps/game-music-emu/gme/Vgm_Emu_Impl.cpp', [
    (
        'case cmd_ym2612_port0:',
        'case cmd_ym2151:\n\t\t\tif ( ym2151.run_until( to_fm_time( vgm_time ) ) )\n\t\t\t\tym2151.write( pos [0], pos [1] );\n\t\t\tpos += 2;\n\t\t\tbreak;\n\n\t\tcase cmd_ym2612_port0:'
    ),
    (
        '\trun_commands( vgm_time );',
        '\telse if ( ym2151.enabled() )\n\t{\n\t\tym2151.begin_frame( buf );\n\t\tmemset( buf, 0, pairs * stereo * sizeof *buf );\n\t}\n\n\trun_commands( vgm_time );'
    ),
    (
        '\tfm_time_offset = (vgm_time * fm_time_factor + fm_time_offset) -',
        '\tif ( ym2151.enabled() )\n\t\tym2151.run_until( pairs );\n\n\tfm_time_offset = (vgm_time * fm_time_factor + fm_time_offset) -'
    ),
])

# 3. Vgm_Emu.cpp
patch('deps/game-music-emu/gme/Vgm_Emu.cpp', [
    (
        '\tif ( uses_fm )\n\t{\n\t\tRETURN_ERR( Dual_Resampler::reset( blip_buf.length() * blip_buf.sample_rate() / 1000 ) );\n\t\tpsg[0].volume( 0.135 * fm_gain * gain() );\n\t\tif ( psg_dual )\n\t\t\tpsg[1].volume( 0.135 * fm_gain * gain() );\n\t}\n\telse\n\t{\n\t\tym2612[0].enable( false );\n\t\tym2612[1].enable( false );\n\t\tym2413[0].enable( false );\n\t\tym2413[1].enable( false );\n\t\tpsg[0].volume( gain() );\n\t\tpsg[1].volume( gain() );\n\t}',
        '\tlong ym2151_rate = get_le32( header().ym2151_rate );\n\tif ( !uses_fm && ym2151_rate )\n\t{\n\t\tuses_fm = true;\n\t\tif ( disable_oversampling_ )\n\t\t\tfm_rate = ym2151.sample_rate( ym2151_rate );\n\t\tDual_Resampler::setup( fm_rate / blip_buf.sample_rate(), rolloff, fm_gain * gain() );\n\t\tRETURN_ERR( ym2151.set_rate( fm_rate, ym2151_rate ) );\n\t\tym2151.enable( true );\n\t\tset_voice_count( 8 );\n\t}\n\n\tif ( uses_fm )\n\t{\n\t\tRETURN_ERR( Dual_Resampler::reset( blip_buf.length() * blip_buf.sample_rate() / 1000 ) );\n\t\tpsg[0].volume( 0.135 * fm_gain * gain() );\n\t\tif ( psg_dual )\n\t\t\tpsg[1].volume( 0.135 * fm_gain * gain() );\n\t}\n\telse\n\t{\n\t\tym2612[0].enable( false );\n\t\tym2612[1].enable( false );\n\t\tym2413[0].enable( false );\n\t\tym2413[1].enable( false );\n\t\tym2151.enable( false );\n\t\tpsg[0].volume( gain() );\n\t\tpsg[1].volume( gain() );\n\t}'
    ),
    (
        '\t\tif ( ym2612[1].enabled() )\n\t\t\tym2612[1].reset();\n\n\t\tfm_time_offset = 0;',
        '\t\tif ( ym2612[1].enabled() )\n\t\t\tym2612[1].reset();\n\n\t\tif ( ym2151.enabled() )\n\t\t\tym2151.reset();\n\n\t\tfm_time_offset = 0;'
    ),
])

print("Todos os patches aplicados com sucesso!")