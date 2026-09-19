// Mono OPL-family (YM3812/OPL2, YM3526/OPL) sound chip emulator interface,
// backed by Aaron Giles' `ymfm` library (BSD-3-Clause). Templated because
// both chips share the exact same simple single-port write / mono-output
// interface; only the underlying ymfm chip type differs.

// Game_Music_Emu https://bitbucket.org/mpyne/game-music-emu/
#ifndef YMFM_OPL_MONO_EMU_H
#define YMFM_OPL_MONO_EMU_H

#include "ymfm_opl.h"

template<class ChipType>
class Ymfm_Opl_Mono_Emu : public ymfm::ymfm_interface {
public:
	Ymfm_Opl_Mono_Emu() : chip( *this ) { }

	const char* set_rate( double sample_rate, double clock_rate )
	{
		(void) sample_rate;
		(void) clock_rate;
		return NULL;
	}

	void reset()
	{
		chip.reset();
	}

	enum { channel_count = 9 };
	void mute_voices( int mask ) { (void) mask; }

	// Same address-then-data pattern as YM2151.
	void write( int addr, int data )
	{
		chip.write( 0, (unsigned char) addr );
		chip.write( 1, (unsigned char) data );
	}

	// Run and add pair_count samples into current output buffer contents.
	// These chips are mono (OUTPUTS == 1); duplicate to both L and R so
	// they fit gme's stereo FM mixing buffer.
	typedef short sample_t;
	enum { out_chan_count = 2 };
	void run( int pair_count, sample_t* out )
	{
		for ( int i = 0; i < pair_count; i++ )
		{
			typename ChipType::output_data output;
			chip.generate( &output, 1 );
			output.clamp16();
			out [0] = (sample_t) (out [0] + output.data [0]);
			out [1] = (sample_t) (out [1] + output.data [0]);
			out += 2;
		}
	}

	uint32_t sample_rate( uint32_t input_clock ) const
	{
		return chip.sample_rate( input_clock );
	}

private:
	ChipType chip;
};

typedef Ymfm_Opl_Mono_Emu<ymfm::ym3812> Ymfm_Ym3812_Emu;
typedef Ymfm_Opl_Mono_Emu<ymfm::ym3526> Ymfm_Ym3526_Emu;

#endif