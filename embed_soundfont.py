#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Converte um .sf2 num header C com os bytes embutidos, no mesmo espirito do
gen_mt32_inc.py (ROMs do MT-32): gera um array estatico usado como fallback
quando o FluidSynth (ou o TSF) nao encontra um SoundFont externo no
diretorio de sistema.

Uso:
    python embed_soundfont.py entrada.sf2 saida.inc [prefixo]

O prefixo (opcional, default "fluid") define os nomes gerados no .inc:
    static const unsigned char <prefixo>_sf2_data[];
    #define <PREFIXO>_SF2_SIZE  (tamanho em bytes)

Exemplos:
    python embed_soundfont.py "GeneralUser GS v1.511.sf2" src/fluid_soundfont.inc
        -> fluid_sf2_data / FLUID_SF2_SIZE   (usado pelo FluidSynth, prefixo default)

    python embed_soundfont.py "TimGM6mb.sf2" src/gm_soundfont.inc gm
        -> gm_sf2_data / GM_SF2_SIZE         (usado pelo TSF em open_gm())

Rode de novo sempre que trocar o .sf2 de origem -- o arquivo gerado nao deve
ser editado a mao.
"""
import sys

BYTES_PER_LINE = 20


def main():
    if len(sys.argv) not in (3, 4):
        sys.stderr.write("uso: embed_soundfont.py entrada.sf2 saida.inc [prefixo]\n")
        sys.exit(1)

    src_path, dst_path = sys.argv[1], sys.argv[2]
    prefix = sys.argv[3] if len(sys.argv) == 4 else "fluid"

    var_name = "%s_sf2_data" % prefix
    size_macro = "%s_SF2_SIZE" % prefix.upper()

    with open(src_path, "rb") as f:
        data = f.read()

    with open(dst_path, "w", newline="\n") as f:
        f.write("/* gerado automaticamente por embed_soundfont.py a partir de\n")
        f.write("   %s -- nao editar a mao, rode o script de novo se o .sf2 mudar */\n\n"
                % src_path.replace("\\", "/"))
        f.write("static const unsigned char %s[] = {\n" % var_name)
        for i in range(0, len(data), BYTES_PER_LINE):
            chunk = data[i:i + BYTES_PER_LINE]
            f.write("   " + ",".join("0x%02x" % b for b in chunk) + ",\n")
        f.write("};\n")
        f.write("#define %s %dUL\n" % (size_macro, len(data)))

    sys.stderr.write("ok: %d bytes (%.1f MB) -> %s (%s / %s)\n"
                      % (len(data), len(data) / 1048576.0, dst_path, var_name, size_macro))


if __name__ == "__main__":
    main()
