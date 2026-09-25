#include <stdlib.h>
#include <boolean.h>
#include <string.h>
#if !defined(_WIN32) && !defined(_WIN64)
#include <strings.h>
#endif
#include <file/file_path.h>
#include <streams/file_stream.h>
#include "zlib.h"

#include "fileformat.h"
#include "unzip.h"

/* forward declarations */
RFILE* rfopen(const char *path, const char *mode);
int rfclose(RFILE* stream);
int64_t rftell(RFILE* stream);
int rferror(RFILE* stream);
int64_t rfread(void* buffer,
   size_t elem_size, size_t elem_count, RFILE* stream);
int64_t rfseek(RFILE* stream, int64_t offset, int origin);
int rfeof(RFILE* stream);

static const char *gme_allowed_exts[] = {
    "ay",
    "gbs",
    "gym",
    "hes",
    "kss",
    "nsf",
    "nsfe",
    "sap",
    "spc",
    "vgm",
    "vgz",
    "mod",
    "s3m",
    "xm",
    "it",
    "mp3",
    "mid",
    "midi"
};

/* comparacao case-insensitive: "Mod", "MOD", "mod", "mOd" etc devem bater
   igual. Antes a lista so cobria "mod"/"MOD" (tudo minusculo ou tudo
   maiusculo), entao qualquer extensao com capitalizacao mista (ex: ".Mod")
   nao batia com strcmp e o arquivo era descartado silenciosamente. */
static bool is_gme_allowed_ext(char *ext)
{
   int i;
   int arr_length = sizeof(gme_allowed_exts) / sizeof(char*);
   for(i=0;i<arr_length;i++)
   {
#if defined(_WIN32) || defined(_WIN64)
      if(_stricmp(ext,gme_allowed_exts[i])==0)
#else
      if(strcasecmp(ext,gme_allowed_exts[i])==0)
#endif
         return true;
   }
   return false;
}

/* alguns .zip (ex: gerados pelo Compress-Archive do PowerShell no Windows)
   gravam o caminho interno das entradas usando '\' em vez de '/'.
   O formato ZIP em si so reconhece '/' como separador de pasta, entao
   normalizamos aqui, num unico lugar, assim que o nome sai do unzip -
   qualquer zip antigo (com '\') ou novo (com '/') passa a funcionar igual
   em todo o resto do arquivo. */
static void normalize_zip_path(char *name)
{
   char *p;
   for (p = name; *p; p++)
   {
      if (*p == '\\')
         *p = '/';
   }
}

static bool uncompress_file_data(file_data** fd)
{
   int srcLen,dstLen;
   int err            = -1;
   z_stream strm      = {0};
   file_data* src_fd  = *fd;
   file_data* dest_fd = NULL;

   srcLen             = src_fd->length;
   memcpy(&dstLen,&(src_fd->data[src_fd->length-4]),4);
   dest_fd            = malloc(sizeof(file_data));
   dest_fd->length    = dstLen;
   dest_fd->name      = calloc(strlen(src_fd->name)+1,sizeof(char));
   strcpy(dest_fd->name,src_fd->name);
   dest_fd->data      = malloc(dstLen * sizeof(char));
   strm.total_in      = strm.avail_in  = srcLen;
   strm.total_out     = strm.avail_out = dstLen;
   strm.next_in       = (Bytef *) src_fd->data;
   strm.next_out      = (Bytef *) dest_fd->data;

   strm.zalloc        = Z_NULL;
   strm.zfree         = Z_NULL;
   strm.opaque        = Z_NULL;

   // 15 window bits, and the +32 tells zlib 
   // to to detect if using gzip or zlib
   if ((err = inflateInit2(&strm, (15 + 32))) == Z_OK)
   {
      if ((err = inflate(&strm, Z_FINISH)) != Z_STREAM_END)
      {
         inflateEnd(&strm);
         return false;
      }
   }
   else
   {
      inflateEnd(&strm);
      return false;
   }

   inflateEnd(&strm);
   free(src_fd->data);
   free(src_fd->name);
   free(src_fd);
   *fd = dest_fd;
   return true;
}

