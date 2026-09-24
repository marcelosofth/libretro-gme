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

# ------------------------------------------------------------ pre-checagens
for f in ["src/midi_backend.cpp", "src/midi_backend.h", "src/player.c"]:
    if not os.path.isfile(f):
        print("Falta %s. Rode antes o apply_midi.py. Nada foi alterado." % f)
        sys.exit(1)

if "tsf.h" in rd("src/midi_backend.cpp"):
    print("Ja aplicado (midi_backend.cpp ja inclui tsf.h). Abortando.")
    sys.exit(1)

if not os.path.isfile("deps/tsf/tsf.h"):
    print("Falta deps/tsf/tsf.h (nada foi alterado). Rode:")
    print("  mkdir -p deps/tsf && curl -fL -o deps/tsf/tsf.h https://github.com/schellingb/TinySoundFont/raw/refs/heads/main/tsf.h")
    sys.exit(1)

hdr = rd("deps/tsf/tsf.h")
NEED = ["tsf_load_filename", "tsf_copy", "tsf_close", "tsf_reset", "tsf_set_output",
        "tsf_render_short", "tsf_active_voice_count", "tsf_channel_note_on",
        "tsf_channel_note_off", "tsf_channel_midi_control",
        "tsf_channel_set_presetnumber", "tsf_channel_set_pitchwheel"]
bad = [f for f in NEED if not re.search(r"\b%s\s*\(" % f, hdr)]
if "TSF_STEREO_INTERLEAVED" not in hdr:
    bad.append("TSF_STEREO_INTERLEAVED")
if bad:
    print("O deps/tsf/tsf.h nao tem estes nomes (nada foi alterado):")
    for b in bad:
        print("   " + b)
    sys.exit(1)

# ------------------------------------------------------------ midi_backend.h
H = apply_edits("src/midi_backend.h", [
    ("codigos de retorno",
     flex("-4 = sem conversao de taxa */"),
     "-4 = sem conversao de taxa, -5 = SoundFont nao encontrado, -6 = SoundFont invalido */", 1),
    ("decl is_gm",
     flex("int  midi_backend_ended(void);"),
     "int  midi_backend_ended(void);\n"
     "int  midi_backend_is_gm(void);   /* 1 = o ultimo .mid aberto e MIDI comum (SoundFont), 0 = MT-32 */", 1),
])

# ------------------------------------------------------------ midi_backend.cpp
GM_BLOCK = r'''/* ------------------------------------------------------------ MIDI comum (General MIDI) via SoundFont */

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

static int open_gm(const char *sysdir)
{
   char sf[700];

   if (!sysdir || !sysdir[0] || !find_sf2(sysdir, sf, sizeof(sf)))
   {
      midi_backend_close();
      return -5;
   }

   /* o SoundFont e carregado uma vez e compartilhado entre as faixas (tsf_copy) */
   if (!g_sf_master || strcmp(g_sf_path, sf) != 0)
   {
      tsf *fresh = tsf_load_filename(sf);
      if (!fresh)
      {
         midi_backend_close();
         return -6;
      }
      if (g_sf_master)
         tsf_close(g_sf_master);
      g_sf_master = fresh;
      snprintf(g_sf_path, sizeof(g_sf_path), "%s", sf);
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

'''

OPEN_HEAD = r'''g_song = new MidiSong();
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

   if (!sysdir || !sysdir[0] || !find_roms(sysdir, ctl, sizeof(ctl), pcm, sizeof(pcm)))
   {
      midi_backend_close();
      return -2;
   }'''

