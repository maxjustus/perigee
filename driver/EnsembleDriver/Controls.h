#ifndef Controls_h
#define Controls_h

#include <stddef.h>
#include <stdint.h>

namespace Ensemble {

constexpr uint8_t kCommandOutputAttenuation = 0x11;
constexpr uint8_t kMonitorOutputs = 3;
constexpr uint8_t kSpeaker = 2;
constexpr uint8_t kMaxAttenuation = 64;

constexpr uint8_t kCommandClockSource = 0x2A;
constexpr uint8_t kReportClockLock = 0x42;
constexpr const char * kClockSourceNames[] = {"Internal", "Word Clock", "S/PDIF Coax",
                                              "Optical 1", "Optical 2"};
constexpr uint32_t kClockSourceCount = sizeof(kClockSourceNames) / sizeof(kClockSourceNames[0]);

inline void channelName(bool input, uint32_t index, char * out, size_t size)
{
    static const char * const fixed[] = {"Front Mic L", "Front Mic R", "S/PDIF L", "S/PDIF R",
                                         "Mix 1 L", "Mix 1 R", "FX Send L", "FX Send R"};
    const char * text = nullptr;
    uint32_t number = 0;
    if (!input) {
        text = "Playback ";
        number = index + 1;
    } else if (index <= 7) {
        text = "Analog ";
        number = index + 1;
    } else if (index <= 9) {
        text = fixed[index - 8];
    } else if (index <= 11) {
        text = "Guitar ";
        number = index - 9;
    } else if (index <= 13) {
        text = fixed[index - 10];
    } else if (index <= 29) {
        text = "Optical ";
        number = index - 13;
    } else {
        text = fixed[4 + (index - 30) % 4];
    }
    size_t at = 0;
    for (; *text != '\0' && at + 1 < size; text++) {
        out[at++] = *text;
    }
    char digits[10];
    size_t count = 0;
    for (; number > 0; number /= 10) {
        digits[count++] = char('0' + number % 10);
    }
    while (count > 0 && at + 1 < size) {
        out[at++] = digits[--count];
    }
    out[at] = '\0';
}

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
