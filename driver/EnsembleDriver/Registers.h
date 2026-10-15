#ifndef Registers_h
#define Registers_h

#include <stdint.h>

namespace Ensemble {

constexpr uint64_t kID = 0x00;
constexpr uint64_t kGeneral = 0x0C;
constexpr uint64_t kInterrupt = 0x14;
constexpr uint64_t kNumHostMeters = 0x1C;
constexpr uint64_t kMeterTimer = 0x20;
constexpr uint64_t kMeterAddressLow = 0x24;
constexpr uint64_t kInputBufferSize = 0x2C;
constexpr uint64_t kInputAddressLow = 0x30;
constexpr uint64_t kOutputBufferSize = 0x40;
constexpr uint64_t kOutputAddressLow = 0x44;
constexpr uint64_t kUniqueIDLow = 0x54;
constexpr uint64_t kUniqueIDHigh = 0x58;
constexpr uint64_t kSampleDepth = 0x60;
constexpr uint64_t kNumberOfChannels = 0x64;
constexpr uint64_t kInfo = 0x68;

constexpr uint64_t kRxSlots = 0x400;
constexpr uint64_t kRxState = 0x7C0;
constexpr uint64_t kPsocEvent = 0x7E0;
constexpr uint64_t kTxSlots = 0x800;
constexpr uint64_t kTxState = 0xBC0;
constexpr uint64_t kHandshake = 0xBE0;
constexpr uint64_t kRxWriteIndex = 0xBE4;
constexpr uint64_t kRxReadIndex = 0xBE8;
constexpr uint64_t kTxWriteIndex = 0xBEC;
constexpr uint64_t kTxReadIndex = 0xBF0;

constexpr uint64_t kSlotBytes = 0x78;
constexpr uint32_t kSlotCount = 8;
constexpr uint32_t kSlotFull = 0x20;
constexpr uint32_t kSlotLength = 0x1F;
constexpr uint32_t kHandshakeValue = 0xABCD1234;

constexpr uint32_t kGeneralAudioArmAndRun = 0x05A00000;
constexpr uint32_t kGeneralAudioRun = 0x04800000;
constexpr uint32_t kGeneralMeterArmAndRun = 0x28000000;
constexpr uint32_t kGeneralMeterRun = 0x20000000;
constexpr uint32_t kGeneralFastClock = 0x40000000;
constexpr uint32_t kGeneralMailboxReset = 0x20;
constexpr uint32_t kGeneralDoorbell = 0x40;
constexpr uint32_t kInterruptWrap = 0x01000000;

// INFO bits 7:6 read 1 while the PSoC application runs, and 2 while its
// bootloader runs.
constexpr uint32_t kStatusApplication = 1;
constexpr uint32_t kStatusBootloader = 2;

inline uint32_t bootloaderStatus(uint32_t info)
{
    return (info >> 6) & 3;
}

constexpr uint32_t kRingFrames = 0x4000;
constexpr uint32_t kOutputChannels = 36;
constexpr uint32_t kInputChannels = 34;
constexpr uint32_t kMaxDepth = 32;
constexpr uint8_t kMinFirmwareRevision = 0x56;

inline uint32_t meterTimer(uint32_t hz, uint32_t general)
{
    return ((general & kGeneralFastClock) ? 244140u : 122070u) / hz - 1;
}

inline uint32_t meterBufferBytes(uint32_t meters)
{
    return 4 + 2 * meters;
}

// An MSI can be lost, so the wrap count comes from the time between MSIs.
inline uint64_t wrapsIn(uint64_t elapsed_ns, double rate)
{
    return uint64_t(double(elapsed_ns) * rate / 1e9 / kRingFrames + 0.5);
}

inline uint32_t depthFor(double rate)
{
    return rate <= 48000.0 ? 2 : rate <= 96000.0 ? 8 : kMaxDepth;
}

struct Latency {
    uint32_t safety;
    uint32_t input;
    uint32_t output;
};

// The vendor HAL values, in frames. The device latency is one DMA burst
// plus a converter delay.
inline Latency latencyFor(double rate)
{
    if (rate <= 48000.0) {
        return {3, 13, 43};
    }
    if (rate <= 96000.0) {
        return {12, 19, 22};
    }
    return {48, 45, 43};
}

}

#endif
