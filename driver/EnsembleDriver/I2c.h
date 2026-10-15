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
// The byte count sits in bits 15:8. A larger count carries into the 0x6C
// field of the enable value. The vendor sends at most 124 bytes.
constexpr uint32_t kI2cMaxBytes = 255;
constexpr uint32_t kI2cStartBit = 1u << 30;
constexpr uint32_t kI2cReadBit = 1u << 7;
constexpr uint32_t kI2cBusyBit = 1u << 31;
// Clears start, read, and the count that the previous transfer left.
constexpr uint32_t kI2cControlMask = 0xBFFF007Fu;
constexpr uint32_t kI2cPollTries = 999;
constexpr uint32_t kI2cPollSleepMilliseconds = 1;
// The vendor HAL waits this long after it enables the engine, before Enter.
constexpr uint32_t kI2cSettleMilliseconds = 3000;

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

struct I2cRequest {
    bool read;
    uint32_t bytes;
    const uint8_t * packet;
};

inline bool validBootloaderPacket(const uint8_t * packet, uint32_t bytes);

// A client sends [1, count] to read or [0, packet...] to write.
inline bool parseI2cRequest(const uint8_t * request, uint32_t length, I2cRequest * out)
{
    if (length == 2 && request[0] == 1) {
        *out = {true, request[1], nullptr};
        return validI2cLength(out->bytes);
    }
    if (length >= 1 && request[0] == 0) {
        *out = {false, length - 1, request + 1};
        return validI2cLength(out->bytes) && validBootloaderPacket(out->packet, out->bytes);
    }
    return false;
}

constexpr uint8_t kBootloaderEnter = 0x38;
constexpr uint8_t kBootloaderReportSize = 0x32;
constexpr uint8_t kBootloaderRowChecksum = 0x3A;
constexpr uint8_t kBootloaderExit = 0x3B;
constexpr uint8_t kFlashArrays = 4;
constexpr uint32_t kFlashRows = 256;
constexpr uint8_t kEepromArray = 0x40;
constexpr uint32_t kEepromRows = 128;

// Only the reads that the vendor updater sends pass, in the vendor shape.
// The Cypress loader writes flash for 0x34, 0x36, 0x37, and 0x39. The unit's
// v1.20 loader does not bound the row of 0x3A, so a larger row reads past
// the array, or past the EEPROM into peripheral registers.
inline bool validBootloaderPacket(const uint8_t * packet, uint32_t bytes)
{
    if (bytes < 7 || packet[0] != 0x01 || packet[bytes - 1] != 0x17) {
        return false;
    }
    const uint32_t length = packet[2] | uint32_t(packet[3]) << 8;
    if (bytes != 7 + length) {
        return false;
    }
    uint16_t sum = 0;
    for (uint32_t i = 0; i < 4 + length; i++) {
        sum = uint16_t(sum + packet[i]);
    }
    if (uint16_t(packet[4 + length] | packet[5 + length] << 8) != uint16_t(-sum)) {
        return false;
    }
    const uint8_t * data = packet + 4;
    switch (packet[1]) {
    case kBootloaderEnter:
        return length == 0;
    case kBootloaderReportSize:
        return length == 1 && data[0] < kFlashArrays;
    case kBootloaderRowChecksum: {
        if (length != 3) {
            return false;
        }
        const uint32_t row = data[1] | uint32_t(data[2]) << 8;
        return (data[0] < kFlashArrays && row < kFlashRows) ||
               (data[0] == kEepromArray && row < kEepromRows);
    }
    case kBootloaderExit:
        return length == 1 && data[0] == 0;
    default:
        return false;
    }
}

}

#endif
