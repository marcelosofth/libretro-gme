#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vector>
#include <algorithm>
#include "midi_backend.h"

#define MT32EMU_API_TYPE 1
#include "../deps/munt/mt32emu/src/c_interface/c_interface.h"

#include <ctype.h>
#include <dirent.h>
#define TSF_IMPLEMENTATION
#include "../deps/tsf/tsf.h"
#include "gm_soundfont.inc"
#include "mt32_roms.inc"

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
static tsf            *g_tsf    = NULL;     /* sintese GM (SoundFont) da faixa atual */
static tsf            *g_sf_master = NULL;  /* SoundFont carregado uma vez, compartilhado entre as faixas */
static char            g_sf_path[700] = "";
static int             g_gm     = 0;        /* 1 = o ultimo MIDI aberto e General MIDI */
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
   if (g_tsf)
   {
      tsf_close(g_tsf);
      g_tsf = NULL;
   }
   delete g_song;
   g_song   = NULL;
   g_idx    = 0;
   g_pos    = 0;
   g_tail   = 0;
   g_ended  = 0;
}

/* ------------------------------------------------------------ MIDI comum (General MIDI) via SoundFont */

enum { MIDI_MODE_MT32 = 0, MIDI_MODE_GM = 1 };

/* Decide se o arquivo foi feito para MT-32 ou e um MIDI comum (GM/GS/XG):
   1) SysEx da Roland com modelo 0x16 (MT-32/CM-32L)       => MT-32
   2) SysEx de GM On / GM2 On, GS ou XG                    => GM
   3) sem SysEx identificador: o MT-32 usa por padrao so os canais 2 a 10;
      nota no canal 1 ou nos canais 11-16 => GM, senao => MT-32 */
static int classify(const MidiSong &s)
{
   bool gm_mark = false;
   bool outside = false;
   size_t i;

   for (i = 0; i < s.ev.size(); i++)
   {
      const MidiEvent &e = s.ev[i];
      if (e.kind == 1)
      {
         const unsigned char *p = &s.sysex[0] + e.a;
         unsigned long n = e.b;
         if (n >= 5 && p[1] == 0x41 && p[3] == 0x16)
            return MIDI_MODE_MT32;
         if ((n >= 6 && p[1] == 0x7E && p[3] == 0x09) ||   /* GM / GM2 On */
             (n >= 5 && p[1] == 0x41 && p[3] == 0x42) ||   /* Roland GS */
             (n >= 5 && p[1] == 0x43 && p[3] == 0x4C))     /* Yamaha XG */
            gm_mark = true;
      }
      else if (e.kind == 0)
      {
         unsigned st = (unsigned)(e.a & 0xFF);
         if ((st & 0xF0) == 0x90 && ((e.a >> 16) & 0x7F))
         {
            unsigned ch = st & 0x0F;
            if (ch == 0 || ch >= 10)
               outside = true;
         }
      }
   }
   return (gm_mark || outside) ? MIDI_MODE_GM : MIDI_MODE_MT32;
}

static bool ends_sf2(const char *n)
{
   size_t l = strlen(n);
   return l > 4 && n[l - 4] == '.' &&
          tolower((unsigned char)n[l - 3]) == 's' &&
          tolower((unsigned char)n[l - 2]) == 'f' &&
          n[l - 1] == '2';
}

/* procura um .sf2 no diretorio de sistema (e em soundfonts/, soundfont/, sf2/);
   nomes conhecidos primeiro (gm.sf2 tem prioridade), depois qualquer .sf2 */
