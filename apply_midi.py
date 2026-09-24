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

MUNT = "deps/munt/mt32emu/src"

# ------------------------------------------------------------ pre-checagens
if "midi_backend.h" in rd("src/playlist.c"):
    print("Ja aplicado (playlist.c ja inclui midi_backend.h). Abortando.")
    sys.exit(1)

SRC = ["Analog", "BReverbModel", "Display", "File", "FileStream", "LA32FloatWaveGenerator",
       "LA32Ramp", "LA32WaveGenerator", "MidiStreamParser", "Part", "Partial", "PartialManager",
       "Poly", "ROMInfo", "SampleRateConverter", "Synth", "TVA", "TVF", "TVP", "Tables",
       "c_interface/c_interface", "sha1/sha1", "srchelper/InternalResampler",
       "srchelper/srctools/src/FIRResampler", "srchelper/srctools/src/IIR2xResampler",
       "srchelper/srctools/src/LinearResampler", "srchelper/srctools/src/ResamplerModel",
       "srchelper/srctools/src/SincResampler"]
missing = [s for s in SRC if not os.path.isfile("%s/%s.cpp" % (MUNT, s))]
if missing:
    print("Faltam estes arquivos do Munt (nada foi alterado):")
    for m in missing:
        print("   %s/%s.cpp" % (MUNT, m))
    sys.exit(1)

hdr = rd(MUNT + "/c_interface/c_interface.h")
API = ["mt32emu_create_context", "mt32emu_free_context", "mt32emu_add_rom_file",
       "mt32emu_open_synth", "mt32emu_close_synth", "mt32emu_set_stereo_output_samplerate",
       "mt32emu_get_actual_stereo_output_samplerate", "mt32emu_render_bit16s",
       "mt32emu_play_msg_now", "mt32emu_play_sysex_now", "mt32emu_is_active"]
bad = [f for f in API if not re.search(r"\b%s\s*\(" % f, hdr)]
for tok in ["MT32EMU_RC_OK", "mt32emu_report_handler_i"]:
    if tok not in hdr:
        bad.append(tok)
if bad:
    print("O c_interface.h do seu Munt nao tem estes nomes (nada foi alterado):")
    for b in bad:
        print("   " + b)
    print("Cole a saida de:  grep -n 'mt32emu_' %s/c_interface/c_interface.h | head -150" % MUNT)
    sys.exit(1)

# versao do Munt (so informativa no config.h)
ver = (2, 7, 0)
try:
    m = re.search(r"VERSION\s+(\d+)\.(\d+)\.(\d+)", rd("deps/munt/mt32emu/CMakeLists.txt"))
    if m:
        ver = tuple(int(x) for x in m.groups())
except Exception:
    pass

CONFIG_H = '''#ifndef MT32EMU_CONFIG_H
#define MT32EMU_CONFIG_H

/* gerado por apply_midi.py: equivalente ao config.h.in do Munt para build estatico (C e C++) */
#define MT32EMU_VERSION       "%d.%d.%d"
#define MT32EMU_VERSION_MAJOR %d
#define MT32EMU_VERSION_MINOR %d
#define MT32EMU_VERSION_PATCH %d

#define MT32EMU_EXPORTS_TYPE 3
#define MT32EMU_WITH_VERSION_TAGGING 0
#undef MT32EMU_RUNTIME_VERSION_CHECK

#endif /* #ifndef MT32EMU_CONFIG_H */
''' % (ver[0], ver[1], ver[2], ver[0], ver[1], ver[2])

