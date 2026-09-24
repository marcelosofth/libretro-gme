#!/usr/bin/env python3
import hashlib, os, re, sys

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

def find_rom(names):
    for d in SEARCH:
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return None

ctl_path = find_rom(CTL_NAMES)
pcm_path = find_rom(PCM_NAMES)
if not ctl_path or not pcm_path:
    print("Faltam as ROMs. Coloque MT32_CONTROL.ROM e MT32_PCM.ROM em deps/mt32rom/ e rode de novo.")
    sys.exit(1)

with open(ctl_path, "rb") as f:
    ctl = f.read()
with open(pcm_path, "rb") as f:
    pcm = f.read()
if len(ctl) != 65536:
    print("%s tem %d bytes; esperado 65536. Abortando." % (ctl_path, len(ctl)))
    sys.exit(1)
if len(pcm) not in (524288, 1048576):
    print("%s tem %d bytes; esperado 524288 ou 1048576. Abortando." % (pcm_path, len(pcm)))
    sys.exit(1)
ctl_sha1 = hashlib.sha1(ctl).hexdigest()
pcm_sha1 = hashlib.sha1(pcm).hexdigest()

hdr_path = MUNT + "/c_interface/c_interface.h"
typ_path = MUNT + "/c_interface/c_types.h"
if not os.path.isfile(hdr_path):
    print("Falta %s. Abortando." % hdr_path)
    sys.exit(1)
hdr = rd(hdr_path)
typ = rd(typ_path) if os.path.isfile(typ_path) else ""

m = re.search(r"\bmt32emu_add_rom_data\s*\(\s*(mt32emu_context[^)]*)\)\s*;", hdr, flags=re.S)
if not m:
    print("c_interface.h sem mt32emu_add_rom_data. Abortando.")
    sys.exit(1)
params = [" ".join(p.split()) for p in m.group(1).split(",")]
mode = None
if len(params) == 4 and "*" in params[3]:
    if "mt32emu_sha1_digest" in params[3] and re.search(r"typedef\s+char\s+mt32emu_sha1_digest\s*\[", hdr + typ):
        mode = "digest"
    elif re.search(r"\bchar\b", params[3]):
        mode = "string"
if mode is None:
    print("Nao reconheci a assinatura de mt32emu_add_rom_data. Abortando.")
    sys.exit(1)

def as_array(name, data):
    rows = []
    for i in range(0, len(data), 64):
        rows.append('"' + "".join("\\x%02x" % b for b in data[i:i + 64]) + '"')
    return "static const unsigned char %s[] =\n%s;\n" % (name, "\n".join(rows))

parts = [
    "/* gerado por gen_mt32_inc.py: ROMs do Roland MT-32 (uso pessoal; nao publique este arquivo) */\n",
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

wr(INC, "".join(parts))
print("OK: %s criado (control %d bytes, PCM %d bytes)." % (INC, len(ctl), len(pcm)))
print("Assinatura detectada -- modo: %s" % mode)
