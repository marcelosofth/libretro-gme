#ifndef MIDI_BACKEND_H
#define MIDI_BACKEND_H
#ifdef __cplusplus
extern "C" {
#endif
int  midi_backend_probe(const unsigned char *data, long size, char *title, int title_len, long *duration_ms);
/* retorna 0 = ok, -1 = erro, -2 = ROMs nao encontradas, -3 = ROMs invalidas, -4 = sem conversao de taxa, -5 = SoundFont nao encontrado, -6 = SoundFont invalido */
int  midi_backend_open(const unsigned char *data, long size, long sample_rate, const char *sysdir);
void midi_backend_close(void);
int  midi_backend_render(short *out, int frames);
int  midi_backend_ended(void);
int  midi_backend_is_gm(void);   /* 1 = o ultimo .mid aberto e MIDI comum (SoundFont), 0 = MT-32 */
long midi_backend_tell_ms(void);
long midi_backend_tell_samples(void);
#ifdef __cplusplus
}
#endif
#endif
