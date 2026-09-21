#!/usr/bin/env python3
import hashlib, os, re, sys

CPP = "src/midi_backend.cpp"
INC = "src/mt32_roms.inc"
MUNT = "deps/munt/mt32emu/src"
CTL_NAMES = ["MT32_CONTROL.ROM", "mt32_control.rom"]
PCM_NAMES = ["MT32_PCM.ROM", "mt32_pcm.rom"]
SEARCH = [".", "deps/mt32rom"]

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

def find_rom(names):
    for d in SEARCH:
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return None

# ------------------------------------------------------------ pre-checagens
if not os.path.isfile(CPP):
    print("Falta %s. Rode antes o apply_midi.py, o apply_midi_gm.py e o apply_embed_sf2.py. Nada foi alterado." % CPP)
    sys.exit(1)

cpp_txt = rd(CPP)
if "mt32_roms.inc" in cpp_txt:
    print("Ja aplicado (midi_backend.cpp ja inclui mt32_roms.inc). Abortando.")
    sys.exit(1)
if "gm_soundfont.inc" not in cpp_txt:
    print("O midi_backend.cpp nao inclui gm_soundfont.inc: rode antes o apply_embed_sf2.py. Nada foi alterado.")
    sys.exit(1)

ctl_path = find_rom(CTL_NAMES)
pcm_path = find_rom(PCM_NAMES)
if not ctl_path or not pcm_path:
    print("Faltam as ROMs (nada foi alterado). Copie MT32_CONTROL.ROM e MT32_PCM.ROM para a raiz do repo")
    print("(arraste para o Explorer do Codespace) ou para deps/mt32rom/ e rode de novo.")
    sys.exit(1)

with open(ctl_path, "rb") as f:
    ctl = f.read()
with open(pcm_path, "rb") as f:
    pcm = f.read()
if len(ctl) != 65536:
    print("%s tem %d bytes; o esperado para a control ROM completa e 65536. Nada foi alterado." % (ctl_path, len(ctl)))
    sys.exit(1)
if len(pcm) not in (524288, 1048576):
    print("%s tem %d bytes; o esperado para a PCM ROM e 524288 (MT-32) ou 1048576 (CM-32L). Nada foi alterado." % (pcm_path, len(pcm)))
    sys.exit(1)
ctl_sha1 = hashlib.sha1(ctl).hexdigest()
pcm_sha1 = hashlib.sha1(pcm).hexdigest()

# ------------------------------------------------------------ API do Munt: como passar a ROM da memoria
hdr_path = MUNT + "/c_interface/c_interface.h"
typ_path = MUNT + "/c_interface/c_types.h"
if not os.path.isfile(hdr_path):
    print("Falta %s. Nada foi alterado." % hdr_path)
    sys.exit(1)
hdr = rd(hdr_path)
typ = rd(typ_path) if os.path.isfile(typ_path) else ""

m = re.search(r"\bmt32emu_add_rom_data\s*\(\s*(mt32emu_context[^)]*)\)\s*;", hdr, flags=re.S)
if not m:
    print("O c_interface.h do seu Munt nao tem mt32emu_add_rom_data (nada foi alterado).")
    print("Cole a saida de:  grep -n 'rom' %s | head -60" % hdr_path)
    sys.exit(1)
params = [" ".join(p.split()) for p in m.group(1).split(",")]
proto = "mt32emu_add_rom_data(%s)" % ", ".join(params)
mode = None
if len(params) == 4 and "*" in params[3]:
    if "mt32emu_sha1_digest" in params[3] and re.search(r"typedef\s+char\s+mt32emu_sha1_digest\s*\[", hdr + typ):
        mode = "digest"      # const mt32emu_sha1_digest *
    elif re.search(r"\bchar\b", params[3]):
        mode = "string"      # const char *
if mode is None:
    print("Nao reconheci a assinatura: %s (nada foi alterado)." % proto)
    print("Cole a saida de:  grep -n 'sha1' %s/c_interface/c_interface.h %s/c_interface/c_types.h" % (MUNT, MUNT))
    sys.exit(1)

# ------------------------------------------------------------ midi_backend_open: externas primeiro, senao embutidas
OPEN_ROMS_B = r'''if (external && !(mt32emu_add_rom_file(g_ctx, ctl) > 0 && mt32emu_add_rom_file(g_ctx, pcm) > 0))
   {
      /* ROMs externas nao reconhecidas pelo Munt: recomeca com as embutidas */
      mt32emu_free_context(g_ctx);
      g_ctx = mt32emu_create_context(handler, NULL);
      if (!g_ctx)
      {
         midi_backend_close();
         return -1;
      }
      external = false;
   }
   if (!external &&
       !(mt32emu_add_rom_data(g_ctx, mt32_control_rom, MT32_CONTROL_ROM_SIZE, MT32_CONTROL_SHA1_ARG) > 0 &&
         mt32emu_add_rom_data(g_ctx, mt32_pcm_rom, MT32_PCM_ROM_SIZE, MT32_PCM_SHA1_ARG) > 0))
   {
      midi_backend_close();
      return -3;
   }'''

