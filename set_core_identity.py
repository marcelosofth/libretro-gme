#!/usr/bin/env python3
"""set_core_identity.py - muda o nome e a versao que o CORE reporta em tempo de
execucao (retro_get_system_info, em src/libretro.c), independente do arquivo .info.

Uso (na raiz do repo):  python3 set_core_identity.py
Opcional:               python3 set_core_identity.py --root /caminho/do/repo
                         python3 set_core_identity.py --name "Game Music Emu 2" --version "v1.2"

Nao altera nada se as ancoras esperadas nao forem encontradas.
"""
import os
import sys

ROOT = "."
if "--root" in sys.argv:
    ROOT = sys.argv[sys.argv.index("--root") + 1]

NAME = "Game Music Emu 2"
if "--name" in sys.argv:
    NAME = sys.argv[sys.argv.index("--name") + 1]

VERSION = "v1.2"
if "--version" in sys.argv:
    VERSION = sys.argv[sys.argv.index("--version") + 1]

L_C = os.path.join(ROOT, "src", "libretro.c")


def read(path):
    with open(path, "rb") as f:
        raw = f.read().decode("utf-8")
    crlf = "\r\n" in raw
    return raw.replace("\r\n", "\n"), crlf


def write(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def fail(msg):
    print("ERRO: " + msg)
    print("Nenhum arquivo foi alterado.")
    sys.exit(1)


def replace_once(text, old, new, what):
    n = text.count(old)
    if n != 1:
        fail("ancora '%s' encontrada %d vez(es), esperado 1" % (what, n))
    return text.replace(old, new, 1)


if not os.path.isfile(L_C):
    fail("%s nao encontrado" % L_C)

lc, lc_crlf = read(L_C)

OLD_NAME_LINE = 'info->library_name = "Game Music Emulator";\n'
OLD_VERSION_LINE = 'info->library_version = "v0.6.6";\n'

NEW_NAME_LINE = 'info->library_name = "%s";\n' % NAME
NEW_VERSION_LINE = 'info->library_version = "%s";\n' % VERSION

lc = replace_once(lc, OLD_NAME_LINE, NEW_NAME_LINE, "info->library_name = ...")
lc = replace_once(lc, OLD_VERSION_LINE, NEW_VERSION_LINE, "info->library_version = ...")

write(L_C, lc, lc_crlf)

print("OK: src/libretro.c atualizado")
print("  library_name    -> \"%s\"" % NAME)
print("  library_version -> \"%s\"" % VERSION)
print()
print("Agora recompile: make platform=win -j$(nproc) ... (mesmo comando de sempre)")
print("O novo texto vai aparecer no rodape do RetroArch assim que o core recompilado for carregado.")
