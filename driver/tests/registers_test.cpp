#include <cstdio>
#include <cstdlib>

#include "Registers.h"

using namespace Ensemble;

static int failures = 0;

#define CHECK(condition)                                                   \
    do {                                                                   \
        if (!(condition)) {                                                \
            std::printf("%s:%d: CHECK(%s)\n", __FILE__, __LINE__, #condition); \
            failures++;                                                    \
        }                                                                  \
    } while (0)

static void depth_follows_the_vendor_rate_bands()
{
    CHECK(depthFor(44100.0) == 2 && depthFor(48000.0) == 2);
    CHECK(depthFor(88200.0) == 8 && depthFor(96000.0) == 8);
    CHECK(depthFor(176400.0) == 32 && depthFor(192000.0) == 32);
}

static void meter_timer_divides_the_core_clock_constant()
{
    CHECK(meterTimer(20, 0) == 122070 / 20 - 1);
    CHECK(meterTimer(30, kGeneralFastClock) == 244140 / 30 - 1);
}

static void meter_buffer_holds_the_sequence_byte_and_every_meter()
{
    CHECK(meterBufferBytes(88) == 0xB4);
}

static void wraps_count_ring_periods_not_interrupts()
{
    const uint64_t period = 341333333;
    CHECK(wrapsIn(period, 48000.0) == 1);
    CHECK(wrapsIn(2 * period + 5000000, 48000.0) == 2);
    CHECK(wrapsIn(period * 3 / 2 - 1000000, 48000.0) == 1);
    CHECK(wrapsIn(1000000, 48000.0) == 0);
    CHECK(wrapsIn(85333333, 192000.0) == 1);
}

int main()
{
    meter_timer_divides_the_core_clock_constant();
    meter_buffer_holds_the_sequence_byte_and_every_meter();
    depth_follows_the_vendor_rate_bands();
    wraps_count_ring_periods_not_interrupts();
    if (failures == 0) {
        std::printf("ok\n");
    }
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