static bool get_files_from_zip(const char *path,
      file_data ***dest_files, int *dest_numfiles)
{
   int i;
   char *ext;
   unz_global_info64 gi;
   unz_file_info64 file_info;
   char filename_inzip[256];
   file_data **files;
   int numfiles,position;
   //load zip content
   unzFile uf = unzOpen64(path);
   unzGetGlobalInfo64(uf,&gi);
   numfiles = (int)gi.number_entry;
   files    = malloc(sizeof(file_data*) * numfiles);
   position = 0;
   for(i=0;i<gi.number_entry;i++)
   {
      void* buf;
      int bytes_read;
      uInt size_buf = 8192;
      //read compressed file info
      int err = unzGetCurrentFileInfo64(uf,&file_info,filename_inzip,sizeof(filename_inzip),NULL,0,NULL,0);
      if(err!=UNZ_OK)
         return false;
      normalize_zip_path(filename_inzip);
      if(filename_inzip[file_info.size_filename -1]=='/')
         ext = strrchr(filename_inzip,'/');
      else
         ext = strrchr(filename_inzip,'.') + 1;
      if(is_gme_allowed_ext(ext))
      {
         //get file name in zip
         files[position] = malloc(sizeof(file_data));
         files[position]->name = calloc(strlen(filename_inzip)+1,sizeof(char));
         strcpy(files[position]->name,filename_inzip);
         //allocate uncompressed data buffer
         files[position]->length= sizeof(char) * file_info.uncompressed_size;
         files[position]->data = (char*)malloc(files[position]->length);
         //setup buffer
         bytes_read = 0;
         buf = (void*)malloc(size_buf);
         if (buf==NULL)
            return false;
         //read file from zip
         err = unzOpenCurrentFilePassword(uf,NULL);
         if (err != UNZ_OK)
            return false;
         //get data from zip
         do 
         {
            err = unzReadCurrentFile(uf,buf,size_buf);
            if(err<0)
               return false;
            if(err>0)
            {
               memcpy(files[position]->data + bytes_read,buf,err * sizeof(char));
               bytes_read += err;
            }
         } while (err>0);
         if(buf!=NULL)
            free(buf);

#if defined(_WIN32) || defined(_WIN64)
         if(_stricmp(ext,"vgz")==0)
#else
         if(strcasecmp(ext,"vgz")==0)
#endif
            if(!uncompress_file_data(&(files[position])))
               return false;
         position++;
      }
      else
      {
         numfiles--;
      }
      if ((i+1)<gi.number_entry)
         unzGoToNextFile(uf);
   }
   files = realloc(files,sizeof(file_data*) * numfiles);
   *dest_files = files;
   *dest_numfiles = numfiles;
   return true;
}


/* ---- navegador: lista o conteudo de um .zip (arquivos jogaveis e zips aninhados) ---- */

static bool is_zip_ext(const char *ext)
{
#if defined(_WIN32) || defined(_WIN64)
   return _stricmp(ext,"zip")==0;
#else
   return strcasecmp(ext,"zip")==0;
#endif
}

static int zip_entry_cmp(const void *a, const void *b)
{
   const zip_entry *ea = *(const zip_entry * const *)a;
   const zip_entry *eb = *(const zip_entry * const *)b;
#if defined(_WIN32) || defined(_WIN64)
   return _stricmp(ea->name, eb->name);
#else
   return strcasecmp(ea->name, eb->name);
#endif
}

