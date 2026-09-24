import os, shutil, sys

def patch(path, fn, expected):
    with open(path) as f:
        lines = f.read().split("\n")
    out, hits = [], {}
    for l in lines:
        out.extend(fn(l, hits))
    for k, v in expected.items():
        if hits.get(k, 0) != v:
            print("ERRO em %s: '%s' encontrado %d vez(es), esperado %d. Nada foi gravado." % (path, k, hits.get(k, 0), v))
            sys.exit(1)
    if not os.path.exists(path + ".bak"):
        shutil.copy(path, path + ".bak")
    with open(path, "w") as f:
        f.write("\n".join(out))
    print("OK:", path, "(backup em %s.bak)" % path)

def fix_libretro(l, hits):
    s = l.strip()
    def hit(k): hits[k] = hits.get(k, 0) + 1
    if s == '#include "player.h"':
        hit("include"); return [l, '#include "spectrum.h"']
    if s == "int i;":
        hit("decl"); return [l, "   short *audio;"]
    if s == "//graphic handling":
        hit("marker")
        return ["   //audio primeiro, para o espectro usar os samples deste frame",
                "   audio = play();",
                "   spectrum_push(audio, 735);",
                "   spectrum_update();",
                "", l]
    if s.startswith("memset(framebuffer->pixel_data"):
        hit("memset"); return ["   spectrum_draw_background(framebuffer);"]
    if s == "draw_ui();":
        hit("drawui"); return [l, "   spectrum_draw_bars(framebuffer);"]
    if s == "audio_batch_cb(play(),735);":
        hit("audio"); return ["   audio_batch_cb(audio,735);"]
    return [l]

def fix_makefile(l, hits):
    if l.strip() == "$(CORE_DIR)/src/graphics.c \\":
        hits["src"] = hits.get("src", 0) + 1
        return [l, l.replace("graphics.c", "spectrum.c")]
    return [l]

patch("src/libretro.c", fix_libretro,
      {"include": 1, "decl": 1, "marker": 1, "memset": 1, "drawui": 1, "audio": 1})
patch("Makefile.common", fix_makefile, {"src": 1})
