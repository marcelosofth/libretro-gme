#ifndef GME_LIBRETRO_PLAYER_H__
#define GME_LIBRETRO_PLAYER_H__
#include <stdlib.h>
#include <boolean.h>
#include "gme.h"

bool is_emu_loaded(void);

bool open_file(const char *path, long sample_rate);

void set_system_dir(const char *dir);

void close_file(void);

void start_track(int track);

short *play(void);

/* dir: 0 = normal, 1 = avanco rapido (R segurado), -1 = voltar acelerado (L segurado) */
short *play_scan(int dir);

void next_track(void);

void prev_track(void);

char *get_game_name(char *buf);

char *get_track_count(char *buf);

char *get_song_name(char *buf);

char *get_track_position(char *buf);

int get_track_elapsed_frames(void);

void play_pause(void);

void stop_track(void);

bool get_is_stopped(void);

char *get_system_line(char *buf);

char *get_track_label(char *buf);

char *get_time_text(char *buf);

char *get_rate_text(char *buf);

int get_track_progress_permille(void);

char *get_chip_text(char *buf);

/* ---- navegador: escolher outro arquivo dentro do .zip atualmente carregado ---- */

void set_temp_dir(const char *dir);

int browser_open(void);                  /* abre a lista (na ultima pasta usada, ou raiz); retorna a contagem, ou -1 se nao der */
int browser_last_cursor(void);           /* posicao do ultimo arquivo tocado na listagem atual (0 se nenhum) */
const char *browser_entry_name(int index);
int  browser_entry_is_zip(int index);
int  browser_entry_is_dir(int index);    /* 1 = pasta, navegar para dentro em vez de tocar/extrair */
int  browser_count(void);                /* contagem de itens da listagem atual (apos entrar/sair de pastas) */
void browser_select(int index);          /* pasta: entra nela. arquivo: toca. zip aninhado: extrai e carrega */
int  browser_up(void);                   /* sobe uma pasta; retorna nova contagem, ou -1 se ja estava na raiz */
int  browser_up_cursor(void);            /* posicao da pasta de onde saimos, na listagem de cima (0 se nao achar) */
void browser_close(void);                /* fecha sem escolher nada */
void player_cleanup_temp(void);          /* apaga o zip temporario, se houver (chamar ao descarregar o core) */

void toggle_loop(void);

bool get_loop_enabled(void);

/* alterna o sintetizador MIDI ativo (MT-32 -> TSF -> FluidSynth -> MT-32 -> ...)
   sem parar a musica: reabre a faixa com o novo sintetizador e avanca em
   silencio ate a mesma posicao onde estava. Nao faz nada se a faixa atual
   nao for um arquivo MIDI. */
void cycle_midi_synth(void);

bool get_is_playing(void);

#endif
