#!/usr/bin/env python3
"""rename_gme_to_gme2.py - renomeia o identificador do core de "gme" para "gme2":
  - Makefile: TARGET_NAME
  - gme_libretro.info -> gme2_libretro.info (e corename dentro dele)
  - remove binarios antigos versionados (gme_libretro.dll / .so), se existirem,
    para nao ficarem "orfaos" no repo (o build vai gerar gme2_libretro.* no lugar)

Uso (na raiz do repo):  python3 rename_gme_to_gme2.py
Opcional:               python3 rename_gme_to_gme2.py --root /caminho/do/repo

Nao altera nada se qualquer ancora esperada nao for encontrada.
"""
import os
import sys

ROOT = "."
if "--root" in sys.argv:
    ROOT = sys.argv[sys.argv.index("--root") + 1]

MAKEFILE = os.path.join(ROOT, "Makefile")
INFO_OLD = os.path.join(ROOT, "gme_libretro.info")
INFO_NEW = os.path.join(ROOT, "gme2_libretro.info")
BIN_OLD_DLL = os.path.join(ROOT, "gme_libretro.dll")
BIN_OLD_SO = os.path.join(ROOT, "gme_libretro.so")


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


# ---------------------------------------------------------------- Makefile
if not os.path.isfile(MAKEFILE):
    fail("Makefile nao encontrado em %s" % MAKEFILE)

mk, mk_crlf = read(MAKEFILE)
if "TARGET_NAME := gme2" in mk:
    fail("o Makefile ja parece ter sido renomeado (TARGET_NAME := gme2 ja existe)")

mk = replace_once(mk, "TARGET_NAME := gme\n", "TARGET_NAME := gme2\n", "TARGET_NAME := gme")

# ---------------------------------------------------------------- .info
if not os.path.isfile(INFO_OLD):
    fail("%s nao encontrado (ja foi renomeado?)" % INFO_OLD)
if os.path.exists(INFO_NEW):
    fail("%s ja existe, abortando para nao sobrescrever" % INFO_NEW)

info, info_crlf = read(INFO_OLD)
info = replace_once(info, 'corename = "GME"\n', 'corename = "GME2"\n', 'corename = "GME"')

# ---------------------------------------------------------------- grava tudo
write(MAKEFILE, mk, mk_crlf)
write(INFO_NEW, info, info_crlf)
os.remove(INFO_OLD)

removed_bins = []
for b in (BIN_OLD_DLL, BIN_OLD_SO):
    if os.path.isfile(b):
        os.remove(b)
        removed_bins.append(b)

print("OK: Makefile atualizado (TARGET_NAME := gme2)")
print("OK: %s -> %s" % (INFO_OLD, INFO_NEW))
if removed_bins:
    print("OK: binarios antigos removidos: %s" % ", ".join(removed_bins))
else:
    print("Aviso: nenhum binario antigo (gme_libretro.dll/.so) encontrado na raiz para remover.")

print()
print("Proximos passos:")
print("  1) make platform=win clean   (ou o clean do seu ultimo build)")
print("  2) make platform=win -j$(nproc) ...   (mesmo comando de sempre)")
print("     -> vai gerar gme2_libretro.dll/.so em vez de gme_libretro.*")
print("  3) git add -A && git commit -m \"rename: gme -> gme2\" && git push origin libvgm")