bool list_zip_entries(const char *path, const char *prefix, zip_entry ***dest_entries, int *dest_count)
{
   int i;
   unz_global_info64 gi;
   unz_file_info64 file_info;
   char filename_inzip[256];
   zip_entry **dirs, **files, **entries;
   int dir_count = 0, file_count = 0, cap, count;
   size_t prefix_len = prefix ? strlen(prefix) : 0;
   unzFile uf = unzOpen64(path);
   if (!uf)
      return false;
   if (unzGetGlobalInfo64(uf,&gi) != UNZ_OK)
   {
      unzClose(uf);
      return false;
   }
   cap   = gi.number_entry ? (int)gi.number_entry : 1;
   dirs  = (zip_entry**)malloc(sizeof(zip_entry*) * cap);
   files = (zip_entry**)malloc(sizeof(zip_entry*) * cap);
   if (!dirs || !files)
   {
      free(dirs); free(files);
      unzClose(uf);
      return false;
   }
   for(i=0;i<(int)gi.number_entry;i++)
   {
      int err = unzGetCurrentFileInfo64(uf,&file_info,filename_inzip,sizeof(filename_inzip),NULL,0,NULL,0);
      if (err==UNZ_OK)
         normalize_zip_path(filename_inzip);
      if(err==UNZ_OK && file_info.size_filename>0 && filename_inzip[file_info.size_filename-1] != '/'
         && (prefix_len==0 || strncmp(filename_inzip,prefix,prefix_len)==0))
      {
         const char *rest = filename_inzip + prefix_len;
         if (rest[0])
         {
            const char *slash = strchr(rest,'/');
            if (slash) /* item esta dentro de uma subpasta deste nivel */
            {
               size_t dlen = (size_t)(slash - rest);
               int j, found = 0;
               for(j=0;j<dir_count;j++)
               {
                  if (strlen(dirs[j]->name)==dlen && strncmp(dirs[j]->name,rest,dlen)==0)
                  {
                     found = 1;
                     break;
                  }
               }
               if (!found)
               {
                  zip_entry *e = (zip_entry*)malloc(sizeof(zip_entry));
                  if (e)
                  {
                     e->name = (char*)calloc(dlen+1,sizeof(char));
                     if (e->name)
                     {
                        memcpy(e->name, rest, dlen);
                        e->name[dlen] = '\0';
                     }
                     e->is_zip = 0;
                     e->is_dir = 1;
                     dirs[dir_count++] = e;
                  }
               }
            }
            else /* arquivo (ou zip aninhado) direto neste nivel */
            {
               char *ext = strrchr(rest,'.');
               if (ext)
               {
                  ext++;
                  if (is_zip_ext(ext) || is_gme_allowed_ext(ext))
                  {
                     zip_entry *e = (zip_entry*)malloc(sizeof(zip_entry));
                     if (e)
                     {
                        e->name = (char*)calloc(strlen(rest)+1,sizeof(char));
                        if (e->name)
                           strcpy(e->name, rest);
                        e->is_zip = is_zip_ext(ext) ? 1 : 0;
                        e->is_dir = 0;
                        files[file_count++] = e;
                     }
                  }
               }
            }
         }
      }
      if ((i+1) < (int)gi.number_entry)
         unzGoToNextFile(uf);
   }
   unzClose(uf);

   count = dir_count + file_count;
   if (count == 0)
   {
      free(dirs); free(files);
      return false;
   }

   qsort(dirs,  dir_count,  sizeof(zip_entry*), zip_entry_cmp);
   qsort(files, file_count, sizeof(zip_entry*), zip_entry_cmp);

   entries = (zip_entry**)malloc(sizeof(zip_entry*) * count);
   if (!entries)
   {
      free(dirs); free(files);
      return false;
   }
   /* pastas primeiro, depois arquivos - igual ao WinRAR/explorer */
   for(i=0;i<dir_count;i++)  entries[i]            = dirs[i];
   for(i=0;i<file_count;i++) entries[dir_count + i] = files[i];
   free(dirs);
   free(files);
   *dest_entries = entries;
   *dest_count   = count;
   return true;
}

void free_zip_entries(zip_entry **entries, int count)
{
   int i;
   if (!entries)
      return;
   for(i=0;i<count;i++)
   {
      if (entries[i])
      {
         free(entries[i]->name);
         free(entries[i]);
      }
   }
   free(entries);
}

/* le o conteudo (ja descomprimido) de UM arquivo dentro do zip, para a memoria.
   Antes usava unzLocateFile(), que compara entry_name com o nome EXATAMENTE
   como esta gravado no zip (inclusive '\' vs '/'); como a arvore do navegador
   agora trabalha sempre com '/' (normalizado), a busca precisa normalizar
   tambem o nome de cada entrada do zip antes de comparar, ou zips com '\'
   deixam de ser encontrados na hora de extrair. */
