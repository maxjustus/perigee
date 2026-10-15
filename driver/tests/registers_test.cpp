#include "check.h"
#include "Registers.h"

using namespace Ensemble;

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

static void latency_matches_the_vendor_hal()
{
    const Latency single = latencyFor(48000.0);
    CHECK(single.safety == 3 && single.input == 13 && single.output == 43);
    const Latency twice = latencyFor(88200.0);
    CHECK(twice.safety == 12 && twice.input == 19 && twice.output == 22);
    const Latency quad = latencyFor(192000.0);
    CHECK(quad.safety == 48 && quad.input == 45 && quad.output == 43);
}

static void bootloader_status_reads_info_bits_7_to_6()
{
    CHECK(bootloaderStatus(0x50) == kStatusApplication);
    CHECK(bootloaderStatus(0x90) == kStatusBootloader);
    CHECK(bootloaderStatus(0xFFFFFFFF) == 3);
}

int main()
{
    meter_timer_divides_the_core_clock_constant();
    meter_buffer_holds_the_sequence_byte_and_every_meter();
    depth_follows_the_vendor_rate_bands();
    wraps_count_ring_periods_not_interrupts();
    latency_matches_the_vendor_hal();
    bootloader_status_reads_info_bits_7_to_6();
    return finish();
}
