#include <stdlib.h>
#include <boolean.h>
#include <string.h>
#include "file/file_path.h"

#include "playlist.h"
#include "xmp_backend.h"
#include "mp3_backend.h"
#include "midi_backend.h"
#include <stdio.h>
#include "libretro.h"

extern retro_log_printf_t log_cb;

bool get_playlist(const char *path, playlist **dest_pl)
{
   //local variables
   int i,j;
   int position = 0;
   Music_Emu *temp_emu = NULL;
   gme_file_data *gfd = NULL;
   gme_err_t err_msg;
   //init playlist
   playlist *pl = (playlist *)calloc(1, sizeof(playlist));
   //load libretro content file
   if(get_playlist_gme_files(path,&(pl->files),&(pl->num_files),&(pl->num_tracks)))
   {
      pl->tracks = (gme_track_data **)calloc(pl->num_tracks, sizeof(gme_track_data*));
      //read tracks
      for(i=0;i<pl->num_files;i++)
      {
         gfd      = pl->files[i];
          if (gfd->is_tracker)
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
          }
          if (gfd->is_midi)
          {
             if (get_midi_track_data(gfd, i, &(pl->tracks[position])))
                position++;
             continue;
          }
          temp_emu = gme_new_emu(gfd->file_type,gme_info_only);
         err_msg  = gme_load_data(temp_emu,gfd->data,gfd->length);

         if (err_msg)
            goto error;

         for(j=0;j<gfd->num_tracks;j++)
         {
            if(get_track_data(temp_emu,i,j,gfd->name,
                     &(pl->tracks[position])))
               position++;
         }				

         gme_delete(temp_emu);
         temp_emu = NULL;
      }
   }
   else
      goto error;

   if (pl->num_tracks == 0)
      goto error;

   *dest_pl = pl;
   return true;

error:
   if (temp_emu)
      gme_delete(temp_emu);

   if (pl)
      cleanup_playlist(pl);

   return false;
}

bool get_playlist_gme_files(const char *path,gme_file_data ***dest_files,int *dest_num_files, int *dest_num_tracks)
{
   int i;
   bool success              = true;
   file_data **files         = NULL;
   gme_file_data **gme_files = NULL;
   int num_files             = 0;
   int num_tracks            = 0;

   if(get_file_data(path,&files,&num_files))
   {
      gme_files = malloc(sizeof(gme_file_data*) * num_files);
      for(i=0;i< num_files;i++)
      {
         gme_files[i] = NULL;
         if(!get_gme_file_data(files[i],&(gme_files[i])))
         {
            success = false;
            break;
         }
         free(files[i]);
         if(gme_files[i]==NULL)
         {
            success = false;
            break;
         }
         num_tracks += gme_files[i]->num_tracks;
      }
      free(files);
   }
   else
      success = false;
   *dest_files = gme_files;
   *dest_num_files = num_files;
   *dest_num_tracks = num_tracks;
   return success;
}

#include <zlib.h>

#define GZ_MAX_OUT (64u * 1024u * 1024u)

/* Se os dados forem gzip (1F 8B), devolve um buffer novo (malloc) descomprimido.
   Retorna NULL se nao for gzip ou se a descompressao falhar. */
static unsigned char *gunzip_buffer(const unsigned char *src, int src_len, int *out_len)
{
   z_stream zs;
   unsigned char *out;
   size_t cap, used = 0;
   int ret;

   if (src_len < 18 || src[0] != 0x1F || src[1] != 0x8B)
      return NULL;

   memset(&zs, 0, sizeof(zs));
   if (inflateInit2(&zs, 15 + 16) != Z_OK)
      return NULL;

   cap = (size_t)src_len * 4 + 4096;
   out = (unsigned char*)malloc(cap);
   if (!out)
   {
      inflateEnd(&zs);
      return NULL;
   }

   zs.next_in  = (Bytef*)src;
   zs.avail_in = (uInt)src_len;

   do
   {
      if (used == cap)
      {
         size_t ncap = cap * 2;
         unsigned char *tmp;
         if (ncap > GZ_MAX_OUT)
            goto fail;
         tmp = (unsigned char*)realloc(out, ncap);
         if (!tmp)
            goto fail;
         out = tmp;
         cap = ncap;
      }
      zs.next_out  = out + used;
      zs.avail_out = (uInt)(cap - used);
      ret = inflate(&zs, Z_NO_FLUSH);
      used = cap - zs.avail_out;
      if (ret != Z_OK && ret != Z_STREAM_END)
         goto fail;
   } while (ret != Z_STREAM_END);

   inflateEnd(&zs);
   if (used == 0)
   {
      free(out);
      return NULL;
   }
   *out_len = (int)used;
   return out;

fail:
   inflateEnd(&zs);
   free(out);
   return NULL;
}

