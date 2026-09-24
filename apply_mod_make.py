#!/usr/bin/env python3
import os, sys

XMP = "deps/libxmp"
core = ("virtual format period player read_event misc dataio lfo scan control "
        "filter effects flow mixer mix_all load_helpers load filetype hio smix "
        "memio rng win32").split()
loaders = "common itsex sample xm_load mod_load s3m_load it_load".split()

files = ["$(XMP_DIR)/src/%s.c" % n for n in core] + \
        ["$(XMP_DIR)/src/loaders/%s.c" % n for n in loaders]

missing = [f for f in files if not os.path.isfile(f.replace("$(XMP_DIR)", XMP))]
if missing:
    print("Faltam estes arquivos em deps/libxmp (nada foi alterado):")
    for m in missing:
        print("  ", m.replace("$(XMP_DIR)", XMP))
    sys.exit(1)

with open("Makefile.common", encoding="utf-8", newline="") as f:
    mk = f.read()

if "XMP_DIR" in mk:
    print("Makefile.common ja tem o bloco da libxmp. Abortando.")
    sys.exit(1)

anchor = "INCFLAGS += -I$(DEPS_DIR)/libvgm"
if mk.count(anchor) != 1:
    print("Ancora '%s' achou %d vezes, esperado 1. Nada foi alterado." % (anchor, mk.count(anchor)))
    sys.exit(1)

block = anchor + "\n\n"
block += "# ---- libxmp (MOD/S3M/XM/IT), perfil lite: mesmas fontes e defines da libxmp-lite ----\n"
block += "XMP_DIR := $(DEPS_DIR)/libxmp\n"
block += "INCFLAGS += -I$(XMP_DIR)/include\n"
block += "CFLAGS += -DLIBXMP_CORE_PLAYER -DLIBXMP_STATIC\n"
block += "SOURCES_C += $(CORE_DIR)/src/xmp_backend.c \\\n"
block += " \\\n".join("                 " + f for f in files) + "\n"

with open("Makefile.common.pre_xmp", "w", encoding="utf-8", newline="") as f:
    f.write(mk)
with open("Makefile.common", "w", encoding="utf-8", newline="") as f:
    f.write(mk.replace(anchor, block))
print("OK: Makefile.common atualizado (backup em Makefile.common.pre_xmp).")
