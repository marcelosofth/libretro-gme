#!/usr/bin/env python3
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

# 1. Vgm_Emu.h -- extend header_t with the fields from 0x38 through 0x60
patch('deps/game-music-emu/gme/Vgm_Emu.h', [
    (
        '\t\tbyte data_offset [4];\n\t\tbyte unused2 [8];\n\t};',
        '\t\tbyte data_offset [4];\n'
        '\t\tbyte segapcm_rate [4];    // 0x38\n'
        '\t\tbyte spcm_interface [4];  // 0x3C\n'
        '\t\tbyte rf5c68_rate [4];     // 0x40\n'
        '\t\tbyte ym2203_rate [4];     // 0x44\n'
        '\t\tbyte ym2608_rate [4];     // 0x48\n'
        '\t\tbyte ym2610_rate [4];     // 0x4C\n'
        '\t\tbyte ym3812_rate [4];     // 0x50\n'
        '\t\tbyte ym3526_rate [4];     // 0x54\n'
        '\t\tbyte y8950_rate [4];      // 0x58\n'
        '\t\tbyte ymf262_rate [4];     // 0x5C\n'
        '\t};'
    ),
])

# 2. Vgm_Emu_Impl.h -- include + members
patch('deps/game-music-emu/gme/Vgm_Emu_Impl.h', [
    (
        '#include "Ymfm_Opm_Emu.h"\n#include "Sms_Apu.h"',
        '#include "Ymfm_Opm_Emu.h"\n#include "Ymfm_Opl_Mono_Emu.h"\n#include "Sms_Apu.h"'
    ),
    (
        'Ym_Emu<Ymfm_Opm_Emu> ym2151;',
        'Ym_Emu<Ymfm_Opm_Emu> ym2151;\n\tYm_Emu<Ymfm_Ym3812_Emu> ym3812;\n\tYm_Emu<Ymfm_Ym3526_Emu> ym3526;'
    ),
])

# 3. Vgm_Emu_Impl.cpp -- opcode enum, dispatch cases, play_frame wiring
patch('deps/game-music-emu/gme/Vgm_Emu_Impl.cpp', [
    (
        'cmd_ym2151          = 0x54,',
        'cmd_ym2151          = 0x54,\n\t\tcmd_ym3812          = 0x5A,\n\t\tcmd_ym3526          = 0x5B,'
    ),
    (
        'case cmd_ym2612_port0:',
        'case cmd_ym3812:\n'
        '\t\t\tif ( ym3812.run_until( to_fm_time( vgm_time ) ) )\n'
        '\t\t\t\tym3812.write( pos [0], pos [1] );\n'
        '\t\t\tpos += 2;\n'
        '\t\t\tbreak;\n\n'
        '\t\tcase cmd_ym3526:\n'
        '\t\t\tif ( ym3526.run_until( to_fm_time( vgm_time ) ) )\n'
        '\t\t\t\tym3526.write( pos [0], pos [1] );\n'
        '\t\t\tpos += 2;\n'
        '\t\t\tbreak;\n\n'
        '\t\tcase cmd_ym2612_port0:'
    ),
    (
        '\telse if ( ym2151.enabled() )\n\t{\n\t\tym2151.begin_frame( buf );\n\t\tmemset( buf, 0, pairs * stereo * sizeof *buf );\n\t}\n\n\trun_commands( vgm_time );',
        '\telse if ( ym2151.enabled() )\n\t{\n\t\tym2151.begin_frame( buf );\n\t\tmemset( buf, 0, pairs * stereo * sizeof *buf );\n\t}\n'
        '\telse if ( ym3812.enabled() )\n\t{\n\t\tym3812.begin_frame( buf );\n\t\tmemset( buf, 0, pairs * stereo * sizeof *buf );\n\t}\n'
        '\telse if ( ym3526.enabled() )\n\t{\n\t\tym3526.begin_frame( buf );\n\t\tmemset( buf, 0, pairs * stereo * sizeof *buf );\n\t}\n'
        '\n\trun_commands( vgm_time );'
    ),
    (
        '\tif ( ym2151.enabled() )\n\t\tym2151.run_until( pairs );\n\n\tfm_time_offset',
        '\tif ( ym2151.enabled() )\n\t\tym2151.run_until( pairs );\n\n'
        '\tif ( ym3812.enabled() )\n\t\tym3812.run_until( pairs );\n\n'
        '\tif ( ym3526.enabled() )\n\t\tym3526.run_until( pairs );\n\n'
        '\tfm_time_offset'
    ),
])

