#!/usr/bin/env python3
import re, sys

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

if "xmp_backend.h" in rd("src/playlist.c"):
    print("Ja aplicado (playlist.c ja inclui xmp_backend.h). Abortando.")
    sys.exit(1)

# ------------------------------------------------------------ novos arquivos
XMP_H = r'''#ifndef XMP_BACKEND_H
#define XMP_BACKEND_H
#ifdef __cplusplus
extern "C" {
#endif
int  xmp_backend_probe(const unsigned char *data, long size, char *name, int name_len, long *duration_ms);
int  xmp_backend_open(const unsigned char *data, long size, long sample_rate);
void xmp_backend_close(void);
int  xmp_backend_render(short *out, int frames);
int  xmp_backend_ended(void);
long xmp_backend_tell_ms(void);
long xmp_backend_tell_samples(void);
#ifdef __cplusplus
}
#endif
#endif
'''

XMP_C = r'''#include <stdlib.h>
#include <string.h>
#include "xmp.h"
#include "xmp_backend.h"

/* separacao estereo: 100 = Amiga puro (canais 100% L/R), menor = mais suave */
#define XMP_STEREO_MIX 70

static xmp_context g_ctx     = NULL;
static int         g_loaded  = 0;
static int         g_started = 0;
static int         g_ended   = 0;
static long        g_rate    = 44100;
static long        g_frames  = 0;

/* so ASCII imprimivel (a fonte do player cobre 0x20-0x7E) */
static void copy_title(const char *src, char *dst, int len)
{
   int i, n = 0;
   if (!dst || len <= 0)
      return;
   for (i = 0; src && src[i] && n < len - 1; i++)
   {
      unsigned char c = (unsigned char)src[i];
      dst[n++] = (c >= 0x20 && c <= 0x7E) ? (char)c : ' ';
   }
   while (n > 0 && dst[n - 1] == ' ')
      n--;
   dst[n] = '\0';
}

int xmp_backend_probe(const unsigned char *data, long size, char *name, int name_len, long *duration_ms)
{
   xmp_context ctx;
   struct xmp_module_info mi;

   if (name && name_len > 0)
      name[0] = '\0';
   if (duration_ms)
      *duration_ms = 0;

   ctx = xmp_create_context();
   if (!ctx)
      return -1;
   if (xmp_load_module_from_memory(ctx, (void *)data, size) < 0)
   {
      xmp_free_context(ctx);
      return -1;
   }
   xmp_get_module_info(ctx, &mi);
   if (mi.mod)
      copy_title(mi.mod->name, name, name_len);
   if (duration_ms && mi.seq_data && mi.num_sequences > 0)
      *duration_ms = mi.seq_data[0].duration;
   xmp_release_module(ctx);
   xmp_free_context(ctx);
   return 0;
}

void xmp_backend_close(void)
{
   if (g_ctx)
   {
      if (g_started)
         xmp_end_player(g_ctx);
      if (g_loaded)
         xmp_release_module(g_ctx);
      xmp_free_context(g_ctx);
   }
   g_ctx     = NULL;
   g_started = 0;
   g_loaded  = 0;
   g_ended   = 0;
   g_frames  = 0;
}

/* data precisa continuar valido enquanto tocar (fica no playlist) */
int xmp_backend_open(const unsigned char *data, long size, long sample_rate)
{
   xmp_backend_close();

   g_ctx = xmp_create_context();
   if (!g_ctx)
      return -1;
   if (xmp_load_module_from_memory(g_ctx, (void *)data, size) < 0)
      goto fail;
   g_loaded = 1;

   g_rate = sample_rate > 0 ? sample_rate : 44100;
   if (xmp_start_player(g_ctx, (int)g_rate, 0) < 0)   /* 0 = 16 bits estereo */
      goto fail;
   g_started = 1;

   xmp_set_player(g_ctx, XMP_PLAYER_MIX, XMP_STEREO_MIX);
   g_frames = 0;
   g_ended  = 0;
   return 0;

fail:
   xmp_backend_close();
   return -1;
}

int xmp_backend_render(short *out, int frames)
{
   int r;
   if (!g_ctx || !g_started || frames <= 0)
      return 0;
   memset(out, 0, (size_t)frames * 2 * sizeof(short));
   if (g_ended)
      return 0;
   r = xmp_play_buffer(g_ctx, out, frames * 4, 0);   /* loop = 0: termina no 1o loop */
   if (r != 0)
      g_ended = 1;
   g_frames += frames;
   return frames;
}

int xmp_backend_ended(void)
{
   return g_ctx && g_ended;
}

long xmp_backend_tell_ms(void)
{
   return g_rate > 0 ? (long)(((long long)g_frames * 1000LL) / g_rate) : 0;
}

long xmp_backend_tell_samples(void)
{
   return g_frames * 2;
}
'''

