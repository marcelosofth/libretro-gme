#!/usr/bin/env python3
"""apply_font_v2.py - troca a fonte do player pela Raw Pixel Bold (tudo em MAIUSCULA).

Uso (na raiz do repo):  python3 apply_font_v2.py [caminho/graphics.h]
- Faz backup em graphics.h.bak_font_v2
- Substitui so o conteudo em string do bloco `static const surface font`
- Atlas 128x128, 2 bytes/pixel: aceso = \\000\\000, fundo = \\377\\377
- Slots minusculos (a-z) ja contem as letras MAIUSCULAS, entao todo texto sai em caixa alta
"""
import re, sys, shutil

ATLAS_HEX = [
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00c0f02c30c860c0208000000000000c",
    "00c0f06cf8d090c0404060000000000c",
    "00c0a0fccc1090808020606000000018",
    "00c00078f8206000802000f800e00030",
    "00c000fc1c40a8008020006000000060",
    "00800058cc58980040400000800000c0",
    "00c00058f898680020800000c000c0c0",
    "00000000300000000000000080000000",
    "78e078780cfc78f87878000000000078",
    "cce0cccc1cc0cc18ccccc0c0300080cc",
    "cc600c1c7cf8c018dccc000060f8c00c",
    "fc603018ccfcf83078fc0000c0006018",
    "ec60600cfc0ccc60dc0c000060f8c030",
    "cc60e0cc7ccccc60ccccc0c030008020",
    "78f0fc780c7878607878008000000030",
    "00000000000000000000000000000000",
    "7c30f878f8f8f878ccf03cccc0c6cc78",
    "c678ccccccc0c0cccc600cd8c0eeeccc",
    "baccdcc0ccc0c0c0cc600cf0c0fefccc",
    "eaccf8c0ccf8f8dcfc600ce0c0d6dccc",
    "befcccc0ccc0c0cccc608cf0c0c6cccc",
    "c0ccccccccc0c0cccc60ccd8c0c6cccc",
    "7eccf878f8f8c078ccf078ccf8c6cc78",
    "00000000000000000000000000000000",
    "f878f878fcccccc6ccccfce0c0e02000",
    "cccccccc30ccccc6cccc0c80c0205000",
    "ccccccc030ccccc67878188060208800",
    "f8ccf87830ccccd63030308030200000",
    "c0dcdc0c30ccccfe7830608018200000",
    "c078cccc30cc78eecc30c0800c200000",
    "c01ccc78307830c6cc30fce00ce00000",
    "000000000000000000000000000000f8",
    "c030f878f8f8f878ccf03cccc0c6cc78",
    "6078ccccccc0c0cccc600cd8c0eeeccc",
    "00ccdcc0ccc0c0c0cc600cf0c0fefccc",
    "00ccf8c0ccf8f8dcfc600ce0c0d6dccc",
    "00fcccc0ccc0c0cccc608cf0c0c6cccc",
    "00ccccccccc0c0cccc60ccd8c0c6cccc",
    "00ccf878f8f8c078ccf078ccf8c6cc78",
    "00000000000000000000000000000000",
    "f878f878fcccccc6ccccfc3080c00000",
    "cccccccc30ccccc6cccc0c2080400000",
    "ccccccc030ccccc67878182080406800",
    "f8ccf87830ccccd6303030c08030b000",
    "c0dcdc0c30ccccfe7830602080400000",
    "c078cccc30cc78eecc30c02080400000",
    "c01ccc78307830c6cc30fc3080c00000",
    "00000000000000000000000080000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
    "00000000000000000000000000000000",
]

def build_bytes():
    out = bytearray()
    for h in ATLAS_HEX:
        bits = bin(int(h, 16))[2:].zfill(128)
        for b in bits:
            out += b"\x00\x00" if b == "1" else b"\xff\xff"
    assert len(out) == 128 * 128 * 2
    return bytes(out)

def decode_c_literals(region):
    """Decodifica literais C adjacentes ("..." "...") em bytes."""
    out = bytearray()
    simple = {"n": 10, "t": 9, "r": 13, "\\": 92, '"': 34, "'": 39, "a": 7, "b": 8, "f": 12, "v": 11}
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', region, re.S):
        s = m.group(1); i = 0
        while i < len(s):
            c = s[i]
            if c != "\\":
                out.append(ord(c)); i += 1; continue
            i += 1; c = s[i]
            if c in "01234567":
                j = i
                while j < len(s) and j < i + 3 and s[j] in "01234567": j += 1
                out.append(int(s[i:j], 8) & 255); i = j
            elif c == "x":
                j = i + 1
                while j < len(s) and s[j] in "0123456789abcdefABCDEF": j += 1
                out.append(int(s[i+1:j], 16) & 255); i = j
            else:
                out.append(simple[c]); i += 1
    return bytes(out)

def encode_block(data, indent="  "):
    lines = []
    for y in range(128):
        row = data[y*256:(y+1)*256]
        lines.append(indent + '"' + "".join("\\%03o" % b for b in row) + '"')
    return "\n".join(lines)

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "graphics.h"
    src = open(path, encoding="utf-8", errors="surrogateescape").read()
    m = re.search(r"static\s+const\s+surface\s+font\b", src)
    if not m:
        sys.exit("ERRO: nao achei 'static const surface font' em " + path)
    end = src.index(";", m.end())          # fim do bloco (strings nao contem ';')
    block = src[m.start():end]
    q1 = block.index('"'); q2 = block.rindex('"')
    old_region = block[q1:q2 + 1]
    old = decode_c_literals(old_region)
    print("bytes na fonte atual:", len(old))
    if len(old) not in (128*128*2, 128*128*2 + 1):
        sys.exit("ERRO: tamanho inesperado (%d) - abortei sem alterar nada. Mande o bloco da fonte." % len(old))
    new = build_bytes()
    new_region = encode_block(new).lstrip()
    new_block = block[:q1] + new_region + block[q2 + 1:]
    out = src[:m.start()] + new_block + src[end:]
    # verificacao: reler e comparar
    m2 = re.search(r"static\s+const\s+surface\s+font\b", out)
    b2 = out[m2.start():out.index(";", m2.end())]
    chk = decode_c_literals(b2[b2.index('"'):b2.rindex('"') + 1])
    assert chk == new, "verificacao falhou"
    shutil.copyfile(path, path + ".bak_font_v2")
    open(path, "w", encoding="utf-8", errors="surrogateescape").write(out)
    print("OK: fonte substituida em", path, "(backup:", path + ".bak_font_v2)")

if __name__ == "__main__":
    main()