static int ext_is(const char *e, const char *w)
{
   while (*e && *w)
   {
      char c = *e;
      if (c >= 'A' && c <= 'Z')
         c = (char)(c + 32);
      if (c != *w)
         return 0;
      e++;
      w++;
   }
   return *e == *w;
}

static int is_tracker_ext(const char *e)
{
   return ext_is(e, "mod") || ext_is(e, "s3m") || ext_is(e, "xm") || ext_is(e, "it");
}

bool get_gme_file_data(file_data *fd,gme_file_data **dest_gfd)
{
   Music_Emu* temp_emu;
   gme_err_t err_msg;
   gme_file_data *gfd;
   const char *dot = strrchr(fd->name,'.');
   const char *ext = dot ? dot + 1 : "";
   const char *load_data = fd->data;
   int load_len = fd->length;
   unsigned char *raw = NULL;
   int raw_len = 0;

   gfd = malloc(sizeof(gme_file_data));
   if (!gfd)
      return false;

   gfd->is_tracker = 0;
   gfd->is_mp3     = 0;
   gfd->is_midi    = 0;
   gfd->file_type  = NULL;

   /* MOD/S3M/XM/IT: nao passa pelo GME, so valida com a libxmp */
   if (is_tracker_ext(ext))
   {
      char probe_name[64];
      long probe_ms = 0;
      if (xmp_backend_probe((const unsigned char*)fd->data, fd->length,
               probe_name, sizeof(probe_name), &probe_ms) != 0)
      {
         log_cb(RETRO_LOG_ERROR, "[GME] Error: libxmp nao carregou %s\n", fd->name);
         free(gfd);
         return false;
      }
      gfd->is_tracker = 1;
      gfd->num_tracks = 1;
      gfd->name = calloc(strlen(fd->name)+1,sizeof(char));
      strcpy(gfd->name,fd->name);
      gfd->data = malloc(fd->length ? fd->length : 1);
      memcpy(gfd->data,fd->data,fd->length);
      gfd->length = fd->length;
      *dest_gfd = gfd;
      return true;
   }

   /* MP3: decodificado pelo dr_mp3, sem GME. Assume a posse do buffer (evita copiar arquivos grandes) */
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

   /* MIDI: valida o SMF aqui; a sintese (Munt/MT-32) so acontece ao tocar e precisa das ROMs */
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

   //check extension to determine player type
   if(strcmp(ext,"ay")==0 || strcmp(ext,"AY")==0)
      gfd->file_type = gme_ay_type;
   else if(strcmp(ext,"gbs")==0 || strcmp(ext,"GBS")==0)
      gfd->file_type = gme_gbs_type;
   else if(strcmp(ext,"gym")==0 || strcmp(ext,"GYM")==0)
      gfd->file_type = gme_gym_type;
   else if(strcmp(ext,"hes")==0 || strcmp(ext,"HES")==0)
      gfd->file_type = gme_hes_type;
   else if(strcmp(ext,"kss")==0 || strcmp(ext,"KSS")==0)
      gfd->file_type = gme_kss_type;
   else if(strcmp(ext,"nsf")==0 || strcmp(ext,"NSF")==0)
      gfd->file_type = gme_nsf_type;
   else if(strcmp(ext,"nsfe")==0 || strcmp(ext,"NSFE")==0)
      gfd->file_type = gme_nsfe_type;
   else if(strcmp(ext,"sap")==0 || strcmp(ext,"SAP")==0)
      gfd->file_type = gme_sap_type;
   else if(strcmp(ext,"spc") == 0 || strcmp(ext,"SPC")==0)
      gfd->file_type = gme_spc_type;
   else if(strcmp(ext,"vgm") == 0 || strcmp(ext,"VGM")==0)
      gfd->file_type = gme_vgm_type;
   else if(strcmp(ext,"vgz") == 0 || strcmp(ext,"VGZ")==0)
      gfd->file_type = gme_vgz_type;
   else
   {
      free(gfd);
      return false;
   }

   //.vgm que na verdade e gzip (VGZ com extensao errada): descomprime uma vez aqui
   if (gfd->file_type == gme_vgm_type)
   {
      raw = gunzip_buffer((const unsigned char*)fd->data, fd->length, &raw_len);
      if (raw)
      {
         load_data = (const char*)raw;
         load_len  = raw_len;
         log_cb(RETRO_LOG_INFO, "[GME] %s: gzip detectado com extensao .vgm, descomprimido (%d -> %d bytes)\n",
                fd->name, fd->length, raw_len);
      }
   }

   temp_emu = gme_new_emu(gfd->file_type,gme_info_only);
   if (!temp_emu)
   {
      log_cb(RETRO_LOG_ERROR, "[GME] Error: gme_new_emu falhou para %s\n", fd->name);
      free(raw);
      free(gfd);
      return false;
   }

   err_msg = gme_load_data(temp_emu,load_data,load_len);
   if (err_msg)
   {
      log_cb(RETRO_LOG_ERROR, "[GME] Error: %s (%s)\n", err_msg, fd->name);
      gme_delete(temp_emu);
      free(raw);
      free(gfd);
      return false;
   }
   gfd->num_tracks = gme_track_count(temp_emu);
   gme_delete( temp_emu );

   //deep copy file data (ja descomprimido, se for o caso)
   gfd->name = calloc(strlen(fd->name)+1,sizeof(char));
   strcpy(gfd->name,fd->name);
   gfd->data = malloc(load_len * sizeof(char));
   memcpy(gfd->data,load_data,load_len);
   gfd->length = load_len;
   free(raw);
   *dest_gfd = gfd;
   return true;
}

