#ifndef MP3_BACKEND_H
#define MP3_BACKEND_H
#ifdef __cplusplus
extern "C" {
#endif
int  mp3_backend_probe(const unsigned char *data, long size, char *title, int title_len,
                       char *artist, int artist_len, long *duration_ms);
int  mp3_backend_open(const unsigned char *data, long size, long sample_rate);
void mp3_backend_close(void);
int  mp3_backend_render(short *out, int frames);
int  mp3_backend_ended(void);
long mp3_backend_tell_ms(void);
long mp3_backend_tell_samples(void);
#ifdef __cplusplus
}
#endif
#endif
