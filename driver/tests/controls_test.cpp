#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "Controls.h"

using namespace Ensemble;

static int failures = 0;

#define CHECK(condition)                                                   \
    do {                                                                   \
        if (!(condition)) {                                                \
            std::printf("%s:%d: CHECK(%s)\n", __FILE__, __LINE__, #condition); \
            failures++;                                                    \
        }                                                                  \
    } while (0)

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

static void clock_sources_follow_the_vendor_order()
{
    CHECK(kClockSourceCount == 5);
    CHECK(std::strcmp(kClockSourceNames[0], "Internal") == 0);
    CHECK(std::strcmp(kClockSourceNames[4], "Optical 2") == 0);
}

int main()
{
    clock_sources_follow_the_vendor_order();
    attenuation_is_whole_decibels_below_zero();
    follow_moves_every_monitor_by_the_speaker_change();
    follow_clamps_each_monitor();
    if (failures == 0) {
        std::printf("ok\n");
    }
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
