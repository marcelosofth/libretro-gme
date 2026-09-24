#!/usr/bin/env python3
import os, re, sys

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

if not os.path.isfile("deps/dr_libs/dr_mp3.h"):
    print("Falta deps/dr_libs/dr_mp3.h (faca o passo 1). Nada foi alterado.")
    sys.exit(1)
if "mp3_backend.h" in rd("src/playlist.c"):
    print("Ja aplicado (playlist.c ja inclui mp3_backend.h). Abortando.")
    sys.exit(1)

# ------------------------------------------------------------ novos arquivos
MP3_H = r'''#ifndef MP3_BACKEND_H
#define MP3_BACKEND_H
#ifdef __cplusplus
extern "C" {
#endif
int  mp3_backend_probe(const unsigned char *data, long size, char *title, int title_len,
                       char *artist, int artist_len, long *duration_ms);
int  mp3_backend_open(const unsigned char *data, long size, long sample_rate);
void mp3_backend_close(void);
int  mp3_backend_render(short *out, int frames);
int  mp3_backend_ended(void);
long mp3_backend_tell_ms(void);
long mp3_backend_tell_samples(void);
#ifdef __cplusplus
}
#endif
#endif
'''

MP3_C = r'''#include <stdlib.h>
#include <string.h>
#include "mp3_backend.h"

#define DR_MP3_NO_STDIO
#define DR_MP3_IMPLEMENTATION
#include "dr_mp3.h"

#define SB_CAP 4096          /* quadros estereo no buffer de decodificacao */

static drmp3  g_mp3;
static int    g_open     = 0;
static int    g_eof      = 0;
static int    g_ended    = 0;
static int    g_count    = 0;        /* quadros validos em g_sbuf */
static long   g_out_rate = 44100;
static long   g_frames   = 0;        /* quadros de saida ja entregues */
static double g_pos      = 0.0;      /* posicao fracionaria em g_sbuf */
static double g_step     = 1.0;      /* taxa da fonte / taxa de saida */
static short  g_sbuf[SB_CAP * 2];
static short  g_tmp[SB_CAP];

/* ------------------------------------------------------------ tags ID3 */

static unsigned long syncsafe(const unsigned char *p)
{
   return ((unsigned long)(p[0] & 0x7F) << 21) | ((unsigned long)(p[1] & 0x7F) << 14) |
          ((unsigned long)(p[2] & 0x7F) << 7)  |  (unsigned long)(p[3] & 0x7F);
}

static unsigned long be32(const unsigned char *p)
{
   return ((unsigned long)p[0] << 24) | ((unsigned long)p[1] << 16) |
          ((unsigned long)p[2] << 8)  |  (unsigned long)p[3];
}

static unsigned long be24(const unsigned char *p)
{
   return ((unsigned long)p[0] << 16) | ((unsigned long)p[1] << 8) | (unsigned long)p[2];
}

/* Latin-1 acentuado (0xC0-0xFF) -> letra base ASCII */
static const char LATIN_MAP[] =
   "AAAAAAACEEEEIIII"
   "DNOOOOOxOUUUUYPs"
   "aaaaaaaceeeeiiii"
   "dnooooo/ouuuuypy";

static void put_cp(char *dst, int *n, int len, unsigned cp)
{
   char c;
   if (*n >= len - 1)
      return;
   if (cp >= 0x20 && cp <= 0x7E)
      c = (char)cp;
   else if (cp >= 0xC0 && cp <= 0xFF)
      c = LATIN_MAP[cp - 0xC0];
   else if (cp >= 0x80)
      c = '?';
   else
      return;
   dst[(*n)++] = c;
}

/* enc: 0 = Latin-1, 1 = UTF-16 com BOM, 2 = UTF-16BE, 3 = UTF-8 */
static void decode_text(const unsigned char *p, unsigned long n, int enc, char *dst, int len)
{
   int out = 0;
   unsigned long i;

   if (!dst || len <= 0)
      return;
   dst[0] = 0;

   if (enc == 1 || enc == 2)
   {
      int be = (enc == 2);
      if (enc == 1 && n >= 2)
      {
         if (p[0] == 0xFE && p[1] == 0xFF)
         {
            be = 1;
            p += 2;
            n -= 2;
         }
         else if (p[0] == 0xFF && p[1] == 0xFE)
         {
            be = 0;
            p += 2;
            n -= 2;
         }
      }
      for (i = 0; i + 1 < n; i += 2)
      {
         unsigned cp = be ? (((unsigned)p[i] << 8) | p[i + 1])
                          : (((unsigned)p[i + 1] << 8) | p[i]);
         if (cp == 0)
            break;
         put_cp(dst, &out, len, cp);
      }
   }
   else
   {
      for (i = 0; i < n && p[i]; i++)
      {
         unsigned cp = p[i];
         if (enc == 3 && cp >= 0xC2 && cp <= 0xDF && i + 1 < n)
         {
            cp = ((cp & 0x1F) << 6) | (p[i + 1] & 0x3F);
            i++;
         }
         else if (enc == 3 && cp >= 0xE0)
         {
            while (i + 1 < n && (p[i + 1] & 0xC0) == 0x80)
               i++;
            cp = 0x2000;
         }
         put_cp(dst, &out, len, cp);
      }
   }
   while (out > 0 && dst[out - 1] == ' ')
      out--;
   dst[out] = 0;
}

static void id3_read(const unsigned char *d, long size, char *title, int tlen, char *artist, int alen)
{
   if (title && tlen > 0)
      title[0] = 0;
   if (artist && alen > 0)
      artist[0] = 0;

   if (size >= 10 && d[0] == 'I' && d[1] == 'D' && d[2] == '3' && d[3] >= 2 && d[3] <= 4)
   {
      int ver = d[3];
      int hdr = (ver == 2) ? 6 : 10;
      unsigned long end = 10 + syncsafe(d + 6);
      unsigned long pos = 10;

      if (end > (unsigned long)size)
         end = (unsigned long)size;
      if (d[5] & 0x40)
      {
         if (ver == 4)
            pos += syncsafe(d + 10);
         else if (ver == 3)
            pos += 4 + be32(d + 10);
      }
      while (pos + hdr <= end)
      {
         const unsigned char *f = d + pos;
         unsigned long fsize;
         int is_title, is_artist;

         if (f[0] == 0)
            break;
         if (ver == 2)
            fsize = be24(f + 3);
         else if (ver == 3)
            fsize = be32(f + 4);
         else
            fsize = syncsafe(f + 4);
         if (fsize == 0 || pos + hdr + fsize > end)
            break;

         if (ver == 2)
         {
            is_title  = (memcmp(f, "TT2", 3) == 0);
            is_artist = (memcmp(f, "TP1", 3) == 0);
         }
         else
         {
            is_title  = (memcmp(f, "TIT2", 4) == 0);
            is_artist = (memcmp(f, "TPE1", 4) == 0);
         }
         if (is_title && title && !title[0])
            decode_text(f + hdr + 1, fsize - 1, f[hdr], title, tlen);
         if (is_artist && artist && !artist[0])
            decode_text(f + hdr + 1, fsize - 1, f[hdr], artist, alen);
         pos += hdr + fsize;
      }
   }

   /* ID3v1 no fim do arquivo, so se o v2 nao trouxe o campo */
   if (size >= 128 && memcmp(d + size - 128, "TAG", 3) == 0)
   {
      const unsigned char *t = d + size - 128;
      if (title && !title[0])
         decode_text(t + 3, 30, 0, title, tlen);
      if (artist && !artist[0])
         decode_text(t + 33, 30, 0, artist, alen);
   }
}

/* ------------------------------------------------------------ backend */

int mp3_backend_probe(const unsigned char *data, long size, char *title, int title_len,
                      char *artist, int artist_len, long *duration_ms)
{
   drmp3 mp3;
   drmp3_uint64 frames;

   if (duration_ms)
      *duration_ms = 0;
   if (!drmp3_init_memory(&mp3, data, (size_t)size, NULL))
      return -1;
   if (mp3.sampleRate == 0 || (mp3.channels != 1 && mp3.channels != 2))
   {
      drmp3_uninit(&mp3);
      return -1;
   }
   if (duration_ms)
   {
      frames = drmp3_get_pcm_frame_count(&mp3);
      *duration_ms = (long)((frames * 1000ULL) / mp3.sampleRate);
   }
   drmp3_uninit(&mp3);
   id3_read(data, size, title, title_len, artist, artist_len);
   return 0;
}

void mp3_backend_close(void)
{
   if (g_open)
      drmp3_uninit(&g_mp3);
   g_open   = 0;
   g_eof    = 0;
   g_ended  = 0;
   g_count  = 0;
   g_frames = 0;
   g_pos    = 0.0;
}

/* data precisa continuar valido enquanto tocar (fica no playlist) */
int mp3_backend_open(const unsigned char *data, long size, long sample_rate)
{
   mp3_backend_close();
   if (!drmp3_init_memory(&g_mp3, data, (size_t)size, NULL))
      return -1;
   if (g_mp3.sampleRate == 0 || (g_mp3.channels != 1 && g_mp3.channels != 2))
   {
      drmp3_uninit(&g_mp3);
      return -1;
   }
   g_open     = 1;
   g_out_rate = sample_rate > 0 ? sample_rate : 44100;
   g_step     = (double)g_mp3.sampleRate / (double)g_out_rate;
   return 0;
}

/* le quadros estereo de 16 bits (mono e duplicado nos dois canais) */
static int read_stereo(short *dst, int max_frames)
{
   int i, got;
   if (g_mp3.channels == 2)
      return (int)drmp3_read_pcm_frames_s16(&g_mp3, (drmp3_uint64)max_frames, dst);
   got = (int)drmp3_read_pcm_frames_s16(&g_mp3, (drmp3_uint64)max_frames, g_tmp);
   for (i = 0; i < got; i++)
   {
      dst[i * 2]     = g_tmp[i];
      dst[i * 2 + 1] = g_tmp[i];
   }
   return got;
}

int mp3_backend_render(short *out, int frames)
{
   int n, i, drop, want, got;
   double frac;
   const short *a, *b;

   if (!g_open || frames <= 0)
      return 0;
   memset(out, 0, (size_t)frames * 2 * sizeof(short));
   if (g_ended)
      return 0;

   for (n = 0; n < frames; n++)
   {
      for (;;)
      {
         i = (int)g_pos;
         if (i + 1 < g_count || g_eof)
            break;
         drop = i < g_count ? i : g_count;
         if (drop > 0)
         {
            memmove(g_sbuf, g_sbuf + drop * 2, (size_t)(g_count - drop) * 2 * sizeof(short));
            g_pos   -= drop;
            g_count -= drop;
         }
         want = SB_CAP - g_count;
         got  = read_stereo(g_sbuf + g_count * 2, want);
         g_count += got;
         if (got < want)
            g_eof = 1;
      }
      i = (int)g_pos;
      if (i + 1 >= g_count)
      {
         g_ended = 1;
         break;
      }
      frac = g_pos - (double)i;
      a = g_sbuf + i * 2;
      b = a + 2;
      out[n * 2]     = (short)(a[0] + (b[0] - a[0]) * frac);
      out[n * 2 + 1] = (short)(a[1] + (b[1] - a[1]) * frac);
      g_pos += g_step;
   }
   g_frames += n;
   return n;
}

int mp3_backend_ended(void)
{
   return g_open && g_ended;
}

long mp3_backend_tell_ms(void)
{
   return g_out_rate > 0 ? (long)(((long long)g_frames * 1000LL) / g_out_rate) : 0;
}

long mp3_backend_tell_samples(void)
{
   return g_frames * 2;
}
'''