# ------------------------------------------------------------ novos arquivos
MIDI_H = r'''#ifndef MIDI_BACKEND_H
#define MIDI_BACKEND_H
#ifdef __cplusplus
extern "C" {
#endif
int  midi_backend_probe(const unsigned char *data, long size, char *title, int title_len, long *duration_ms);
/* retorna 0 = ok, -1 = erro, -2 = ROMs nao encontradas, -3 = ROMs invalidas, -4 = sem conversao de taxa */
int  midi_backend_open(const unsigned char *data, long size, long sample_rate, const char *sysdir);
void midi_backend_close(void);
int  midi_backend_render(short *out, int frames);
int  midi_backend_ended(void);
long midi_backend_tell_ms(void);
long midi_backend_tell_samples(void);
#ifdef __cplusplus
}
#endif
#endif
'''

MIDI_CPP = r'''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vector>
#include <algorithm>
#include "midi_backend.h"

#define MT32EMU_API_TYPE 1
#include "../deps/munt/mt32emu/src/c_interface/c_interface.h"

#define MIDI_TAIL_MIN_MS      500     /* espera minima depois do ultimo evento */
#define MIDI_TAIL_MAX_MS      6000    /* teto da cauda (notas presas, reverb longo) */
#define MIDI_TAIL_ESTIMATE_MS 2000    /* usado so na duracao da barra de progresso */

/* ------------------------------------------------------------ leitor de SMF */

struct MidiEvent
{
   unsigned long long tick;
   long long          frame;
   unsigned long      a;      /* curta: mensagem empacotada; sysex: offset; tempo: us por quarto */
   unsigned long      b;      /* sysex: tamanho */
   unsigned char      kind;   /* 0 = curta, 1 = sysex, 2 = tempo */
};

static bool ev_before(const MidiEvent &x, const MidiEvent &y)
{
   return x.tick < y.tick;
}

struct MidiSong
{
   std::vector<MidiEvent>     ev;
   std::vector<unsigned char> sysex;
   int    division;
   double smpte_us;
   char   title[64];
   MidiSong() : division(480), smpte_us(0.0) { title[0] = 0; }
};

static unsigned long rd_be32(const unsigned char *p)
{
   return ((unsigned long)p[0] << 24) | ((unsigned long)p[1] << 16) |
          ((unsigned long)p[2] << 8)  |  (unsigned long)p[3];
}

static unsigned long rd_le32(const unsigned char *p)
{
   return ((unsigned long)p[3] << 24) | ((unsigned long)p[2] << 16) |
          ((unsigned long)p[1] << 8)  |  (unsigned long)p[0];
}

static int rd_be16(const unsigned char *p)
{
   return (p[0] << 8) | p[1];
}

static bool read_vlq(const unsigned char *&p, const unsigned char *end, unsigned long &v)
{
   int i;
   v = 0;
   for (i = 0; i < 4; i++)
   {
      unsigned char b;
      if (p >= end)
         return false;
      b = *p++;
      v = (v << 7) | (b & 0x7F);
      if (!(b & 0x80))
         return true;
   }
   return false;
}

/* Latin-1 acentuado (0xC0-0xFF) -> letra base ASCII (a fonte do player so tem ASCII) */
static const char LATIN_MAP[] =
   "AAAAAAACEEEEIIII"
   "DNOOOOOxOUUUUYPs"
   "aaaaaaaceeeeiiii"
   "dnooooo/ouuuuypy";

static void copy_title(const unsigned char *src, unsigned long n, char *dst, int len)
{
   int out = 0;
   unsigned long i;
   for (i = 0; i < n && out < len - 1; i++)
   {
      unsigned c = src[i];
      if (c == 0)
         break;
      if (c >= 0x20 && c <= 0x7E)
         dst[out++] = (char)c;
      else if (c >= 0xC0)
         dst[out++] = LATIN_MAP[c - 0xC0];
      else
         dst[out++] = ' ';
   }
   while (out > 0 && dst[out - 1] == ' ')
      out--;
   dst[out] = 0;
}

static void add_ev(MidiSong &s, unsigned long long tick, int kind, unsigned long a, unsigned long b)
{
   MidiEvent e;
   e.tick  = tick;
   e.frame = 0;
   e.a     = a;
   e.b     = b;
   e.kind  = (unsigned char)kind;
   s.ev.push_back(e);
}

static void parse_track(const unsigned char *p, const unsigned char *end, MidiSong &s, bool first)
{
   unsigned long long tick = 0;
   unsigned char running = 0;

   while (p < end)
   {
      unsigned long delta, len;
      unsigned char st;
      int n;
      unsigned long msg;

      if (!read_vlq(p, end, delta))
         return;
      tick += delta;
      if (p >= end)
         return;

      st = *p;
      if (st == 0xFF)                        /* meta */
      {
         unsigned char type;
         p++;
         if (p >= end)
            return;
         type = *p++;
         if (!read_vlq(p, end, len) || (unsigned long)(end - p) < len)
            return;
         if (type == 0x2F)
            return;
         if (type == 0x51 && len == 3)
            add_ev(s, tick, 2, ((unsigned long)p[0] << 16) | ((unsigned long)p[1] << 8) | p[2], 0);
         else if (type == 0x03 && first && !s.title[0])
            copy_title(p, len, s.title, (int)sizeof(s.title));
         p += len;
         running = 0;
         continue;
      }
      if (st == 0xF0 || st == 0xF7)          /* sysex */
      {
         p++;
         if (!read_vlq(p, end, len) || (unsigned long)(end - p) < len)
            return;
         if (st == 0xF0)
         {
            unsigned long off = (unsigned long)s.sysex.size();
            s.sysex.push_back(0xF0);
            s.sysex.insert(s.sysex.end(), p, p + len);
            add_ev(s, tick, 1, off, len + 1);
         }
         p += len;
         running = 0;
         continue;
      }
      if (st >= 0xF1)                        /* mensagens de sistema nao existem em SMF */
         return;
      if (st & 0x80)
      {
         running = st;
         p++;
      }
      else if (!running)
         return;

      st = running;
      n  = ((st & 0xF0) == 0xC0 || (st & 0xF0) == 0xD0) ? 1 : 2;
      if (end - p < n)
         return;
      msg = (unsigned long)st | ((unsigned long)p[0] << 8);
      if (n == 2)
         msg |= (unsigned long)p[1] << 16;
      p += n;
      add_ev(s, tick, 0, msg, 0);
   }
}

static bool parse_smf(const unsigned char *d, long size, MidiSong &s)
{
   const unsigned char *p   = d;
   const unsigned char *end = d + size;
   unsigned long hlen;
   int ntrks, div, t;

   if (size < 14)
      return false;

   /* .rmi: SMF dentro de um envelope RIFF */
   if (size >= 20 && !memcmp(p, "RIFF", 4) && !memcmp(p + 8, "RMID", 4))
   {
      const unsigned char *q = p + 12;
      while (end - q >= 8)
      {
         unsigned long cl = rd_le32(q + 4);
         if ((unsigned long)(end - q) < 8 + cl)
            break;
         if (!memcmp(q, "data", 4))
         {
            p   = q + 8;
            end = p + cl;
            break;
         }
         q += 8 + cl + (cl & 1);
      }
   }

   if (end - p < 14 || memcmp(p, "MThd", 4) != 0)
      return false;
   hlen = rd_be32(p + 4);
   if (hlen < 6 || (unsigned long)(end - p) < 8 + hlen)
      return false;
   ntrks = rd_be16(p + 10);
   div   = rd_be16(p + 12);
   if (div == 0)
      return false;

   if (div & 0x8000)                         /* tempo em SMPTE */
   {
      int fps = 256 - (div >> 8);
      int tpf = div & 0xFF;
      double rate;
      if (fps <= 0 || tpf == 0)
         return false;
      rate = (fps == 29) ? 29.97 : (double)fps;
      s.smpte_us = 1000000.0 / (rate * (double)tpf);
      s.division = 0;
   }
   else
   {
      s.division = div;
      s.smpte_us = 0.0;
   }

   p += 8 + hlen;
   t = 0;
   while (t < ntrks && end - p >= 8)
   {
      const unsigned char *chunk = p;
      unsigned long clen = rd_be32(chunk + 4);
      const unsigned char *tp = chunk + 8;
      const unsigned char *tend = ((unsigned long)(end - tp) < clen) ? end : tp + clen;
      p = tend;
      if (memcmp(chunk, "MTrk", 4) != 0)
         continue;
      parse_track(tp, tend, s, t == 0);
      t++;
   }
   return !s.ev.empty();
}

/* ordena (estavel: empates ficam na ordem das trilhas) e converte ticks em quadros de saida */
static void schedule(MidiSong &s, long rate)
{
   double tempo = 500000.0;                  /* us por quarto (120 BPM) */
   double t_us  = 0.0;
   unsigned long long last = 0;
   size_t i;

   std::stable_sort(s.ev.begin(), s.ev.end(), ev_before);
   for (i = 0; i < s.ev.size(); i++)
   {
      MidiEvent &e = s.ev[i];
      double upt = s.division > 0 ? tempo / (double)s.division : s.smpte_us;
      t_us += (double)(e.tick - last) * upt;
      last  = e.tick;
      e.frame = (long long)(t_us * (double)rate / 1000000.0 + 0.5);
      if (e.kind == 2 && e.a > 0 && s.division > 0)
         tempo = (double)e.a;
   }
}

extern "C" int midi_backend_probe(const unsigned char *data, long size, char *title, int title_len, long *duration_ms)
{
   MidiSong s;
   if (title && title_len > 0)
      title[0] = 0;
   if (duration_ms)
      *duration_ms = 0;
   if (!parse_smf(data, size, s))
      return -1;
   schedule(s, 1000);
   if (duration_ms)
      *duration_ms = (long)(s.ev.back().frame + MIDI_TAIL_ESTIMATE_MS);
   if (title && title_len > 0)
   {
      strncpy(title, s.title, (size_t)title_len - 1);
      title[title_len - 1] = 0;
   }
   return 0;
}

/* ------------------------------------------------------------ sintese (Munt) */

static mt32emu_context g_ctx    = NULL;
static int             g_opened = 0;
static MidiSong       *g_song   = NULL;
static size_t          g_idx    = 0;
static long long       g_pos    = 0;      /* quadros de saida ja renderizados */
static long long       g_tail   = 0;
static int             g_ended  = 0;
static long            g_rate   = 44100;

static bool file_exists(const char *path)
{
   FILE *f = fopen(path, "rb");
   if (!f)
      return false;
   fclose(f);
   return true;
}

static bool find_roms(const char *dir, char *ctl, size_t cl, char *pcm, size_t pl)
{
   static const char *subdirs[] = { "", "mt32/", "MT32/" };
   static const char *names[][2] = {
      { "MT32_CONTROL.ROM",  "MT32_PCM.ROM"  },
      { "mt32_control.rom",  "mt32_pcm.rom"  },
      { "CM32L_CONTROL.ROM", "CM32L_PCM.ROM" },
      { "cm32l_control.rom", "cm32l_pcm.rom" }
   };
   size_t s, n;
   for (s = 0; s < sizeof(subdirs) / sizeof(subdirs[0]); s++)
      for (n = 0; n < sizeof(names) / sizeof(names[0]); n++)
      {
         snprintf(ctl, cl, "%s/%s%s", dir, subdirs[s], names[n][0]);
         snprintf(pcm, pl, "%s/%s%s", dir, subdirs[s], names[n][1]);
         if (file_exists(ctl) && file_exists(pcm))
            return true;
      }
   return false;
}

extern "C" void midi_backend_close(void)
{
   if (g_ctx)
   {
      if (g_opened)
         mt32emu_close_synth(g_ctx);
      mt32emu_free_context(g_ctx);
   }
   g_ctx    = NULL;
   g_opened = 0;
   delete g_song;
   g_song   = NULL;
   g_idx    = 0;
   g_pos    = 0;
   g_tail   = 0;
   g_ended  = 0;
}

static bool rate_ok(void)
{
   double actual = (double)mt32emu_get_actual_stereo_output_samplerate(g_ctx);
   return actual > (double)g_rate - 1.0 && actual < (double)g_rate + 1.0;
}

extern "C" int midi_backend_open(const unsigned char *data, long size, long sample_rate, const char *sysdir)
{
   char ctl[700], pcm[700];
   mt32emu_report_handler_i handler;

   midi_backend_close();

   if (!sysdir || !sysdir[0] || !find_roms(sysdir, ctl, sizeof(ctl), pcm, sizeof(pcm)))
      return -2;

   g_song = new MidiSong();
   if (!parse_smf(data, size, *g_song))
   {
      midi_backend_close();
      return -1;
   }
   g_rate = sample_rate > 0 ? sample_rate : 44100;
   schedule(*g_song, g_rate);

   memset(&handler, 0, sizeof(handler));
   g_ctx = mt32emu_create_context(handler, NULL);
   if (!g_ctx)
   {
      midi_backend_close();
      return -1;
   }
   if (mt32emu_add_rom_file(g_ctx, ctl) <= 0 || mt32emu_add_rom_file(g_ctx, pcm) <= 0)
   {
      midi_backend_close();
      return -3;
   }

   mt32emu_set_stereo_output_samplerate(g_ctx, (double)g_rate);
   if (mt32emu_open_synth(g_ctx) != MT32EMU_RC_OK)
   {
      midi_backend_close();
      return -3;
   }
   g_opened = 1;

   if (!rate_ok())
   {
      mt32emu_set_stereo_output_samplerate(g_ctx, (double)g_rate);   /* algumas versoes so aplicam apos abrir */
      if (!rate_ok())
      {
         midi_backend_close();
         return -4;
      }
   }
   return 0;
}

static void deliver(const MidiEvent &e)
{
   if (e.kind == 0)
      mt32emu_play_msg_now(g_ctx, (mt32emu_bit32u)e.a);
   else if (e.kind == 1)
      mt32emu_play_sysex_now(g_ctx, &g_song->sysex[0] + e.a, (mt32emu_bit32u)e.b);
   /* kind 2 (tempo) so afeta o agendamento, ja feito em schedule() */
}

extern "C" int midi_backend_render(short *out, int frames)
{
   int n = 0;

   if (!g_ctx || !g_opened || !g_song || frames <= 0)
      return 0;
   memset(out, 0, (size_t)frames * 2 * sizeof(short));
   if (g_ended)
      return 0;

   while (n < frames)
   {
      int chunk = frames - n;

      while (g_idx < g_song->ev.size() && g_song->ev[g_idx].frame <= g_pos)
      {
         deliver(g_song->ev[g_idx]);
         g_idx++;
      }
      if (g_idx < g_song->ev.size())
      {
         long long until = g_song->ev[g_idx].frame - g_pos;
         if (until < chunk)
            chunk = (int)until;
      }
      if (chunk < 1)
         chunk = 1;

      mt32emu_render_bit16s(g_ctx, out + (size_t)n * 2, (mt32emu_bit32u)chunk);
      n     += chunk;
      g_pos += chunk;

      if (g_idx >= g_song->ev.size())
      {
         g_tail += chunk;
         if (g_tail >= (long long)g_rate * MIDI_TAIL_MAX_MS / 1000)
            g_ended = 1;
         else if (g_tail >= (long long)g_rate * MIDI_TAIL_MIN_MS / 1000 && !mt32emu_is_active(g_ctx))
            g_ended = 1;
         if (g_ended)
            break;
      }
   }
   return n;
}

extern "C" int midi_backend_ended(void)
{
   return g_ctx && g_ended;
}

extern "C" long midi_backend_tell_ms(void)
{
   return g_rate > 0 ? (long)((g_pos * 1000LL) / g_rate) : 0;
}

extern "C" long midi_backend_tell_samples(void)
{
   return (long)(g_pos * 2);
}
'''

