#include <stdlib.h>
#include <string.h>
#include "vgm_backend.h"
#include "zlib.h"

#include "player/playerbase.hpp"
#include "player/vgmplayer.hpp"
#include "player/playera.hpp"
#include "utils/DataLoader.h"
#include "utils/MemoryLoader.h"

#define VGM_BUFFER_LEN   2048
#define VGM_LOOPS        2
#define VGM_FADE_SECONDS 8.0

static PlayerA     *g_player = NULL;
static DATA_LOADER *g_loader = NULL;
static UINT8       *g_data   = NULL;
static UINT32       g_total  = 0;
static UINT32       g_done   = 0;
static UINT32       g_rate   = 44100;

/* Copia os dados; se for gzip (.vgz), descomprime com o zlib do repo. */
static UINT8 *load_data(const UINT8 *src, UINT32 size, UINT32 *out_size)
{
   UINT8 *dst;
   if (size > 18 && src[0] == 0x1F && src[1] == 0x8B)
   {
      z_stream zs;
      int r;
      UINT32 isize = (UINT32)src[size - 4]
                   | ((UINT32)src[size - 3] << 8)
                   | ((UINT32)src[size - 2] << 16)
                   | ((UINT32)src[size - 1] << 24);
      if (isize == 0 || isize > (64u << 20))
         return NULL;
      dst = (UINT8 *)malloc(isize);
      if (!dst)
         return NULL;
      memset(&zs, 0, sizeof(zs));
      if (inflateInit2(&zs, 15 + 16) != Z_OK)
      {
         free(dst);
         return NULL;
      }
      zs.next_in   = (Bytef *)src;
      zs.avail_in  = size;
      zs.next_out  = dst;
      zs.avail_out = isize;
      r = inflate(&zs, Z_FINISH);
      inflateEnd(&zs);
      if (r != Z_STREAM_END)
      {
         free(dst);
         return NULL;
      }
      *out_size = (UINT32)zs.total_out;
      return dst;
   }
   dst = (UINT8 *)malloc(size ? size : 1);
   if (!dst)
      return NULL;
   memcpy(dst, src, size);
   *out_size = size;
   return dst;
}

extern "C" void vgm_backend_close(void)
{
   if (g_player)
   {
      g_player->Stop();
      g_player->UnloadFile();
      g_player->UnregisterAllPlayers();
      delete g_player;
      g_player = NULL;
   }
   if (g_loader)
   {
      DataLoader_Deinit(g_loader);
      g_loader = NULL;
   }
   free(g_data);
   g_data  = NULL;
   g_total = 0;
   g_done  = 0;
}

extern "C" int vgm_backend_open(const unsigned char *data, long size, long sample_rate)
{
   UINT32 len = 0;
   PlayerBase *eng;
   PlayerA::Config cfg;

   vgm_backend_close();

   g_data = load_data((const UINT8 *)data, (UINT32)size, &len);
   if (!g_data)
      return -1;

   g_rate   = sample_rate > 0 ? (UINT32)sample_rate : 44100;
   g_player = new PlayerA();
   g_player->RegisterPlayerEngine(new VGMPlayer);

   if (g_player->SetOutputSettings(g_rate, 2, 16, VGM_BUFFER_LEN))
      goto fail;

   cfg = g_player->GetConfiguration();
   cfg.masterVol       = 0x10000;
   cfg.loopCount       = VGM_LOOPS;
   cfg.fadeSmpls       = (UINT32)(g_rate * VGM_FADE_SECONDS);
   cfg.endSilenceSmpls = 0;
   cfg.pbSpeed         = 1.0;
   g_player->SetConfiguration(cfg);

   g_loader = MemoryLoader_Init(g_data, len);
   if (!g_loader)
      goto fail;
   DataLoader_SetPreloadBytes(g_loader, 0x100);
   if (DataLoader_Load(g_loader))
      goto fail;
   if (g_player->LoadFile(g_loader))
      goto fail;

   eng = g_player->GetPlayer();
   if (eng->GetPlayerType() == FCC_VGM)
   {
      VGMPlayer *vp = static_cast<VGMPlayer *>(eng);
      g_player->SetLoopCount(vp->GetModifiedLoopCount(VGM_LOOPS));
   }

   g_player->Start();

   g_total = eng->Tick2Sample(eng->GetTotalPlayTicks(VGM_LOOPS));
   if (eng->GetLoopTicks() > 0)
      g_total += g_player->GetFadeSamples();
   g_done = 0;
   return 0;

fail:
   vgm_backend_close();
   return -1;
}

extern "C" int vgm_backend_render(short *out, int frames)
{
   UINT32 remain, n;
   if (!g_player || frames <= 0)
      return 0;
   memset(out, 0, (size_t)frames * 2 * sizeof(short));
   remain = g_total > g_done ? g_total - g_done : 0;
   n      = (UINT32)frames < remain ? (UINT32)frames : remain;
   if (n)
      g_player->Render(n * 4, out);   /* 16 bits x 2 canais = 4 bytes por quadro */
   g_done += n;
   return (int)n;
}

extern "C" int vgm_backend_ended(void)
{
   return g_player && g_done >= g_total;
}

extern "C" long vgm_backend_tell_ms(void)
{
   return (long)(((unsigned long long)g_done * 1000ULL) / g_rate);
}

extern "C" long vgm_backend_tell_samples(void)
{
   return (long)g_done * 2;
}