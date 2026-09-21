#ifndef XMP_BACKEND_H
#define XMP_BACKEND_H
#ifdef __cplusplus
extern "C" {
#endif
int  xmp_backend_probe(const unsigned char *data, long size, char *name, int name_len, long *duration_ms);
int  xmp_backend_open(const unsigned char *data, long size, long sample_rate);
void xmp_backend_close(void);
int  xmp_backend_render(short *out, int frames);
int  xmp_backend_ended(void);
long xmp_backend_tell_ms(void);
long xmp_backend_tell_samples(void);
#ifdef __cplusplus
}
#endif
#endif
