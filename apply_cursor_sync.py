#!/usr/bin/env python3
"""apply_cursor_sync.py - ao abrir o navegador (SELECT), o cursor agora
comeca sempre na faixa que esta tocando de fato, mesmo que ela tenha sido
trocada com L/R (fora do navegador) ou pelo fim automatico da faixa.

Antes, last_selected_name_/last_browse_dir_ so eram atualizados dentro de
browser_select() (escolha feita de dentro do navegador). Agora sao
atualizados em start_track(), que e chamada por L/R, pelo avanco
automatico de faixa e pelo proprio navegador - entao cobre todos os casos.

Uso (na raiz do repo):  python3 apply_cursor_sync.py
Opcional:               python3 apply_cursor_sync.py --root /caminho/do/repo

Nao altera nenhum arquivo se qualquer ancora nao for encontrada.
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

pc = read("src/player.c")

if "remember_selected" in pc:
    print("Ja aplicado (remember_selected ja existe em player.c). Nada a fazer.")
    sys.exit(0)

# 1) helper que atualiza last_browse_dir_/last_selected_name_ a partir do
#    caminho completo do arquivo dentro do zip (ex: "Jogos/Fase1/track.vgm")
OLD_DECLS = '''static char up_from_name_[300]       = "";  /* nome da pasta de onde saimos ao apertar B (subir um nivel) */'''

NEW_DECLS = '''static char up_from_name_[300]       = "";  /* nome da pasta de onde saimos ao apertar B (subir um nivel) */

/* atualiza last_browse_dir_/last_selected_name_ a partir do caminho completo
   dentro do zip (ex: "Jogos/Fase1/track.vgm"), para o navegador (SELECT)
   sempre abrir mostrando a faixa que esta tocando de fato - nao importa
   se ela mudou por L/R, pelo fim automatico da faixa, ou pelo navegador. */
static void remember_selected(const char *full_name)
{
   const char *slash;
   if (!full_name || !full_name[0])
      return;
   slash = strrchr(full_name, '/');
   if (slash)
   {
      size_t dlen = (size_t)(slash - full_name) + 1;
      if (dlen >= sizeof(last_browse_dir_))
         dlen = sizeof(last_browse_dir_) - 1;
      memcpy(last_browse_dir_, full_name, dlen);
      last_browse_dir_[dlen] = '\\0';
      snprintf(last_selected_name_, sizeof(last_selected_name_), "%s", slash + 1);
   }
   else
   {
      last_browse_dir_[0] = '\\0';
      snprintf(last_selected_name_, sizeof(last_selected_name_), "%s", full_name);
   }
}'''

pc = sub_once(
    pc,
    re.escape(OLD_DECLS),
    lambda m: NEW_DECLS,
    "declaracao de up_from_name_ (topo do navegador em player.c)",
)

# 2) chama o helper sempre que uma faixa comeca a tocar de verdade
OLD_START = '''      file = plist->files[track->file_id];
      prev_fileid = track->file_id;'''

NEW_START = '''      file = plist->files[track->file_id];
      prev_fileid = track->file_id;
      remember_selected(file->name);'''

pc = sub_once(
    pc,
    re.escape(OLD_START),
    lambda m: NEW_START,
    "atribuicao de file/prev_fileid em start_track",
)

write("src/player.c", pc)
print("OK: src/player.c atualizado.")
print("Agora compile: make platform=win -j$(nproc) ... (mesmo comando de sempre)")