# ------------------------------------------------------------ playlist.h
PL_H = apply_edits("src/playlist.h", [
    ("campo is_mp3",
     flex("int is_tracker; } gme_file_data;"),
     "int is_tracker;\n        int is_mp3;\n} gme_file_data;", 1),
    ("decl get_mp3_track_data",
     flex("bool get_tracker_track_data(gme_file_data *gfd, int fileid, gme_track_data **dest_gtd);"),
     "bool get_tracker_track_data(gme_file_data *gfd, int fileid, gme_track_data **dest_gtd);\n"
     "bool get_mp3_track_data(gme_file_data *gfd, int fileid, gme_track_data **dest_gtd);", 1),
])

# ------------------------------------------------------------ playlist.c
PL_LOOP = r'''if (gfd->is_tracker)
          {
             if (get_tracker_track_data(gfd, i, &(pl->tracks[position])))
                position++;
             continue;
          }
          if (gfd->is_mp3)
          {
             if (get_mp3_track_data(gfd, i, &(pl->tracks[position])))
                position++;
             continue;
          }'''

MP3_BRANCH = r'''/* MP3: decodificado pelo dr_mp3, sem GME. Assume a posse do buffer (evita copiar arquivos grandes) */
   if (ext_is(ext, "mp3"))
   {
      char probe_title[64], probe_artist[64];
      long probe_ms = 0;
      if (mp3_backend_probe((const unsigned char*)fd->data, fd->length,
               probe_title, sizeof(probe_title), probe_artist, sizeof(probe_artist), &probe_ms) != 0)
      {
         log_cb(RETRO_LOG_ERROR, "[GME] Error: dr_mp3 nao carregou %s\n", fd->name);
         free(gfd);
         return false;
      }
      gfd->is_mp3     = 1;
      gfd->num_tracks = 1;
      gfd->name       = fd->name;
      gfd->data       = fd->data;
      gfd->length     = fd->length;
      *dest_gfd = gfd;
      return true;
   }

   //check extension to determine player type'''

