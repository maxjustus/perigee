#ifndef Protocol_h
#define Protocol_h

#include <stdint.h>

namespace Ensemble {

constexpr uint32_t kSlotWords = 30;
// The PSoC copies `state & 0x1F` words into a receive buffer whose 30-word
// size is inferred, not declared. The vendor kext sends at most 29.
constexpr uint32_t kSendSlotWords = 29;
constexpr uint8_t kMaxReportData = 100;

constexpr uint8_t kCommandSampleRate = 0x29;

constexpr double kSampleRates[] = {44100.0, 48000.0, 88200.0, 96000.0, 176400.0, 192000.0};
constexpr uint32_t kSampleRateCount = sizeof(kSampleRates) / sizeof(kSampleRates[0]);

inline int rateIndex(double rate)
{
    for (uint32_t i = 0; i < kSampleRateCount; i++) {
        if (kSampleRates[i] == rate) {
            return int(i);
        }
    }
    return -1;
}

// The dext sends a report of this type, with no data, after a PSoC restart.
constexpr uint8_t kTypeRestarted = 5;

struct Report {
    uint8_t type;
    uint8_t command;
    uint8_t p1;
    uint8_t p2;
    uint8_t length;
    uint8_t data[kMaxReportData];
};

constexpr uint32_t kReportArguments = 1 + (kMaxReportData + 7) / 8;

inline void pack(const Report & report, uint64_t args[kReportArguments])
{
    args[0] = report.type | uint64_t(report.command) << 8 | uint64_t(report.p1) << 16 |
              uint64_t(report.p2) << 24 | uint64_t(report.length) << 32;
    for (uint32_t i = 1; i < kReportArguments; i++) {
        args[i] = 0;
    }
    for (uint32_t i = 0; i < report.length; i++) {
        args[1 + i / 8] |= uint64_t(report.data[i]) << (8 * (i % 8));
    }
}

struct Message {
    uint32_t words[kSlotWords];
    uint32_t count;
};

inline Message getAll()
{
    return {{1, 0, 4}, 3};
}

inline Message set(uint8_t command, uint8_t p1, uint8_t value)
{
    return {{1, 0, 1u | uint32_t(command) << 8 | uint32_t(p1) << 16 | uint32_t(value) << 24}, 3};
}

inline uint8_t byteAt(const uint32_t * words, uint32_t i)
{
    return uint8_t(words[i / 4] >> (8 * (i % 4)));
}

// Bootloader entry, firmware selectors, update data, the restart-state
// store, and DSP core erase and halt. Clients must not send these.
constexpr uint8_t kDeniedCommands[] = {0x60, 0x61, 0x62, 0x63, 0xD6, 0xD7};

// The PSoC parser misreads the record after a type-2 record of length 1 to
// 3, and after a type-3 or type-4 record. So a client sends one record.
// It dispatches stale data for a type-2 length of 0 or above 99.
inline bool validMessage(const Message & message)
{
    if (message.count < 3 || message.count > kSlotWords) {
        return false;
    }
    const uint8_t type = byteAt(message.words, 8);
    const uint8_t command = byteAt(message.words, 9);
    uint32_t end;
    if (type == 1 || type == 4) {
        end = 12;
    } else if (type == 2 && message.count > 3) {
        const uint8_t length = byteAt(message.words, 12);
        if (length == 0 || length > 99) {
            return false;
        }
        end = 13u + length;
    } else {
        return false;
    }
    for (uint8_t denied : kDeniedCommands) {
        if (command == denied) {
            return false;
        }
    }
    if (end > message.count * 4 || message.count * 4 - end >= 4) {
        return false;
    }
    for (uint32_t i = end; i < message.count * 4; i++) {
        if (byteAt(message.words, i) != 0) {
            return false;
        }
    }
    return true;
}

// Words 0 and 1 are a header. Records follow. The PSoC can claim more data
// than the message holds (report 0x41), so every read stops at `count`.
template <typename Emit>
void parseMessage(const uint32_t * words, uint32_t count, Emit && emit)
{
    auto byte = [&](uint32_t i) { return byteAt(words, i); };
    const uint32_t end = count * 4;
    uint32_t at = 8;
    while (at + 4 <= end) {
        Report r = {};
        r.type = byte(at);
        r.command = byte(at + 1);
        r.p1 = byte(at + 2);
        if (r.type == 1) {
            r.length = 1;
            r.data[0] = byte(at + 3);
            at += 4;
        } else if (r.type == 2 && at + 5 <= end) {
            r.p2 = byte(at + 3);
            const uint8_t claimed = byte(at + 4) < kMaxReportData ? byte(at + 4) : kMaxReportData;
            const uint32_t available = end - (at + 5);
            r.length = claimed < available ? claimed : uint8_t(available);
            for (uint32_t i = 0; i < r.length; i++) {
                r.data[i] = byte(at + 5 + i);
            }
            const uint32_t extra = claimed > 3 ? claimed - 3u : 0u;
            at += 4 * (2 + (extra + 3) / 4);
        } else {
            return;
        }
        emit(r);
    }
}

}

#endif