# ------------------------------------------------------------ playlist.h
PL_H = apply_edits("src/playlist.h", [
    ("campo is_tracker",
     flex("int num_tracks; } gme_file_data;"),
     "int num_tracks;\n        int is_tracker;\n} gme_file_data;", 1),
    ("decl get_tracker_track_data",
     flex("bool get_track_data(Music_Emu* emu, int fileid, int trackid, char *filename, gme_track_data **dest_gtd);"),
     "bool get_track_data(Music_Emu* emu, int fileid, int trackid, char *filename, gme_track_data **dest_gtd);\n"
     "bool get_tracker_track_data(gme_file_data *gfd, int fileid, gme_track_data **dest_gtd);", 1),
])

# ------------------------------------------------------------ playlist.c
TRK_HELPERS = r'''static int ext_is(const char *e, const char *w)
{
   while (*e && *w)
   {
      char c = *e;
      if (c >= 'A' && c <= 'Z')
         c = (char)(c + 32);
      if (c != *w)
         return 0;
      e++;
      w++;
   }
   return *e == *w;
}

static int is_tracker_ext(const char *e)
{
   return ext_is(e, "mod") || ext_is(e, "s3m") || ext_is(e, "xm") || ext_is(e, "it");
}

'''

TRK_BRANCH = r'''gfd->is_tracker = 0;
   gfd->file_type  = NULL;

   /* MOD/S3M/XM/IT: nao passa pelo GME, so valida com a libxmp */
   if (is_tracker_ext(ext))
   {
      char probe_name[64];
      long probe_ms = 0;
      if (xmp_backend_probe((const unsigned char*)fd->data, fd->length,
               probe_name, sizeof(probe_name), &probe_ms) != 0)
      {
         log_cb(RETRO_LOG_ERROR, "[GME] Error: libxmp nao carregou %s\n", fd->name);
         free(gfd);
         return false;
      }
      gfd->is_tracker = 1;
      gfd->num_tracks = 1;
      gfd->name = calloc(strlen(fd->name)+1,sizeof(char));
      strcpy(gfd->name,fd->name);
      gfd->data = malloc(fd->length ? fd->length : 1);
      memcpy(gfd->data,fd->data,fd->length);
      gfd->length = fd->length;
      *dest_gfd = gfd;
      return true;
   }

   //check extension to determine player type'''

TRK_TRACKDATA = r'''bool get_tracker_track_data(gme_file_data *gfd, int fileid, gme_track_data **dest_gtd)
{
   char title[64];
   long ms = 0;
   char *dot;
   gme_track_data *gtd = malloc(sizeof(gme_track_data));
   if (!gtd)
      return false;

   title[0] = '\0';
   xmp_backend_probe((const unsigned char*)gfd->data, gfd->length, title, sizeof(title), &ms);

   gtd->file_id  = fileid;
   gtd->track_id = 0;

   gtd->game_name = calloc(strlen(gfd->name) + 1, sizeof(char));
   strcpy(gtd->game_name, gfd->name);

   gtd->track_length = ms > 0 ? (int)ms : (int)(2.5 * 60 * 1000);

   if (title[0])
   {
      gtd->track_name = calloc(strlen(title) + 1, sizeof(char));
      strcpy(gtd->track_name, title);
   }
   else
   {
      gtd->track_name = calloc(strlen(gfd->name) + 1, sizeof(char));
      strcpy(gtd->track_name, gfd->name);
      dot = strrchr(gtd->track_name, '.');
      if (dot)
         *dot = '\0';
   }
   *dest_gtd = gtd;
   return true;
}

bool cleanup_playlist(playlist *playlist)'''

