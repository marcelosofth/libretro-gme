#ifndef XMP_BACKEND_H
#define XMP_BACKEND_H
#ifdef __cplusplus
extern "C" {
#endif
int  xmp_backend_probe(const unsigned char *data, long size, char *name, int name_len, long *duration_ms);
/* filename: usado so para decidir a mixagem (extensao .mod + assinatura Amiga no offset 1080).
   Pode ser NULL/vazio; nesse caso a mixagem Paula nunca e ligada. */
int  xmp_backend_open(const unsigned char *data, long size, long sample_rate, const char *filename);
void xmp_backend_close(void);
int  xmp_backend_render(short *out, int frames);
int  xmp_backend_ended(void);
long xmp_backend_tell_ms(void);
long xmp_backend_tell_samples(void);
/* true se o modulo aberto e um MOD Amiga de verdade e esta usando a mixagem Paula (A500) */
int  xmp_backend_uses_amiga_mix(void);
#ifdef __cplusplus
}
#endif
#endif
