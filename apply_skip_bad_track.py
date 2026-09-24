#!/usr/bin/env python3
"""apply_skip_bad_track.py - se um arquivo dentro de um .zip nao carregar
(ex: um .mod que o libxmp rejeita), pula so ele em vez de derrubar a
playlist inteira do zip. Antes, get_playlist_gme_files() abortava tudo
na primeira falha (success=false; break;), entao um unico arquivo
problematico impedia todas as outras faixas validas do mesmo zip de
tocarem.

Uso (na raiz do repo):  python3 apply_skip_bad_track.py
Opcional:               python3 apply_skip_bad_track.py --root /caminho/do/repo

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

if "pulando este arquivo" in plc:
    print("Ja aplicado (mensagem de skip ja existe em playlist.c). Nada a fazer.")
    sys.exit(0)

OLD = '''bool get_playlist_gme_files(const char *path,gme_file_data ***dest_files,int *dest_num_files, int *dest_num_tracks)
{
   int i;
   bool success              = true;
   file_data **files         = NULL;
   gme_file_data **gme_files = NULL;
   int num_files             = 0;
   int num_tracks            = 0;

   if(get_file_data(path,&files,&num_files))
   {
      gme_files = malloc(sizeof(gme_file_data*) * num_files);
      for(i=0;i< num_files;i++)
      {
         gme_files[i] = NULL;
         if(!get_gme_file_data(files[i],&(gme_files[i])))
         {
            success = false;
            break;
         }
         free(files[i]);
         if(gme_files[i]==NULL)
         {
            success = false;
            break;
         }
         num_tracks += gme_files[i]->num_tracks;
      }
      free(files);
   }
   else
      success = false;
   *dest_files = gme_files;
   *dest_num_files = num_files;
   *dest_num_tracks = num_tracks;
   return success;
}'''

NEW = '''bool get_playlist_gme_files(const char *path,gme_file_data ***dest_files,int *dest_num_files, int *dest_num_tracks)
{
   int i, position;
   bool success              = true;
   file_data **files         = NULL;
   gme_file_data **gme_files = NULL;
   int num_files             = 0;
   int num_tracks            = 0;

   if(get_file_data(path,&files,&num_files))
   {
      gme_files = malloc(sizeof(gme_file_data*) * num_files);
      position = 0;
      for(i=0;i< num_files;i++)
      {
         gme_file_data *gfd = NULL;
         if(!get_gme_file_data(files[i],&gfd) || gfd==NULL)
         {
            /* arquivo problematico: pula ele em vez de derrubar o zip inteiro */
            log_cb(RETRO_LOG_ERROR, "[GME] '%s' nao pode ser carregado, pulando este arquivo.\\n", files[i]->name);
            free(files[i]->data);
            free(files[i]->name);
            free(files[i]);
            continue;
         }
         gme_files[position] = gfd;
         num_tracks += gfd->num_tracks;
         position++;
         free(files[i]);
      }
      free(files);
      num_files = position;
      if (num_files > 0)
         gme_files = realloc(gme_files, sizeof(gme_file_data*) * num_files);
      else
      {
         free(gme_files);
         gme_files = NULL;
         success = false;
      }
   }
   else
      success = false;
   *dest_files = gme_files;
   *dest_num_files = num_files;
   *dest_num_tracks = num_tracks;
   return success;
}'''

plc = sub_once(plc, re.escape(OLD), lambda m: NEW, "get_playlist_gme_files (aborta zip inteiro na 1a falha)")

write("src/playlist.c", plc)
print("OK: src/playlist.c atualizado.")
print("Agora compile: make platform=win -j$(nproc) ... (mesmo comando de sempre)")
