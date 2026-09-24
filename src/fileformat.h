#ifndef GME_LIBRETRO_FILEFORMAT_H__
#define GME_LIBRETRO_FILEFORMAT_H__

typedef struct
{
   char* name;
   char* data;
   int length;
} file_data;

bool get_file_data(const char *path,file_data ***files, int *dest_numfiles);

/* ---- navegador: lista o conteudo de um .zip (arquivos jogaveis e zips aninhados) ---- */

typedef struct
{
   char *name;   /* nome do item NESTE nivel (sem o caminho da pasta atual), ex: "SuperContra.zip" ou "Jogos" */
   int   is_zip; /* 1 = zip aninhado (precisa extrair pra rodar), 0 = arquivo jogavel ou pasta */
   int   is_dir; /* 1 = pasta (subdiretorio dentro do zip, navegar para dentro) */
} zip_entry;

/* prefix: caminho da pasta atual dentro do zip (ex: "" para a raiz, "Jogos/" para dentro de "Jogos").
   Lista so os itens IMEDIATOS daquele nivel: pastas (deduplicadas) primeiro, depois arquivos/zips. */
bool list_zip_entries(const char *path, const char *prefix, zip_entry ***dest_entries, int *dest_count);
void free_zip_entries(zip_entry **entries, int count);
bool extract_zip_entry(const char *zip_path, const char *entry_name, char **dest_data, int *dest_len);

#endif
