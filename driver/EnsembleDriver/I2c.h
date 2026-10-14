#ifndef I2c_h
#define I2c_h

#include <stdint.h>

namespace Ensemble {

// The FPGA remote-I2C engine, from NOTES-vendor-driver.md section 7.
// Enable: write 0x00040000, then 0x006C0036. Disable: write zero.
// The low six bits of the second value carry the target address byte.
constexpr uint64_t kI2cControlRegister = 0x18;
constexpr uint64_t kI2cWindow = 0x3C00;
constexpr uint32_t kI2cEnablePre = 0x00040000;
constexpr uint32_t kI2cEnable = 0x006C0036;
constexpr uint32_t kI2cMaxBytes = 1024;
constexpr uint32_t kI2cStartBit = 1u << 30;
constexpr uint32_t kI2cReadBit = 1u << 7;
constexpr uint32_t kI2cBusyBit = 1u << 31;
constexpr uint32_t kI2cControlMask = 0xBFFFFF7Fu;
constexpr uint32_t kI2cPollTries = 999;
constexpr uint32_t kI2cPollSleepMilliseconds = 1;

inline uint32_t i2cControl(uint32_t control, uint32_t bytes, bool read)
{
    return (control & kI2cControlMask) | (bytes << 8) | (read ? kI2cReadBit : 0) |
           kI2cStartBit;
}

// The vendor waits for the transfer with this delay. The independent review
// measured the x86_64 kext divisor as 150, and the vendor source divides by
// 1000. Use the larger delay: an early poll is harmless, a missing sleep is
// not.
inline uint32_t i2cDelayMilliseconds(uint32_t bytes)
{
    return (9 * bytes + 9) / 150;
}

inline uint32_t i2cWindowWords(uint32_t bytes)
{
    return (bytes + 3) / 4;
}

inline bool validI2cLength(uint32_t bytes)
{
    return bytes > 0 && bytes <= kI2cMaxBytes;
}

}

#endif