MP3_TRACKDATA = r'''static char *dup_cstr(const char *s)
{
   char *p = calloc(strlen(s) + 1, sizeof(char));
   if (p)
      strcpy(p, s);
   return p;
}

bool get_mp3_track_data(gme_file_data *gfd, int fileid, gme_track_data **dest_gtd)
{
   char title[64], artist[64];
   long ms = 0;
   const char *base;
   const char *slash;
   char *dot;
   gme_track_data *gtd = malloc(sizeof(gme_track_data));
   if (!gtd)
      return false;

   title[0]  = 0;
   artist[0] = 0;
   mp3_backend_probe((const unsigned char*)gfd->data, gfd->length,
         title, sizeof(title), artist, sizeof(artist), &ms);

   base  = gfd->name;
   slash = strrchr(base, '/');
   if (slash)
      base = slash + 1;
   slash = strrchr(base, '\\');
   if (slash)
      base = slash + 1;

   gtd->file_id      = fileid;
   gtd->track_id     = 0;
   gtd->track_length = ms > 0 ? (int)ms : (int)(3 * 60 * 1000);

   gtd->game_name = dup_cstr(artist[0] ? artist : base);

   if (title[0])
      gtd->track_name = dup_cstr(title);
   else
   {
      gtd->track_name = dup_cstr(base);
      if (gtd->track_name)
      {
         dot = strrchr(gtd->track_name, '.');
         if (dot)
            *dot = 0;
      }
   }
   *dest_gtd = gtd;
   return true;
}

bool cleanup_playlist(playlist *playlist)'''