# ------------------------------------------------------------ playlist.h
PL_H = apply_edits("src/playlist.h", [
    ("campo is_midi",
     flex("int is_mp3; } gme_file_data;"),
     "int is_mp3;\n        int is_midi;\n} gme_file_data;", 1),
    ("decl get_midi_track_data",
     flex("bool get_mp3_track_data(gme_file_data *gfd, int fileid, gme_track_data **dest_gtd);"),
     "bool get_mp3_track_data(gme_file_data *gfd, int fileid, gme_track_data **dest_gtd);\n"
     "bool get_midi_track_data(gme_file_data *gfd, int fileid, gme_track_data **dest_gtd);", 1),
])

# ------------------------------------------------------------ playlist.c
PL_LOOP = r'''if (gfd->is_mp3)
          {
             if (get_mp3_track_data(gfd, i, &(pl->tracks[position])))
                position++;
             continue;
          }
          if (gfd->is_midi)
          {
             if (get_midi_track_data(gfd, i, &(pl->tracks[position])))
                position++;
             continue;
          }'''

MIDI_BRANCH = r'''/* MIDI: valida o SMF aqui; a sintese (Munt/MT-32) so acontece ao tocar e precisa das ROMs */
   if (ext_is(ext, "mid") || ext_is(ext, "midi"))
   {
      char probe_title[64];
      long probe_ms = 0;
      if (midi_backend_probe((const unsigned char*)fd->data, fd->length,
               probe_title, sizeof(probe_title), &probe_ms) != 0)
      {
         log_cb(RETRO_LOG_ERROR, "[GME] Error: arquivo MIDI invalido: %s\n", fd->name);
         free(gfd);
         return false;
      }
      gfd->is_midi    = 1;
      gfd->num_tracks = 1;
      gfd->name       = fd->name;
      gfd->data       = fd->data;
      gfd->length     = fd->length;
      *dest_gfd = gfd;
      return true;
   }

   //check extension to determine player type'''

