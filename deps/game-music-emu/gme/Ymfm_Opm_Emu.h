// YM2151 (OPM) sound chip emulator interface, backed by Aaron Giles' `ymfm`
// library (BSD-3-Clause). Written for this project to expose the same
// contract gme's other FM chip wrappers use (see Ym2612_Nuked.h), so it can
// be dropped into Vgm_Emu_Impl the same way Ym2612_Emu/Ym2413_Emu are.

// Game_Music_Emu https://bitbucket.org/mpyne/game-music-emu/
#ifndef YMFM_OPM_EMU_H
#define YMFM_OPM_EMU_H

#include "ymfm_opm.h"

class Ymfm_Opm_Emu : public ymfm::ymfm_interface {
public:
	Ymfm_Opm_Emu() : chip( *this ) { }

	// Set output sample rate and chip clock rate, in Hz. Returns non-zero
	// (a message) if error. ymfm derives all internal timing from clock
	// ticks, so there is nothing to configure here beyond a fresh reset.
	const char* set_rate( double sample_rate, double clock_rate )
	{
		(void) sample_rate;
		(void) clock_rate;
		return NULL;
	}

	// Reset to power-up state
	void reset()
	{
		chip.reset();
	}

	// Mute voice n if bit n (1 << n) of mask is set. ymfm doesn't expose
	// per-voice muting the way gme's other chips do; no-op for now.
	enum { channel_count = 8 };
	void mute_voices( int mask ) { (void) mask; }

	// VGM's single YM2151 command bundles "register addr" + "data" into one
	// call, but the real chip (and ymfm) has two separate bus ports: write
	// the address first (offset 0), then the data (offset 1).
	void write( int addr, int data )
	{
		chip.write( 0, (unsigned char) addr );
		chip.write( 1, (unsigned char) data );
	}

	// Run and add pair_count samples into current output buffer contents
	typedef short sample_t;
	enum { out_chan_count = 2 }; // stereo
	void run( int pair_count, sample_t* out )
	{
		for ( int i = 0; i < pair_count; i++ )
		{
			ymfm::ym2151::output_data output;
			chip.generate( &output, 1 );
			output.clamp16();
			out [0] = (sample_t) (out [0] + output.data [0]);
			out [1] = (sample_t) (out [1] + output.data [1]);
			out += 2;
		}
	}

	// Exposes ymfm's own clock->sample-rate math, so Vgm_Emu.cpp can compute
	// fm_rate the same way it does for ym2612 (clock/144.0) and ym2413
	// (clock/72.0), but reading it from ymfm instead of guessing a divisor.
	uint32_t sample_rate( uint32_t input_clock ) const
	{
		return chip.sample_rate( input_clock );
	}

private:
	ymfm::ym2151 chip;
};

#endif
