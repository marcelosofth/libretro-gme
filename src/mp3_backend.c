#include <stdlib.h>
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
