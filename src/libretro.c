#include <string.h>
#include <stdlib.h>
#include <assert.h>
#include <stdio.h>

#include <libretro.h>
#include <retro_miscellaneous.h>
#include <streams/file_stream.h>

#include "graphics.h"
#include "player.h"
#include "spectrum.h"
#include "credits_bg.h"
#include "credits_music.h"
#include "credits_logo.h"
#include "credits_sonic.h"
#include "credits_sprites.h"

// Static globals
static surface *framebuffer = NULL;
static uint16_t previnput = 0;
static int browser_open_state = 0;
static int browser_cursor      = 0;
static int browser_count_ui    = 0;
static int l_active_ = 0;
static int r_active_ = 0;
static int credits_open_state = 0;
static int credits_frame      = 0;
static int credits_anim       = 0;   /* frames desde que a janela abriu (anima o sprite; nao para com o B) */
static int credits_paused     = 0;   /* 1 = texto dos creditos parado (B pausa/continua) */

// Callbacks

retro_log_printf_t log_cb;

static retro_video_refresh_t video_cb;
static retro_input_poll_t input_poll_cb;
static retro_input_state_t input_state_cb;
static retro_environment_t environ_cb;
static retro_audio_sample_t audio_cb;
static retro_audio_sample_batch_t audio_batch_cb;
// libretro global setters
void retro_set_video_refresh(retro_video_refresh_t cb) { video_cb = cb; }
void retro_set_input_poll(retro_input_poll_t cb) { input_poll_cb = cb; }
void retro_set_input_state(retro_input_state_t cb) { input_state_cb = cb; }

void retro_set_environment(retro_environment_t cb)
{
   struct retro_vfs_interface_info vfs_iface_info;
   environ_cb = cb;

   vfs_iface_info.required_interface_version = 1;
   vfs_iface_info.iface                      = NULL;
   if (cb(RETRO_ENVIRONMENT_GET_VFS_INTERFACE, &vfs_iface_info))
      filestream_vfs_init(&vfs_iface_info);
}

void retro_set_audio_sample(retro_audio_sample_t cb) { audio_cb = cb; }
void retro_set_audio_sample_batch(retro_audio_sample_batch_t cb) { audio_batch_cb = cb; }

unsigned retro_api_version(void) { return RETRO_API_VERSION; }
unsigned retro_get_region(void) { return RETRO_REGION_PAL; }

// Serialisation methods
size_t retro_serialize_size(void) { return 0; }
bool retro_serialize(void *data, size_t size) { return false; }
bool retro_unserialize(const void *data, size_t size) { return false; }

// libretro unused api functions
void retro_set_controller_port_device(unsigned port, unsigned device) {}
void *retro_get_memory_data(unsigned id) { return NULL; }
size_t retro_get_memory_size(unsigned id){ return 0; }

// Cheats
void retro_cheat_reset(void) {}
void retro_cheat_set(unsigned index, bool enabled, const char *code) {}

/* ---- desenho de texto (sem alocar memoria, com clip) ---- */

static void put_glyph(unsigned char ch, int px, int py, unsigned short color, int cx0, int cx1)
{
   int x, y, sx, sy;
   int charx = (ch % 16) * 8;
   int chary = (ch >> 4) * 8;
   for (y = 0; y < 8; y++)
   {
      for (x = 0; x < 8; x++)
      {
         if (!is_font_pixel(charx + x, chary + y))
            continue;
         for (sy = 0; sy < 2; sy++)
         {
            int yy = py + y * 2 + sy;
            if (yy < 0 || yy >= 480)
               continue;
            for (sx = 0; sx < 2; sx++)
            {
               int xx = px + x * 2 + sx;
               if (xx < cx0 || xx >= cx1 || xx < 0 || xx >= 640)
                  continue;
               set_pixel(framebuffer, xx, yy, color);
            }
         }
      }
   }
}

/* colunas realmente usadas pelo glifo (para espacamento proporcional) */
static void glyph_extent(unsigned char ch, int *x0, int *x1)
{
   int x, y;
   int charx = (ch % 16) * 8;
   int chary = (ch >> 4) * 8;
   *x0 = 8;
   *x1 = -1;
   for (x = 0; x < 8; x++)
      for (y = 0; y < 8; y++)
         if (is_font_pixel(charx + x, chary + y))
         {
            if (x < *x0) *x0 = x;
            if (x > *x1) *x1 = x;
         }
}

static int text_width_prop(const char *text)
{
   int w = 0, x0, x1;
   for (; *text; text++)
   {
      glyph_extent((unsigned char)*text, &x0, &x1);
      w += (x1 < 0) ? 4 : (x1 - x0 + 2);
   }
   w = w > 0 ? w - 1 : 0;
   return w * 2;
}

static void draw_text_prop(const char *text, int x, int y, unsigned short color)
{
   int x0, x1;
   for (; *text; text++)
   {
      unsigned char ch = (unsigned char)*text;
      glyph_extent(ch, &x0, &x1);
      if (x1 < 0)
      {
         x += 4 * 2;
         continue;
      }
      put_glyph(ch, x - x0 * 2, y, color, 0, 640);
      x += (x1 - x0 + 2) * 2;
   }
}

/* texto monoespacado; se passar de maxw, rola de um lado para o outro */
static void draw_text_scroll(const char *text, int x, int y, int maxw, unsigned short color)
{
   int len   = (int)strlen(text);
   int textw = len * 8 * 2;
   int off   = 0, i;

   if (textw > maxw)
   {
      int delta  = textw - maxw;
      int delay  = 30;
      int modulo = delta + delay * 2;
      int frames = get_track_elapsed_frames();
      off = (modulo - abs((frames / 2) % (2 * modulo) - modulo)) - delay;
      if (off < 0)     off = 0;
      if (off > delta) off = delta;
   }

   for (i = 0; i < len; i++)
   {
      int gx = x - off + i * 8 * 2;
      if (gx + 8 * 2 <= x || gx >= x + maxw)
         continue;
      put_glyph((unsigned char)text[i], gx, y, color, x, x + maxw);
   }
}

/* texto proporcional cortado em maxx */
static void draw_text_prop_clip(const char *text, int x, int y, unsigned short color, int maxx)
{
   int x0, x1;
   for (; *text && x < maxx; text++)
   {
      unsigned char ch = (unsigned char)*text;
      glyph_extent(ch, &x0, &x1);
      if (x1 < 0)
      {
         x += 4 * 2;
         continue;
      }
      put_glyph(ch, x - x0 * 2, y, color, 0, maxx);
      x += (x1 - x0 + 2) * 2;
   }
}

/* LED de atividade: acende com o volume do audio e decai rapido */
static int led_level = 0;

static void led_update(const short *audio, int n)
{
   int i, pk = 0, cur;
   for (i = 0; i < n; i++)
   {
      int v = audio[i];
      if (v < 0) v = -v;
      if (v > pk) pk = v;
   }
   cur = pk / 40;
   if (cur > 255) cur = 255;
   led_level = (led_level * 192) >> 8;
   if (cur > led_level)
      led_level = cur;
}

static void draw_led(int cx, int cy)
{
   int dx, dy;
   int t = led_level;
   int r = 8 + (23 * t) / 255, g = 3 + (9 * t) / 255, b = 2 + (5 * t) / 255;
   unsigned short col;
   if (t < 48) /* em repouso/fraco: escurece ate o preto; acima disso fica igual */
   {
      r = (r * t) / 48;
      g = (g * t) / 48;
      b = (b * t) / 48;
   }
   if (t < 4) /* sem som: preto */
      col = get_color(0, 0, 0);
   else
      col = get_color(r, g, b);
   for (dy = -6; dy <= 6; dy++)
      for (dx = -6; dx <= 6; dx++)
         if (dx * dx + dy * dy <= 40)
            set_pixel(framebuffer, cx + dx, cy + dy, col);
   if (t > 200) /* brilho branco do LED: 2x2 pixels (antes era 1) */
   {
      unsigned short wh = get_color(31, 40, 30);
      set_pixel(framebuffer, cx - 3, cy - 3, wh);
      set_pixel(framebuffer, cx - 2, cy - 3, wh);
      set_pixel(framebuffer, cx - 3, cy - 2, wh);
      set_pixel(framebuffer, cx - 2, cy - 2, wh);
   }
}

/* versao reduzida do mesmo LED (mesma cor/pulsar de led_level), so que menor -
 * usada para sobrepor a bolinha do "joystick" no logo (que e parte do fundo). */
static void draw_led_mini(int cx, int cy, int r)
{
   int dx, dy;
   int t = led_level;
   int rr = 8 + (23 * t) / 255, gg = 3 + (9 * t) / 255, bb = 2 + (5 * t) / 255;
   unsigned short col;
   if (t < 48)
   {
      rr = (rr * t) / 48;
      gg = (gg * t) / 48;
      bb = (bb * t) / 48;
   }
   col = (t < 4) ? get_color(0, 0, 0) : get_color(rr, gg, bb);
   for (dy = -r; dy <= r; dy++)
      for (dx = -r; dx <= r; dx++)
         if (dx * dx + dy * dy <= r * r)
            set_pixel(framebuffer, cx + dx, cy + dy, col);
   if (t > 200 && r >= 3)
   {
      unsigned short wh = get_color(31, 40, 30);
      set_pixel(framebuffer, cx, cy - 1, wh);
   }
}

/* ---- layout: cabecalho / espectro / progresso ---- */
#define UI_LEFT   32
#define UI_RIGHT  608
#define UI_W      (UI_RIGHT - UI_LEFT)

/* Cabecalho: 4 linhas, uma por faixa do fundo (y = topo do texto).
 * 1) chip  2) sistema  3) jogo  4) faixa + Track N/M.
 * HDR_TEXT_MAX_X: limite direito das linhas 1-3 (o logo comeca depois). */
#define HDR_Y1 24
#define HDR_Y2 60
#define HDR_Y3 96
#define HDR_Y4 132
#define HDR_TEXT_MAX_X 416

/* ---- fonte do CHIP: Press Start 2P (src/font_chip.h) com degrade vertical ---- */
#include "font_chip.h"

#define CHIP_SPACE 5   /* largura do espaco (px do atlas) */

static unsigned short chip_grad[8];

static void chip_grad_init(void)
{
   /* degrade da imagem de referencia: azul -> branco (topo), dourado -> creme (base) */
   static const unsigned char rgb[8][3] = {
      { 69, 149, 204}, {135, 190, 231}, {212, 237, 253}, {255, 255, 255},
      {183, 129,  41}, {229, 185,  87}, {252, 245, 232}, {252, 245, 232}
   };
   int i;
   for (i = 0; i < 8; i++)
      chip_grad[i] = get_color(rgb[i][0] >> 3, rgb[i][1] >> 2, rgb[i][2] >> 3);
}

static int chip_pixel(unsigned char ch, int x, int y)
{
   const unsigned short *p = (const unsigned short *)font_chip.pixel_data;
   return p[(ch % 16) * 8 + x + ((ch >> 4) * 8 + y) * 128] == 0;
}

