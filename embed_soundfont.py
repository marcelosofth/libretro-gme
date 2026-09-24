#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Converte um .sf2 num header C com os bytes embutidos, no mesmo espirito do
gen_mt32_inc.py (ROMs do MT-32): gera um array estatico usado como fallback
quando o FluidSynth nao encontra um SoundFont externo no diretorio de sistema.

Uso:
    python embed_soundfont.py "GeneralUser GS v1.511.sf2" fluid_soundfont.inc

O .inc gerado define:
    static const unsigned char fluid_sf2_data[];
    #define FLUID_SF2_SIZE  (tamanho em bytes)

Rode de novo sempre que trocar o .sf2 de origem -- o arquivo gerado nao deve
ser editado a mao.
"""
import sys

BYTES_PER_LINE = 20


def main():
    if len(sys.argv) != 3:
        sys.stderr.write("uso: embed_soundfont.py entrada.sf2 saida.inc\n")
        sys.exit(1)

    src_path, dst_path = sys.argv[1], sys.argv[2]

    with open(src_path, "rb") as f:
        data = f.read()

    with open(dst_path, "w", newline="\n") as f:
        f.write("/* gerado automaticamente por embed_soundfont.py a partir de\n")
        f.write("   %s -- nao editar a mao, rode o script de novo se o .sf2 mudar */\n\n"
                % src_path.replace("\\", "/"))
        f.write("static const unsigned char fluid_sf2_data[] = {\n")
        for i in range(0, len(data), BYTES_PER_LINE):
            chunk = data[i:i + BYTES_PER_LINE]
            f.write("   " + ",".join("0x%02x" % b for b in chunk) + ",\n")
        f.write("};\n")
        f.write("#define FLUID_SF2_SIZE %dUL\n" % len(data))

    sys.stderr.write("ok: %d bytes (%.1f MB) -> %s\n"
                      % (len(data), len(data) / 1048576.0, dst_path))


if __name__ == "__main__":
    main()
