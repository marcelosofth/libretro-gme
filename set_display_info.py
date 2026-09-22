#!/usr/bin/env python3
"""set_display_info.py - atualiza o nome e a versao exibidos pelo RetroArch
no menu rapido, editando display_name e display_version no arquivo .info do core.

Uso (na raiz do repo):  python3 set_display_info.py
Opcional:               python3 set_display_info.py --root /caminho/do/repo
                         python3 set_display_info.py --name "Outro Nome" --version "v2.0"

Procura automaticamente por gme2_libretro.info; se nao existir, tenta gme_libretro.info.
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

CANDIDATES = [
    os.path.join(ROOT, "gme2_libretro.info"),
    os.path.join(ROOT, "gme_libretro.info"),
]


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


INFO_PATH = None
for c in CANDIDATES:
    if os.path.isfile(c):
        INFO_PATH = c
        break

if INFO_PATH is None:
    fail("nenhum arquivo .info encontrado (procurei: %s)" % ", ".join(CANDIDATES))

text, crlf = read(INFO_PATH)
lines = text.split("\n")

name_idx = None
version_idx = None
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith("display_name") and "=" in stripped:
        name_idx = i
    if stripped.startswith("display_version") and "=" in stripped:
        version_idx = i

if name_idx is None:
    fail("linha 'display_name = ...' nao encontrada em %s" % INFO_PATH)
if version_idx is None:
    fail("linha 'display_version = ...' nao encontrada em %s" % INFO_PATH)

old_name_line = lines[name_idx]
old_version_line = lines[version_idx]

lines[name_idx] = 'display_name = "%s"' % NAME
lines[version_idx] = 'display_version = "%s"' % VERSION

new_text = "\n".join(lines)
write(INFO_PATH, new_text, crlf)

print("Arquivo alterado: %s" % INFO_PATH)
print("  %s" % old_name_line.strip())
print("  -> %s" % lines[name_idx])
print("  %s" % old_version_line.strip())
print("  -> %s" % lines[version_idx])
print()
print("Recompile e copie o core + o .info atualizado para a pasta de cores do RetroArch")
print("(ou reenvie o build, se estiver usando um core baixado por outro caminho).")
