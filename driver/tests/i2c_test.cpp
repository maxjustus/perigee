// Tests for the FPGA remote-I2C transfer arithmetic.

#include "I2c.h"

#include <stdio.h>

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
    CHECK(Ensemble::i2cWindowWords(1024) == 256);
}

static void length_bound()
{
    CHECK(!Ensemble::validI2cLength(0));
    CHECK(Ensemble::validI2cLength(1));
    CHECK(Ensemble::validI2cLength(1024));
    CHECK(!Ensemble::validI2cLength(1025));
}

static void pack_carries_the_result()
{
    uint64_t args[Ensemble::kI2cArguments];
    const uint8_t data[] = {0x38, 0x00, 0x01, 0x10};
    Ensemble::packI2c(true, false, data, sizeof(data), args);
    CHECK(args[0] == (1u | 4u << 8));
    CHECK((args[1] & 0xFFFFFFFFu) == (0x10u << 24 | 0x01u << 16 | 0x00u << 8 | 0x38u));
    uint64_t busy[Ensemble::kI2cArguments];
    Ensemble::packI2c(false, true, nullptr, 0, busy);
    CHECK(busy[0] == (uint64_t(1) << 40));
}

int main()
{
    control_word_keeps_the_address_and_sets_the_transfer();
    delay_matches_the_verified_divisor();
    window_words_round_up();
    length_bound();
    pack_carries_the_result();
    if (failures == 0) {
        printf("ok\n");
    }
    return failures == 0 ? 0 : 1;
}