# 4. Vgm_Emu.cpp -- enable logic, version-gated
patch('deps/game-music-emu/gme/Vgm_Emu.cpp', [
    (
        '\tlong ym2151_rate = get_le32( header().ym2151_rate );\n'
        '\tif ( !uses_fm && ym2151_rate )\n'
        '\t{\n'
        '\t\tuses_fm = true;\n'
        '\t\tif ( disable_oversampling_ )\n'
        '\t\t\tfm_rate = ym2151.sample_rate( ym2151_rate );\n'
        '\t\tDual_Resampler::setup( fm_rate / blip_buf.sample_rate(), rolloff, fm_gain * gain() );\n'
        '\t\tRETURN_ERR( ym2151.set_rate( fm_rate, ym2151_rate ) );\n'
        '\t\tym2151.enable( true );\n'
        '\t\tset_voice_count( 8 );\n'
        '\t}\n',
        '\tlong ym2151_rate = get_le32( header().ym2151_rate );\n'
        '\tif ( !uses_fm && ym2151_rate )\n'
        '\t{\n'
        '\t\tuses_fm = true;\n'
        '\t\tif ( disable_oversampling_ )\n'
        '\t\t\tfm_rate = ym2151.sample_rate( ym2151_rate );\n'
        '\t\tDual_Resampler::setup( fm_rate / blip_buf.sample_rate(), rolloff, fm_gain * gain() );\n'
        '\t\tRETURN_ERR( ym2151.set_rate( fm_rate, ym2151_rate ) );\n'
        '\t\tym2151.enable( true );\n'
        '\t\tset_voice_count( 8 );\n'
        '\t}\n'
        '\n'
        '\tlong vgm_version = get_le32( header().version );\n'
        '\tlong ym3812_rate = vgm_version >= 0x151 ? get_le32( header().ym3812_rate ) : 0;\n'
        '\tif ( !uses_fm && ym3812_rate )\n'
        '\t{\n'
        '\t\tuses_fm = true;\n'
        '\t\tif ( disable_oversampling_ )\n'
        '\t\t\tfm_rate = ym3812.sample_rate( ym3812_rate );\n'
        '\t\tDual_Resampler::setup( fm_rate / blip_buf.sample_rate(), rolloff, fm_gain * gain() );\n'
        '\t\tRETURN_ERR( ym3812.set_rate( fm_rate, ym3812_rate ) );\n'
        '\t\tym3812.enable( true );\n'
        '\t\tset_voice_count( 9 );\n'
        '\t}\n'
        '\n'
        '\tlong ym3526_rate = vgm_version >= 0x151 ? get_le32( header().ym3526_rate ) : 0;\n'
        '\tif ( !uses_fm && ym3526_rate )\n'
        '\t{\n'
        '\t\tuses_fm = true;\n'
        '\t\tif ( disable_oversampling_ )\n'
        '\t\t\tfm_rate = ym3526.sample_rate( ym3526_rate );\n'
        '\t\tDual_Resampler::setup( fm_rate / blip_buf.sample_rate(), rolloff, fm_gain * gain() );\n'
        '\t\tRETURN_ERR( ym3526.set_rate( fm_rate, ym3526_rate ) );\n'
        '\t\tym3526.enable( true );\n'
        '\t\tset_voice_count( 9 );\n'
        '\t}\n'
    ),
    (
        '\t\tym2151.enable( false );\n\t\tpsg[0].volume( gain() );',
        '\t\tym2151.enable( false );\n\t\tym3812.enable( false );\n\t\tym3526.enable( false );\n\t\tpsg[0].volume( gain() );'
    ),
    (
        '\t\tif ( ym2151.enabled() )\n\t\t\tym2151.reset();\n\n\t\tfm_time_offset = 0;',
        '\t\tif ( ym2151.enabled() )\n\t\t\tym2151.reset();\n\n'
        '\t\tif ( ym3812.enabled() )\n\t\t\tym3812.reset();\n\n'
        '\t\tif ( ym3526.enabled() )\n\t\t\tym3526.reset();\n\n'
        '\t\tfm_time_offset = 0;'
    ),
])

print("Todos os patches do Lote 2 aplicados com sucesso!")