bool get_track_data(Music_Emu* emu, int fileid, int trackid, char *filename,gme_track_data **dest_gtd)
{
   gme_info_t* ti;
   gme_track_data *gtd = malloc(sizeof(gme_track_data));
   gtd->file_id        = fileid;
   gtd->track_id       = trackid;
   gme_track_info(emu, &ti,trackid);
   //game name
   if(strcmp(ti->game,"")==0)
   {
      gtd->game_name = calloc(strlen(filename)+1,sizeof(char));
      strcpy(gtd->game_name,filename);
   }
   else
   {
      gtd->game_name = calloc(strlen(ti->game)+1,sizeof(char));
      strcpy(gtd->game_name,ti->game);
   }
   //track length
   gtd->track_length = ti->length;
   if ( gtd->track_length <= 0 )
      gtd->track_length = ti->intro_length + ti->loop_length * 2;
   if ( gtd->track_length <= 0 )
      gtd->track_length = (long) (2.5 * 60 * 1000);
   //track name
   if(strcmp(ti->song,"") == 0)
   {
      gtd->track_name = calloc(10,sizeof(char));
      sprintf(gtd->track_name, "Track %i",trackid+1);
   }
   else
   {
      gtd->track_name = calloc(strlen(ti->song)+1,sizeof(char));
      strcpy(gtd->track_name, ti->song);
   }
   gme_free_info(ti);
   *dest_gtd = gtd;
   return true;
}

bool get_tracker_track_data(gme_file_data *gfd, int fileid, gme_track_data **dest_gtd)
{
   char title[64];
   long ms = 0;
   char *dot;
   gme_track_data *gtd = malloc(sizeof(gme_track_data));
   if (!gtd)
      return false;

   title[0] = '\0';
   xmp_backend_probe((const unsigned char*)gfd->data, gfd->length, title, sizeof(title), &ms);

   gtd->file_id  = fileid;
   gtd->track_id = 0;

   gtd->game_name = calloc(strlen(gfd->name) + 1, sizeof(char));
   strcpy(gtd->game_name, gfd->name);

   gtd->track_length = ms > 0 ? (int)ms : (int)(2.5 * 60 * 1000);

   if (title[0])
   {
      gtd->track_name = calloc(strlen(title) + 1, sizeof(char));
      strcpy(gtd->track_name, title);
   }
   else
   {
      gtd->track_name = calloc(strlen(gfd->name) + 1, sizeof(char));
      strcpy(gtd->track_name, gfd->name);
      dot = strrchr(gtd->track_name, '.');
      if (dot)
         *dot = '\0';
   }
   *dest_gtd = gtd;
   return true;
}

static char *dup_cstr(const char *s)
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

bool get_midi_track_data(gme_file_data *gfd, int fileid, gme_track_data **dest_gtd)
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

bool cleanup_playlist(playlist *playlist)	
{
   int i;
   if(playlist->tracks!=NULL)
   {
      for(i=0;i<playlist->num_tracks;i++)
      {
         if(playlist->tracks[i] != NULL)
         {
            if(playlist->tracks[i]->game_name != NULL)
               free(playlist->tracks[i]->game_name);
            if(playlist->tracks[i]->track_name != NULL)
               free(playlist->tracks[i]->track_name);
            free(playlist->tracks[i]);
         }
      }
      free(playlist->tracks);
   }
   if(playlist->files!=NULL)
   {
      for(i=0;i<playlist->num_files;i++)
      {
         if(playlist->files[i] != NULL)
         {
            if(playlist->files[i]->data != NULL)
               free(playlist->files[i]->data);
            if(playlist->files[i]->name != NULL)
               free(playlist->files[i]->name);
            free(playlist->files[i]);
         }
      }
      free(playlist->files);
   }
   free(playlist);
   return true;
}
