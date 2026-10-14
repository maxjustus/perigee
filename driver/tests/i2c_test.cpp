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

int main()
{
    control_word_keeps_the_address_and_sets_the_transfer();
    delay_matches_the_verified_divisor();
    window_words_round_up();
    length_bound();
    if (failures == 0) {
        printf("ok\n");
    }
    return failures == 0 ? 0 : 1;
}
