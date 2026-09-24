#include <stdlib.h>
#include <string.h>
#if !defined(_WIN32) && !defined(_WIN64)
#include <strings.h>
#endif
#include "xmp.h"
#include "xmp_backend.h"

/* separacao estereo: 100 = Amiga puro (canais 100% L/R), menor = mais suave */
#define XMP_STEREO_MIX 70

static xmp_context g_ctx        = NULL;
static int         g_loaded     = 0;
static int         g_started    = 0;
static int         g_ended      = 0;
static long        g_rate       = 44100;
static long        g_frames     = 0;
static int         g_amiga_mix  = 0;

/* ---- deteccao: MOD Amiga de verdade x MOD "normal" (feito/estendido pra PC) ----
 * O Amiga so tem 4 canais de hardware (chip Paula), entao qualquer MOD com mais
 * canais, ou com uma extensao de formato criada por tracker de PC, nunca rodou
 * num Amiga de verdade - so faz sentido ligar a emulacao do Paula nos formatos
 * classicos de 4 canais. A assinatura fica nos 4 bytes do offset 1080. */
static int has_ext(const char *filename, const char *ext)
{
   size_t flen, elen;
   if (!filename)
      return 0;
   flen = strlen(filename);
   elen = strlen(ext);
   if (flen < elen + 1 || filename[flen - elen - 1] != '.')
      return 0;
#if defined(_WIN32) || defined(_WIN64)
   return _stricmp(filename + (flen - elen), ext) == 0;
#else
   return strcasecmp(filename + (flen - elen), ext) == 0;
#endif
}

static int is_amiga_mod(const unsigned char *data, long size, const char *filename)
{
   const unsigned char *tag;
   static const char *amiga_tags[] = {
      "M.K.", "M!K!", "M&K!", "N.T.", "FLT4", "EXO4", "FEST", "PATT"
   };
   int i;

   if (!has_ext(filename, "mod"))
      return 0;                 /* .s3m/.xm/.it nunca sao "Amiga" */
   if (!data || size < 1084)
      return 0;                 /* curto demais para ter o cabecalho de 31 instrumentos */

   tag = data + 1080;
   for (i = 0; i < (int)(sizeof(amiga_tags) / sizeof(amiga_tags[0])); i++)
      if (memcmp(tag, amiga_tags[i], 4) == 0)
         return 1;

   return 0;   /* 6CHN/8CHN/10CH.../32CH, TDZ1-3, CD81, OKTA/OCTA, etc: extensoes de PC */
}

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
   g_ctx       = NULL;
   g_started   = 0;
   g_loaded    = 0;
   g_ended     = 0;
   g_frames    = 0;
   g_amiga_mix = 0;
}

int xmp_backend_uses_amiga_mix(void)
{
   return g_ctx && g_started && g_amiga_mix;
}

/* data precisa continuar valido enquanto tocar (fica no playlist) */
int xmp_backend_open(const unsigned char *data, long size, long sample_rate, const char *filename)
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

   g_amiga_mix = is_amiga_mod(data, size, filename);
   xmp_set_player(g_ctx, XMP_PLAYER_MIX, XMP_STEREO_MIX);
   /* Mix. Paula (emulacao do chip Amiga 500) so em MOD Amiga de verdade;
      MOD "normal" (estendido pra PC) e S3M/XM/IT tocam com a mixagem padrao da libxmp */
   xmp_set_player(g_ctx, XMP_PLAYER_FLAGS, g_amiga_mix ? XMP_FLAGS_A500 : 0);
   g_frames = 0;
   g_ended  = 0;
   return 0;

fail:
   g_amiga_mix = 0;
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
   /* loop=0 na libxmp DESATIVA a checagem de loop (o modulo repete pra sempre
      internamente e xmp_play_buffer nunca retorna fim). loop=1 para a reproducao
      assim que o contador de loop chega em 1, ou seja, apos a 1a passada. */
   r = xmp_play_buffer(g_ctx, out, frames * 4, 1);
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