static void chip_extent(unsigned char ch, int *x0, int *x1)
{
   int x, y;
   *x0 = 8;
   *x1 = -1;
   for (x = 0; x < 8; x++)
      for (y = 0; y < 8; y++)
         if (chip_pixel(ch, x, y))
         {
            if (x < *x0) *x0 = x;
            if (x > *x1) *x1 = x;
         }
}

static void chip_put_glyph(unsigned char ch, int px, int py, int cx1)
{
   int x, y, sx, sy;
   for (y = 0; y < 8; y++)
      for (x = 0; x < 8; x++)
      {
         if (!chip_pixel(ch, x, y))
            continue;
         for (sy = 0; sy < 2; sy++)
         {
            int yy = py + y * 2 + sy;
            if (yy < 0 || yy >= 480)
               continue;
            for (sx = 0; sx < 2; sx++)
            {
               int xx = px + x * 2 + sx;
               if (xx < 0 || xx >= 640 || xx >= cx1)
                  continue;
               set_pixel(framebuffer, xx, yy, chip_grad[y]);
            }
         }
      }
}

static int chip_text_width(const char *text)
{
   int w = 0, x0, x1;
   for (; *text; text++)
   {
      chip_extent((unsigned char)*text, &x0, &x1);
      w += (x1 < 0) ? CHIP_SPACE : (x1 - x0 + 2);
   }
   w = w > 0 ? w - 1 : 0;
   return w * 2;
}

/* maxx = limite direito absoluto (x) */
static void chip_draw_text(const char *text, int x, int y, int maxx)
{
   int x0, x1;
   chip_grad_init();
   for (; *text && x < maxx; text++)
   {
      unsigned char ch = (unsigned char)*text;
      chip_extent(ch, &x0, &x1);
      if (x1 < 0)
      {
         x += CHIP_SPACE * 2;
         continue;
      }
      chip_put_glyph(ch, x - x0 * 2, y, maxx);
      x += (x1 - x0 + 2) * 2;
   }
}

/* ---- barra de transporte: Prev / Stop / Play / Pause / Loop / Next ---- */

static void draw_bar(int x, int y, int w, int h, unsigned short color)
{
   draw_shape(framebuffer, color, x, y, w, h);
}

/* triangulo generico: de x_tip (bico, altura 0) ate x_base (base, altura 2*half_h+1) */
static void draw_tri(int x_tip, int x_base, int cy, int half_h, unsigned short color)
{
   int width = x_base - x_tip;
   int steps = abs(width);
   int i;
   if (steps == 0)
      return;
   for (i = 0; i <= steps; i++)
   {
      int x = x_tip + (width >= 0 ? i : -i);
      int h = (half_h * i) / steps;
      int y;
      for (y = -h; y <= h; y++)
         set_pixel(framebuffer, x, cy + y, color);
   }
}

static void draw_loop_icon(int cx, int cy, int r, unsigned short color)
{
   int dx, dy;
   for (dy = -r; dy <= r; dy++)
      for (dx = -r; dx <= r; dx++)
      {
         int d2 = dx * dx + dy * dy;
         if (d2 <= r * r && d2 > (r - 3) * (r - 3))
         {
            if (dy > r / 3 && dx > 0) /* abertura para a seta */
               continue;
            set_pixel(framebuffer, cx + dx, cy + dy, color);
         }
      }
   draw_tri(cx + r - 8, cx + r - 2, cy + r - 4, 4, color);
}

#define TRANS_Y  449
#define ICON_HH  6   /* meia-altura padrao dos icones (altura total 12, igual a foto) */

static void draw_transport_bar(void)
{
   static const int off[6] = { -110, -57, -18, 18, 57, 110 };
   int cx = (UI_LEFT + UI_RIGHT) / 2;
   int cy = TRANS_Y;
   int ix;
   unsigned short dim  = get_color(9, 20, 12);
   unsigned short lit  = get_color(8, 56, 17);
   bool playing  = get_is_playing();
   bool stopped  = get_is_stopped();
   bool paused   = !playing && !stopped;
   bool loop_on  = get_loop_enabled();
   unsigned short prev_col = l_active_ ? lit : dim;
   unsigned short next_col = r_active_ ? lit : dim;

   /* prev: barra + triangulo apontando p/ esquerda */
   ix = cx + off[0];
   draw_bar(ix - 6, cy - ICON_HH, 2, ICON_HH * 2, prev_col);
   draw_tri(ix - 4, ix + 5, cy, ICON_HH, prev_col);

   /* stop: quadrado */
   ix = cx + off[1];
   draw_bar(ix - 6, cy - 6, 12, 12, stopped ? lit : dim);

   /* play: triangulo apontando p/ direita */
   ix = cx + off[2];
   draw_tri(ix + 5, ix - 5, cy, ICON_HH, playing ? lit : dim);

   /* pause: duas barras */
   ix = cx + off[3];
   draw_bar(ix - 4, cy - ICON_HH, 2, ICON_HH * 2, paused ? lit : dim);
   draw_bar(ix + 2, cy - ICON_HH, 2, ICON_HH * 2, paused ? lit : dim);

   /* loop */
   ix = cx + off[4];
   draw_loop_icon(ix, cy, 8, loop_on ? lit : dim);

   /* next: triangulo apontando p/ direita + barra */
   ix = cx + off[5];
   draw_tri(ix + 3, ix - 5, cy, ICON_HH, next_col);
   draw_bar(ix + 5, cy - ICON_HH, 2, ICON_HH * 2, next_col);
}

/* posicao da bolinha do "joystick" no logo (medida na tela 640x480; ajuste
   fino se nao bater exatamente com a arte do seu fundo) */
#define LOGO_LED_X 534
#define LOGO_LED_Y 64
#define LOGO_LED_R 4

static void draw_ui(void)
{
   char message[512];
   int w, prog;

   /* cabecalho: linha 4 = faixa (esq) + Track N/M (dir) */
   get_track_label(message);
   w = text_width_prop(message);
   draw_text_prop(message, UI_RIGHT - w, HDR_Y4, get_color(28, 56, 28));
   draw_text_scroll(get_song_name(message), UI_LEFT, HDR_Y4, UI_W - w - 16, get_color(30, 58, 25));

   /* linha 3 = jogo */
   draw_text_scroll(get_game_name(message), UI_LEFT, HDR_Y3, HDR_TEXT_MAX_X - UI_LEFT, get_color(19, 36, 27));

   /* linha 2 = sistema */
   get_system_line(message);
   draw_text_prop_clip(message, UI_LEFT, HDR_Y2, get_color(15, 33, 21), HDR_TEXT_MAX_X);

   /* linha 1 = CHIP: (led) chip de audio - Press Start 2P com degrade */
   {
      int lx = UI_LEFT + chip_text_width("CHIP:") + 16;
      chip_draw_text("CHIP:", UI_LEFT, HDR_Y1, HDR_TEXT_MAX_X);
      draw_led(lx + 6, HDR_Y1 + 6);
      chip_draw_text(get_chip_text(message), lx + 24, HDR_Y1, HDR_TEXT_MAX_X);
   }

   /* copia menor do LED, por cima da bolinha do joystick no logo (fundo) */
   draw_led_mini(LOGO_LED_X, LOGO_LED_Y, LOGO_LED_R);

   /* barra de progresso (proxima ao espectro, cuja base fica em y=408) */
   draw_shape(framebuffer, get_color(4, 8, 9), UI_LEFT, 413, UI_W, 12);
   prog = get_track_progress_permille();
   if (prog > 0)
      draw_shape(framebuffer, get_color(12, 25, 28), UI_LEFT, 413, (UI_W * prog) / 1000, 12);

   /* tempo (esquerda) e taxa de amostragem (direita) */
   draw_text_prop(get_time_text(message), UI_LEFT, 442, get_color(27, 54, 29));

   get_rate_text(message);
   w = text_width_prop(message);
   draw_text_prop(message, UI_RIGHT - w, 442, get_color(15, 33, 21));

   draw_transport_bar();
}

/* ---- osciloscopio estereo (espaco entre o cabecalho e o espectro) ---- */
#define WAVE_TOP  167
#define WAVE_H    48
#define WAVE_GAP  10

static void draw_wave_channel(const short *audio, int frames, int offset,
                               int y0, int h, unsigned short color, int gain_q8)
{
   int x, px = -1, py = 0;
   int mid = y0 + h / 2;

   draw_line(framebuffer, get_color(4, 7, 8), UI_LEFT, mid, UI_RIGHT, mid);

   for (x = 0; x < UI_W; x++)
   {
      int idx = (x * frames) / UI_W;
      int s   = audio[idx * 2 + offset];
      int v = (s * gain_q8) >> 8;
      int y = mid - (v * (h / 2)) / 32768;
      if (y < y0)         y = y0;
      if (y >= y0 + h)     y = y0 + h - 1;
      if (px >= 0)
         draw_line(framebuffer, color, UI_LEFT + px, py, UI_LEFT + x, y);
      px = x;
      py = y;
   }
}

/* Janela do osciloscopio: WAVE_SPAN amostras (por canal) mais recentes.
 * 735 = 1 quadro (~16,7 ms); maior = mais oscilacoes visiveis na tela.
 * WAVE_RING deve ser potencia de 2 e maior que WAVE_SPAN. */
#define WAVE_SPAN 1470
#define WAVE_RING 8192

static short wave_ring[WAVE_RING * 2];
static short wave_lin[WAVE_SPAN * 2];
static unsigned wave_pos = 0;

/* Ganho automatico do osciloscopio (mais movimento nas ondas) */
#define WAVE_TARGET   28000   /* pico alvo (max 32767) */
#define WAVE_MAX_GAIN 12      /* ganho maximo (x) */
#define WAVE_MIN_PEAK 1500    /* abaixo disso nao amplia mais (evita ruido) */

static int wave_peak[2] = { 0, 0 };

static void draw_waveform(const short *audio, int frames)
{
   int i, ch;
   int gain[2];
   unsigned start;

   for (i = 0; i < frames; i++)
   {
      unsigned p = wave_pos & (WAVE_RING - 1);
      wave_ring[p * 2]     = audio[i * 2];
      wave_ring[p * 2 + 1] = audio[i * 2 + 1];
      wave_pos++;
   }

   start = wave_pos - WAVE_SPAN;
   for (i = 0; i < WAVE_SPAN; i++)
   {
      unsigned p = (start + (unsigned)i) & (WAVE_RING - 1);
      wave_lin[i * 2]     = wave_ring[p * 2];
      wave_lin[i * 2 + 1] = wave_ring[p * 2 + 1];
   }

   for (ch = 0; ch < 2; ch++)
   {
      int pk = 0;
      for (i = 0; i < WAVE_SPAN; i++)
      {
         int s = wave_lin[i * 2 + ch];
         if (s < 0) s = -s;
         if (s > pk) pk = s;
      }
      wave_peak[ch] -= wave_peak[ch] / 32;      /* decai devagar */
      if (pk > wave_peak[ch]) wave_peak[ch] = pk;
      pk = wave_peak[ch];
      if (pk < WAVE_MIN_PEAK) pk = WAVE_MIN_PEAK;
      gain[ch] = (WAVE_TARGET * 256) / pk;      /* ponto fixo 8.8 */
      if (gain[ch] > WAVE_MAX_GAIN * 256) gain[ch] = WAVE_MAX_GAIN * 256;
      if (gain[ch] < 256) gain[ch] = 256;
   }

   draw_wave_channel(wave_lin, WAVE_SPAN, 0, WAVE_TOP, WAVE_H, get_color(10, 28, 31), gain[0]);
   draw_wave_channel(wave_lin, WAVE_SPAN, 1, WAVE_TOP + WAVE_H + WAVE_GAP, WAVE_H, get_color(28, 12, 27), gain[1]);
}


