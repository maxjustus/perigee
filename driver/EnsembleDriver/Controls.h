#ifndef Controls_h
#define Controls_h

#include <stdint.h>

namespace Ensemble {

constexpr uint8_t kCommandOutputAttenuation = 0x11;
constexpr uint8_t kMonitorOutputs = 3;
constexpr uint8_t kSpeaker = 2;
constexpr uint8_t kMaxAttenuation = 64;

constexpr uint8_t kCommandClockSource = 0x2A;
constexpr const char * kClockSourceNames[] = {"Internal", "Word Clock", "S/PDIF Coax",
                                              "Optical 1", "Optical 2"};
constexpr uint32_t kClockSourceCount = sizeof(kClockSourceNames) / sizeof(kClockSourceNames[0]);

inline float decibels(uint8_t attenuation)
{
    return -float(attenuation);
}

inline uint8_t attenuation(float decibels)
{
    const float steps = -decibels;
    if (steps <= 0.0f) {
        return 0;
    }
    if (steps >= kMaxAttenuation) {
        return kMaxAttenuation;
    }
    return uint8_t(steps + 0.5f);
}

inline void follow(uint8_t monitors[kMonitorOutputs], uint8_t speaker)
{
    const int delta = int(speaker) - monitors[kSpeaker];
    for (uint8_t i = 0; i < kMonitorOutputs; i++) {
        const int moved = monitors[i] + delta;
        monitors[i] = uint8_t(moved < 0 ? 0 : moved > kMaxAttenuation ? kMaxAttenuation : moved);
    }
}

}

#endif