PL_C = apply_edits("src/playlist.c", [
    ("include xmp",
     flex('#include "playlist.h"'),
     '#include "playlist.h"\n#include "xmp_backend.h"\n#include <stdio.h>', 1),
    ("loop get_playlist",
     flex("gfd = pl->files[i]; temp_emu = gme_new_emu(gfd->file_type,gme_info_only);"),
     "gfd      = pl->files[i];\n"
     "          if (gfd->is_tracker)\n"
     "          {\n"
     "             if (get_tracker_track_data(gfd, i, &(pl->tracks[position])))\n"
     "                position++;\n"
     "             continue;\n"
     "          }\n"
     "          temp_emu = gme_new_emu(gfd->file_type,gme_info_only);", 1),
    ("helpers + assinatura get_gme_file_data",
     flex("bool get_gme_file_data(file_data *fd,gme_file_data **dest_gfd)"),
     TRK_HELPERS + "bool get_gme_file_data(file_data *fd,gme_file_data **dest_gfd)", 1),
    ("ramo tracker em get_gme_file_data",
     re.escape("//check extension to determine player type"),
     TRK_BRANCH, 1),
    ("get_tracker_track_data",
     flex("bool cleanup_playlist(playlist *playlist)"),
     TRK_TRACKDATA, 1),
])

# ------------------------------------------------------------ player.c
P_IS_LOADED = r'''bool is_emu_loaded(void)
{
   return (emu != NULL) || use_xmp_;
}'''

P_CLOSE = r'''void close_file(void)
{
   xmp_backend_close();
   use_xmp_ = false;
   vgm_backend_close();
   use_vgm_ = false;
   gme_delete(emu);
   emu = NULL;
   if(plist!=NULL)
      cleanup_playlist(plist);
   plist = NULL;
   track = NULL;
}'''

P_START = r'''void start_track(int tracknr)
{
   memset(audio_buffer,0,8192 * sizeof(short));
   xmp_backend_close();
   use_xmp_ = false;
   vgm_backend_close();
   use_vgm_ = false;
   current_track = tracknr;
   track = plist->tracks[tracknr];
   if(track)
   {
      is_playing_ = false;
      file = plist->files[track->file_id];
      prev_fileid = track->file_id;

      /* MOD/S3M/XM/IT: o audio vem da libxmp, sem passar pelo GME */
      if (file->is_tracker)
      {
         if (emu)
         {
            gme_delete(emu);
            emu = NULL;
         }
         if (xmp_backend_open((const unsigned char*)file->data, file->length, sample_rate_) == 0)
         {
            use_xmp_    = true;
            is_playing_ = true;
         }
         else
            log_cb(RETRO_LOG_ERROR, "[GME] libxmp falhou ao abrir este modulo.\n");
         detect_chips();
         return;
      }

      if (emu)
         gme_delete (emu);
      emu = gme_new_emu(file->file_type,sample_rate_);
      gme_load_data(emu,file->data,file->length);
      is_playing_ = true;
      detect_chips();

      /* VGM/VGZ: o audio vem da libvgm (todos os chips do VGMPlay) */
      if (file->file_type == gme_vgm_type || file->file_type == gme_vgz_type)
      {
         if (vgm_backend_open((const unsigned char*)file->data, file->length, sample_rate_) == 0)
            use_vgm_ = true;
         else
            log_cb(RETRO_LOG_ERROR, "[GME] libvgm falhou, usando GME para este arquivo.\n");
      }
   }
   else
   {
      log_cb(RETRO_LOG_ERROR, "[GME] Error: Unknown track type.\n" );
      is_playing_ = false;
   }
   if (is_playing_)
      gme_start_track(emu, track->track_id);
}'''

P_PLAY = r'''short *play(void)
{
   if (is_playing_)
   {
      if (use_xmp_)
      {
         if (xmp_backend_ended())
         {
            if(current_track< (plist->num_tracks-1))
               start_track(++current_track);
            else
               is_playing_ = false;
         }
         else
            xmp_backend_render(audio_buffer, 735);
      }
      else if (use_vgm_)
      {
         if (vgm_backend_ended())
         {
            if(current_track< (plist->num_tracks-1))
               start_track(++current_track);
            else
               is_playing_ = false;
         }
         else
            vgm_backend_render(audio_buffer, 735);
      }
      else if(gme_track_ended(emu))
      {
         if(current_track< (plist->num_tracks-1))
            start_track(++current_track);
         else
            is_playing_ = false;
      }
      else
         gme_play( emu, 1470, audio_buffer );
   }
   else
      memset(audio_buffer,0,8192 * sizeof(short));
   return audio_buffer;
}'''

