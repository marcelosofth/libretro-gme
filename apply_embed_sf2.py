#!/usr/bin/env python3
import hashlib, os, re, sys

CPP = "src/midi_backend.cpp"
INC = "src/gm_soundfont.inc"
SF2 = "deps/tsf/TimGM6mb.sf2"
SF2_SHA256 = "c5378b62028c920cb11e4803327983fee2f2cdff5dc89c708e39da417e51c854"

def rd(p):
    with open(p, encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.read()

def wr(p, s):
    with open(p, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(s)

def flex(s):
    return r"\s+".join(re.escape(t) for t in s.split())

def apply_edits(path, edits):
    txt = rd(path)
    for label, pat, rep, cnt in edits:
        n = len(re.findall(pat, txt, flags=re.S))
        if n != cnt:
            print("FALHOU em %s: '%s' achou %d, esperado %d. Nada foi gravado." % (path, label, n, cnt))
            sys.exit(1)
        txt = re.sub(pat, lambda m, r=rep: r, txt, flags=re.S)
    return txt

# ------------------------------------------------------------ pre-checagens
if not os.path.isfile(CPP):
    print("Falta %s. Rode antes o apply_midi.py e o apply_midi_gm.py. Nada foi alterado." % CPP)
    sys.exit(1)

if "gm_soundfont.inc" in rd(CPP):
    print("Ja aplicado (midi_backend.cpp ja inclui gm_soundfont.inc). Abortando.")
    sys.exit(1)

if not os.path.isfile(SF2):
    print("Falta %s (nada foi alterado). Rode:" % SF2)
    print("  curl -fL -o %s https://github.com/arbruijn/TimGM6mb/raw/master/TimGM6mb.sf2" % SF2)
    print("ou copie para la o seu TimGM6mb.sf2.")
    sys.exit(1)

with open(SF2, "rb") as f:
    data = f.read()
if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"sfbk":
    print("%s nao parece um SoundFont2 valido (cabecalho RIFF/sfbk). Nada foi alterado." % SF2)
    sys.exit(1)
if hashlib.sha256(data).hexdigest() != SF2_SHA256:
    print("AVISO: %s e diferente do TimGM6mb.sf2 que voce testou. Seguindo mesmo assim." % SF2)

# ------------------------------------------------------------ open_gm: externo (se houver) senao embutido
OPEN_NEW = r'''#define GM_EMBEDDED_KEY "<embutido>"

static int open_gm(const char *sysdir)
{
   char sf[700];
   bool external;

   sf[0] = 0;
   /* um .sf2 no diretorio de sistema tem prioridade; sem ele usa o TimGM6mb embutido no core */
   external = sysdir && sysdir[0] && find_sf2(sysdir, sf, sizeof(sf));

   /* o SoundFont e carregado uma vez e compartilhado entre as faixas (tsf_copy) */
   if (!g_sf_master || strcmp(g_sf_path, external ? sf : GM_EMBEDDED_KEY) != 0)
   {
      tsf *fresh = NULL;
      const char *key = GM_EMBEDDED_KEY;

      if (external)
      {
         fresh = tsf_load_filename(sf);
         if (fresh)
            key = sf;
      }
      if (!fresh)
         fresh = tsf_load_memory(gm_sf2_data, (int)GM_SF2_SIZE);
      if (!fresh)
      {
         midi_backend_close();
         return -6;
      }
      if (g_sf_master)
         tsf_close(g_sf_master);
      g_sf_master = fresh;
      snprintf(g_sf_path, sizeof(g_sf_path), "%s", key);
   }'''

CPP_NEW = apply_edits(CPP, [
    ("include do SoundFont embutido",
     flex('#include "../deps/tsf/tsf.h"'),
     '#include "../deps/tsf/tsf.h"\n#include "gm_soundfont.inc"', 1),
    ("open_gm",
     flex("static int open_gm(const char *sysdir) { char sf[700]; "
          "if (!sysdir || !sysdir[0] || !find_sf2(sysdir, sf, sizeof(sf))) { midi_backend_close(); return -5; } "
          "/* o SoundFont e carregado uma vez e compartilhado entre as faixas (tsf_copy) */ "
          "if (!g_sf_master || strcmp(g_sf_path, sf) != 0) { "
          "tsf *fresh = tsf_load_filename(sf); "
          "if (!fresh) { midi_backend_close(); return -6; } "
          "if (g_sf_master) tsf_close(g_sf_master); "
          "g_sf_master = fresh; "
          'snprintf(g_sf_path, sizeof(g_sf_path), "%s", sf); }'),
     OPEN_NEW, 1),
])

# ------------------------------------------------------------ gm_soundfont.inc (bytes como literais de string)
rows = []
for i in range(0, len(data), 64):
    rows.append('"' + "".join("\\x%02x" % b for b in data[i:i + 64]) + '"')
INC_TXT = ("/* gerado por apply_embed_sf2.py a partir de TimGM6mb.sf2 (Tim Brechbill, GPL) */\n"
           "#define GM_SF2_SIZE %d\n"
           "static const unsigned char gm_sf2_data[] =\n" % len(data)) + "\n".join(rows) + ";\n"

# ------------------------------------------------------------ tudo validado: grava
wr(INC, INC_TXT)
wr(CPP, CPP_NEW)
print("OK: %s criado (%d bytes de SoundFont) e open_gm alterado." % (INC, len(data)))
print("O .sf2 externo continua tendo prioridade se existir; sem ele, toca com o embutido.")