/* ---- navegador: janela com o conteudo do .zip atual ----
 * Largura reduzida em 30% e centralizada na tela (horizontal e vertical). */
#define BROWSER_ROWS   10   /* era 14: ~30% menos linhas visiveis */
#define BROWSER_ROW_H  26
#define BROWSER_BG_ALPHA  190  /* 0 = totalmente transparente, 255 = totalmente solido */
#define BROWSER_GLYPH_H   16   /* altura do glifo desenhado (fonte 8x8 em escala 2x) */
#define BROWSER_W      ((UI_W * 7) / 10)   /* largura reduzida em 30% */

static void draw_browser(void)
{
   int i, first, y;
   int visible = BROWSER_ROWS;
   int box_w = BROWSER_W, box_h;
   int box_x0, box_y0;
   char line[300];

   if (browser_count_ui < visible)
      visible = browser_count_ui;
   box_h = 40 + visible * BROWSER_ROW_H;

   /* centraliza a caixa na tela inteira (640x480) */
   box_x0 = (640 - box_w) / 2;
   box_y0 = (480 - box_h) / 2;

   first = browser_cursor - visible / 2;
   if (first > browser_count_ui - visible) first = browser_count_ui - visible;
   if (first < 0) first = 0;

   draw_shape_alpha(framebuffer, get_color(2,4,5),   BROWSER_BG_ALPHA, box_x0,   box_y0,   box_w,   box_h);
   draw_shape_alpha(framebuffer, get_color(6,12,14), BROWSER_BG_ALPHA, box_x0+2, box_y0+2, box_w-4, box_h-4);

   y = box_y0 + 20 + (BROWSER_ROW_H - BROWSER_GLYPH_H) / 2;
   for (i = first; i < first + visible && i < browser_count_ui; i++)
   {
      int is_sel = (i == browser_cursor);
      int is_dir = browser_entry_is_dir(i);
      int is_zip = browser_entry_is_zip(i);
      unsigned short col = is_sel ? get_color(31,63,20) : (is_dir ? get_color(28,50,31) : get_color(20,40,22));
      if (is_sel)
         draw_shape_alpha(framebuffer, get_color(10,20,15), BROWSER_BG_ALPHA, box_x0+4, y-4, box_w-8, BROWSER_ROW_H);
      snprintf(line, sizeof(line), "%s%s%s%s", is_sel ? "> " : "  ",
               browser_entry_name(i), is_dir ? "/" : "", is_zip ? "  [ZIP]" : "");
      draw_text_prop_clip(line, box_x0 + 12, y, col, box_x0 + box_w - 12);
      y += BROWSER_ROW_H;
   }
}

/* ---- janela de creditos (botao B, fora do navegador) ----
 * Mesma caixa centralizada/translucida do navegador de zip, com o texto
 * subindo de baixo pra cima continuamente, estilo creditos de filme. */

/* ------------------------------------------------------------------
 * TEXTO DAS INSTRUCOES (B) -- edite as linhas abaixo livremente.
 * Uma string por linha; "" = linha em branco (espaco entre paragrafos).
 * Linhas longas quebram sozinhas; 3+ espacos apos o 1o termo = 2 colunas.
 * A ordem de cima para baixo neste array e a ordem de exibicao (a
 * primeira linha e a primeira a subir e a primeira a sair pelo topo).
 * ------------------------------------------------------------------ */
static const char *credits_lines[] = {
   "=====================================================================================",
   "VGM'2 - INSTRUCTIONS",
   "=====================================================================================",
   "",
   "USE WITH JOYSTICK:",
   "",
   "Button START = Pause/Play",
   "Button SELECT = Load Track",
   "Button X  = MT32/GM/Fluidsynth",
   "Button B  = Instructions",
   "UP/DOWN   = Track Selection",
   "Button R1 = Next Track",
   "Button L1 = Rewind Track",
   "Button R1 = Fast Forward (Holding)",
   "Button L1 = Fast Rewind (Holding)",
   "Button R2 = Vol. +",
   "Button L2 = Vol. -",
   "",
   "CORE: gme2_libretro (fork) - SUPPORTED SYSTEMS AND CHIPS",
   "",
   "============================================================",
   "- ARCADE (VGM multichip, libvgm) 48 Chip/Drivers",
   "",
   "* SEGA",
   "SN76489    Assorted Sega signs",
   "YM2151     Sega System 16, X-Board, Y-Board",
   "YM2610     SNK Neo Geo MVS (Metal Slug, King of Fighters)...",
   "YM2612     Sega System C / C2",
   "SegaPCM    Out Run, After Burner, Space Harrier, Hang-On...",
   "RF5C68     Sega System 18 (Shadow Dancer), Sega System 32",
   "MultiPCM   Sega Model 1 e 2 / System 32",
   "SCSP       Sega Model 2 e 3",
   "uPD7759    Various Sega boards",
   "YMW258     Sega MultiPCM, (Virtua Fighter...),",
   "           Sega Model 2 (Daytona USA...)",
   "",
   "* KONAMI",
   "YM2151     Several Konami boards",
   "K051649    SCC (Also on MSX cartridges)",
   "K054539    Xexex, The Simpsons and others...",
   "K053260    Late-80s Konami...",
   "K007232    Contra, Super Contra, Gradius III...",
   "K005289    Boards GX400 (Gradius, Salamander...)",
   "",
   "* CAPCOM",
   "YM2151     CPS-1 (Street Fighter II), System 16 (Altered Beast...)",
   "YM2203     Ghosts 'n Goblins, 1942, Commando and others...",
   "OKIM6295   CPS1, Final Fight, Ghouls 'n Ghosts...",
   "QSound     CPS2, Marvel vs. Capcom, S. Street Fighter II Turbo...",
   "           CPS-1, (Cadillacs and Dinosaurs...)",
   "",
   "* NAMCO",
   "YM2151     System 2",
   "C140       System 2 and System 21",
   "C352       System 22 and Super System 23",
   "",
   "* TAITO",
   "YM2203     Various boards...",
   "YM3812     Toaplan (Truxton), Data East (Robocop...)",
   "YM3526     Taito / Data East",
   "MSM5232    Boards Taito",
   "MSM5205    Double Dragon, Moon Patrol, Karate Champ...",
   "",
   "* IREM / SETA / JALECO / SEIBU",
   "GA20       Irem (M92 and others)",
   "X1-010     Seta",
   "YMF271     Jaleco / Seibu, IBM-PC Doom, (Sound Blaster Pro)",
   "",
   "* CAVE / IGS / Others",
   "YMZ280B    Cave (DonPachi, DoDonPachi) and others",
   "OKIM6295   Cave, Data East and many others",
   "ICS2115    IGS PGM (Oriental Legend, Knights of Valour)",
   "ES5506     Ensoniq and some arcade games",
   "BSMT2000   Battletoads, Pinballs Data East/Sega/Stern.",
   "",
   "* ATARI",
   "POKEY      Centipede, Missile Command and others",
   "",
   "* PSG GENERIC",
   "AY8910     Countless arcades and microcomputers",
   "",
   "=====================================================================================",
   "CONSOLES AND HANDHELDS (fixed audio chip)",
   "",
   "GBS        Game Boy                 Chip: DMG",
   "NSF/NSFE   Nintendo NES / Famicom   Chip: 2A03 + Expansions",
   "HES        PC Engine / TurboGrafx   Chip: HuC6280",
   "SPC        Super Nintendo           Chip: S-SMP + S-DSP",
   "GYM        Sega Genesis/Mega Drive  Chip: YM2612 + SN76489",
   "",
   "* ALSO VIA VGM (MULTICHIP)",
   "",
   "Master System / Game Gear - SN76489, YM2413",
   "Mega Drive - YM2612, SN76489",
   "Sega CD - RF5C164",
   "Sega 32X - PWM",
   "Sega Saturn - SCSP",
   "Sega Pico - VGM",
   "Game Boy - GB DMG",
   "Game Boy Color - VGM",
   "NES / Famicom - NES APU",
   "Famicom Disk System - VGM",
   "PC Engine - HuC6280",
   "PC Engine CD-ROM2 - VGM",
   "Atari Lynx - Mikey",
   "FM Towns - VGM",
   "Virtual Boy - VSU-VUE",
   "WonderSwan - WonderSwan",
   "Neo-Geo (AES/MVS) - YM2610",
   "Neo-Geo Pocket - VGM",
   "Vectrex - VGM",
   "",
   "=====================================================================================",
   "HOME COMPUTERS",
   "",
   "AY         ZX Spectrum / Amstrad CPC - Chip: AY-3-8910",
   "KSS        MSX 1/2 (SMS, Game Gear, ColecoVision)",
   "           Chips: PSG, SCC, FM-PAC",
   "SAP        Atari XL/XE (8 bits) = Chip: POKEY",
   "",
   "* ALSO VIA VGM (MULTICHIP)",
   "",
   "MSX 1/2 - AY8910, K051649 (SCC), YM2413 (MSX-MUSIC),",
   "    Y8950 (MSX-Audio)",
   "NEC PC-88 / PC-98 - YM2203, YM2608",
   "Sharp X1 Turbo - VGM",
   "Sharp X68000 - YM2151, OKIM6258",
   "Fujitsu FM Towns - RF5C68",
   "Apple IIGS - ES5503",
   "Atari-ST - VGM",
   "Sam Coupe - SAA1099",
   "IBM PC (AdLib / Sound Blaster) - YM3812 (OPL2), YMF262 (OPL3)",
   "MoonSound (MSX) - YMF278B (OPL4)",
   "BBC Micro / ColecoVision - SN76489",
   "",
   "=====================================================================================",
   "ADDITIONAL IMPLEMENTATIONS",
   "",
   "MOD. Amiga MODULES / Mixing Paula \"Autodetect\" (.mod.s3m.xm.it)",
   "MIDI. General MIDI / Roland-MT-32 / Fluidsynth \"Autodetect\" (.mid)",
   "MPEG-1 Audio Layer III (.mp3)",
   "",
   "* The VMG2 accepts .zip files for loading music, supporting multiple tracks within a single .zip file as well as folders and subfolders!",
   "",
   "=====================================================================================",
   "VIDEO GAME MUSIC 2 (2026) by MTN ^_^",
   "=====================================================================================",
   "",
   "",
};
#define CREDITS_LINE_COUNT ((int)(sizeof(credits_lines) / sizeof(credits_lines[0])))

