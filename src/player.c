#include <stdio.h>
#include <string.h>
#include <time.h>
#include <boolean.h>
#include "player.h"
#include "playlist.h"
#include "fileformat.h"
#include "libretro.h"
#include "vgm_backend.h"
#include "xmp_backend.h"
#include "mp3_backend.h"
#include "midi_backend.h"
#include <zlib.h>

extern retro_log_printf_t log_cb;

static playlist *plist = NULL;
static gme_track_data *track = NULL;
static gme_file_data *file = NULL;
static int prev_fileid;
Music_Emu* emu = NULL;
static short audio_buffer[8192];
static bool is_playing_;
static bool use_vgm_ = false;
static bool use_xmp_ = false;
static bool use_mp3_ = false;
static bool use_midi_ = false;
static bool loop_enabled_ = false;
static char system_dir_[512];
static long sample_rate_;
static int current_track;
static void detect_chips(void);

/* ---- avanco rapido (R) / voltar acelerado (L) ---- */

#ifndef SCAN_MULT
#define SCAN_MULT       6        /* velocidade do avanco/volta (3x) */
#endif
#ifndef HIST_SECONDS
#define HIST_SECONDS    60       /* quanto audio recente fica guardado para o "voltar" */
#endif
#define HIST_FRAMES     (44100 * HIST_SECONDS)
#ifndef SEEK_BUDGET_MS
#define SEEK_BUDGET_MS  12       /* tempo maximo por frame gasto reposicionando a musica */
#endif

static short *hist_buf   = NULL; /* audio estereo (2 shorts por frame) */
static long   hist_head  = 0;    /* proximo frame a ser escrito */
static long   hist_count = 0;    /* frames validos no historico */
static long   rw_back_   = 0;    /* quantos frames estamos "voltados" em relacao ao decoder */
static int    seek_active_          = 0;
static int    seek_resume_playing_  = 0;
static long   seek_target_ms_       = 0;
static int    seek_track_           = 0;
static int    internal_restart_     = 0;
static short  scan_out_[1470];   /* 735 frames estereo */

static void hist_reset(void)
{
   hist_head  = 0;
   hist_count = 0;
   rw_back_   = 0;
}

static void hist_free(void)
{
   free(hist_buf);
   hist_buf = NULL;
   hist_reset();
   seek_active_ = 0;
}

static void hist_push(const short *buf, int frames)
{
   int i;
   if (!hist_buf)
      hist_buf = (short*)calloc((size_t)HIST_FRAMES * 2, sizeof(short));
   if (!hist_buf)
      return;
   for (i = 0; i < frames; i++)
   {
      hist_buf[hist_head * 2]     = buf[i * 2];
      hist_buf[hist_head * 2 + 1] = buf[i * 2 + 1];
      if (++hist_head >= HIST_FRAMES)
         hist_head = 0;
   }
   hist_count += frames;
   if (hist_count > HIST_FRAMES)
      hist_count = HIST_FRAMES;
}

/* tempo decorrido REAL do decoder, em ms */
static long raw_elapsed_ms(void)
{
   if (use_midi_) return (long)midi_backend_tell_ms();
   if (use_mp3_)  return (long)mp3_backend_tell_ms();
   if (use_xmp_)  return (long)xmp_backend_tell_ms();
   if (use_vgm_)  return (long)vgm_backend_tell_ms();
   if (emu)       return (long)gme_tell(emu);
   return 0;
}

/* tempo mostrado na tela: o do decoder menos o quanto o "voltar" ja recuou */
static long backend_elapsed_ms(void)
{
   long rate = sample_rate_ > 0 ? sample_rate_ : 44100;
   long ms   = raw_elapsed_ms() - (rw_back_ * 1000L) / rate;
   return ms < 0 ? 0 : ms;
}

void set_system_dir(const char *dir)
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

bool is_emu_loaded(void)
{
   return (emu != NULL) || use_xmp_ || use_mp3_ || use_midi_;
}

