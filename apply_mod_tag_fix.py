#!/usr/bin/env python3
"""apply_mod_tag_fix.py - normaliza a tag 'M!K!' (ProTracker MOD com mais
de 64 patterns) para 'M.K.' antes de processar um .mod. Confirmado por
teste manual: a libxmp desse build rejeita arquivos com a tag 'M!K!' mesmo
sendo dados validos - o layout dos bytes e identico entre as duas tags,
so muda o texto de 4 bytes no offset 1080.

Uso (na raiz do repo):  python3 apply_mod_tag_fix.py
Opcional:               python3 apply_mod_tag_fix.py --root /caminho/do/repo

Nao altera nenhum arquivo se a ancora nao for encontrada.
"""
import os
import re
import sys

ROOT = "."
if "--root" in sys.argv:
    ROOT = sys.argv[sys.argv.index("--root") + 1]

def read(rel):
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8", newline="") as f:
        return f.read()

def write(rel, content):
    with open(os.path.join(ROOT, rel), "w", encoding="utf-8", newline="") as f:
        f.write(content)

def sub_once(text, pattern, repl, label):
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        print(f"ERRO: ancora '{label}' encontrada {len(matches)} vez(es), esperado 1")
        sys.exit(1)
    return text[:matches[0].start()] + repl(matches[0]) + text[matches[0].end():]

plc = read("src/playlist.c")

if "normalize_mod_tag" in plc:
    print("Ja aplicado (normalize_mod_tag ja existe em playlist.c). Nada a fazer.")
    sys.exit(0)

# 1) helper que troca a tag, logo apos is_tracker_ext()
OLD_DECL = '''static int is_tracker_ext(const char *e)
{
   return ext_is(e, "mod") || ext_is(e, "s3m") || ext_is(e, "xm") || ext_is(e, "it");
}'''

NEW_DECL = '''static int is_tracker_ext(const char *e)
{
   return ext_is(e, "mod") || ext_is(e, "s3m") || ext_is(e, "xm") || ext_is(e, "it");
}

/* Alguns builds da libxmp tratam a tag 'M!K!' (ProTracker com mais de 64
   patterns) de forma mais rigorosa que a 'M.K.' padrao e acabam rejeitando
   o modulo, mesmo com dados validos no mesmo layout de 4 canais. Troca
   so os 4 bytes da tag (offset 1080) antes de processar o arquivo - o
   restante dos dados nao muda. */
static void normalize_mod_tag(char *data, int length)
{
   if (length >= 1084 && memcmp(data + 1080, "M!K!", 4) == 0)
      memcpy(data + 1080, "M.K.", 4);
}'''

plc = sub_once(plc, re.escape(OLD_DECL), lambda m: NEW_DECL,
               "definicao de is_tracker_ext (para inserir normalize_mod_tag)")

# 2) chama o helper antes do probe, so para .mod
OLD_PROBE = '''   /* MOD/S3M/XM/IT: nao passa pelo GME, so valida com a libxmp */
   if (is_tracker_ext(ext))
   {
      char probe_name[64];
      long probe_ms = 0;
      if (xmp_backend_probe((const unsigned char*)fd->data, fd->length,'''

NEW_PROBE = '''   /* MOD/S3M/XM/IT: nao passa pelo GME, so valida com a libxmp */
   if (is_tracker_ext(ext))
   {
      char probe_name[64];
      long probe_ms = 0;
      if (ext_is(ext, "mod"))
         normalize_mod_tag(fd->data, fd->length);
      if (xmp_backend_probe((const unsigned char*)fd->data, fd->length,'''

plc = sub_once(plc, re.escape(OLD_PROBE), lambda m: NEW_PROBE,
               "bloco de probe do tracker (is_tracker_ext) em get_gme_file_data")

write("src/playlist.c", plc)
print("OK: src/playlist.c atualizado.")
print("Agora compile: make platform=win -j$(nproc) ... (mesmo comando de sempre)")