MIDI_TRACKDATA = r'''bool get_midi_track_data(gme_file_data *gfd, int fileid, gme_track_data **dest_gtd)
{
   char title[64];
   long ms = 0;
   const char *base;
   const char *slash;
   char *dot;
   gme_track_data *gtd = malloc(sizeof(gme_track_data));
   if (!gtd)
      return false;

   title[0] = 0;
   midi_backend_probe((const unsigned char*)gfd->data, gfd->length, title, sizeof(title), &ms);

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
   gtd->game_name    = dup_cstr(base);

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
    ("include midi",
     flex('#include "mp3_backend.h"'),
     '#include "mp3_backend.h"\n#include "midi_backend.h"', 1),
    ("loop get_playlist",
     flex("if (gfd->is_mp3) { if (get_mp3_track_data(gfd, i, &(pl->tracks[position]))) position++; continue; }"),
     PL_LOOP, 1),
    ("init is_midi",
     flex("gfd->is_mp3 = 0; gfd->file_type = NULL;"),
     "gfd->is_mp3     = 0;\n   gfd->is_midi    = 0;\n   gfd->file_type  = NULL;", 1),
    ("ramo midi em get_gme_file_data",
     re.escape("//check extension to determine player type"),
     MIDI_BRANCH, 1),
    ("get_midi_track_data",
     flex("bool cleanup_playlist(playlist *playlist)"),
     MIDI_TRACKDATA, 1),
])

# ------------------------------------------------------------ player.h / player.c
PLAYER_H = apply_edits("src/player.h", [
    ("decl set_system_dir",
     flex("bool open_file(const char *path, long sample_rate);"),
     "bool open_file(const char *path, long sample_rate);\n\nvoid set_system_dir(const char *dir);", 1),
])

P_SYSDIR = r'''void set_system_dir(const char *dir)
{
   snprintf(system_dir_, sizeof(system_dir_), "%s", dir ? dir : "");
}