CPP = apply_edits("src/midi_backend.cpp", [
    ("include tsf",
     flex('#include "../deps/munt/mt32emu/src/c_interface/c_interface.h"'),
     '#include "../deps/munt/mt32emu/src/c_interface/c_interface.h"\n\n'
     '#include <ctype.h>\n#include <dirent.h>\n'
     '#define TSF_IMPLEMENTATION\n#include "../deps/tsf/tsf.h"', 1),
    ("globais gm",
     flex("static MidiSong *g_song = NULL;"),
     "static MidiSong       *g_song   = NULL;\n"
     "static tsf            *g_tsf    = NULL;     /* sintese GM (SoundFont) da faixa atual */\n"
     "static tsf            *g_sf_master = NULL;  /* SoundFont carregado uma vez, compartilhado entre as faixas */\n"
     'static char            g_sf_path[700] = "";\n'
     "static int             g_gm     = 0;        /* 1 = o ultimo MIDI aberto e General MIDI */", 1),
    ("close fecha tsf",
     flex("g_ctx = NULL; g_opened = 0; delete g_song;"),
     "g_ctx    = NULL;\n   g_opened = 0;\n   if (g_tsf)\n   {\n      tsf_close(g_tsf);\n      g_tsf = NULL;\n   }\n   delete g_song;", 1),
    ("open: classifica antes das ROMs",
     flex("if (!sysdir || !sysdir[0] || !find_roms(sysdir, ctl, sizeof(ctl), pcm, sizeof(pcm))) return -2; "
          "g_song = new MidiSong(); if (!parse_smf(data, size, *g_song)) { midi_backend_close(); return -1; } "
          "g_rate = sample_rate > 0 ? sample_rate : 44100; schedule(*g_song, g_rate);"),
     OPEN_HEAD, 1),
    ("deliver: ramo gm",
     flex("static void deliver(const MidiEvent &e) {"),
     "static void deliver(const MidiEvent &e)\n{\n   if (g_tsf)\n   {\n      gm_deliver(e);\n      return;\n   }\n", 1),
    ("render: guarda",
     flex("if (!g_ctx || !g_opened || !g_song || frames <= 0)"),
     "if (!g_opened || !g_song || frames <= 0)", 1),
    ("render: chamada",
     flex("mt32emu_render_bit16s(g_ctx, out + (size_t)n * 2, (mt32emu_bit32u)chunk);"),
     "if (g_tsf)\n         tsf_render_short(g_tsf, out + (size_t)n * 2, chunk, 0);\n"
     "      else\n         mt32emu_render_bit16s(g_ctx, out + (size_t)n * 2, (mt32emu_bit32u)chunk);", 1),
    ("render: fim da cauda",
     flex("!mt32emu_is_active(g_ctx)"),
     "!synth_active()", 1),
    ("ended",
     flex("return g_ctx && g_ended;"),
     "return g_opened && g_ended;", 1),
    ("is_gm",
     flex('extern "C" long midi_backend_tell_samples(void) {'),
     'extern "C" int midi_backend_is_gm(void)\n{\n   return g_gm;\n}\n\n'
     'extern "C" long midi_backend_tell_samples(void)\n{', 1),
    ("bloco gm",
     flex("static bool rate_ok(void) {"),
     GM_BLOCK + "static bool rate_ok(void)\n{", 1),
])

# ------------------------------------------------------------ player.c
ERR_BLOCK = r'''else if (mrc == -5)
         {
            log_cb(RETRO_LOG_ERROR, "[GME] MIDI GM: nenhum SoundFont (.sf2) encontrado em '%s'.\n", system_dir_);
            set_track_error("SOUNDFONT GM NAO ENCONTRADO");
         }
         else if (mrc == -6)
         {
            log_cb(RETRO_LOG_ERROR, "[GME] MIDI GM: nao foi possivel carregar o SoundFont.\n");
            set_track_error("SOUNDFONT GM INVALIDO");
         }
         else if (mrc == -4)'''

PLAYER = apply_edits("src/player.c", [
    ("linha do sistema",
     flex('sys = "Roland MT-32";'),
     'sys = midi_backend_is_gm() ? "General MIDI" : "Roland MT-32";', 1),
    ("chip",
     flex('strcpy(chip_text, "MT-32");'),
     'strcpy(chip_text, midi_backend_is_gm() ? "GM" : "MT-32");', 1),
    ("erros de SoundFont",
     flex("else if (mrc == -4)"),
     ERR_BLOCK, 1),
])

# ------------------------------------------------------------ tudo validado: grava
wr("src/midi_backend.h", H)
wr("src/midi_backend.cpp", CPP)
wr("src/player.c", PLAYER)
print("OK: .mid agora e classificado. MT-32 -> Munt; GM/GS/XG (ou canal 1 / 11-16 em uso) -> SoundFont via TinySoundFont.")
print("Coloque um SoundFont GM (.sf2) no diretorio de sistema (ex.: /userdata/bios/ ou system/ do RetroArch). 'gm.sf2' tem prioridade.")