PL_C = apply_edits("src/playlist.c", [
    ("include mp3",
     flex('#include "xmp_backend.h"'),
     '#include "xmp_backend.h"\n#include "mp3_backend.h"', 1),
    ("loop get_playlist",
     flex("if (gfd->is_tracker) { if (get_tracker_track_data(gfd, i, &(pl->tracks[position]))) position++; continue; }"),
     PL_LOOP, 1),
    ("init is_mp3",
     flex("gfd->is_tracker = 0; gfd->file_type = NULL;"),
     "gfd->is_tracker = 0;\n   gfd->is_mp3     = 0;\n   gfd->file_type  = NULL;", 1),
    ("ramo mp3 em get_gme_file_data",
     re.escape("//check extension to determine player type"),
     MP3_BRANCH, 1),
    ("get_mp3_track_data",
     flex("bool cleanup_playlist(playlist *playlist)"),
     MP3_TRACKDATA, 1),
])

# ------------------------------------------------------------ player.c
P_MP3_START = r'''if (file->is_mp3)
      {
         if (emu)
         {
            gme_delete(emu);
            emu = NULL;
         }
         if (mp3_backend_open((const unsigned char*)file->data, file->length, sample_rate_) == 0)
         {
            use_mp3_    = true;
            is_playing_ = true;
         }
         else
            log_cb(RETRO_LOG_ERROR, "[GME] dr_mp3 falhou ao abrir este MP3.\n");
         detect_chips();
         return;
      }

      if (emu)
         gme_delete (emu);
      emu = gme_new_emu(file->file_type,sample_rate_);'''

P_MP3_PLAY = r'''if (use_mp3_)
      {
         if (mp3_backend_ended())
         {
            if(current_track< (plist->num_tracks-1))
               start_track(++current_track);
            else
               is_playing_ = false;
         }
         else
            mp3_backend_render(audio_buffer, 735);
      }
      else if (use_xmp_)
      {
         if (xmp_backend_ended())'''

