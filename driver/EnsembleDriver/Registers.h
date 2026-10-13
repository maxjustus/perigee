#ifndef Registers_h
#define Registers_h

#include <stdint.h>

namespace Ensemble {

constexpr uint64_t kID = 0x00;
constexpr uint64_t kGeneral = 0x0C;
constexpr uint64_t kInterrupt = 0x14;
constexpr uint64_t kInputBufferSize = 0x2C;
constexpr uint64_t kInputAddressLow = 0x30;
constexpr uint64_t kOutputBufferSize = 0x40;
constexpr uint64_t kOutputAddressLow = 0x44;
constexpr uint64_t kUniqueIDLow = 0x54;
constexpr uint64_t kUniqueIDHigh = 0x58;
constexpr uint64_t kSampleDepth = 0x60;
constexpr uint64_t kNumberOfChannels = 0x64;

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
constexpr uint32_t kGeneralMailboxReset = 0x20;
constexpr uint32_t kGeneralDoorbell = 0x40;
constexpr uint32_t kInterruptWrap = 0x01000000;

constexpr uint32_t kRingFrames = 0x4000;
constexpr uint32_t kOutputChannels = 36;
constexpr uint32_t kInputChannels = 34;
constexpr uint32_t kMaxDepth = 32;

inline uint32_t depthFor(double rate)
{
    return rate <= 48000.0 ? 2 : rate <= 96000.0 ? 8 : kMaxDepth;
}

}

#endif
