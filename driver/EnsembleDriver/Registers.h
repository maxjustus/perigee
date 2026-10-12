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

constexpr uint32_t kGeneralAudioArmAndRun = 0x05A00000;
constexpr uint32_t kGeneralAudioRun = 0x04800000;
constexpr uint32_t kInterruptWrap = 0x01000000;

constexpr uint32_t kRingFrames = 0x4000;
constexpr uint32_t kOutputChannels = 36;
constexpr uint32_t kInputChannels = 34;
constexpr double kSampleRate = 48000.0;
constexpr uint32_t kDepth = 2;

}

#endif
