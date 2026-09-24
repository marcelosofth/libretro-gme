#!/usr/bin/env python3
"""apply_scan.py - R segurado = avanco rapido, L segurado = voltar acelerado,
toque curto (< ~0,3 s) = troca de faixa ao soltar.

Uso (na raiz do repo):  python3 apply_scan.py
Opcional:               python3 apply_scan.py --root /caminho/do/repo

Nao altera nenhum arquivo se qualquer ancora nao for encontrada.
"""
import os
import re
import sys

ROOT = "."
if "--root" in sys.argv:
    ROOT = sys.argv[sys.argv.index("--root") + 1]

P_C = os.path.join(ROOT, "src", "player.c")
P_H = os.path.join(ROOT, "src", "player.h")
L_C = os.path.join(ROOT, "src", "libretro.c")


def read(path):
    with open(path, "rb") as f:
        raw = f.read().decode("utf-8")
    crlf = "\r\n" in raw
    return raw.replace("\r\n", "\n"), crlf


def write(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def fail(msg):
    print("ERRO: " + msg)
    print("Nenhum arquivo foi alterado.")
    sys.exit(1)


def sub_once(text, pattern, repl, what, flags=0):
    """re.sub com FUNCAO de substituicao (nao interpreta \\ no texto novo)."""
    new, n = re.subn(pattern, lambda m: repl(m), text, count=0, flags=flags)
    if n != 1:
        fail("ancora '%s' encontrada %d vez(es), esperado 1" % (what, n))
    return new


pc, pc_crlf = read(P_C)
ph, ph_crlf = read(P_H)
lc, lc_crlf = read(L_C)

if "play_scan" in pc or "play_scan" in ph or "play_scan" in lc:
    fail("o patch parece ja ter sido aplicado (play_scan ja existe)")

# ---------------------------------------------------------------- player.h
ph = sub_once(
    ph,
    r"short \*play\(void\);\n",
    lambda m: m.group(0)
    + "\n/* dir: 0 = normal, 1 = avanco rapido (R segurado), -1 = voltar acelerado (L segurado) */\n"
    + "short *play_scan(int dir);\n",
    "short *play(void);",
)

# ---------------------------------------------------------------- player.c
# 1) include
pc = sub_once(
    pc,
    r"#include <string\.h>\n",
    lambda m: m.group(0) + "#include <time.h>\n",
    "#include <string.h>",
)

# 2) estado + historico de audio + tempo decorrido (antes de close_file/start_track)
BLOCK_STATE = r'''
/* ---- avanco rapido (R) / voltar acelerado (L) ---- */

#ifndef SCAN_MULT
#define SCAN_MULT       3        /* velocidade do avanco/volta (3x) */
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
'''

pc = sub_once(
    pc,
    r"static void detect_chips\(void\);\n",
    lambda m: m.group(0) + BLOCK_STATE,
    "static void detect_chips(void);",
)

# 3) close_file libera o historico
pc = sub_once(
    pc,
    r"void close_file\(void\)\n\{\n",
    lambda m: m.group(0) + "   hist_free();\n",
    "void close_file(void)",
)

# 4) start_track zera o historico (e cancela reposicionamento, exceto o interno)
pc = sub_once(
    pc,
    r"void start_track\(int tracknr\)\n\{\n",
    lambda m: m.group(0)
    + "   hist_reset();\n"
    + "   if (!internal_restart_)\n"
    + "      seek_active_ = 0;\n",
    "void start_track(int tracknr)",
)

# 5) play_pause ignora enquanto reposiciona
pc = sub_once(
    pc,
    r"void play_pause\(void\)\n\{\n",
    lambda m: m.group(0) + "   if (seek_active_)\n      return;\n",
    "void play_pause(void)",
)

# 6) tempo mostrado na tela passa a usar backend_elapsed_ms()
TERNARY = (
    "use_midi_ ? midi_backend_tell_ms() : use_mp3_ ? mp3_backend_tell_ms() : "
    "use_xmp_ ? xmp_backend_tell_ms() : use_vgm_ ? vgm_backend_tell_ms() : gme_tell(emu)"
)
n_tern = pc.count(TERNARY)
if n_tern != 3:
    fail("expressao de tempo decorrido encontrada %d vez(es), esperado 3" % n_tern)
pc = pc.replace(TERNARY, "backend_elapsed_ms()")

# 7) play_scan (depois de play(), antes de next_track)
BLOCK_SCAN = r'''/* ---- avanco rapido / voltar acelerado ---- */

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

'''

pc = sub_once(
    pc,
    r"void next_track\(void\)\n\{",
    lambda m: BLOCK_SCAN + m.group(0),
    "void next_track(void)",
)

# ---------------------------------------------------------------- libretro.c
m = re.search(r"void retro_run\(void\)\s*\{", lc)
if not m:
    fail("retro_run nao encontrado em src/libretro.c")
start = m.start()
end = lc.find("\n}\n", m.end())
if end < 0:
    fail("fim de retro_run nao encontrado em src/libretro.c")
end += 3
run = lc[start:end]

# 8) variaveis locais
run = sub_once(
    run,
    r"(short \*audio;\n)",
    lambda mm: mm.group(1) + "   uint16_t released = 0;\n   int scan_dir = 0;\n",
    "short *audio; (em retro_run)",
)

# 9) tratamento de L/R
NEW_INPUT = r'''input = realinput & ~previnput;
   released = previnput & ~realinput;
   previnput = realinput;

   /* L/R: toque curto troca de faixa (ao soltar); segurando vira voltar/avancar acelerado */
   if(released & (1<<RETRO_DEVICE_ID_JOYPAD_L))
   {
      if(l_hold_frames < SCAN_HOLD_FRAMES)
         prev_track();
      l_hold_frames = 0;
   }
   else if((realinput & (1<<RETRO_DEVICE_ID_JOYPAD_L)) && l_hold_frames < 100000)
      l_hold_frames++;

   if(released & (1<<RETRO_DEVICE_ID_JOYPAD_R))
   {
      if(r_hold_frames < SCAN_HOLD_FRAMES)
         next_track();
      r_hold_frames = 0;
   }
   else if((realinput & (1<<RETRO_DEVICE_ID_JOYPAD_R)) && r_hold_frames < 100000)
      r_hold_frames++;

   {
      int l_scan = (realinput & (1<<RETRO_DEVICE_ID_JOYPAD_L)) && l_hold_frames >= SCAN_HOLD_FRAMES;
      int r_scan = (realinput & (1<<RETRO_DEVICE_ID_JOYPAD_R)) && r_hold_frames >= SCAN_HOLD_FRAMES;
      if(r_scan && !l_scan)
         scan_dir = 1;
      else if(l_scan && !r_scan)
         scan_dir = -1;
   }'''

run = sub_once(
    run,
    r"input\s*=\s*realinput\s*&\s*~previnput;\s*"
    r"previnput\s*=\s*realinput;\s*"
    r"if\s*\(\s*input\s*&\s*\(1<<RETRO_DEVICE_ID_JOYPAD_L\)\s*\)\s*prev_track\(\);\s*"
    r"if\s*\(\s*input\s*&\s*\(1<<RETRO_DEVICE_ID_JOYPAD_R\)\s*\)\s*next_track\(\);",
    lambda mm: NEW_INPUT,
    "bloco de input L/R (em retro_run)",
)

# 10) audio = play(); -> play_scan(scan_dir)
run = sub_once(
    run,
    r"audio\s*=\s*play\(\s*\);",
    lambda mm: "audio = play_scan(scan_dir);",
    "audio = play(); (em retro_run)",
)

HEADER_VARS = '''/* toque curto (< ~0,3 s a 60 fps) troca de faixa; segurar mais que isso vira avanco/volta acelerada */
#define SCAN_HOLD_FRAMES 18
static int l_hold_frames = 0;
static int r_hold_frames = 0;

'''
lc = lc[:start] + HEADER_VARS + run + lc[end:]

# ---------------------------------------------------------------- grava tudo
write(P_C, pc, pc_crlf)
write(P_H, ph, ph_crlf)
write(L_C, lc, lc_crlf)
print("OK: src/player.c, src/player.h e src/libretro.c atualizados.")
print("Agora compile: make platform=win -j$(nproc) ... (mesmo comando de sempre)")