#define CREDITS_W          ((UI_W * 8) / 10)
#define CREDITS_H          360
#define CREDITS_MARGIN     14   /* margem lateral; as barras "=====" vao de x0+MARGIN ate x0+W-MARGIN */
#define CREDITS_INNER_W    (CREDITS_W - 2 * CREDITS_MARGIN)
#define CREDITS_LINE_H     ((CREDITS_TEXT_PX * 3) / 2)   /* 12 px com o texto em 8 px */
#define CREDITS_BG_ALPHA   210
#define CREDITS_IMG_ALPHA  253  /* alpha real do fundo22.png (0-255), lido do canal alfa do PNG;
                                    usado para misturar a imagem com o que ja esta no framebuffer */
#define CREDITS_SPEED_Q8   (CREDITS_TEXT_PX * 15)   /* ponto fixo 8.8: 120/256 = 0,469 px/frame (~28 px/s a 60 fps) com texto de 8 px (+25% sobre o *12 anterior).
                                                        Era *8 (64); aumente/diminua o multiplicador para acelerar/frear */

/* tamanho (em px de tela) de cada glifo do CORPO do texto dos creditos (fonte base 8x8).
   USE SOMENTE 8 (escala 1x) OU 16 (escala 2x): sao os unicos tamanhos em que cada pixel da
   fonte vira um numero inteiro de pixels de tela. Tamanhos intermediarios (ex.: 12) fazem a
   amostragem "do vizinho mais proximo" alternar pixels de 1 e 2 px -> letras tortas/entupidas.
   Altura da linha, 2a coluna e velocidade de rolagem se ajustam sozinhas a este valor.
   O TITULO tambem usa so escala inteira (ver credits_chip_draw_line mais abaixo). */
#define CREDITS_TEXT_PX 8

/* logo "Video Game Music 2" no topo do texto que sobe (credits_logo.h, 264x132 px).
   Medido na foto de referencia: logo centralizado na caixa e 75 px entre a base dele e a
   1a barra "=====" (o logo sobe junto com o texto). CREDITS_LOGO_ROWS = linhas em branco
   reservadas no inicio do texto para o logo caber acima da barra, com CREDITS_LOGO_TOP_MARGIN
   px livres acima dele. */
#define CREDITS_LOGO_GAP         75
#define CREDITS_LOGO_TOP_MARGIN  12
#define CREDITS_LOGO_ROWS  ((CREDITS_LOGO_TOP_MARGIN + CREDITS_LOGO_GAP + CREDITS_LOGO_H - (CREDITS_LINE_H / 2 - 1) + CREDITS_LINE_H - 1) / CREDITS_LINE_H)

/* como put_glyph (usado pelo cabecalho), mas em escala CREDITS_TEXT_PX/8 (amostragem do
   vizinho mais proximo, funciona para qualquer tamanho) e com clip vertical tambem
   (aqui o texto precisa ser cortado no topo/base da caixa, nao so nas laterais) */
static void credits_put_glyph(unsigned char ch, int px, int py, unsigned short color,
                               int cx0, int cx1, int cy0, int cy1)
{
   int ox, oy;
   int charx = (ch % 16) * 8;
   int chary = (ch >> 4) * 8;
   for (oy = 0; oy < CREDITS_TEXT_PX; oy++)
   {
      int yy = py + oy;
      int sy = (oy * 8) / CREDITS_TEXT_PX;
      if (yy < cy0 || yy >= cy1)
         continue;
      for (ox = 0; ox < CREDITS_TEXT_PX; ox++)
      {
         int xx = px + ox;
         int sx = (ox * 8) / CREDITS_TEXT_PX;
         if (xx < cx0 || xx >= cx1)
            continue;
         if (is_font_pixel(charx + sx, chary + sy))
            set_pixel(framebuffer, xx, yy, color);
      }
   }
}

/* largura proporcional de 'text' no tamanho do corpo (CREDITS_TEXT_PX), equivalente a
   text_width_prop() mas na escala menor usada pelos creditos */
static int credits_text_width(const char *text)
{
   int w = 0, x0, x1;
   for (; *text; text++)
   {
      glyph_extent((unsigned char)*text, &x0, &x1);
      w += (x1 < 0) ? 4 : (x1 - x0 + 2);
   }
   w = w > 0 ? w - 1 : 0;
   return (w * CREDITS_TEXT_PX) / 8;
}

/* desenha texto a partir de x (canto esquerdo), cortado na caixa (cx0..cx1, cy0..cy1) */
static void credits_draw_text_at(const char *text, int x, int y, unsigned short color,
                                  int cx0, int cx1, int cy0, int cy1)
{
   int x0, x1;
   for (; *text; text++)
   {
      unsigned char ch = (unsigned char)*text;
      glyph_extent(ch, &x0, &x1);
      if (x1 < 0)
      {
         x += (4 * CREDITS_TEXT_PX) / 8;
         continue;
      }
      credits_put_glyph(ch, x - (x0 * CREDITS_TEXT_PX) / 8, y, color, cx0, cx1, cy0, cy1);
      x += ((x1 - x0 + 2) * CREDITS_TEXT_PX) / 8;
   }
}

/* titulos. Mesma fonte/degrade do CHIP: no cabecalho (Press Start 2P, azul->branco no
   topo e dourado->creme na base, ver chip_grad_init()).
   - titulo inicial ("VGM'2 - INSTRUCTIONS", accent = 2): grande. Altura sempre
     2x (crisp); a LARGURA e a maior que cabe entre as barras (credits_title_hsq, Q8: 512 = 2x
     inteiro como antes, menor = fonte levemente condensada, calculada em credits_build_rows()).
     Todas as letras usam o mesmo padrao de colunas, entao ficam iguais entre si. Ocupa 2 linhas.
   - titulo final (accent = 1): 1x, com CREDITS_TITLE_TRACK px extras entre as letras,
     centralizado (nao precisa chegar ate as pontas das barras). */
#define CREDITS_TITLE_TRACK 2

static int credits_title_hsq = 512;   /* escala horizontal do titulo grande, ponto fixo Q8 */

/* texto usado so para DEFINIR o tamanho do titulo grande (o que o titulo antigo tinha). Nao aparece
   na tela: o que aparece e a 1a linha de credits_lines[] que comeca com "VGM'2" ou "VIDEO GAME MUSIC 2". */
#define CREDITS_TITLE_REF "VIDEO GAME MUSIC 2 - INSTRUCTIONS"

/* largura (px de tela) de 'text': cada letra avanca ((x1-x0+2)*hsq)>>8 px, mesma conta do desenho */
static int credits_chip_width(const char *text, int hsq, int track)
{
   int x0, x1, w = 0, n = (int)strlen(text);
   for (; *text; text++)
   {
      chip_extent((unsigned char)*text, &x0, &x1);
      w += (x1 < 0) ? (CHIP_SPACE * hsq) >> 8 : ((x1 - x0 + 2) * hsq) >> 8;
   }
   w -= (hsq >> 8);                      /* sem o espaco depois da ultima letra */
   return w + track * (n > 0 ? n - 1 : 0);
}

/* desenha a letra com origem ox (esquerda da tinta), colunas x0..x1 da fonte em escala hsq (Q8)
   na horizontal e vsc (inteiro) na vertical */
static void credits_chip_put_glyph(unsigned char ch, int x0, int ox, int py, int hsq, int vsc,
                                    int cx0, int cx1, int cy0, int cy1)
{
   int gx, gy, xx, yy;
   for (gx = x0; gx < 8; gx++)
   {
      int xa = ox + (((gx - x0) * hsq) >> 8);
      int xb = ox + (((gx - x0 + 1) * hsq) >> 8);
      for (gy = 0; gy < 8; gy++)
      {
         if (!chip_pixel(ch, gx, gy))
            continue;
         for (yy = py + gy * vsc; yy < py + (gy + 1) * vsc; yy++)
         {
            if (yy < cy0 || yy >= cy1)
               continue;
            for (xx = xa; xx < xb; xx++)
            {
               if (xx < cx0 || xx >= cx1)
                  continue;
               set_pixel(framebuffer, xx, yy, chip_grad[gy]);
            }
         }
      }
   }
}

/* centralizada entre as barras (left .. left + CREDITS_INNER_W) */
static void credits_chip_draw_line(const char *text, int left, int y, int big,
                                    int cx0, int cx1, int cy0, int cy1)
{
   int x0, x1;
   const int hsq   = big ? credits_title_hsq : 256;
   const int vsc   = big ? 2 : 1;
   const int track = big ? 0 : CREDITS_TITLE_TRACK;
   const int n     = (int)strlen(text);
   const int width = credits_chip_width(text, hsq, track);
   const int sx0   = left + (CREDITS_INNER_W - width) / 2;
   const int rowh  = big ? 2 * CREDITS_LINE_H : CREDITS_LINE_H;   /* o titulo grande ocupa 2 linhas */
   const int py    = y + (rowh - 8 * vsc) / 2;
   int u = 0, i;
   chip_grad_init();
   for (i = 0; i < n; i++)
   {
      unsigned char ch = (unsigned char)text[i];
      chip_extent(ch, &x0, &x1);
      if (x1 < 0)
      {
         u += (CHIP_SPACE * hsq) >> 8;
         continue;
      }
      credits_chip_put_glyph(ch, x0, sx0 + u + track * i, py, hsq, vsc, cx0, cx1, cy0, cy1);
      u += ((x1 - x0 + 2) * hsq) >> 8;
   }
}

/* fundo (imagem) da janela de creditos, RGB565 -> cor da plataforma via get_color(),
   com cache estatico decodificado uma unica vez (mesmo padrao de spectrum_draw_background
   em spectrum.c). CREDITS_BG_W/H (460x360, ver credits_bg.h) batem exatamente com
   CREDITS_W/CREDITS_H, entao a imagem preenche a caixa toda sem escalar.
   O fundo2.png original tem um canal alfa uniforme (246/255); em vez de gravar
   a imagem por cima do framebuffer, cada pixel e misturado (blend) com o que ja
   esta desenhado ali (fundo/espectro por baixo da janela) usando esse mesmo alfa,
   preservando a transparencia real da imagem. */
static void draw_credits_background(int x0, int y0)
{
   static unsigned short cache[CREDITS_BG_W * CREDITS_BG_H];
   static int ready = 0;
   int xx, yy;
   uint16_t *px = (uint16_t *)framebuffer->pixel_data;

   if (!ready)
   {
      int i;
      for (i = 0; i < CREDITS_BG_W * CREDITS_BG_H; i++)
      {
         unsigned short v = credits_bg_pixels[i];
         cache[i] = get_color((v >> 11) & 31, (v >> 5) & 63, v & 31);
      }
      ready = 1;
   }

   for (yy = 0; yy < CREDITS_BG_H; yy++)
      for (xx = 0; xx < CREDITS_BG_W; xx++)
      {
         unsigned short img = cache[xx + yy * CREDITS_BG_W];
         uint16_t *dst = &px[(x0 + xx) + (y0 + yy) * framebuffer->width];
         unsigned short bg = *dst;

         int ir = (img >> 11) & 31, ig = (img >> 5) & 63, ib = img & 31;
         int br = (bg  >> 11) & 31, bg_g = (bg >> 5) & 63, bb = bg & 31;

         int r = (ir * CREDITS_IMG_ALPHA + br   * (255 - CREDITS_IMG_ALPHA)) / 255;
         int g = (ig * CREDITS_IMG_ALPHA + bg_g * (255 - CREDITS_IMG_ALPHA)) / 255;
         int b = (ib * CREDITS_IMG_ALPHA + bb   * (255 - CREDITS_IMG_ALPHA)) / 255;

         *dst = get_color(r, g, b);
      }
}

