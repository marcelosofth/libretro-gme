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

char *get_system_line(char *buf);

char *get_track_label(char *buf);

char *get_time_text(char *buf);

char *get_rate_text(char *buf);

int get_track_progress_permille(void);

char *get_chip_text(char *buf);

void toggle_loop(void);

bool get_loop_enabled(void);

bool get_is_playing(void);

#endif
