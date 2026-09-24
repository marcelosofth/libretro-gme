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

# 1. Vgm_Emu_Impl.h -- include + member
patch('deps/game-music-emu/gme/Vgm_Emu_Impl.h', [
    (
        '#include "Ymfm_Opl_Mono_Emu.h"\n#include "Sms_Apu.h"',
        '#include "Ymfm_Opl_Mono_Emu.h"\n#include "Ymfm_Opn_Emu.h"\n#include "Sms_Apu.h"'
    ),
    (
        'Ym_Emu<Ymfm_Ym3526_Emu> ym3526;',
        'Ym_Emu<Ymfm_Ym3526_Emu> ym3526;\n\tYm_Emu<Ymfm_Opn_Emu> ym2203;'
    ),
])

# 2. Vgm_Emu_Impl.cpp -- opcode enum, dispatch case, play_frame wiring
patch('deps/game-music-emu/gme/Vgm_Emu_Impl.cpp', [
    (
        'cmd_ym3526          = 0x5B,',
        'cmd_ym3526          = 0x5B,\n\t\tcmd_ym2203          = 0x55,'
    ),
    (
        'case cmd_ym2612_port0:',
        'case cmd_ym2203:\n'
        '\t\t\tif ( ym2203.run_until( to_fm_time( vgm_time ) ) )\n'
        '\t\t\t\tym2203.write( pos [0], pos [1] );\n'
        '\t\t\tpos += 2;\n'
        '\t\t\tbreak;\n\n'
        '\t\tcase cmd_ym2612_port0:'
    ),
    (
        '\telse if ( ym3526.enabled() )\n\t{\n\t\tym3526.begin_frame( buf );\n\t\tmemset( buf, 0, pairs * stereo * sizeof *buf );\n\t}\n\n\trun_commands( vgm_time );',
        '\telse if ( ym3526.enabled() )\n\t{\n\t\tym3526.begin_frame( buf );\n\t\tmemset( buf, 0, pairs * stereo * sizeof *buf );\n\t}\n'
        '\telse if ( ym2203.enabled() )\n\t{\n\t\tym2203.begin_frame( buf );\n\t\tmemset( buf, 0, pairs * stereo * sizeof *buf );\n\t}\n'
        '\n\trun_commands( vgm_time );'
    ),
    (
        '\tif ( ym3526.enabled() )\n\t\tym3526.run_until( pairs );\n\n\tfm_time_offset',
        '\tif ( ym3526.enabled() )\n\t\tym3526.run_until( pairs );\n\n'
        '\tif ( ym2203.enabled() )\n\t\tym2203.run_until( pairs );\n\n'
        '\tfm_time_offset'
    ),
])

# 3. Vgm_Emu.cpp -- enable logic (version-gated, offset 0x44 is beyond the
# short 0x40 header), disable-all block, reset block
patch('deps/game-music-emu/gme/Vgm_Emu.cpp', [
    (
        '\t\tRETURN_ERR( ym3526.set_rate( fm_rate, ym3526_rate ) );\n\t\tym3526.enable( true );\n\t\tset_voice_count( 9 );\n\t}\n',
        '\t\tRETURN_ERR( ym3526.set_rate( fm_rate, ym3526_rate ) );\n\t\tym3526.enable( true );\n\t\tset_voice_count( 9 );\n\t}\n'
        '\n'
        '\tlong ym2203_rate = vgm_version >= 0x151 ? get_le32( header().ym2203_rate ) : 0;\n'
        '\tif ( !uses_fm && ym2203_rate )\n'
        '\t{\n'
        '\t\tuses_fm = true;\n'
        '\t\tif ( disable_oversampling_ )\n'
        '\t\t\tfm_rate = ym2203.sample_rate( ym2203_rate );\n'
        '\t\tDual_Resampler::setup( fm_rate / blip_buf.sample_rate(), rolloff, fm_gain * gain() );\n'
        '\t\tRETURN_ERR( ym2203.set_rate( fm_rate, ym2203_rate ) );\n'
        '\t\tym2203.enable( true );\n'
        '\t\tset_voice_count( 6 );\n'
        '\t}\n'
    ),
    (
        '\t\tym3812.enable( false );\n\t\tym3526.enable( false );\n\t\tpsg[0].volume( gain() );',
        '\t\tym3812.enable( false );\n\t\tym3526.enable( false );\n\t\tym2203.enable( false );\n\t\tpsg[0].volume( gain() );'
    ),
    (
        '\t\tif ( ym3526.enabled() )\n\t\t\tym3526.reset();\n\n\t\tfm_time_offset = 0;',
        '\t\tif ( ym3526.enabled() )\n\t\t\tym3526.reset();\n\n'
        '\t\tif ( ym2203.enabled() )\n\t\t\tym2203.reset();\n\n'
        '\t\tfm_time_offset = 0;'
    ),
])

# 4. Makefile.common -- add ymfm_opn.cpp
with open('Makefile.common', 'r') as f:
    mk = f.read()
old_mk = '$(DEPS_DIR)/ymfm/src/ymfm_opl.cpp \\\n'
new_mk = old_mk + '            $(DEPS_DIR)/ymfm/src/ymfm_opn.cpp \\\n'
if old_mk not in mk:
    print("AVISO: ancora do Makefile.common (ymfm_opl.cpp) nao encontrada")
    sys.exit(1)
mk = mk.replace(old_mk, new_mk, 1)
with open('Makefile.common', 'w') as f:
    f.write(mk)
print("OK: Makefile.common patchado (ymfm_opn.cpp adicionado).")

print("Todos os patches do YM2203 aplicados com sucesso!")