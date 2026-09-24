#!/usr/bin/env python3
import sys

def patch(path, replacements):
    with open(path, 'r') as f:
        content = f.read()
    for old, new in replacements:
        if content.count(old) != 1:
            print(f"AVISO: ancora nao encontrada (ou nao unica) em {path}:\n{old!r}")
            sys.exit(1)
        content = content.replace(old, new, 1)
    with open(path, 'w') as f:
        f.write(content)
    print(f"OK: {path} patchado.")

patch('src/spectrum.c', [
    (
        '#define BAR_BASE   408',
        '#define BAR_BASE   390'
    ),
])

print("Espectro subido (BAR_BASE 408 -> 390, ~18px de respiro a mais da barra de progresso).")