static bool find_sf2(const char *dir, char *out, size_t len)
{
   static const char *subdirs[] = { "", "soundfonts/", "soundfont/", "SoundFonts/", "sf2/" };
   static const char *names[] = {
      "gm.sf2", "GM.sf2", "soundfont.sf2", "SoundFont.sf2", "default.sf2",
      "GeneralUser GS.sf2", "GeneralUser-GS.sf2", "TimGM6mb.sf2", "FluidR3_GM.sf2"
   };
   char path[700];
   size_t s, n;

   for (s = 0; s < sizeof(subdirs) / sizeof(subdirs[0]); s++)
      for (n = 0; n < sizeof(names) / sizeof(names[0]); n++)
      {
         snprintf(path, sizeof(path), "%s/%s%s", dir, subdirs[s], names[n]);
         if (file_exists(path))
         {
            snprintf(out, len, "%s", path);
            return true;
         }
      }

   for (s = 0; s < sizeof(subdirs) / sizeof(subdirs[0]); s++)
   {
      DIR *d;
      struct dirent *de;
      snprintf(path, sizeof(path), "%s/%s", dir, subdirs[s]);
      d = opendir(path);
      if (!d)
         continue;
      while ((de = readdir(d)) != NULL)
      {
         if (ends_sf2(de->d_name))
         {
            snprintf(out, len, "%s%s", path, de->d_name);
            closedir(d);
            return true;
         }
      }
      closedir(d);
   }
   return false;
}

static void gm_channels(void)
{
   int ch;
   for (ch = 0; ch < 16; ch++)
      tsf_channel_set_presetnumber(g_tsf, ch, 0, ch == 9);   /* canal 10 = bateria */
}

static void gm_reset(void)
{
   tsf_reset(g_tsf);
   gm_channels();
}

#define GM_EMBEDDED_KEY "<embutido>"

static int open_gm(const char *sysdir)
{
   char sf[700];
   bool external;

   sf[0] = 0;
   /* um .sf2 no diretorio de sistema tem prioridade; sem ele usa o TimGM6mb embutido no core */
   external = sysdir && sysdir[0] && find_sf2(sysdir, sf, sizeof(sf));

   /* o SoundFont e carregado uma vez e compartilhado entre as faixas (tsf_copy) */
   if (!g_sf_master || strcmp(g_sf_path, external ? sf : GM_EMBEDDED_KEY) != 0)
   {
      tsf *fresh = NULL;
      const char *key = GM_EMBEDDED_KEY;

      if (external)
      {
         fresh = tsf_load_filename(sf);
         if (fresh)
            key = sf;
      }
      if (!fresh)
         fresh = tsf_load_memory(gm_sf2_data, (int)GM_SF2_SIZE);
      if (!fresh)
      {
         midi_backend_close();
         return -6;
      }
      if (g_sf_master)
         tsf_close(g_sf_master);
      g_sf_master = fresh;
      snprintf(g_sf_path, sizeof(g_sf_path), "%s", key);
   }

   g_tsf = tsf_copy(g_sf_master);
   if (!g_tsf)
   {
      midi_backend_close();
      return -6;
   }
   tsf_set_output(g_tsf, TSF_STEREO_INTERLEAVED, (int)g_rate, 0.0f);
   gm_channels();
   g_opened = 1;
   return 0;
}

static void gm_deliver(const MidiEvent &e)
{
   if (e.kind == 0)
   {
      unsigned st = (unsigned)(e.a & 0xFF);
      int ch = (int)(st & 0x0F);
      int d1 = (int)((e.a >> 8) & 0x7F);
      int d2 = (int)((e.a >> 16) & 0x7F);

      switch (st & 0xF0)
      {
         case 0x80:
            tsf_channel_note_off(g_tsf, ch, d1);
            break;
         case 0x90:
            if (d2)
               tsf_channel_note_on(g_tsf, ch, d1, (float)d2 / 127.0f);
            else
               tsf_channel_note_off(g_tsf, ch, d1);
            break;
         case 0xB0:
            tsf_channel_midi_control(g_tsf, ch, d1, d2);
            break;
         case 0xC0:
            tsf_channel_set_presetnumber(g_tsf, ch, d1, ch == 9);
            break;
         case 0xE0:
            tsf_channel_set_pitchwheel(g_tsf, ch, d1 | (d2 << 7));
            break;
         default:
            break;
      }
   }
   else if (e.kind == 1)
   {
      const unsigned char *p = &g_song->sysex[0] + e.a;
      unsigned long n = e.b;
      if ((n >= 6 && p[1] == 0x7E && p[3] == 0x09 && (p[4] == 0x01 || p[4] == 0x03)) ||        /* GM / GM2 On */
          (n >= 9 && p[1] == 0x41 && p[3] == 0x42 && p[4] == 0x12 &&
           p[5] == 0x40 && p[6] == 0x00 && p[7] == 0x7F))                                      /* GS Reset */
         gm_reset();
   }
}