bool open_file(const char *path, long sample_rate)
{
   sample_rate_  = sample_rate;
   current_track = 0;
   prev_fileid   = -1;

   if(get_playlist(path,&plist))
   {
      start_track(current_track);
      return true;
   }
   return false;
}

void close_file(void)
{
   hist_free();
   midi_backend_close();
   use_midi_ = false;
   mp3_backend_close();
   use_mp3_ = false;
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
}

void start_track(int tracknr)
{
   hist_reset();
   if (!internal_restart_)
      seek_active_ = 0;
   memset(audio_buffer,0,8192 * sizeof(short));
   midi_backend_close();
   use_midi_ = false;
   mp3_backend_close();
   use_mp3_ = false;
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

      if (file->is_midi)
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
         else if (mrc == -5)
         {
            log_cb(RETRO_LOG_ERROR, "[GME] MIDI GM: nenhum SoundFont (.sf2) encontrado em '%s'.\n", system_dir_);
            set_track_error("SOUNDFONT GM NAO ENCONTRADO");
         }
         else if (mrc == -6)
         {
            log_cb(RETRO_LOG_ERROR, "[GME] MIDI GM: nao foi possivel carregar o SoundFont.\n");
            set_track_error("SOUNDFONT GM INVALIDO");
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
}

short *play(void)
{
   if (is_playing_)
   {
      if (use_midi_)
      {
         if (midi_backend_ended())
         {
            if (loop_enabled_)
               start_track(current_track);
            else if(current_track< (plist->num_tracks-1))
               start_track(++current_track);
            else
               is_playing_ = false;
         }
         else
            midi_backend_render(audio_buffer, 735);
      }
      else if (use_mp3_)
      {
         if (mp3_backend_ended())
         {
            if (loop_enabled_)
               start_track(current_track);
            else if(current_track< (plist->num_tracks-1))
               start_track(++current_track);
            else
               is_playing_ = false;
         }
         else
            mp3_backend_render(audio_buffer, 735);
      }
      else if (use_xmp_)
      {
         if (xmp_backend_ended())
         {
            if (loop_enabled_)
               start_track(current_track);
            else if(current_track< (plist->num_tracks-1))
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
            if (loop_enabled_)
               start_track(current_track);
            else if(current_track< (plist->num_tracks-1))
               start_track(++current_track);
            else
               is_playing_ = false;
         }
         else
            vgm_backend_render(audio_buffer, 735);
      }
      else if(gme_track_ended(emu))
      {
         if (loop_enabled_)
            start_track(current_track);
         else if(current_track< (plist->num_tracks-1))
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
}

/* ---- avanco rapido / voltar acelerado ---- */

/* "voltar": toca o historico de audio de tras pra frente, SCAN_MULT vezes mais rapido */
static void rewind_step(void)
{
   int i, c, k;

   memset(scan_out_, 0, sizeof(scan_out_));
   if (!hist_buf)
      return;

   for (i = 0; i < 735; i++)
   {
      if (rw_back_ + SCAN_MULT > hist_count)
         break;                       /* acabou o historico: fica em silencio */
      for (c = 0; c < 2; c++)
      {
         long sum = 0;
         for (k = 1; k <= SCAN_MULT; k++)
         {
            long idx = hist_head - (rw_back_ + k);
            if (idx < 0)
               idx += HIST_FRAMES;
            sum += hist_buf[idx * 2 + c];
         }
         scan_out_[i * 2 + c] = (short)(sum / SCAN_MULT);
      }
      rw_back_ += SCAN_MULT;
   }
}

/* ao soltar o L: recomeca a faixa e avanca em silencio ate o ponto onde a volta parou */
static void seek_begin(void)
{
   long rate = sample_rate_ > 0 ? sample_rate_ : 44100;
   long target = raw_elapsed_ms() - (rw_back_ * 1000L) / rate;
   if (target < 0)
      target = 0;

   seek_resume_playing_ = is_playing_;
   seek_track_          = current_track;
   seek_target_ms_      = target;

   internal_restart_ = 1;
   start_track(current_track);       /* zera historico e rw_back_ */
   internal_restart_ = 0;

   seek_active_ = is_playing_ ? 1 : 0;
}

static short *seek_step(void)
{
   clock_t t0 = clock();

   while (seek_active_ && raw_elapsed_ms() < seek_target_ms_)
   {
      play();
      if (!seek_active_ || current_track != seek_track_ || !is_playing_)
      {
         seek_active_ = 0;           /* trocou de faixa / acabou: desiste */
         break;
      }
      hist_push(audio_buffer, 735);  /* reconstroi o historico para poder voltar de novo */
      if (((clock() - t0) * 1000) / CLOCKS_PER_SEC >= SEEK_BUDGET_MS)
         break;                      /* continua no proximo frame */
   }

   if (seek_active_ && raw_elapsed_ms() >= seek_target_ms_)
   {
      seek_active_ = 0;
      if (!seek_resume_playing_)
         is_playing_ = false;
   }

   memset(scan_out_, 0, sizeof(scan_out_));
   return scan_out_;
}

short *play_scan(int dir)
{
   static short raw[SCAN_MULT * 1470];
   int i, c, k;

   if (seek_active_)
      return seek_step();

   /* soltou o L depois de voltar: reposiciona a musica */
   if (dir == 0 && rw_back_ > 0)
   {
      seek_begin();
      if (seek_active_)
         return seek_step();
   }

   if (dir < 0 && is_playing_)
   {
      rewind_step();
      return scan_out_;
   }

   if (dir > 0 && is_playing_)
   {
      /* avanco rapido: gera SCAN_MULT frames de video de audio e reduz para 735 amostras */
      for (k = 0; k < SCAN_MULT; k++)
      {
         play();
         memcpy(raw + k * 1470, audio_buffer, 1470 * sizeof(short));
         if (is_playing_)
            hist_push(audio_buffer, 735);
      }
      for (i = 0; i < 735; i++)
         for (c = 0; c < 2; c++)
         {
            long sum = 0;
            for (k = 0; k < SCAN_MULT; k++)
               sum += raw[(i * SCAN_MULT + k) * 2 + c];
            scan_out_[i * 2 + c] = (short)(sum / SCAN_MULT);
         }
      return scan_out_;
   }

   play();
   if (is_playing_)
      hist_push(audio_buffer, 735);
   return audio_buffer;
}

void next_track(void)
{
   if(current_track< (plist->num_tracks-1))
      start_track(++current_track);
}

void prev_track(void)
{
   if(current_track > 0)
      start_track(--current_track);
}

char *get_game_name(char *buf)
{
   if (track)
      sprintf(buf, "%s",track->game_name);
   else
      buf[0] = '\0';
   return buf;
}

char *get_track_count(char *buf)
{
   if (plist)
      sprintf(buf, "%d/%d",current_track+1,plist->num_tracks);
   else
      buf[0] = '\0';
   return buf;
}

char *get_song_name(char *buf)
{
   if (track)
      sprintf(buf, "%s",track->track_name);
   else
      buf[0] = '\0';
   return buf;
}

char *get_track_position(char *buf)
{
   if (track && (emu || use_xmp_ || use_mp3_ || use_midi_)) {
      long seconds         = track->track_length / 1000;
      long elapsed_seconds = (backend_elapsed_ms()) / 1000;
      sprintf(buf, "(%ld:%02ld / %ld:%02ld)",elapsed_seconds/60,elapsed_seconds%60,seconds/60,seconds % 60);
   } else {
      buf[0] = '\0';
   }
   return buf;
}

int get_track_elapsed_frames(void)
{
   if (use_midi_)
      return midi_backend_tell_samples() / 1470;
   if (use_mp3_)
      return mp3_backend_tell_samples() / 1470;
   if (use_xmp_)
      return xmp_backend_tell_samples() / 1470;
   if (use_vgm_)
      return vgm_backend_tell_samples() / 1470;
   if (emu)
      return gme_tell_samples(emu) / 1470;
   return 0;
}

void play_pause(void)
{
   if (seek_active_)
      return;
   is_playing_ = !is_playing_;
}

void toggle_loop(void)
{
   loop_enabled_ = !loop_enabled_;
}

bool get_loop_enabled(void)
{
   return loop_enabled_;
}

bool get_is_playing(void)
{
   return is_playing_;
}


/* ---- textos do novo layout ---- */

char *get_system_line(char *buf)
{
   const char *sys = "";
   const char *dot;
   char ext[12];
   int i = 0;

   buf[0] = '\0';
   if (!track || !file)
      return buf;

   if (file->is_midi)
      sys = midi_backend_is_gm() ? "General MIDI" : "Roland MT-32";
   else if (file->is_mp3)
      sys = "Audio Digital";
   else if (file->is_tracker)
      sys = "Amiga / Tracker";
   else if (file->file_type == gme_spc_type)
      sys = "Super Nintendo";
   else if (file->file_type == gme_nsf_type || file->file_type == gme_nsfe_type)
      sys = "Nintendo NES";
   else if (file->file_type == gme_gbs_type)
      sys = "Game Boy";
   else if (file->file_type == gme_gym_type)
      sys = "Sega Genesis";
   else if (file->file_type == gme_vgm_type || file->file_type == gme_vgz_type)
      sys = "Sega / Arcade";
   else if (file->file_type == gme_hes_type)
      sys = "TurboGrafx-16";
   else if (file->file_type == gme_kss_type)
      sys = "MSX / Master System";
   else if (file->file_type == gme_ay_type)
      sys = "ZX Spectrum";
   else if (file->file_type == gme_sap_type)
      sys = "Atari XL/XE";

   dot = strrchr(file->name, '.');
   if (dot)
      for (dot++; *dot && i < 10; dot++, i++)
         ext[i] = (*dot >= 'a' && *dot <= 'z') ? (char)(*dot - 32) : *dot;
   ext[i] = '\0';

   if (sys[0] && ext[0])
      snprintf(buf, 96, "%s - %s", sys, ext);
   else if (sys[0])
      snprintf(buf, 96, "%s", sys);
   else
      snprintf(buf, 96, "%s", ext);
   return buf;
}

char *get_track_label(char *buf)
{
   if (plist)
      sprintf(buf, "Track %02d / %02d", current_track + 1, plist->num_tracks);
   else
      buf[0] = '\0';
   return buf;
}

char *get_time_text(char *buf)
{
   if (track && (emu || use_xmp_ || use_mp3_ || use_midi_))
   {
      long total   = track->track_length / 1000;
      long elapsed = (backend_elapsed_ms()) / 1000;
      sprintf(buf, "%02ld:%02ld/%02ld:%02ld", elapsed / 60, elapsed % 60, total / 60, total % 60);
   }
   else
      buf[0] = '\0';
   return buf;
}

char *get_rate_text(char *buf)
{
   sprintf(buf, "%ld.%ld kHz", sample_rate_ / 1000, (sample_rate_ % 1000) / 100);
   return buf;
}

int get_track_progress_permille(void)
{
   long total, elapsed;
   if (!(track && (emu || use_xmp_ || use_mp3_ || use_midi_)))
      return 0;
   total = track->track_length;
   if (total <= 0)
      return 0;
   elapsed = backend_elapsed_ms();
   if (elapsed < 0)     elapsed = 0;
   if (elapsed > total) elapsed = total;
   return (int)((double)elapsed * 1000.0 / (double)total);
}


/* ---- deteccao do(s) chip(s) de audio ---- */

typedef struct { int off; int minver; const char *name; } chip_entry;

static const chip_entry chip_tab[] = {
   {0x0C,0x100,"SN76489"},{0x10,0x100,"YM2413"},{0x2C,0x110,"YM2612"},{0x30,0x110,"YM2151"},
   {0x38,0x151,"SegaPCM"},{0x40,0x151,"RF5C68"},{0x44,0x151,"YM2203"},{0x48,0x151,"YM2608"},
   {0x4C,0x151,"YM2610"},{0x50,0x151,"YM3812"},{0x54,0x151,"YM3526"},{0x58,0x151,"Y8950"},
   {0x5C,0x151,"YMF262"},{0x60,0x151,"YMF278B"},{0x64,0x151,"YMF271"},{0x68,0x151,"YMZ280B"},
   {0x6C,0x151,"RF5C164"},{0x70,0x151,"PWM"},{0x74,0x151,"AY8910"},
   {0x80,0x161,"GB DMG"},{0x84,0x161,"NES APU"},{0x88,0x161,"MultiPCM"},{0x8C,0x161,"uPD7759"},
   {0x90,0x161,"OKIM6258"},{0x98,0x161,"OKIM6295"},{0x9C,0x161,"K051649"},{0xA0,0x161,"K054539"},
   {0xA4,0x161,"HuC6280"},{0xA8,0x161,"C140"},{0xAC,0x161,"K053260"},{0xB0,0x161,"POKEY"},
   {0xB4,0x161,"QSound"},{0xB8,0x171,"SCSP"},{0xC0,0x171,"WonderSwan"},{0xC4,0x171,"VSU-VUE"},
   {0xC8,0x171,"SAA1099"},{0xCC,0x171,"ES5503"},{0xD0,0x171,"ES5506"},{0xD4,0x171,"X1-010"},
   {0xD8,0x171,"C352"},{0xDC,0x171,"GA20"},
   {0xE4,0x171,"Mikey"},{0xE8,0x171,"K007232"},{0xEC,0x171,"K005289"},
   {0xF0,0x171,"MSM5205"},{0xF4,0x171,"MSM5232"},{0xF8,0x171,"BSMT2000"},
   {0xFC,0x171,"ICS2115"}
};

static char chip_text[128];

static unsigned long rd_le32(const unsigned char *p)
{
   return (unsigned long)p[0] | ((unsigned long)p[1] << 8) |
          ((unsigned long)p[2] << 16) | ((unsigned long)p[3] << 24);
}

static void chip_add(const char *name, int dual, int *shown, int *count)
{
   size_t l = strlen(chip_text);
   (*count)++;
   if (*shown >= 3)
      return;
   snprintf(chip_text + l, sizeof(chip_text) - l, "%s%s%s",
            l ? " + " : "", name, dual ? " x2" : "");
   (*shown)++;
}

/* le os primeiros 256 bytes do VGM (descomprime se for gzip) */
static int vgm_read_header(const unsigned char *d, int len, unsigned char *out)
{
   int n;
   if (len >= 2 && d[0] == 0x1F && d[1] == 0x8B)
   {
      z_stream zs;
      int r;
      memset(&zs, 0, sizeof(zs));
      if (inflateInit2(&zs, 15 + 16) != Z_OK)
         return 0;
      zs.next_in   = (Bytef*)d;
      zs.avail_in  = (uInt)len;
      zs.next_out  = out;
      zs.avail_out = 256;
      r = inflate(&zs, Z_SYNC_FLUSH);
      n = 256 - (int)zs.avail_out;
      inflateEnd(&zs);
      if (r != Z_OK && r != Z_STREAM_END && r != Z_BUF_ERROR)
         return 0;
      return n;
   }
   n = len < 256 ? len : 256;
   memcpy(out, d, n);
   return n;
}

static void detect_chips(void)
{
   int shown = 0, count = 0;
   const unsigned char *d;
   chip_text[0] = '\0';
   if (!file)
      return;
   d = (const unsigned char*)file->data;

   if (file->is_midi)
   {
      strcpy(chip_text, midi_backend_is_gm() ? "GM" : "MT-32");
      return;
   }

   if (file->is_mp3)
   {
      strcpy(chip_text, "MP3");
      return;
   }

   if (file->is_tracker)
   {
      const char *dt = strrchr(file->name, '.');
      int is_mod = dt && (dt[1]=='m'||dt[1]=='M') && (dt[2]=='o'||dt[2]=='O')
                      && (dt[3]=='d'||dt[3]=='D') && dt[4]=='\0';
      strcpy(chip_text, is_mod ? "AMIGA: MIX. PAULA" : "TRACKER");
      return;
   }

   if (file->file_type == gme_vgm_type || file->file_type == gme_vgz_type)
   {
      unsigned char h[256];
      int n = vgm_read_header(d, file->length, h);
      if (n >= 0x40 && memcmp(h, "Vgm ", 4) == 0)
      {
         unsigned long ver = rd_le32(h + 0x08);
         int hdrlen = 0x40, i;
         if (ver >= 0x150)
         {
            unsigned long dof = rd_le32(h + 0x34);
            if (dof)
               hdrlen = 0x34 + (int)dof;
         }
         for (i = 0; i < (int)(sizeof(chip_tab) / sizeof(chip_tab[0])); i++)
         {
            unsigned long clk;
            if (ver < (unsigned long)chip_tab[i].minver)
               continue;
            if (chip_tab[i].off + 4 > hdrlen || chip_tab[i].off + 4 > n)
               continue;
            clk = rd_le32(h + chip_tab[i].off);
            if (clk & 0x3FFFFFFFUL)
            {
               const char *nm = chip_tab[i].name;
               if (chip_tab[i].off == 0x4C && (clk & 0x80000000UL))
                  nm = "YM2610B";
               chip_add(nm, (clk & 0x40000000UL) != 0, &shown, &count);
            }
         }
         if (count > shown)
         {
            size_t l = strlen(chip_text);
            snprintf(chip_text + l, sizeof(chip_text) - l, " + %d", count - shown);
         }
      }
      if (!chip_text[0])
         strcpy(chip_text, "VGM");
      return;
   }

   if (file->file_type == gme_spc_type)
   {
      chip_add("S-SMP", 0, &shown, &count);
      chip_add("S-DSP", 0, &shown, &count);
   }
   else if (file->file_type == gme_nsf_type || file->file_type == gme_nsfe_type)
   {
      chip_add("2A03", 0, &shown, &count);
      if (file->file_type == gme_nsf_type && file->length > 0x7C && memcmp(d, "NESM", 4) == 0)
      {
         unsigned f = d[0x7B];
         if (f & 0x01) chip_add("VRC6", 0, &shown, &count);
         if (f & 0x02) chip_add("VRC7", 0, &shown, &count);
         if (f & 0x04) chip_add("FDS", 0, &shown, &count);
         if (f & 0x08) chip_add("MMC5", 0, &shown, &count);
         if (f & 0x10) chip_add("N163", 0, &shown, &count);
         if (f & 0x20) chip_add("FME7", 0, &shown, &count);
      }
   }
   else if (file->file_type == gme_gbs_type)
      chip_add("GB DMG", 0, &shown, &count);
   else if (file->file_type == gme_gym_type)
   {
      chip_add("YM2612", 0, &shown, &count);
      chip_add("SN76489", 0, &shown, &count);
   }
   else if (file->file_type == gme_hes_type)
      chip_add("HuC6280", 0, &shown, &count);
   else if (file->file_type == gme_kss_type)
   {
      chip_add("AY8910", 0, &shown, &count);
      chip_add("SN76489", 0, &shown, &count);
      chip_add("SCC", 0, &shown, &count);
   }
   else if (file->file_type == gme_ay_type)
      chip_add("AY-3-8910", 0, &shown, &count);
   else if (file->file_type == gme_sap_type)
      chip_add("POKEY", 0, &shown, &count);

   if (count > shown)
   {
      size_t l = strlen(chip_text);
      snprintf(chip_text + l, sizeof(chip_text) - l, " + %d", count - shown);
   }
}

char *get_chip_text(char *buf)
{
   if (track && chip_text[0])
      snprintf(buf, 128, "%s", chip_text);
   else
      buf[0] = '\0';
   return buf;
}
