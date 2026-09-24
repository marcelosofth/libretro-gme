#ifndef VGM_BACKEND_H
#define VGM_BACKEND_H
#ifdef __cplusplus
extern "C" {
#endif
int vgm_backend_open(const unsigned char *data, long size, long sample_rate);
void vgm_backend_close(void);
int vgm_backend_render(short *out, int frames);
int vgm_backend_ended(void);
long vgm_backend_tell_ms(void);
long vgm_backend_tell_samples(void);
#ifdef __cplusplus
}
#endif
#endif
