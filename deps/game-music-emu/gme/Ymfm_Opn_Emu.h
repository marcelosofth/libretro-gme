// YM2203 (OPN) sound chip emulator interface, backed by Aaron Giles' `ymfm`
// library (BSD-3-Clause). The YM2203 has an embedded SSG alongside its FM
// engine; ymfm exposes them as separate outputs: index 0 is the mono FM
// signal, indices 1-3 are the three SSG channels. We sum all of them into one
// mono signal and duplicate to L/R.
//
// ymfm's YM2203 runs at a very high native rate (chip.sample_rate(clock), about
// clock/4), far above gme's FM rate. So the chip is run at its native rate here
// and decimated to gme's rate with a box (averaging) filter.

// Game_Music_Emu https://bitbucket.org/mpyne/game-music-emu/
#ifndef YMFM_OPN_EMU_H
#define YMFM_OPN_EMU_H

#include "ymfm_opn.h"
#include <stdint.h>
#include <stdio.h>
#include <chrono>

class Ymfm_Opn_Emu : public ymfm::ymfm_interface {
public:
	Ymfm_Opn_Emu() : chip( *this ), out_rate( 44100.0 ), clock( 0 ), cur( 0.0 ), cur_left( 0.0 ) { }

	// sample_rate: rate gme wants for the FM buffer; clock_rate: chip clock.
	const char* set_rate( double sample_rate, double clock_rate )
	{
		out_rate = sample_rate;
		clock = (uint32_t) clock_rate;
                chip.set_fidelity( ymfm::OPN_FIDELITY_MIN );
		return NULL;
	}

	void reset()
	{
		chip.reset();
                chip.set_fidelity( ymfm::OPN_FIDELITY_MIN );
		cur = 0.0;
		cur_left = 0.0;
	}

	enum { channel_count = 3 + 3 }; // 3 FM channels + 3 SSG channels
	void mute_voices( int mask ) { (void) mask; }

	void write( int addr, int data )
	{
		chip.write( 0, (unsigned char) addr );
		chip.write( 1, (unsigned char) data );
	}

	// Run and add pair_count samples into current output buffer contents.
	typedef short sample_t;
	enum { out_chan_count = 2 };
	void run( int pair_count, sample_t* out )
	{
		static const double level = 0.10; // overall level of FM + SSG mix

		for ( int i = 0; i < pair_count; i++ )
		{
			// chip samples to consume for one output sample
			double step = (double) chip.sample_rate( clock ) / out_rate;
			if ( step <= 0.0 )
				step = 1.0;

			double remaining = step;
			double acc = 0.0;
			while ( remaining > 1e-9 )
			{
				if ( cur_left <= 1e-9 )
				{
					ymfm::ym2203::output_data o;
					chip.generate( &o, 1 );
					o.clamp16();
                                        n_gen++;
                                        for ( unsigned c = 0; c < 4; c++ )
                                        {
                                                int a = o.data [c] < 0 ? -o.data [c] : o.data [c];
                                                if ( a > pk [c] ) pk [c] = a;
                                        }
					int s = 0;
					for ( unsigned c = 0; c < ymfm::ym2203::OUTPUTS; c++ )
						s += o.data [c];
					cur = s * level;
					cur_left = 1.0;
				}
				double take = cur_left < remaining ? cur_left : remaining;
				acc += cur * take;
				cur_left -= take;
				remaining -= take;
			}

			int mono = (int) ( acc / step );
                        { int a = mono < 0 ? -mono : mono; if ( a > pk_mix ) pk_mix = a; }
			if ( mono > 32767 ) mono = 32767;
			if ( mono < -32768 ) mono = -32768;
			out [0] = (sample_t) (out [0] + mono);
			out [1] = (sample_t) (out [1] + mono);
			out += 2;
                        if ( ++n_out >= (unsigned long) out_rate )
                        {
                                double dt = dt_since_last();
                                fprintf( dbg_file(), "ym2203: clock=%u nativo=%u saida=%.0f step=%.3f gen/out=%.3f pico=%d,%d,%d,%d mix=%d dt=%.3f\n",
                                         clock, (unsigned) chip.sample_rate( clock ), out_rate, step,
                                         (double) n_gen / n_out, pk [0], pk [1], pk [2], pk [3], pk_mix, dt );
                                fflush( dbg_file() );
                                n_gen = n_out = 0;
                                pk [0] = pk [1] = pk [2] = pk [3] = pk_mix = 0;
                        }
		}
	}

	double dt_since_last()
        {
                std::chrono::steady_clock::time_point now = std::chrono::steady_clock::now();
                double d = t_ok ? std::chrono::duration<double>( now - t_last ).count() : 0.0;
                t_last = now; t_ok = true;
                return d;
        }

        static FILE* dbg_file()
        {
                static FILE* f = 0;
                if ( !f ) { f = fopen( "ym2203_debug.txt", "a" ); if ( !f ) f = stderr; }
                return f;
        }

        uint32_t sample_rate( uint32_t input_clock ) const
	{
		return chip.sample_rate( input_clock );
	}

private:
	ymfm::ym2203 chip;
	double out_rate;
	uint32_t clock;
	double cur;      // current chip sample (already scaled)
	double cur_left; // fraction of the current chip sample not yet consumed
        unsigned long n_gen = 0, n_out = 0; // debug
        int pk [4] = { 0, 0, 0, 0 };
        int pk_mix = 0;
        std::chrono::steady_clock::time_point t_last;
        bool t_ok = false;
};

#endif