static int synth_active(void)
{
   if (g_tsf)
      return tsf_active_voice_count(g_tsf) > 0;
   return mt32emu_is_active(g_ctx) ? 1 : 0;
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
   bool external;

   midi_backend_close();

   g_song = new MidiSong();
   if (!parse_smf(data, size, *g_song))
   {
      midi_backend_close();
      return -1;
   }
   g_rate = sample_rate > 0 ? sample_rate : 44100;
   schedule(*g_song, g_rate);

   /* MT-32 (Munt) ou MIDI comum (SoundFont) */
   g_gm = (classify(*g_song) == MIDI_MODE_GM) ? 1 : 0;
   if (g_gm)
      return open_gm(sysdir);

   /* ROMs no diretorio de sistema tem prioridade; sem elas usa as embutidas no core */
   external = sysdir && sysdir[0] && find_roms(sysdir, ctl, sizeof(ctl), pcm, sizeof(pcm));

   memset(&handler, 0, sizeof(handler));
   g_ctx = mt32emu_create_context(handler, NULL);
   if (!g_ctx)
   {
      midi_backend_close();
      return -1;
   }
   if (external && !(mt32emu_add_rom_file(g_ctx, ctl) > 0 && mt32emu_add_rom_file(g_ctx, pcm) > 0))
   {
      /* ROMs externas nao reconhecidas pelo Munt: recomeca com as embutidas */
      mt32emu_free_context(g_ctx);
      g_ctx = mt32emu_create_context(handler, NULL);
      if (!g_ctx)
      {
         midi_backend_close();
         return -1;
      }
      external = false;
   }
   if (!external &&
       !(mt32emu_add_rom_data(g_ctx, mt32_control_rom, MT32_CONTROL_ROM_SIZE, MT32_CONTROL_SHA1_ARG) > 0 &&
         mt32emu_add_rom_data(g_ctx, mt32_pcm_rom, MT32_PCM_ROM_SIZE, MT32_PCM_SHA1_ARG) > 0))
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
   if (g_tsf)
   {
      gm_deliver(e);
      return;
   }

   if (e.kind == 0)
      mt32emu_play_msg_now(g_ctx, (mt32emu_bit32u)e.a);
   else if (e.kind == 1)
      mt32emu_play_sysex_now(g_ctx, &g_song->sysex[0] + e.a, (mt32emu_bit32u)e.b);
   /* kind 2 (tempo) so afeta o agendamento, ja feito em schedule() */
}

extern "C" int midi_backend_render(short *out, int frames)
{
   int n = 0;

   if (!g_opened || !g_song || frames <= 0)
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

      if (g_tsf)
         tsf_render_short(g_tsf, out + (size_t)n * 2, chunk, 0);
      else
         mt32emu_render_bit16s(g_ctx, out + (size_t)n * 2, (mt32emu_bit32u)chunk);
      n     += chunk;
      g_pos += chunk;

      if (g_idx >= g_song->ev.size())
      {
         g_tail += chunk;
         if (g_tail >= (long long)g_rate * MIDI_TAIL_MAX_MS / 1000)
            g_ended = 1;
         else if (g_tail >= (long long)g_rate * MIDI_TAIL_MIN_MS / 1000 && !synth_active())
            g_ended = 1;
         if (g_ended)
            break;
      }
   }
   return n;
}

extern "C" int midi_backend_ended(void)
{
   return g_opened && g_ended;
}

extern "C" long midi_backend_tell_ms(void)
{
   return g_rate > 0 ? (long)((g_pos * 1000LL) / g_rate) : 0;
}

extern "C" int midi_backend_is_gm(void)
{
   return g_gm;
}

extern "C" long midi_backend_tell_samples(void)
{
   return (long)(g_pos * 2);
}
