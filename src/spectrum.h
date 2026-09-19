#ifndef GME_LIBRETRO_SPECTRUM_H__
#define GME_LIBRETRO_SPECTRUM_H__

#include "graphics.h"

void spectrum_push(const short *stereo, int frames);
void spectrum_update(void);
void spectrum_draw_background(surface *surf);
void spectrum_draw_bars(surface *surf);

#endif
