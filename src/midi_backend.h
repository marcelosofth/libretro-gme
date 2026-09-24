#ifndef MIDI_BACKEND_H
#define MIDI_BACKEND_H
#ifdef __cplusplus
extern "C" {
#endif

/* sintetizadores disponiveis; usado em midi_backend_set_synth() e midi_backend_active_synth() */
enum
{
   MIDI_SYNTH_AUTO       = 0,   /* escolhe automaticamente MT-32 ou GM conforme o conteudo do arquivo (padrao) */
   MIDI_SYNTH_MT32       = 1,   /* forca emulacao MT-32 / CM-32L (Munt) */
   MIDI_SYNTH_TSF        = 2,   /* forca sintese GM via SoundFont interno (TSF) */
   MIDI_SYNTH_FLUIDSYNTH = 3    /* forca sintese GM via SoundFont externo (FluidSynth) */
};

int  midi_backend_probe(const unsigned char *data, long size, char *title, int title_len, long *duration_ms);
/* retorna 0 = ok, -1 = erro, -2 = ROMs nao encontradas, -3 = ROMs invalidas, -4 = sem conversao de taxa, -5 = SoundFont nao encontrado, -6 = SoundFont invalido */
int  midi_backend_open(const unsigned char *data, long size, long sample_rate, const char *sysdir);
void midi_backend_close(void);
int  midi_backend_render(short *out, int frames);
int  midi_backend_ended(void);
int  midi_backend_is_gm(void);   /* 1 = o sintetizador ativo e via SoundFont (TSF ou FluidSynth), 0 = MT-32 */
long midi_backend_tell_ms(void);
long midi_backend_tell_samples(void);

/* escolha manual do sintetizador (persiste entre chamadas ate ser trocada de novo).
   deve ser chamada ANTES de midi_backend_open(); MIDI_SYNTH_AUTO restaura o
   comportamento automatico (classificacao MT-32 x GM pelo conteudo do arquivo). */
void midi_backend_set_synth(int synth);

/* qual sintetizador esta de fato em uso apos o midi_backend_open() mais recente
   (um dos valores MIDI_SYNTH_*); util quando o modo e MIDI_SYNTH_AUTO */
int  midi_backend_active_synth(void);

#ifdef __cplusplus
}
#endif
#endif