bool extract_zip_entry(const char *zip_path, const char *entry_name, char **dest_data, int *dest_len)
{
   unz_global_info64 gi;
   unz_file_info64 file_info;
   char filename_inzip[256];
   char *buf;
   int bytes_read = 0;
   int i;
   bool found = false;
   unzFile uf = unzOpen64(zip_path);
   if (!uf)
      return false;
   if (unzGetGlobalInfo64(uf,&gi) != UNZ_OK)
   {
      unzClose(uf);
      return false;
   }
   for(i=0;i<(int)gi.number_entry;i++)
   {
      if (unzGetCurrentFileInfo64(uf,&file_info,filename_inzip,sizeof(filename_inzip),NULL,0,NULL,0) == UNZ_OK)
      {
         normalize_zip_path(filename_inzip);
#if defined(_WIN32) || defined(_WIN64)
         if (_stricmp(filename_inzip, entry_name) == 0)
#else
         if (strcasecmp(filename_inzip, entry_name) == 0)
#endif
         {
            found = true;
            break;
         }
      }
      if ((i+1) < (int)gi.number_entry)
         unzGoToNextFile(uf);
      else
         break;
   }
   if (!found)
   {
      unzClose(uf);
      return false;
   }
   if (unzGetCurrentFileInfo64(uf,&file_info,NULL,0,NULL,0,NULL,0) != UNZ_OK)
   {
      unzClose(uf);
      return false;
   }
   buf = (char*)malloc(file_info.uncompressed_size ? (size_t)file_info.uncompressed_size : 1);
   if (!buf)
   {
      unzClose(uf);
      return false;
   }
   if (unzOpenCurrentFilePassword(uf,NULL) != UNZ_OK)
   {
      free(buf);
      unzClose(uf);
      return false;
   }
   while (bytes_read < (int)file_info.uncompressed_size)
   {
      int chunk = (int)file_info.uncompressed_size - bytes_read;
      int err;
      if (chunk > 65536)
         chunk = 65536;
      err = unzReadCurrentFile(uf, buf + bytes_read, (unsigned)chunk);
      if (err < 0)
      {
         unzCloseCurrentFile(uf);
         unzClose(uf);
         free(buf);
         return false;
      }
      if (err == 0)
         break;
      bytes_read += err;
   }
   unzCloseCurrentFile(uf);
   unzClose(uf);
   *dest_data = buf;
   *dest_len  = bytes_read;
   return true;
}

bool get_file_data(const char *path,file_data ***dest_files, int *dest_numfiles)
{
   //local variables
   RFILE *fp;
   file_data *fd;
   file_data **files;
   //get file name and extension
   const char *bname = path_basename(path);
   char *ext         = strrchr(path,'.') +1;
   //get file data
#if defined(_WIN32) || defined(_WIN64)
   if(_stricmp(ext,"zip")==0)
#else
   if(strcasecmp(ext,"zip")==0)
#endif
      return get_files_from_zip(path,dest_files,dest_numfiles);
   if (!(fp = rfopen(path,"rb")))
      return false;
   files = malloc(sizeof(file_data*));
   fd    = malloc(sizeof(file_data));
   //get file length
   fd->length = filestream_get_size(fp);
   //get file data
   fd->data = malloc(sizeof(char)*fd->length);
   rfread(fd->data,1,fd->length,fp);
   rfclose(fp);
   fd->name = calloc(strlen(bname)+1,sizeof(char));
   strcpy(fd->name,bname);
#if defined(_WIN32) || defined(_WIN64)
   if(_stricmp(ext,"vgz")==0)
#else
   if(strcasecmp(ext,"vgz")==0)
#endif
   {
      if(!uncompress_file_data(&fd))
         return false;
   }
   files[0]       = fd;
   *dest_files    = files;
   *dest_numfiles = 1;
   return true;
}