P_CHIPS = r'''d = (const unsigned char*)file->data;

   if (file->is_tracker)
   {
      const char *dt = strrchr(file->name, '.');
      int is_mod = dt && (dt[1]=='m'||dt[1]=='M') && (dt[2]=='o'||dt[2]=='O')
                      && (dt[3]=='d'||dt[3]=='D') && dt[4]=='\0';
      strcpy(chip_text, is_mod ? "PAULA" : "TRACKER");
      return;
   }'''

PLAYER_C = apply_edits("src/player.c", [
    ("include xmp",
     flex('#include "vgm_backend.h"'),
     '#include "vgm_backend.h"\n#include "xmp_backend.h"', 1),
    ("flag use_xmp_",
     flex("static bool use_vgm_ = false;"),
     "static bool use_vgm_ = false;\nstatic bool use_xmp_ = false;", 1),
    ("is_emu_loaded", r"bool\s+is_emu_loaded\s*\(\s*void\s*\)\s*\{.*?\n\}", P_IS_LOADED, 1),
    ("close_file",    r"void\s+close_file\s*\(\s*void\s*\)\s*\{.*?\n\}",    P_CLOSE, 1),
    ("start_track",   r"void\s+start_track\s*\(\s*int\s+tracknr\s*\)\s*\{.*?\n\}", P_START, 1),
    ("play",          r"short\s*\*\s*play\s*\(\s*void\s*\)\s*\{.*?\n\}",    P_PLAY, 1),
    ("track && emu",  re.escape("track && emu"), "track && (emu || use_xmp_)", 3),
    ("tell_ms (parenteses)",
     flex("(use_vgm_ ? vgm_backend_tell_ms() : gme_tell(emu))"),
     "(use_xmp_ ? xmp_backend_tell_ms() : use_vgm_ ? vgm_backend_tell_ms() : gme_tell(emu))", 2),
    ("tell_ms (progresso)",
     flex("elapsed = use_vgm_ ? vgm_backend_tell_ms() : gme_tell(emu);"),
     "elapsed = use_xmp_ ? xmp_backend_tell_ms() : use_vgm_ ? vgm_backend_tell_ms() : gme_tell(emu);", 1),
    ("elapsed_frames",
     flex("if (use_vgm_) return vgm_backend_tell_samples() / 1470;"),
     "if (use_xmp_)\n      return xmp_backend_tell_samples() / 1470;\n"
     "   if (use_vgm_)\n      return vgm_backend_tell_samples() / 1470;", 1),
    ("linha do sistema",
     flex('if (file->file_type == gme_spc_type) sys = "Super Nintendo";'),
     'if (file->is_tracker)\n      sys = "Amiga / Tracker";\n'
     '   else if (file->file_type == gme_spc_type)\n      sys = "Super Nintendo";', 1),
    ("detect_chips",
     flex("d = (const unsigned char*)file->data;"),
     P_CHIPS, 1),
])

# ------------------------------------------------------------ fileformat.c e libretro.c
FF_C = apply_edits("src/fileformat.c", [
    ("extensoes no zip",
     re.escape('"vgz","VGZ"'),
     '"vgz","VGZ",\n      "mod","MOD",\n      "s3m","S3M",\n      "xm","XM",\n      "it","IT"', 1),
])

LR_C = apply_edits("src/libretro.c", [
    ("valid_extensions",
     re.escape("spc|vgm|vgz|zip"),
     "spc|vgm|vgz|mod|s3m|xm|it|zip", 1),
])

# ------------------------------------------------------------ tudo validado: grava
wr("src/xmp_backend.h", XMP_H)
wr("src/xmp_backend.c", XMP_C)
wr("src/playlist.h", PL_H)
wr("src/playlist.c", PL_C)
wr("src/player.c", PLAYER_C)
wr("src/fileformat.c", FF_C)
wr("src/libretro.c", LR_C)
print("OK: xmp_backend.{h,c} criados; playlist.{h,c}, player.c, fileformat.c e libretro.c patchados.")
print("Falta o Makefile.common (libxmp-lite) e compilar.")