CPP_NEW = apply_edits(CPP, [
    ("include das ROMs embutidas",
     flex('#include "gm_soundfont.inc"'),
     '#include "gm_soundfont.inc"\n#include "mt32_roms.inc"', 1),
    ("variavel external",
     flex("mt32emu_report_handler_i handler;"),
     "mt32emu_report_handler_i handler;\n   bool external;", 1),
    ("procura ROMs externas",
     flex("if (!sysdir || !sysdir[0] || !find_roms(sysdir, ctl, sizeof(ctl), pcm, sizeof(pcm))) "
          "{ midi_backend_close(); return -2; }"),
     "/* ROMs no diretorio de sistema tem prioridade; sem elas usa as embutidas no core */\n"
     "   external = sysdir && sysdir[0] && find_roms(sysdir, ctl, sizeof(ctl), pcm, sizeof(pcm));", 1),
    ("carrega ROMs",
     flex("if (mt32emu_add_rom_file(g_ctx, ctl) <= 0 || mt32emu_add_rom_file(g_ctx, pcm) <= 0) "
          "{ midi_backend_close(); return -3; }"),
     OPEN_ROMS_B, 1),
])

# ------------------------------------------------------------ mt32_roms.inc
def as_array(name, data):
    rows = []
    for i in range(0, len(data), 64):
        rows.append('"' + "".join("\\x%02x" % b for b in data[i:i + 64]) + '"')
    return "static const unsigned char %s[] =\n%s;\n" % (name, "\n".join(rows))

parts = [
    "/* gerado por apply_embed_mt32.py: ROMs do Roland MT-32 (uso pessoal; nao publique este arquivo) */\n",
    "#define MT32_CONTROL_ROM_SIZE %d\n" % len(ctl),
    "#define MT32_PCM_ROM_SIZE %d\n" % len(pcm),
]
if mode == "digest":
    parts.append('static const mt32emu_sha1_digest mt32_control_sha1 = "%s";\n' % ctl_sha1)
    parts.append('static const mt32emu_sha1_digest mt32_pcm_sha1 = "%s";\n' % pcm_sha1)
    parts.append("#define MT32_CONTROL_SHA1_ARG (&mt32_control_sha1)\n#define MT32_PCM_SHA1_ARG (&mt32_pcm_sha1)\n")
else:
    parts.append('static const char mt32_control_sha1[] = "%s";\n' % ctl_sha1)
    parts.append('static const char mt32_pcm_sha1[] = "%s";\n' % pcm_sha1)
    parts.append("#define MT32_CONTROL_SHA1_ARG mt32_control_sha1\n#define MT32_PCM_SHA1_ARG mt32_pcm_sha1\n")
parts.append(as_array("mt32_control_rom", ctl))
parts.append(as_array("mt32_pcm_rom", pcm))
INC_TXT = "".join(parts)

# ------------------------------------------------------------ .gitignore (as ROMs sao da Roland: nao devem ir para um repo publico)
GI = ".gitignore"
gi_txt = rd(GI) if os.path.isfile(GI) else ""
gi_lines = [l.strip() for l in gi_txt.splitlines()]
GI_ADD = [p for p in ("src/mt32_roms.inc", "deps/mt32rom/", "MT32_CONTROL.ROM", "MT32_PCM.ROM") if p not in gi_lines]
GI_NEW = gi_txt
if GI_ADD:
    if GI_NEW and not GI_NEW.endswith("\n"):
        GI_NEW += "\n"
    GI_NEW += "\n".join(GI_ADD) + "\n"

# ------------------------------------------------------------ tudo validado: grava
wr(INC, INC_TXT)
wr(CPP, CPP_NEW)
if GI_ADD:
    wr(GI, GI_NEW)
print("OK: %s criado (control %d bytes, PCM %d bytes) e midi_backend_open alterado." % (INC, len(ctl), len(pcm)))
print("Assinatura usada: %s  (modo: %s)" % (proto, mode))
print("ROMs em bios/system continuam tendo prioridade; sem elas, toca com as embutidas.")
if GI_ADD:
    print(".gitignore atualizado: %s" % ", ".join(GI_ADD))
