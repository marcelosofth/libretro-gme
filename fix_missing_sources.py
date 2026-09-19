mk = open('Makefile.common').read()

fixes = [
    # (arquivo que precisa ser adicionado, ancora onde inserir logo apos, linha nova)
    ('$(GME_DIR)/gme/Nes_Vrc7_Apu.cpp', '$(GME_DIR)/gme/Nes_Vrc6_Apu.cpp \\\n',
     '            $(GME_DIR)/gme/Nes_Vrc7_Apu.cpp \\\n'),
    ('$(GME_DIR)/gme/Nes_Fds_Apu.cpp', '$(GME_DIR)/gme/Nes_Vrc6_Apu.cpp \\\n',
     '            $(GME_DIR)/gme/Nes_Fds_Apu.cpp \\\n'),
    ('$(GME_DIR)/gme/Hes_Apu_Adpcm.cpp', '$(GME_DIR)/gme/Hes_Apu.cpp \\\n',
     '            $(GME_DIR)/gme/Hes_Apu_Adpcm.cpp \\\n'),
    ('$(DEPS_DIR)/ymfm/src/ymfm_ssg.cpp', '$(DEPS_DIR)/ymfm/src/ymfm_opn.cpp \\\n',
     '            $(DEPS_DIR)/ymfm/src/ymfm_ssg.cpp \\\n'),
    ('$(DEPS_DIR)/ymfm/src/ymfm_pcm.cpp', '$(DEPS_DIR)/ymfm/src/ymfm_opn.cpp \\\n',
     '            $(DEPS_DIR)/ymfm/src/ymfm_pcm.cpp \\\n'),
]

for check_line, anchor, new_line in fixes:
    if check_line in mk:
        print(f"(ja presente, pulando: {check_line})")
        continue
    if anchor not in mk:
        print(f"AVISO: ancora nao encontrada para {check_line}: {anchor!r}")
        raise SystemExit(1)
    mk = mk.replace(anchor, anchor + new_line, 1)
    print(f"OK: adicionado {check_line}")

open('Makefile.common', 'w').write(mk)
print("Terminado.")
