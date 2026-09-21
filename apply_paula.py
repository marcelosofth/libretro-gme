#!/usr/bin/env python3
"""
apply_paula.py

Liga o Mix. Paula (emulacao do chip de mixagem do Amiga 500) para os
modulos .mod tocados via libxmp neste core.

O que este script faz:
  1. Confere que deps/libxmp/src/mix_paula.c, paula.h e precomp_blep.h existem.
  2. Confere que Makefile.common tem a linha com -DLIBXMP_CORE_PLAYER -DLIBXMP_STATIC
     e que -DLIBXMP_PAULA_SIMULATOR ainda nao foi adicionada (evita duplicar).
  3. Confere que Makefile.common tem a linha do mix_all.c dentro do SOURCES_C
     e que mix_paula.c ainda nao foi adicionado.
  4. Confere que src/xmp_backend.c tem a linha exata da chamada XMP_PLAYER_MIX
     e que XMP_FLAGS_A500 ainda nao foi adicionada.

Se qualquer verificacao falhar, o script aborta SEM alterar nenhum arquivo
e imprime o motivo. So grava depois que as 3 alteracoes (Makefile x2 +
xmp_backend.c) forem validadas em memoria.

Uso: rodar na raiz do repo (/workspaces/libretro-gme)
    python3 apply_paula.py
"""
import os
import sys

MAKEFILE = "Makefile.common"
BACKEND = "src/xmp_backend.c"

MIX_PAULA_C = "deps/libxmp/src/mix_paula.c"
PAULA_H = "deps/libxmp/src/paula.h"
PRECOMP_BLEP_H = "deps/libxmp/src/precomp_blep.h"

OLD_CFLAGS_LINE = "CFLAGS += -DLIBXMP_CORE_PLAYER -DLIBXMP_STATIC"
NEW_CFLAGS_LINE = "CFLAGS += -DLIBXMP_CORE_PLAYER -DLIBXMP_STATIC -DLIBXMP_PAULA_SIMULATOR"

OLD_SOURCES_LINE = "                 $(XMP_DIR)/src/mix_all.c \\\n"
NEW_SOURCES_LINE = "                 $(XMP_DIR)/src/mix_all.c \\\n                 $(XMP_DIR)/src/mix_paula.c \\\n"

OLD_BACKEND_LINE = "   xmp_set_player(g_ctx, XMP_PLAYER_MIX, XMP_STEREO_MIX);\n"
NEW_BACKEND_LINE = (
    "   xmp_set_player(g_ctx, XMP_PLAYER_MIX, XMP_STEREO_MIX);\n"
    "   xmp_set_player(g_ctx, XMP_PLAYER_FLAGS, XMP_FLAGS_A500);"
    "   /* Mix. Paula: emulacao do chip Amiga 500 */\n"
)


def rd(p):
    with open(p, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.read()


def wr(p, s):
    with open(p, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(s)


def fail(msg):
    print("ABORTADO: " + msg)
    sys.exit(1)


def main():
    # 1) arquivos-fonte do Paula precisam existir
    for p in (MIX_PAULA_C, PAULA_H, PRECOMP_BLEP_H):
        if not os.path.isfile(p):
            fail("nao encontrei %s (deps/libxmp parece incompleto)" % p)

    if not os.path.isfile(MAKEFILE):
        fail("nao encontrei %s na raiz do repo" % MAKEFILE)
    if not os.path.isfile(BACKEND):
        fail("nao encontrei %s" % BACKEND)

    makefile_txt = rd(MAKEFILE)
    backend_txt = rd(BACKEND)

    # 2) CFLAGS: precisa ter a linha antiga exatamente 1x, e a nova ainda nao pode existir
    if "LIBXMP_PAULA_SIMULATOR" in makefile_txt:
        fail("Makefile.common ja tem LIBXMP_PAULA_SIMULATOR -- patch parece ja aplicado")
    n = makefile_txt.count(OLD_CFLAGS_LINE)
    if n == 0:
        fail("nao encontrei a linha exata de CFLAGS esperada em %s "
             "(rode: grep -n \"LIBXMP_CORE_PLAYER\" %s e me mande a saida)" % (MAKEFILE, MAKEFILE))
    if n > 1:
        fail("a linha de CFLAGS esperada aparece %d vezes em %s (esperava 1) -- preciso conferir manualmente" % (n, MAKEFILE))

    # 3) SOURCES_C: precisa ter a linha do mix_all.c exatamente 1x, mix_paula.c ainda nao pode existir na lista
    if "mix_paula.c" in makefile_txt:
        fail("Makefile.common ja referencia mix_paula.c -- patch parece ja aplicado")
    n = makefile_txt.count(OLD_SOURCES_LINE)
    if n == 0:
        fail("nao encontrei a linha exata de mix_all.c em SOURCES_C "
             "(rode: grep -n \"mix_all.c\" %s e me mande a saida)" % MAKEFILE)
    if n > 1:
        fail("a linha de mix_all.c aparece %d vezes em %s (esperava 1) -- preciso conferir manualmente" % (n, MAKEFILE))

    # 4) xmp_backend.c: precisa ter a linha exata do XMP_PLAYER_MIX 1x, XMP_FLAGS_A500 ainda nao pode existir
    if "XMP_FLAGS_A500" in backend_txt:
        fail("%s ja referencia XMP_FLAGS_A500 -- patch parece ja aplicado" % BACKEND)
    n = backend_txt.count(OLD_BACKEND_LINE)
    if n == 0:
        fail("nao encontrei a linha exata da chamada XMP_PLAYER_MIX em %s "
             "(rode: grep -n \"XMP_PLAYER_MIX\" %s e me mande a saida)" % (BACKEND, BACKEND))
    if n > 1:
        fail("a linha da chamada XMP_PLAYER_MIX aparece %d vezes em %s (esperava 1) -- preciso conferir manualmente" % (n, BACKEND))

    # tudo validado em memoria -- monta as versoes novas
    new_makefile_txt = makefile_txt.replace(OLD_CFLAGS_LINE, NEW_CFLAGS_LINE, 1)
    new_makefile_txt = new_makefile_txt.replace(OLD_SOURCES_LINE, NEW_SOURCES_LINE, 1)
    new_backend_txt = backend_txt.replace(OLD_BACKEND_LINE, NEW_BACKEND_LINE, 1)

    # so grava depois que tudo deu certo em memoria
    wr(MAKEFILE, new_makefile_txt)
    wr(BACKEND, new_backend_txt)

    print("OK: patch do Mix. Paula aplicado com sucesso.")
    print("Alterado: %s (CFLAGS + SOURCES_C)" % MAKEFILE)
    print("Alterado: %s (XMP_FLAGS_A500 apos xmp_start_player)" % BACKEND)
    print("")
    print("Proximo passo: recompilar o core e substituir o .dll/.so de teste.")


if __name__ == "__main__":
    main()
