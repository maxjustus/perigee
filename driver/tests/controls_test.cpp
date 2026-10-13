#include <cstring>

#include "check.h"
#include "Controls.h"

using namespace Ensemble;

static void attenuation_is_whole_decibels_below_zero()
{
    CHECK(decibels(47) == -47.0f);
    CHECK(attenuation(-47.4f) == 47 && attenuation(-46.6f) == 47);
    CHECK(attenuation(3.0f) == 0 && attenuation(-100.0f) == kMaxAttenuation);
}

static void follow_moves_every_monitor_by_the_speaker_change()
{
    uint8_t monitors[kMonitorOutputs] = {19, 27, 47};
    follow(monitors, 57);
    CHECK(monitors[0] == 29 && monitors[1] == 37 && monitors[kSpeaker] == 57);
}

static void follow_clamps_each_monitor()
{
    uint8_t monitors[kMonitorOutputs] = {60, 2, 47};
    follow(monitors, 57);
    CHECK(monitors[0] == kMaxAttenuation && monitors[1] == 12);
    follow(monitors, 30);
    CHECK(monitors[0] == 37 && monitors[1] == 0 && monitors[kSpeaker] == 30);
}

static void monitors_wait_for_every_output_before_a_volume_change()
{
    Monitors monitors = {};
    int sent = 0;
    auto count = [&](uint8_t, uint8_t) { return ++sent > 0; };
    monitors.request(10);
    monitors.report(0, 20);
    monitors.report(2, 30);
    monitors.apply(count);
    CHECK(sent == 0);
    monitors.report(1, 25);
    monitors.apply(count);
    CHECK(sent == 3);
    monitors.apply(count);
    CHECK(sent == 3);
}

static void monitors_send_only_the_outputs_that_move()
{
    Monitors monitors = {};
    monitors.report(0, kMaxAttenuation);
    monitors.report(1, 20);
    monitors.report(2, 30);
    monitors.request(35);
    uint8_t outputs[kMonitorOutputs] = {};
    uint8_t values[kMonitorOutputs] = {};
    int sent = 0;
    monitors.apply([&](uint8_t output, uint8_t value) {
        outputs[sent] = output;
        values[sent++] = value;
        return true;
    });
    CHECK(sent == 2);
    CHECK(outputs[0] == 1 && values[0] == 25);
    CHECK(outputs[1] == 2 && values[1] == 35);
}

static void clock_sources_follow_the_vendor_order()
{
    CHECK(kClockSourceCount == 5);
    CHECK(std::strcmp(kClockSourceNames[0], "Internal") == 0);
    CHECK(std::strcmp(kClockSourceNames[4], "Optical 2") == 0);
}

static bool named(bool input, uint32_t index, const char * expected)
{
    char name[32];
    channelName(input, index, name, sizeof(name));
    return std::strcmp(name, expected) == 0;
}

static void channel_names_follow_the_vendor_input_order()
{
    CHECK(named(true, 0, "Analog 1") && named(true, 7, "Analog 8"));
    CHECK(named(true, 8, "Front Mic L") && named(true, 9, "Front Mic R"));
    CHECK(named(true, 10, "Guitar 1") && named(true, 11, "Guitar 2"));
    CHECK(named(true, 12, "S/PDIF L") && named(true, 13, "S/PDIF R"));
    CHECK(named(true, 14, "Optical 1") && named(true, 29, "Optical 16"));
    CHECK(named(true, 30, "Mix 1 L") && named(true, 33, "FX Send R"));
    CHECK(named(false, 0, "Playback 1") && named(false, 35, "Playback 36"));
}

int main()
{
    clock_sources_follow_the_vendor_order();
    channel_names_follow_the_vendor_input_order();
    attenuation_is_whole_decibels_below_zero();
    follow_moves_every_monitor_by_the_speaker_change();
    follow_clamps_each_monitor();
    monitors_wait_for_every_output_before_a_volume_change();
    monitors_send_only_the_outputs_that_move();
    return finish();
}