/* troca o titulo da faixa por uma mensagem de erro visivel na tela */
static void set_track_error(const char *msg)
{
   char *p;
   if (!track)
      return;
   p = (char*)calloc(strlen(msg) + 1, sizeof(char));
   if (!p)
      return;
   strcpy(p, msg);
   free(track->track_name);
   track->track_name = p;
}

bool is_emu_loaded(void)'''

P_MIDI_START = r'''if (file->is_midi)
      {
         int mrc;
         if (emu)
         {
            gme_delete(emu);
            emu = NULL;
         }
         mrc = midi_backend_open((const unsigned char*)file->data, file->length, sample_rate_, system_dir_);
         if (mrc == 0)
         {
            use_midi_   = true;
            is_playing_ = true;
         }
         else if (mrc == -2)
         {
            log_cb(RETRO_LOG_ERROR, "[GME] MT-32: ROMs nao encontradas em '%s' (MT32_CONTROL.ROM + MT32_PCM.ROM).\n", system_dir_);
            set_track_error("MT-32: ROMS NAO ENCONTRADAS");
         }
         else if (mrc == -3)
         {
            log_cb(RETRO_LOG_ERROR, "[GME] MT-32: ROMs nao reconhecidas pelo Munt.\n");
            set_track_error("MT-32: ROMS INVALIDAS");
         }
         else if (mrc == -4)
            log_cb(RETRO_LOG_ERROR, "[GME] MT-32: o Munt nao converteu para %ld Hz.\n", sample_rate_);
         else
            log_cb(RETRO_LOG_ERROR, "[GME] falha ao abrir este MIDI.\n");
         detect_chips();
         return;
      }

      if (file->is_mp3)
      {
         if (emu)
         {'''

P_MIDI_PLAY = r'''if (use_midi_)
      {
         if (midi_backend_ended())
         {
            if(current_track< (plist->num_tracks-1))
               start_track(++current_track);
            else
               is_playing_ = false;
         }
         else
            midi_backend_render(audio_buffer, 735);
      }
      else if (use_mp3_)
      {
         if (mp3_backend_ended())'''

PLAYER_C = apply_edits("src/player.c", [
    ("include midi",
     flex('#include "mp3_backend.h"'),
     '#include "mp3_backend.h"\n#include "midi_backend.h"', 1),
    ("flags use_midi_ e system_dir_",
     flex("static bool use_mp3_ = false;"),
     "static bool use_mp3_ = false;\nstatic bool use_midi_ = false;\nstatic char system_dir_[512];", 1),
    ("set_system_dir antes de is_emu_loaded",
     r"bool\s+is_emu_loaded\s*\(\s*void\s*\)",
     P_SYSDIR, 1),
    ("is_emu_loaded",
     flex("return (emu != NULL) || use_xmp_ || use_mp3_;"),
     "return (emu != NULL) || use_xmp_ || use_mp3_ || use_midi_;", 1),
    ("close_file e start_track: fecha midi",
     flex("mp3_backend_close(); use_mp3_ = false;"),
     "midi_backend_close();\n   use_midi_ = false;\n   mp3_backend_close();\n   use_mp3_ = false;", 2),
    ("start_track: ramo midi",
     flex("if (file->is_mp3) { if (emu) {"),
     P_MIDI_START, 1),
    ("play: ramo midi",
     flex("if (use_mp3_) { if (mp3_backend_ended())"),
     P_MIDI_PLAY, 1),
    ("track && emu",
     flex("track && (emu || use_xmp_ || use_mp3_)"),
     "track && (emu || use_xmp_ || use_mp3_ || use_midi_)", 3),
    ("tell_ms (parenteses)",
     flex("(use_mp3_ ? mp3_backend_tell_ms() :"),
     "(use_midi_ ? midi_backend_tell_ms() : use_mp3_ ? mp3_backend_tell_ms() :", 2),
    ("tell_ms (progresso)",
     flex("elapsed = use_mp3_ ? mp3_backend_tell_ms() :"),
     "elapsed = use_midi_ ? midi_backend_tell_ms() : use_mp3_ ? mp3_backend_tell_ms() :", 1),
    ("elapsed_frames",
     flex("if (use_mp3_) return mp3_backend_tell_samples() / 1470;"),
     "if (use_midi_)\n      return midi_backend_tell_samples() / 1470;\n"
     "   if (use_mp3_)\n      return mp3_backend_tell_samples() / 1470;", 1),
    ("linha do sistema",
     flex('if (file->is_mp3) sys = "Audio Digital";'),
     'if (file->is_midi)\n      sys = "Roland MT-32";\n'
     '   else if (file->is_mp3)\n      sys = "Audio Digital";', 1),
    ("detect_chips",
     flex('if (file->is_mp3) { strcpy(chip_text, "MP3"); return; }'),
     'if (file->is_midi)\n   {\n      strcpy(chip_text, "MT-32");\n      return;\n   }\n\n'
     '   if (file->is_mp3)\n   {\n      strcpy(chip_text, "MP3");\n      return;\n   }', 1),
])

# ------------------------------------------------------------ fileformat.c, libretro.c
FF_C = apply_edits("src/fileformat.c", [
    ("extensoes no zip",
     flex('"mp3","MP3"'),
     '"mp3","MP3",\n      "mid","MID",\n      "midi","MIDI"', 1),
])

LR_C = apply_edits("src/libretro.c", [
    ("valid_extensions",
     re.escape("mod|s3m|xm|it|mp3|zip"),
     "mod|s3m|xm|it|mp3|mid|midi|zip", 1),
    ("diretorio de sistema",
     flex("if (info && open_file(info->path, 44100))"),
     "const char *sysdir = NULL;\n"
     "   if (environ_cb(RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY, &sysdir) && sysdir)\n"
     "      set_system_dir(sysdir);\n"
     "   if (info && open_file(info->path, 44100))", 1),
])

# ------------------------------------------------------------ Makefile.common
MUNT_BLOCK = ("# ---- Munt / mt32emu (emulacao do Roland MT-32), sem dependencias externas ----\n"
              "MUNT_DIR := $(DEPS_DIR)/munt/mt32emu/src\n"
              "CXXFLAGS += -DMT32EMU_WITH_INTERNAL_RESAMPLER -DMT32EMU_WITH_STD_SNPRINTF\n"
              "SOURCES_CXX += $(CORE_DIR)/src/midi_backend.cpp \\\n" +
              " \\\n".join("                $(MUNT_DIR)/%s.cpp" % s for s in SRC) +
              "\n\n"
              "# ---- dr_mp3 (decodificador MP3, dominio publico) ----")

MK_OLD = rd("Makefile.common")
MK = apply_edits("Makefile.common", [
    ("bloco munt",
     re.escape("# ---- dr_mp3 (decodificador MP3, dominio publico) ----"),
     MUNT_BLOCK, 1),
])

# ------------------------------------------------------------ tudo validado: grava
wr("Makefile.common.pre_midi", MK_OLD)
wr("Makefile.common", MK)
wr(MUNT + "/config.h", CONFIG_H)
wr("src/midi_backend.h", MIDI_H)
wr("src/midi_backend.cpp", MIDI_CPP)
wr("src/playlist.h", PL_H)
wr("src/playlist.c", PL_C)
wr("src/player.h", PLAYER_H)
wr("src/player.c", PLAYER_C)
wr("src/fileformat.c", FF_C)
wr("src/libretro.c", LR_C)
print("OK: midi_backend.{h,cpp} e %s/config.h criados; playlist, player, fileformat, libretro e Makefile.common patchados." % MUNT)
print("Backup do Makefile.common em Makefile.common.pre_midi.")
