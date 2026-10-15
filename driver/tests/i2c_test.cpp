// Tests for the FPGA remote-I2C transfer arithmetic.

#include "I2c.h"

#include <stdio.h>
#include <vector>

static int failures = 0;

#define CHECK(condition)                                                              \
    do {                                                                              \
        if (!(condition)) {                                                           \
            printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #condition);                 \
            failures++;                                                               \
        }                                                                             \
    } while (0)

static void control_word_keeps_the_address_and_sets_the_transfer()
{
    // Enable value from the vendor path: bit 30 start, byte count 0x6C,
    // bit 7 clear for a write, address byte 0x36 in bits 5:0.
    uint32_t enabled = 0x006C0036;
    uint32_t write = Ensemble::i2cControl(enabled, 4, false);
    CHECK((write & 0xFFFFFFFFu) == (0x406C0036u | (4u << 8)));
    CHECK((write & Ensemble::kI2cReadBit) == 0);
    CHECK((write & Ensemble::kI2cStartBit) != 0);
    uint32_t read = Ensemble::i2cControl(enabled, 1, true);
    CHECK((read & Ensemble::kI2cReadBit) != 0);
    CHECK(((read >> 8) & 0xFF) == 1);
    // The address byte 0x36 survives.
    CHECK((read & 0x3F) == 0x36);
}

static void control_word_clears_the_previous_count()
{
    const uint32_t after = 0x806C7C36;
    CHECK(Ensemble::i2cControl(after, 8, true) == 0xC06C08B6);
}

static void delay_matches_the_verified_divisor()
{
    CHECK(Ensemble::i2cDelayMilliseconds(1) == 0);
    CHECK(Ensemble::i2cDelayMilliseconds(4) == 0);
    CHECK(Ensemble::i2cDelayMilliseconds(16) == 1);
    CHECK(Ensemble::i2cDelayMilliseconds(65) == 3);
}

static void window_words_round_up()
{
    CHECK(Ensemble::i2cWindowWords(1) == 1);
    CHECK(Ensemble::i2cWindowWords(4) == 1);
    CHECK(Ensemble::i2cWindowWords(5) == 2);
    CHECK(Ensemble::i2cWindowWords(255) == 64);
}

static void length_bound()
{
    CHECK(!Ensemble::validI2cLength(0));
    CHECK(Ensemble::validI2cLength(1));
    CHECK(Ensemble::validI2cLength(255));
    CHECK(!Ensemble::validI2cLength(256));
}

static std::vector<uint8_t> packet(uint8_t command, std::vector<uint8_t> data)
{
    std::vector<uint8_t> bytes = {0x01, command, uint8_t(data.size()), uint8_t(data.size() >> 8)};
    bytes.insert(bytes.end(), data.begin(), data.end());
    uint16_t sum = 0;
    for (uint8_t byte : bytes) {
        sum = uint16_t(sum + byte);
    }
    sum = uint16_t(-sum);
    bytes.insert(bytes.end(), {uint8_t(sum), uint8_t(sum >> 8), 0x17});
    return bytes;
}

static bool writes(std::vector<uint8_t> bytes)
{
    bytes.insert(bytes.begin(), 0);
    Ensemble::I2cRequest request;
    return Ensemble::parseI2cRequest(bytes.data(), uint32_t(bytes.size()), &request) &&
           !request.read && request.bytes == bytes.size() - 1 && request.packet == bytes.data() + 1;
}

static void reads_carry_a_count()
{
    Ensemble::I2cRequest request;
    const uint8_t read[] = {1, 15};
    CHECK(Ensemble::parseI2cRequest(read, 2, &request) && request.read && request.bytes == 15);
    const uint8_t empty[] = {1, 0};
    CHECK(!Ensemble::parseI2cRequest(empty, 2, &request));
    const uint8_t extra[] = {1, 15, 0};
    CHECK(!Ensemble::parseI2cRequest(extra, 3, &request));
    CHECK(!Ensemble::parseI2cRequest(read, 1, &request));
    const uint8_t other[] = {2, 15};
    CHECK(!Ensemble::parseI2cRequest(other, 2, &request));
}

static void writes_carry_only_vendor_reads()
{
    CHECK(writes(packet(0x38, {})));
    CHECK(writes(packet(0x32, {3})));
    CHECK(writes(packet(0x3A, {0, 0xFF, 0})));
    CHECK(writes(packet(0x3A, {0x40, 0x7F, 0})));
    CHECK(writes(packet(0x3B, {0})));
    CHECK(!writes(packet(0x38, {0, 0, 0, 0, 0, 0})));
    CHECK(!writes(packet(0x32, {4})));
    CHECK(!writes(packet(0x32, {0x40})));
    CHECK(!writes(packet(0x3A, {4, 0, 0})));
    CHECK(!writes(packet(0x3A, {0, 0})));
    CHECK(!writes(packet(0x3B, {})));
    CHECK(!writes(packet(0x3B, {1})));
}

static void writes_refuse_flash_and_unknown_commands()
{
    CHECK(!writes(packet(0x34, {1, 0, 0})));
    CHECK(!writes(packet(0x36, {0})));
    CHECK(!writes(packet(0x37, std::vector<uint8_t>(117, 0))));
    CHECK(!writes(packet(0x39, {1, 0, 0, 0xAA})));
    CHECK(!writes(packet(0x35, {})));
    CHECK(!writes(packet(0x31, {})));
    CHECK(!writes(packet(0x45, {1, 0, 0})));
}

static void writes_refuse_broken_frames()
{
    auto checksum = packet(0x38, {});
    checksum[4] ^= 1;
    CHECK(!writes(checksum));
    auto start = packet(0x38, {});
    start[0] = 0x02;
    CHECK(!writes(start));
    auto stop = packet(0x38, {});
    stop.back() = 0x00;
    CHECK(!writes(stop));
    auto length = packet(0x32, {1});
    length.insert(length.end() - 3, 0);
    CHECK(!writes(length));
    CHECK(!writes({}));
}

int main()
{
    control_word_keeps_the_address_and_sets_the_transfer();
    control_word_clears_the_previous_count();
    delay_matches_the_verified_divisor();
    window_words_round_up();
    length_bound();
    reads_carry_a_count();
    writes_carry_only_vendor_reads();
    writes_refuse_flash_and_unknown_commands();
    writes_refuse_broken_frames();
    if (failures == 0) {
        printf("ok\n");
    }
    return failures == 0 ? 0 : 1;
}