/* logo com transparencia (alpha 0..255 por pixel), recortado a area y0..y1 da caixa */
static void draw_credits_logo(int x0, int y0, int cy0, int cy1)
{
   static unsigned short cache[CREDITS_LOGO_W * CREDITS_LOGO_H];
   static int ready = 0;
   int xx, yy;
   uint16_t *px = (uint16_t *)framebuffer->pixel_data;

   if (!ready)
   {
      int i;
      for (i = 0; i < CREDITS_LOGO_W * CREDITS_LOGO_H; i++)
      {
         unsigned short v = credits_logo_rgb[i];
         cache[i] = get_color((v >> 11) & 31, (v >> 5) & 63, v & 31);
      }
      ready = 1;
   }

   for (yy = 0; yy < CREDITS_LOGO_H; yy++)
   {
      int y = y0 + yy;
      if (y < cy0 || y >= cy1)
         continue;
      for (xx = 0; xx < CREDITS_LOGO_W; xx++)
      {
         int a = credits_logo_alpha[xx + yy * CREDITS_LOGO_W];
         unsigned short img, bg;
         uint16_t *dst;
         int ir, ig, ib, br, bg_g, bb;

         if (!a)
            continue;
         img = cache[xx + yy * CREDITS_LOGO_W];
         dst = &px[(x0 + xx) + y * framebuffer->width];
         bg  = *dst;

         ir = (img >> 11) & 31; ig = (img >> 5) & 63; ib = img & 31;
         br = (bg  >> 11) & 31; bg_g = (bg >> 5) & 63; bb = bg & 31;

         *dst = get_color((ir * a + br   * (255 - a)) / 255,
                          (ig * a + bg_g * (255 - a)) / 255,
                          (ib * a + bb   * (255 - a)) / 255);
      }
   }
}

/* sprite animado (credits_sonic.h, 56x63 px, 4 quadros de 60 ms). Sobe junto com o texto: a
   posicao vertical vem da secao (credits_secs[0], centralizado entre as barras); CREDITS_SONIC_X e a
   posicao horizontal (a partir do canto esquerdo da caixa, 460x360), usada por todos os sprites. */
#define CREDITS_SONIC_X       391
#define CREDITS_SONIC_ANCHOR  "USE WITH JOYSTICK:"
#define CREDITS_GREEN_TXT     CREDITS_SONIC_ANCHOR   /* linha desenhada em verde */
#define CREDITS_GREEN         get_color(5, 56, 14)   /* verde do equalizador */

static void draw_credits_sonic(int x0, int y0, int cx0, int cx1, int cy0, int cy1)
{
   static unsigned short cache[CREDITS_SONIC_FRAMES][CREDITS_SONIC_W * CREDITS_SONIC_H];
   static int ready = 0;
   int xx, yy;
   /* quadro atual: 60 ms = 3,6 frames de video a 60 fps */
   int f = (((credits_anim % 3600) * 1000 / 60) / CREDITS_SONIC_MS) % CREDITS_SONIC_FRAMES;   /* %3600 (60 s) evita estouro e emenda sem corte */

   if (!ready)
   {
      int k, i;
      for (k = 0; k < CREDITS_SONIC_FRAMES; k++)
         for (i = 0; i < CREDITS_SONIC_W * CREDITS_SONIC_H; i++)
         {
            unsigned short v = credits_sonic_rgb[k][i];
            cache[k][i] = get_color((v >> 11) & 31, (v >> 5) & 63, v & 31);
         }
      ready = 1;
   }

   for (yy = 0; yy < CREDITS_SONIC_H; yy++)
   {
      int y = y0 + yy;
      if (y < cy0 || y >= cy1)
         continue;
      for (xx = 0; xx < CREDITS_SONIC_W; xx++)
      {
         int x = x0 + xx;
         if (x < cx0 || x >= cx1)
            continue;
         if (credits_sonic_alpha[f][xx + yy * CREDITS_SONIC_W])
            set_pixel(framebuffer, x, y, cache[f][xx + yy * CREDITS_SONIC_W]);
      }
   }
}

/* ---- layout do texto: quebra automatica de linha e colunas ----
 * O texto em credits_lines[] e "cru" (igual ao .txt). Na primeira vez que a janela
 * abre ele e convertido em linhas de tela (credits_rows) que cabem na caixa:
 *  - 3+ espacos seguidos apos o 1o termo  -> 2 colunas (ex.: "YM2151     Sega ...")
 *  - "=====" / "-----"                    -> linha horizontal
 *  - "VGM'2 ..." / "VIDEO GAME MUSIC 2 ..."     -> titulo (fonte do CHIP) centralizado
 *  - amarelo so em "* ..." e no titulo logo abaixo de uma barra
 *  - linhas longas quebram no espaco (com recuo nas continuacoes) */
#define CREDITS_COL2_X     (CREDITS_TEXT_PX * 7)   /* inicio da 2a coluna, em px a partir da margem (84 com texto de 12 px, 56 com 8 px) */
#define CREDITS_MAX_ROWS   500
#define CREDITS_ROW_CHARS  96

enum { CR_TEXT, CR_TITLE, CR_RULE, CR_BLANK };

typedef struct
{
   unsigned char kind;
   unsigned char accent;
   int  x;                       /* recuo de c2 em px, a partir da margem */
   char c1[16];                  /* coluna 1 (opcional), na margem */
   char c2[CREDITS_ROW_CHARS];   /* texto principal */
} credits_row_t;

static credits_row_t credits_rows[CREDITS_MAX_ROWS];
static int credits_row_count = 0;
static int credits_rows_built = 0;

static void credits_add_row(int kind, int accent, int x, const char *c1, const char *c2)
{
   credits_row_t *r;
   if (credits_row_count >= CREDITS_MAX_ROWS)
      return;
   r = &credits_rows[credits_row_count++];
   memset(r, 0, sizeof(*r));
   r->kind = (unsigned char)kind;
   r->accent = (unsigned char)accent;
   r->x = x;
   if (c1)
      strncpy(r->c1, c1, sizeof(r->c1) - 1);
   if (c2)
      strncpy(r->c2, c2, sizeof(r->c2) - 1);
}

/* quebra 's' em linhas de no maximo 'avail' px (por palavras) */
static void credits_wrap(const char *s, int avail, int kind, int first_x, int cont_x,
                          int accent, const char *c1)
{
   char line[CREDITS_ROW_CHARS];
   char trial[CREDITS_ROW_CHARS * 2];
   char word[CREDITS_ROW_CHARS];
   int first = 1, n = 0;

   line[0] = 0;
   while (*s)
   {
      int wl = 0;
      while (*s == ' ')
         s++;
      if (!*s)
         break;
      while (*s && *s != ' ' && wl < CREDITS_ROW_CHARS - 1)
         word[wl++] = *s++;
      word[wl] = 0;

      strcpy(trial, line);
      if (n)
         strcat(trial, " ");
      strcat(trial, word);

      if (n && (credits_text_width(trial) > avail || strlen(trial) >= CREDITS_ROW_CHARS - 1))
      {
         credits_add_row(kind, accent, first ? first_x : cont_x, first ? c1 : NULL, line);
         first = 0;
         strcpy(line, word);
         n = (int)strlen(line);
      }
      else
      {
         strcpy(line, trial);
         n = (int)strlen(line);
      }
   }
   if (n)
      credits_add_row(kind, accent, first ? first_x : cont_x, first ? c1 : NULL, line);
}

/* 2+ espacos viram 1; 3+ espacos viram 'sep' (se sep != NULL); 4+ pontos viram "..." */
static void credits_squeeze(const char *src, char *dst, int cap, const char *sep)
{
   int n = 0;
   while (*src && n < cap - 5)
   {
      if (*src == ' ')
      {
         int run = 0;
         while (src[run] == ' ')
            run++;
         if (run >= 3 && sep)
         {
            const char *q = sep;
            while (*q && n < cap - 5)
               dst[n++] = *q++;
         }
         else
            dst[n++] = ' ';
         src += run;
      }
      else if (src[0] == '.' && src[1] == '.' && src[2] == '.' && src[3] == '.')
      {
         while (*src == '.')
            src++;
         dst[n++] = '.';
         dst[n++] = '.';
         dst[n++] = '.';
      }
      else
         dst[n++] = *src++;
   }
   dst[n] = 0;
}

static int credits_is_rule(const char *s)
{
   int n = 0;
   for (; *s; s++, n++)
      if (*s != '=' && *s != '-')
         return 0;
   return n >= 5;
}

