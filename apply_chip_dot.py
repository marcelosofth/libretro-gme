#!/usr/bin/env python3
# Bolinha do CHIP: preta quando nao ha som, vermelha piscando quando toca,
# e brilho branco interno maior (1 pixel -> 2x2).
# Uso (na raiz do repo):  python3 apply_chip_dot.py
import os, shutil, sys

PATH = "src/libretro.c"
BAK  = PATH + ".bak_chipdot"

OLD1 = """   if (t < 48) /* em repouso/fraco: escurece; acima disso fica igual */
   {
      r = 3 + ((r - 3) * t) / 48;
      g = 1 + ((g - 1) * t) / 48;
      b = 1 + ((b - 1) * t) / 48;
   }
   col = get_color(r, g, b);
"""

NEW1 = """   if (t < 48) /* em repouso/fraco: escurece ate o preto; acima disso fica igual */
   {
      r = (r * t) / 48;
      g = (g * t) / 48;
      b = (b * t) / 48;
   }
   if (t < 4) /* sem som: preto */
      col = get_color(0, 0, 0);
   else
      col = get_color(r, g, b);
"""

OLD2 = """   if (t > 200)
      set_pixel(framebuffer, cx - 2, cy - 2, get_color(31, 40, 30));
}
"""

NEW2 = """   if (t > 200) /* brilho branco do LED: 2x2 pixels (antes era 1) */
   {
      unsigned short wh = get_color(31, 40, 30);
      set_pixel(framebuffer, cx - 3, cy - 3, wh);
      set_pixel(framebuffer, cx - 2, cy - 3, wh);
      set_pixel(framebuffer, cx - 3, cy - 2, wh);
      set_pixel(framebuffer, cx - 2, cy - 2, wh);
   }
}
"""

def main():
    if not os.path.isfile(PATH):
        sys.exit("ERRO: %s nao encontrado. Rode na raiz do repo (/workspaces/libretro-gme)." % PATH)
    src = open(PATH, encoding="utf-8").read()

    if "sem som: preto" in src:
        print("Ja aplicado, nada a fazer.")
        return

    for name, old in (("bloco da cor", OLD1), ("brilho branco", OLD2)):
        n = src.count(old)
        if n != 1:
            sys.exit("ERRO: %s encontrado %d vez(es) em %s (esperado 1). Nada foi alterado." % (name, n, PATH))

    shutil.copy2(PATH, BAK)
    src = src.replace(OLD1, NEW1).replace(OLD2, NEW2)
    open(PATH, "w", encoding="utf-8").write(src)
    print("OK: %s atualizado (backup em %s)." % (PATH, BAK))
    print("Agora recompile o core.")

main()