PLAYER_C = apply_edits("src/player.c", [
    ("include mp3",
     flex('#include "xmp_backend.h"'),
     '#include "xmp_backend.h"\n#include "mp3_backend.h"', 1),
    ("flag use_mp3_",
     flex("static bool use_xmp_ = false;"),
     "static bool use_xmp_ = false;\nstatic bool use_mp3_ = false;", 1),
    ("is_emu_loaded",
     flex("return (emu != NULL) || use_xmp_;"),
     "return (emu != NULL) || use_xmp_ || use_mp3_;", 1),
    ("close_file e start_track: fecha mp3",
     flex("xmp_backend_close(); use_xmp_ = false; vgm_backend_close();"),
     "mp3_backend_close();\n   use_mp3_ = false;\n   xmp_backend_close();\n   use_xmp_ = false;\n   vgm_backend_close();", 2),
    ("start_track: ramo mp3",
     flex("if (emu) gme_delete (emu); emu = gme_new_emu(file->file_type,sample_rate_);"),
     P_MP3_START, 1),
    ("play: ramo mp3",
     flex("if (use_xmp_) { if (xmp_backend_ended())"),
     P_MP3_PLAY, 1),
    ("track && emu",
     flex("track && (emu || use_xmp_)"),
     "track && (emu || use_xmp_ || use_mp3_)", 3),
    ("tell_ms (parenteses)",
     flex("(use_xmp_ ? xmp_backend_tell_ms() :"),
     "(use_mp3_ ? mp3_backend_tell_ms() : use_xmp_ ? xmp_backend_tell_ms() :", 2),
    ("tell_ms (progresso)",
     flex("elapsed = use_xmp_ ? xmp_backend_tell_ms() :"),
     "elapsed = use_mp3_ ? mp3_backend_tell_ms() : use_xmp_ ? xmp_backend_tell_ms() :", 1),
    ("elapsed_frames",
     flex("if (use_xmp_) return xmp_backend_tell_samples() / 1470;"),
     "if (use_mp3_)\n      return mp3_backend_tell_samples() / 1470;\n"
     "   if (use_xmp_)\n      return xmp_backend_tell_samples() / 1470;", 1),
    ("linha do sistema",
     flex('if (file->is_tracker) sys = "Amiga / Tracker";'),
     'if (file->is_mp3)\n      sys = "Audio Digital";\n'
     '   else if (file->is_tracker)\n      sys = "Amiga / Tracker";', 1),
    ("detect_chips",
     flex("if (file->is_tracker) { const char *dt = strrchr(file->name, '.');"),
     'if (file->is_mp3)\n   {\n      strcpy(chip_text, "MP3");\n      return;\n   }\n\n'
     "   if (file->is_tracker)\n   {\n      const char *dt = strrchr(file->name, '.');", 1),
])

# ------------------------------------------------------------ fileformat.c, libretro.c, Makefile.common
FF_C = apply_edits("src/fileformat.c", [
    ("extensoes no zip",
     flex('"it","IT"'),
     '"it","IT",\n      "mp3","MP3"', 1),
])

LR_C = apply_edits("src/libretro.c", [
    ("valid_extensions",
     re.escape("mod|s3m|xm|it|zip"),
     "mod|s3m|xm|it|mp3|zip", 1),
])

MK_OLD = rd("Makefile.common")
MK = apply_edits("Makefile.common", [
    ("bloco dr_mp3",
     re.escape("# ---- libxmp (MOD/S3M/XM/IT), perfil lite: mesmas fontes e defines da libxmp-lite ----"),
     "# ---- dr_mp3 (decodificador MP3, dominio publico) ----\n"
     "INCFLAGS += -I$(DEPS_DIR)/dr_libs\n"
     "SOURCES_C += $(CORE_DIR)/src/mp3_backend.c\n\n"
     "# ---- libxmp (MOD/S3M/XM/IT), perfil lite: mesmas fontes e defines da libxmp-lite ----", 1),
])

# ------------------------------------------------------------ tudo validado: grava
wr("Makefile.common.pre_mp3", MK_OLD)
wr("Makefile.common", MK)
wr("src/mp3_backend.h", MP3_H)
wr("src/mp3_backend.c", MP3_C)
wr("src/playlist.h", PL_H)
wr("src/playlist.c", PL_C)
wr("src/player.c", PLAYER_C)
wr("src/fileformat.c", FF_C)
wr("src/libretro.c", LR_C)
print("OK: mp3_backend.{h,c} criados; playlist, player, fileformat, libretro e Makefile.common patchados.")
print("Backup do Makefile.common em Makefile.common.pre_mp3.")