static void credits_build_rows(void)
{
   int i, after_rule = 0, first_title_done = 0;
   credits_row_count = 0;

   /* espaco no topo para o logo (desenhado em draw_credits) */
   for (i = 0; i < CREDITS_LOGO_ROWS; i++)
      credits_add_row(CR_BLANK, 0, 0, NULL, "");

   for (i = 0; i < CREDITS_LINE_COUNT; i++)
   {
      const char *s = credits_lines[i];
      char c1[16];
      char rest[256];
      int k, accent, lead = 0;
      int below_rule = after_rule;   /* linha logo abaixo de uma barra "=====" */

      while (s[lead] == ' ')
         lead++;
      s += lead;

      if (!*s)
      {
         credits_add_row(CR_BLANK, 0, 0, NULL, "");
         after_rule = 0;
         continue;
      }
      if (credits_is_rule(s))
      {
         credits_add_row(CR_RULE, 0, 0, NULL, "");
         after_rule = 1;
         continue;
      }
      after_rule = 0;

      /* titulos ("VGM'2 ..." / "VIDEO GAME MUSIC 2 ..."): uma unica linha, sem quebra, na fonte do
         CHIP e centralizados; o tamanho vem de CREDITS_TITLE_REF (fim desta funcao) */
      if (strncmp(s, "VGM'2", 5) == 0 || strncmp(s, "VIDEO GAME MUSIC 2", 18) == 0)
      {
         if (!first_title_done)
         {
            credits_add_row(CR_TITLE, 2, 0, NULL, s);   /* grande (2x), ocupa esta linha + a proxima */
            credits_add_row(CR_BLANK, 0, 0, NULL, "");
            first_title_done = 1;
         }
         else
            credits_add_row(CR_TITLE, 1, 0, NULL, s);   /* pequeno (1x) */
         continue;
      }

      /* linha de continuacao (3+ espacos de recuo no .txt): fica alinhada na 2a coluna */
      if (lead >= 3)
      {
         credits_squeeze(s, rest, sizeof(rest), " ");
         credits_wrap(rest, CREDITS_INNER_W - CREDITS_COL2_X, CR_TEXT,
                      CREDITS_COL2_X, CREDITS_COL2_X, 0, NULL);
         continue;
      }

      /* 2 colunas: 1o termo + 3 ou mais espacos */
      for (k = 1; s[k]; k++)
         if (s[k] == ' ' && s[k + 1] == ' ' && s[k + 2] == ' ')
            break;
      if (s[k] && k < (int)sizeof(c1))
      {
         const char *p = s + k;
         memcpy(c1, s, k);
         c1[k] = 0;
         if (credits_text_width(c1) <= CREDITS_COL2_X - (CREDITS_TEXT_PX * 2) / 3)
         {
            while (*p == ' ')
               p++;
            credits_squeeze(p, rest, sizeof(rest), " - ");
            credits_wrap(rest, CREDITS_INNER_W - CREDITS_COL2_X, CR_TEXT,
                         CREDITS_COL2_X, CREDITS_COL2_X, 0, c1);
            continue;
         }
      }

      /* linha corrida (quebra com recuo nas continuacoes).
         Amarelo SOMENTE no titulo logo abaixo de uma barra; linhas que comecam com "* " sao verdes. */
      credits_squeeze(s, rest, sizeof(rest), " ");
      /* accent: 3 = linha "* ..." (verde), 1 = titulo logo abaixo de uma barra (amarelo), 0 = normal.
         As linhas de continuacao (quebra automatica) herdam o mesmo valor. */
      accent = (s[0] == '*' && s[1] == ' ') ? 3 : (below_rule ? 1 : 0);
      credits_wrap(rest, CREDITS_INNER_W, CR_TEXT, 0, CREDITS_TEXT_PX, accent, NULL);
   }

   /* titulo grande: mantem o tamanho (escala) que o titulo antigo "VIDEO GAME MUSIC 2 - INSTRUCTIONS"
      tinha (2x de altura, largura maxima que cabia entre as barras). O texto novo, mais curto, usa
      essa mesma escala e fica centralizado entre as barras. Se algum dia for maior que as barras,
      o laco abaixo ainda o condensa ate caber. */
   {
      int r;
      credits_title_hsq = 512;
      while (credits_title_hsq > 256 &&
             credits_chip_width(CREDITS_TITLE_REF, credits_title_hsq, 0) > CREDITS_INNER_W)
         credits_title_hsq--;
      for (r = 0; r < credits_row_count; r++)
         if (credits_rows[r].kind == CR_TITLE && credits_rows[r].accent == 2)
            while (credits_title_hsq > 256 &&
                   credits_chip_width(credits_rows[r].c2, credits_title_hsq, 0) > CREDITS_INNER_W)
               credits_title_hsq--;
   }
}

/* --- sprites extras (credits_sprites.h: 02 a 09, 11 e 12.gif), mesmo tamanho de celula do Sonic (56x63) ---
   Tambem sobem junto com o texto e ficam na mesma coluna do Sonic (CREDITS_SONIC_X).
   Cada SECAO (Sonic/instrucoes, ARCADE, CONSOLES, HOME COMPUTERS, ADDITIONAL) e o trecho entre a
   barra "=====" que a abre e a barra seguinte. Os sprites da secao ficam CENTRALIZADOS de cima a
   baixo entre as duas barras: com N sprites, os N+1 espacos (acima, entre eles e abaixo) sao iguais.
   A barra de inicio e achada pelo texto da secao (credits_secs[].txt = inicio do texto de uma linha
   dela; a barra e a primeira "=====" acima dessa linha), entao mudar o texto dos creditos nao quebra
   o alinhamento enquanto esses textos continuarem iguais.
   spr[] = indices em credits_sprites[] (0 = 02.gif ... 7 = 09.gif, 8 = 12.gif, 9 = 11.gif); -1 = o Sonic (credits_sonic.h). */
#define CREDITS_SEC_N        5
#define CREDITS_SEC_MAX_SPR  5

typedef struct
{
   const char *txt;       /* inicio do texto de uma linha da secao (acha a barra que a abre) */
   const char *end_txt;   /* se != NULL: a secao termina no TOPO da linha que comeca com este texto
                             (em vez de na proxima barra) */
   int n;
   signed char spr[CREDITS_SEC_MAX_SPR];
} credits_sec_t;

static const credits_sec_t credits_secs[CREDITS_SEC_N] = {
   { CREDITS_SONIC_ANCHOR, NULL, 1, { -1 } },              /* Sonic */
   { "- ARCADE",           NULL, 5, { 0, 1, 2, 3, 4 } },   /* Mario Kart, Dhalsim, Pac-Man, Chun-Li, Sakura */
   { "CONSOLES AND",       NULL, 2, { 5, 8 } },            /* Ken, Mega Man X (12.gif) */
   { "HOME COMPUTERS",     NULL, 2, { 6, 9 } },            /* 08.gif, 11.gif (nave) */
   /* Insert Coin: centralizado entre a barra e o texto amarelo "* The VMG2 accepts..." */
   { "ADDITIONAL IMPL",    "* The VMG2", 1, { 7 } }
};

/* desenha o sprite 'idx' na celula 56x63 cujo canto superior esquerdo e (x0, y0); o sprite fica
   centralizado na celula. A animacao usa a duracao de cada quadro do GIF original. */
static void draw_credits_sprite(int idx, int x0, int y0, int cx0, int cx1, int cy0, int cy1)
{
   const credits_sprite_t *sp = &credits_sprites[idx];
   int t = (int)((((long long)credits_anim * 1000) / 60) % sp->total_ms);
   int step = 0, xx, yy, ox, oy;
   const unsigned short *pix;

   while (step < sp->steps - 1 && t >= sp->end_ms[step])
      step++;
   pix = sp->pix + (unsigned)sp->seq[step] * sp->w * sp->h;
   ox  = x0 + (CREDITS_SPR_CELL_W - sp->w) / 2;
   oy  = y0 + (CREDITS_SPR_CELL_H - sp->h) / 2;

   for (yy = 0; yy < sp->h; yy++)
   {
      int y = oy + yy;
      if (y < cy0 || y >= cy1)
         continue;
      for (xx = 0; xx < sp->w; xx++)
      {
         unsigned short v = pix[xx + yy * sp->w];
         int x = ox + xx;
         if (!v || x < cx0 || x >= cx1)   /* 0 = transparente */
            continue;
         set_pixel(framebuffer, x, y, get_color((v >> 11) & 31, (v >> 5) & 63, v & 31));
      }
   }
}

static void draw_credits(void)
{
   int box_w = CREDITS_W, box_h = CREDITS_H;
   int box_x0 = (640 - box_w) / 2;
   int box_y0 = (480 - box_h) / 2;
   int left = box_x0 + CREDITS_MARGIN;
   int cx0 = box_x0 + 8, cx1 = box_x0 + box_w - 8;
   int cy0 = box_y0 + 4, cy1 = box_y0 + box_h - 4;
   int content_h, total_scroll, offset, i;

   if (!credits_rows_built)
   {
      credits_build_rows();
      credits_rows_built = 1;
   }

   content_h    = credits_row_count * CREDITS_LINE_H;
   total_scroll = box_h + content_h;   /* percurso: entra por baixo, sai por cima */
   offset = ((credits_frame * CREDITS_SPEED_Q8) / 256) % total_scroll;

   draw_credits_background(box_x0, box_y0);
   /* fundo2.png ja traz a transparencia/esmaecimento desejado embutido na
      propria imagem, entao nenhum escurecimento extra e aplicado por cima
      (o antigo overlay CREDITS_IMG_DARKEN_ALPHA foi removido). */
   draw_box(framebuffer, get_color(14, 28, 18), box_x0, box_y0, box_x0 + box_w - 1, box_y0 + box_h - 1);

   /* logo: centralizado na caixa, sobe junto com o texto; sua base fica CREDITS_LOGO_GAP px
      acima da 1a barra (que esta na linha CREDITS_LOGO_ROWS, a LINE_H/2-1 px do topo dela) */
   {
      int logo_y = box_y0 + box_h - offset + CREDITS_LOGO_ROWS * CREDITS_LINE_H
                 + (CREDITS_LINE_H / 2 - 1) - CREDITS_LOGO_GAP - CREDITS_LOGO_H;
      if (logo_y < cy1 && logo_y + CREDITS_LOGO_H > cy0)
         draw_credits_logo(box_x0 + (box_w - CREDITS_LOGO_W) / 2, logo_y, cy0, cy1);
   }

   for (i = 0; i < credits_row_count; i++)
   {
      const credits_row_t *r = &credits_rows[i];
      int y = box_y0 + box_h - offset + i * CREDITS_LINE_H;
      unsigned short color = r->accent ? get_color(31, 52, 6) : get_color(29, 58, 25);

      /* verde (mesmo do equalizador): linhas que comecam com "* " (accent 3) e a linha
         "USE WITH JOYSTICK:" */
      if (r->kind == CR_TEXT &&
          (r->accent == 3 || strncmp(r->c2, CREDITS_GREEN_TXT, strlen(CREDITS_GREEN_TXT)) == 0))
         color = CREDITS_GREEN;

      if (y < box_y0 - 2 * CREDITS_LINE_H || y > box_y0 + box_h)
         continue;

      switch (r->kind)
      {
         case CR_TITLE:
            /* fonte/degrade do CHIP: em vez da fonte normal (cor 'color' ignorada aqui) */
            credits_chip_draw_line(r->c2, left, y, r->accent == 2, cx0, cx1, cy0, cy1);
            break;
         case CR_RULE:
         {
            int ry = y + CREDITS_LINE_H / 2 - 1, rx;
            if (ry >= cy0 && ry < cy1)
               for (rx = left; rx < box_x0 + box_w - CREDITS_MARGIN; rx++)
                  set_pixel(framebuffer, rx, ry, get_color(14, 28, 18));
            break;
         }
         case CR_TEXT:
            if (r->c1[0])
               credits_draw_text_at(r->c1, left, y, color, cx0, cx1, cy0, cy1);
            credits_draw_text_at(r->c2, left + r->x, y, color, cx0, cx1, cy0, cy1);
            break;
         default:
            break;
      }
   }

   /* sprites animados: acompanham o texto, por cima dele */
   {
      static int sec_bar0[CREDITS_SEC_N];   /* linha (credits_rows) da barra que abre a secao, -1 = nao achou */
      static int sec_bar1[CREDITS_SEC_N];   /* linha que fecha a secao: barra seguinte ou linha de end_txt */
      static int sec_end_is_text[CREDITS_SEC_N];   /* 1 = sec_bar1 e uma linha de texto (usa o topo dela) */
      static int sec_ready = 0;
      int base = box_y0 + box_h - offset;
      int k, n;

      if (!sec_ready)
      {
         for (k = 0; k < CREDITS_SEC_N; k++)
         {
            int j, len = (int)strlen(credits_secs[k].txt);
            sec_bar0[k] = sec_bar1[k] = -1;
            for (j = 0; j < credits_row_count; j++)
               if (strncmp(credits_rows[j].c2, credits_secs[k].txt, len) == 0)
                  break;
            if (j >= credits_row_count)
               continue;
            while (j >= 0 && credits_rows[j].kind != CR_RULE)   /* barra acima da linha */
               j--;
            if (j < 0)
               continue;
            sec_bar0[k] = j;
            for (j = j + 1; j < credits_row_count; j++)          /* proxima barra */
               if (credits_rows[j].kind == CR_RULE)
               {
                  sec_bar1[k] = j;
                  break;
               }
            sec_end_is_text[k] = 0;
            if (credits_secs[k].end_txt)                          /* ... ou a linha de texto de fim */
            {
               int e, elen = (int)strlen(credits_secs[k].end_txt);
               for (e = sec_bar0[k] + 1; e < credits_row_count; e++)
                  if (strncmp(credits_rows[e].c2, credits_secs[k].end_txt, elen) == 0)
                  {
                     sec_bar1[k] = e;
                     sec_end_is_text[k] = 1;
                     break;
                  }
            }
         }
         sec_ready = 1;
      }

      for (k = 0; k < CREDITS_SEC_N; k++)
      {
         int bar0, bar1, span;
         if (sec_bar0[k] < 0 || sec_bar1[k] < 0)
            continue;
         /* y das linhas das barras (a barra e desenhada LINE_H/2-1 px abaixo do topo da linha); se a secao
            termina num texto, o limite e o topo da linha desse texto */
         bar0 = base + sec_bar0[k] * CREDITS_LINE_H + CREDITS_LINE_H / 2 - 1;
         bar1 = base + sec_bar1[k] * CREDITS_LINE_H + (sec_end_is_text[k] ? 0 : CREDITS_LINE_H / 2 - 1);
         span = bar1 - bar0;
         if (bar1 < cy0 || bar0 > cy1)
            continue;
         for (n = 0; n < credits_secs[k].n; n++)
         {
            int cnt = credits_secs[k].n;
            /* N sprites: N+1 espacos iguais entre as barras */
            int sy = bar0 + ((span - cnt * CREDITS_SPR_CELL_H) * (n + 1)) / (cnt + 1) + n * CREDITS_SPR_CELL_H;
            int id = credits_secs[k].spr[n];
            if (sy >= cy1 || sy + CREDITS_SPR_CELL_H <= cy0)
               continue;
            if (id < 0)
               draw_credits_sonic(box_x0 + CREDITS_SONIC_X, sy, cx0, cx1, cy0, cy1);
            else
               draw_credits_sprite(id, box_x0 + CREDITS_SONIC_X, sy, cx0, cx1, cy0, cy1);
         }
      }
   }
}

