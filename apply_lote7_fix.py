#!/usr/bin/env python3
"""
apply_lote7_fix.py

Corrige overflow silencioso (wraparound) no Ymfm_Opm_Emu::run(): o valor do
chip ja vem clampado (clamp16()) mas a SOMA com o conteudo existente do
buffer out[] pode passar de +-32767 e estourar por wraparound de short,
gerando ruido digital que nenhum ajuste de ganho externo (Lotes 5/6)
consegue corrigir, por acontecer antes deles na cadeia.

Fix: usar uma soma saturada (clamp apos a soma), igual ao que o proprio
ymfm faz internamente em clamp16(), em vez de deixar o cast pra short
estourar sem controle.
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

patch('deps/game-music-emu/gme/Ymfm_Opm_Emu.h', [
    (
        '                        ymfm::ym2151::output_data output;\n'
        '                        chip.generate( &output, 1 );\n'
        '                        output.clamp16();\n'
        '                        out [0] = (sample_t) (out [0] + output.data [0]);\n'
        '                        out [1] = (sample_t) (out [1] + output.data [1]);\n'
        '                        out += 2;',

        '                        ymfm::ym2151::output_data output;\n'
        '                        chip.generate( &output, 1 );\n'
        '                        output.clamp16();\n'
        '                        // Somar em cima do conteudo existente de out[] pode\n'
        '                        // passar de +-32767 mesmo com output ja clampado,\n'
        '                        // estourando por wraparound silencioso de short (ruido\n'
        '                        // digital, nao apenas clipping suave). Precisa saturar\n'
        '                        // a SOMA, nao so o valor individual do chip.\n'
        '                        out [0] = (sample_t) clamp_sample( (int) out [0] + output.data [0] );\n'
        '                        out [1] = (sample_t) clamp_sample( (int) out [1] + output.data [1] );\n'
        '                        out += 2;'
    ),
    (
        'class Ymfm_Opm_Emu : public ymfm::ymfm_interface {\n'
        'public:',

        'static inline int clamp_sample( int v )\n'
        '{\n'
        '        if ( v < -32768 ) return -32768;\n'
        '        if ( v >  32767 ) return  32767;\n'
        '        return v;\n'
        '}\n'
        '\n'
        'class Ymfm_Opm_Emu : public ymfm::ymfm_interface {\n'
        'public:'
    ),
])

print("Patch do Lote 7 (fix overflow/wraparound no Ymfm_Opm_Emu::run) aplicado com sucesso!")