void retro_get_system_info(struct retro_system_info *info)
{
   memset(info, 0, sizeof(*info));
   info->library_name = "Game Music Emu 2";
   info->library_version = "v1.2";
   info->need_fullpath = true;
   info->valid_extensions = "ay|gbs|gym|hes|kss|nsf|nsfe|sap|spc|vgm|vgz|mod|s3m|xm|it|mp3|mid|midi|zip";
   info->block_extract = true;
}

/*
 * Tell libretro about the AV system; the fps, sound sample rate and the
 * resolution of the display.
 */
void retro_get_system_av_info(struct retro_system_av_info *info)
{
   int pixel_format = RETRO_PIXEL_FORMAT_RGB565;
   memset(info, 0, sizeof(*info));
   info->timing.fps            = 60.0f;
   info->timing.sample_rate    = 44100;
   info->geometry.base_width   = 640;
   info->geometry.base_height  = 480;
   info->geometry.max_width    = 640;
   info->geometry.max_height   = 480;
   info->geometry.aspect_ratio = 640.0f / 480.0f;
   environ_cb(RETRO_ENVIRONMENT_SET_PIXEL_FORMAT, &pixel_format);
}

void retro_init(void)
{
   unsigned level = 0;
   /* set up some logging */
   struct retro_log_callback log;
   if (environ_cb(RETRO_ENVIRONMENT_GET_LOG_INTERFACE, &log))
      log_cb = log.log;
   else
      log_cb = NULL;

   // the performance level is guide to frontend to give an idea of how intensive this core is to run
   environ_cb(RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL, &level);
   framebuffer = create_surface(640,480,2);
}

// End of retrolib
void retro_deinit(void)
{
   if (framebuffer)
      free_surface(framebuffer);
   framebuffer = NULL;
}

// Reset gme
void retro_reset(void)
{
    start_track(0);
}

/* ---- musica da janela de creditos (botao B) ----
 * Enquanto a janela esta aberta, a faixa que estava tocando fica em pausa (play_scan() simplesmente
 * nao e chamado, entao ela continua exatamente de onde parou ao fechar) e este stream toca no lugar.
 * Os dados (credits_music.h) sao IMA ADPCM 4 bits, 44100 Hz estereo, em blocos de
 * CREDITS_MUSIC_BLOCK bytes (formato "IMA WAV"): cabecalho de 4 bytes por canal (predictor int16 +
 * indice + 1 byte de enchimento), depois grupos de 8 amostras por canal (4 bytes, nibble baixo
 * primeiro), canais intercalados. A musica reinicia do comeco a cada abertura e repete no fim. */
static const int cm_index_tab[16] = { -1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8 };
static const short cm_step_tab[89] = {
   7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
   50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
   337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
   2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
   15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
};

static short cm_pcm[CREDITS_MUSIC_SPB * 2];   /* bloco atual decodificado (estereo intercalado) */
static short cm_out[735 * 2];                 /* 1 frame de video de audio (735 amostras a 44,1 kHz / 60 fps) */
static int   cm_block = -1;                   /* bloco decodificado em cm_pcm (-1 = nenhum) */
static int   cm_next  = 0;                    /* proximo bloco a decodificar */
static int   cm_pos   = 0;                    /* amostra atual dentro de cm_pcm */
static int   cm_abs   = 0;                    /* amostras ja tocadas desde o inicio (para repetir no fim) */

static int cm_expand(int nib, int *pred, int *idx)
{
   int step = cm_step_tab[*idx];
   int diff = ((2 * (nib & 7) + 1) * step) >> 3;
   int p    = *pred;
   if (nib & 8)
      diff = -diff;
   p += diff;
   if (p >  32767) p =  32767;
   if (p < -32768) p = -32768;
   *pred = p;
   *idx += cm_index_tab[nib];
   if (*idx < 0)  *idx = 0;
   if (*idx > 88) *idx = 88;
   return p;
}

static void cm_decode_block(int b)
{
   const unsigned char *p = credits_music_data + (size_t)b * CREDITS_MUSIC_BLOCK;
   int pred[2], idx[2], ch, n, k;
   for (ch = 0; ch < 2; ch++)
   {
      pred[ch] = (short)(p[0] | (p[1] << 8));
      idx[ch]  = p[2] > 88 ? 88 : p[2];
      p += 4;
      cm_pcm[ch] = (short)pred[ch];
   }
   for (n = 1; n < CREDITS_MUSIC_SPB; n += 8)
      for (ch = 0; ch < 2; ch++)
         for (k = 0; k < 4; k++)
         {
            unsigned char v = *p++;
            cm_pcm[(n + k * 2)     * 2 + ch] = (short)cm_expand(v & 15, &pred[ch], &idx[ch]);
            cm_pcm[(n + k * 2 + 1) * 2 + ch] = (short)cm_expand(v >> 4,  &pred[ch], &idx[ch]);
         }
   cm_block = b;
}

/* chamada ao abrir a janela de creditos: recomeca a musica do inicio */
static void credits_music_start(void)
{
   cm_block = -1;
   cm_next  = 0;
   cm_pos   = 0;
   cm_abs   = 0;
}

/* 735 amostras estereo da musica dos creditos (mesmo formato de play_scan) */
static short *credits_music_frame(void)
{
   int i;
   for (i = 0; i < 735; i++)
   {
      if (cm_block < 0 || cm_pos >= CREDITS_MUSIC_SPB || cm_abs >= CREDITS_MUSIC_FRAMES)
      {
         if (cm_abs >= CREDITS_MUSIC_FRAMES)   /* fim da musica: repete */
         {
            cm_next = 0;
            cm_abs  = 0;
         }
         cm_decode_block(cm_next);
         cm_next++;
         cm_pos = 0;
      }
      cm_out[i * 2]     = cm_pcm[cm_pos * 2];
      cm_out[i * 2 + 1] = cm_pcm[cm_pos * 2 + 1];
      cm_pos++;
      cm_abs++;
   }
   return cm_out;
}

// Run a single frame
/* toque curto (< ~0,3 s a 60 fps) troca de faixa; segurar mais que isso vira avanco/volta acelerada */
#define SCAN_HOLD_FRAMES 18
static int l_hold_frames = 0;
static int r_hold_frames = 0;

/* repeticao ao segurar CIMA/BAIXO dentro do navegador de zip */
#define BROWSER_REPEAT_DELAY 20   /* frames antes de comecar a repetir (~0,33s a 60fps) */
#define BROWSER_REPEAT_RATE   6   /* frames entre repeticoes depois disso (~0,1s) */
static int down_hold_frames = 0;
static int up_hold_frames   = 0;

/* ---- volume do core (L2 abaixa, R2 aumenta) ----
 * Escala so o audio enviado ao RetroArch; espectro/onda/LED usam o sinal original. */
#define VOL_MAX           200   /* % (100 = volume original; acima disso amplifica com limite) */
#define VOL_STEP           10   /* % por toque */
#define VOL_REPEAT_DELAY   20   /* frames segurando antes de repetir (~0,33 s a 60 fps) */
#define VOL_REPEAT_RATE    4    /* frames entre repeticoes */
#define VOL_OSD_FRAMES     90   /* tempo do aviso na tela (~1,5 s a 60 fps) */
static int volume_pct      = 100;
static int vol_osd_frames  = 0;
static int vol_up_hold     = 0;
static int vol_down_hold   = 0;

static void volume_update(uint16_t pressed, uint16_t held)
{
   int up = 0, down = 0;

   if(pressed & (1<<RETRO_DEVICE_ID_JOYPAD_L2))
   {
      down = 1;
      vol_down_hold = 0;
   }
   else if(held & (1<<RETRO_DEVICE_ID_JOYPAD_L2))
   {
      vol_down_hold++;
      if(vol_down_hold >= VOL_REPEAT_DELAY &&
         (vol_down_hold - VOL_REPEAT_DELAY) % VOL_REPEAT_RATE == 0)
         down = 1;
   }
   else
      vol_down_hold = 0;

   if(pressed & (1<<RETRO_DEVICE_ID_JOYPAD_R2))
   {
      up = 1;
      vol_up_hold = 0;
   }
   else if(held & (1<<RETRO_DEVICE_ID_JOYPAD_R2))
   {
      vol_up_hold++;
      if(vol_up_hold >= VOL_REPEAT_DELAY &&
         (vol_up_hold - VOL_REPEAT_DELAY) % VOL_REPEAT_RATE == 0)
         up = 1;
   }
   else
      vol_up_hold = 0;

   if(up && !down)
      volume_pct += VOL_STEP;
   else if(down && !up)
      volume_pct -= VOL_STEP;
   else
      return;

   if(volume_pct > VOL_MAX) volume_pct = VOL_MAX;
   if(volume_pct < 0)       volume_pct = 0;
   vol_osd_frames = VOL_OSD_FRAMES;
}

/* devolve o buffer a enviar ao frontend (o original se o volume for 100%) */
static short *volume_apply(short *audio, int frames)
{
   static short vol_buf[2048 * 2];
   int i, n = frames * 2;

   if(volume_pct == 100 || n > (int)(sizeof(vol_buf) / sizeof(vol_buf[0])))
      return audio;

   for(i = 0; i < n; i++)
   {
      int v = ((int)audio[i] * volume_pct) / 100;
      if(v >  32767) v =  32767;
      if(v < -32768) v = -32768;
      vol_buf[i] = (short)v;
   }
   return vol_buf;
}

/* aviso "VOL xxx%" com barra, no centro da tela, por alguns instantes */
static void volume_osd_draw(void)
{
   char txt[24];
   int bw = 208, bh = 48;
   int bx = (640 - bw) / 2, by = (480 - bh) / 2;
   int tw, fill, tick;

   if(vol_osd_frames <= 0)
      return;
   vol_osd_frames--;

   snprintf(txt, sizeof(txt), "VOL %d%%", volume_pct);
   tw = text_width_prop(txt);

   draw_shape_alpha(framebuffer, get_color(2, 4, 5),   215, bx,     by,     bw,     bh);
   draw_shape_alpha(framebuffer, get_color(6, 12, 14), 215, bx + 2, by + 2, bw - 4, bh - 4);
   draw_text_prop(txt, bx + (bw - tw) / 2, by + 7, get_color(30, 58, 25));

   /* barra: cheia = VOL_MAX; marca branca = 100% (volume original) */
   draw_shape(framebuffer, get_color(4, 8, 9), bx + 12, by + bh - 16, bw - 24, 8);
   fill = ((bw - 24) * volume_pct) / VOL_MAX;
   if(fill > 0)
      draw_shape(framebuffer, get_color(8, 56, 17), bx + 12, by + bh - 16, fill, 8);
   tick = ((bw - 24) * 100) / VOL_MAX;
   draw_shape(framebuffer, get_color(31, 63, 31), bx + 12 + tick, by + bh - 18, 2, 12);
}

void retro_run(void)
{
   uint16_t input = 0;
   uint16_t realinput = 0;
   int i;
   short *audio;
   uint16_t released = 0;
   int scan_dir = 0;

   // input handling
   input_poll_cb();
   for(i=0;i<16;i++)
   {
      if(input_state_cb(0, RETRO_DEVICE_JOYPAD, 0, i))
         realinput |= 1<<i;
   }
   input = realinput & ~previnput;
   released = previnput & ~realinput;
   previnput = realinput;

   /* L2/R2 = volume (vale em qualquer tela); depois some do "input" para nao
      fechar a janela de creditos nem disparar outras acoes */
   volume_update(input, realinput);
   input &= ~((1<<RETRO_DEVICE_ID_JOYPAD_L2) | (1<<RETRO_DEVICE_ID_JOYPAD_R2));

   /* janela de creditos (B, fora do navegador): enquanto aberta, B pausa/continua
      o texto subindo; qualquer outro botao fecha; nenhum outro controle
      (transporte, navegador) reage */
   if(credits_open_state)
   {
      if(input & (1<<RETRO_DEVICE_ID_JOYPAD_B))
         credits_paused = !credits_paused;
      if(input & ~(1<<RETRO_DEVICE_ID_JOYPAD_B))
         credits_open_state = 0;
   }
   else
   {
   /* SELECT abre/fecha o navegador do zip atual */
   if(input & (1<<RETRO_DEVICE_ID_JOYPAD_SELECT))
   {
      if(!browser_open_state)
      {
         int n = browser_open();
         if(n > 0)
         {
            browser_open_state = 1;
            browser_cursor     = browser_last_cursor();
            browser_count_ui   = n;
            down_hold_frames   = 0;
            up_hold_frames     = 0;
         }
      }
      else
      {
         browser_close();
         browser_open_state = 0;
         down_hold_frames   = 0;
         up_hold_frames     = 0;
      }
   }

   if(browser_open_state)
   {
      {
         int move_down = 0, move_up = 0;

         if(input & (1<<RETRO_DEVICE_ID_JOYPAD_DOWN))
         {
            move_down = 1;
            down_hold_frames = 0;
         }
         else if(realinput & (1<<RETRO_DEVICE_ID_JOYPAD_DOWN))
         {
            down_hold_frames++;
            if(down_hold_frames >= BROWSER_REPEAT_DELAY &&
               (down_hold_frames - BROWSER_REPEAT_DELAY) % BROWSER_REPEAT_RATE == 0)
               move_down = 1;
         }
         else
            down_hold_frames = 0;

         if(input & (1<<RETRO_DEVICE_ID_JOYPAD_UP))
         {
            move_up = 1;
            up_hold_frames = 0;
         }
         else if(realinput & (1<<RETRO_DEVICE_ID_JOYPAD_UP))
         {
            up_hold_frames++;
            if(up_hold_frames >= BROWSER_REPEAT_DELAY &&
               (up_hold_frames - BROWSER_REPEAT_DELAY) % BROWSER_REPEAT_RATE == 0)
               move_up = 1;
         }
         else
            up_hold_frames = 0;

         if(move_down)
         {
            browser_cursor++;
            if(browser_cursor >= browser_count_ui)
               browser_cursor = 0;
         }
         if(move_up)
         {
            browser_cursor--;
            if(browser_cursor < 0)
               browser_cursor = browser_count_ui - 1;
         }
      }
      /* L/R no navegador: pula BROWSER_PAGE_STEP linhas (R desce, L sobe);
         segurando, repete rapido. Passando do fim/inicio da lista, da a volta. */
      {
#define BROWSER_PAGE_STEP 5
         static int page_r_hold = 0, page_l_hold = 0;
         int page_r = 0, page_l = 0;

         if(input & (1<<RETRO_DEVICE_ID_JOYPAD_R))
         {
            page_r = 1;
            page_r_hold = 0;
         }
         else if(realinput & (1<<RETRO_DEVICE_ID_JOYPAD_R))
         {
            page_r_hold++;
            if(page_r_hold >= BROWSER_REPEAT_DELAY &&
               (page_r_hold - BROWSER_REPEAT_DELAY) % BROWSER_REPEAT_RATE == 0)
               page_r = 1;
         }
         else
            page_r_hold = 0;

         if(input & (1<<RETRO_DEVICE_ID_JOYPAD_L))
         {
            page_l = 1;
            page_l_hold = 0;
         }
         else if(realinput & (1<<RETRO_DEVICE_ID_JOYPAD_L))
         {
            page_l_hold++;
            if(page_l_hold >= BROWSER_REPEAT_DELAY &&
               (page_l_hold - BROWSER_REPEAT_DELAY) % BROWSER_REPEAT_RATE == 0)
               page_l = 1;
         }
         else
            page_l_hold = 0;

         if(browser_count_ui <= 0)
            ;   /* lista vazia: nada a mover */
         else if(page_r && !page_l)
            browser_cursor = (browser_cursor + BROWSER_PAGE_STEP) % browser_count_ui;
         else if(page_l && !page_r)
         {
            browser_cursor = (browser_cursor - BROWSER_PAGE_STEP) % browser_count_ui;
            if(browser_cursor < 0)
               browser_cursor += browser_count_ui;
         }
      }
      if(input & (1<<RETRO_DEVICE_ID_JOYPAD_B))
      {
         /* dentro de uma pasta: B sobe um nivel. na raiz: B fecha o navegador */
         int n = browser_up();
         if(n < 0)
         {
            browser_close();
            browser_open_state = 0;
         }
         else
         {
            browser_cursor   = browser_up_cursor();
            browser_count_ui = n;
         }
      }
      else if(input & (1<<RETRO_DEVICE_ID_JOYPAD_A))
      {
         int was_dir = browser_entry_is_dir(browser_cursor);
         browser_select(browser_cursor);
         if(was_dir)
         {
            /* entrou numa pasta: continua no navegador, com a nova listagem */
            browser_cursor   = 0;
            browser_count_ui = browser_count();
         }
         else
         {
            /* tocou um arquivo ou entrou num zip aninhado: fecha o navegador */
            browser_close();
            browser_open_state = 0;
         }
      }
   }
   else
   {
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
      }

      if(input & (1<<RETRO_DEVICE_ID_JOYPAD_START))
         play_pause();

      /* Y = Stop: para a musica (Start volta a tocar do inicio da faixa) */
      if(input & (1<<RETRO_DEVICE_ID_JOYPAD_Y))
         stop_track();

      if(input & (1<<RETRO_DEVICE_ID_JOYPAD_A))
         toggle_loop();

      /* X = alterna o sintetizador MIDI ativo (MT-32 -> TSF -> FluidSynth -> ...);
         sem efeito se a faixa atual nao for um arquivo MIDI */
      if(input & (1<<RETRO_DEVICE_ID_JOYPAD_X))
         cycle_midi_synth();

      /* B (fora do navegador) abre a janela de creditos */
      if(input & (1<<RETRO_DEVICE_ID_JOYPAD_B))
      {
         credits_open_state = 1;
         credits_frame      = 0;
         credits_anim       = 0;
         credits_paused     = 0;
         credits_music_start();   /* pausa a faixa atual e toca a musica dos creditos */
      }
   }
   }

   l_active_ = (realinput & (1<<RETRO_DEVICE_ID_JOYPAD_L)) ? 1 : 0;
   r_active_ = (realinput & (1<<RETRO_DEVICE_ID_JOYPAD_R)) ? 1 : 0;

   //audio primeiro, para o espectro usar os samples deste frame
   /* com a janela de creditos aberta a faixa atual fica em pausa (play_scan nao e chamado)
      e toca a musica dos creditos; ao fechar, a faixa continua de onde parou */
   audio = credits_open_state ? credits_music_frame() : play_scan(scan_dir);
   led_update(audio, 1470);
   spectrum_push(audio, 735);
   spectrum_update();

   //graphic handling
   spectrum_draw_background(framebuffer);
   draw_ui();
   draw_waveform(audio, 735);
   spectrum_draw_bars(framebuffer);
   if(browser_open_state)
      draw_browser();
   if(credits_open_state)
   {
      draw_credits();
      credits_anim++;
      if(!credits_paused)
         credits_frame++;
   }
   volume_osd_draw();
   video_cb(framebuffer->pixel_data, framebuffer->width, framebuffer->height, framebuffer->bytes_per_pixel * framebuffer->width);
   //audio handling
   audio_batch_cb(volume_apply(audio, 735), 735);
}

// File Loading
bool retro_load_game(const struct retro_game_info *info)
{
   const char *sysdir = NULL;
   if (environ_cb(RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY, &sysdir) && sysdir)
      set_system_dir(sysdir);
   {
      const char *savedir = NULL;
      if (environ_cb(RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY, &savedir) && savedir && savedir[0])
         set_temp_dir(savedir);
      else if (sysdir)
         set_temp_dir(sysdir);
   }
   if (info && open_file(info->path, 44100))
      return true;
   return false;
}

bool retro_load_game_special(unsigned game_type, const struct retro_game_info *info, size_t num_info)
{
   return false;
}

void retro_unload_game(void)
{
   close_file();
   player_cleanup_temp();
}
