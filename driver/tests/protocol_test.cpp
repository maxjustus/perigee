#include <vector>

#include "check.h"
#include "Protocol.h"

using namespace Ensemble;

static uint32_t word(uint8_t b0, uint8_t b1, uint8_t b2, uint8_t b3)
{
    return b0 | b1 << 8 | b2 << 16 | uint32_t(b3) << 24;
}

static std::vector<Report> parse(const std::vector<uint32_t> & words)
{
    std::vector<Report> reports;
    parseMessage(words.data(), uint32_t(words.size()), [&](const Report & r) { reports.push_back(r); });
    return reports;
}

static void type1_record_carries_one_value()
{
    auto reports = parse({0, 0, word(1, 0x29, 0, 1)});
    CHECK(reports.size() == 1);
    CHECK(reports[0].type == 1 && reports[0].command == 0x29 && reports[0].p1 == 0);
    CHECK(reports[0].length == 1 && reports[0].data[0] == 1);
}

static void type2_record_spans_words_by_its_length()
{
    auto reports = parse({0, 0, word(2, 0x32, 5, 1), word(2, 0x02, 0x58, 0), word(1, 0x2a, 0, 3)});
    CHECK(reports.size() == 2);
    CHECK(reports[0].command == 0x32 && reports[0].p1 == 5 && reports[0].p2 == 1);
    CHECK(reports[0].length == 2 && reports[0].data[0] == 0x02 && reports[0].data[1] == 0x58);
    CHECK(reports[1].command == 0x2a && reports[1].data[0] == 3);
}

static void record_past_the_message_end_is_truncated()
{
    std::vector<uint32_t> words(16, 0);
    for (int i = 0; i < 4; i++) {
        words[2 + 2 * i] = word(2, 0x40, uint8_t(i), 0);
        words[3 + 2 * i] = word(3, 0, 0, 0);
    }
    words[10] = word(2, 0xd2, 0, 0);
    words[11] = word(7, 0, 0, 0);
    words[13] = word(2, 0x41, 0, 0);
    words[14] = word(8, 0, 0x0d, 0x6a);
    words[15] = word(0, 0x84, 0x44, 0xf1);
    auto reports = parse(words);
    CHECK(reports.size() == 6);
    CHECK(reports[5].command == 0x41 && reports[5].length == 7);
    CHECK(reports[5].data[6] == 0xf1);
}

static void unknown_type_stops_the_parse()
{
    auto reports = parse({0, 0, word(1, 0x29, 0, 1), word(9, 0, 0, 0), word(1, 0x2a, 0, 0)});
    CHECK(reports.size() == 1);
}

static void get_all_is_one_type4_word_after_the_header()
{
    Message m = getAll();
    CHECK(m.count == 3);
    CHECK(m.words[0] == 1 && m.words[1] == 0 && m.words[2] == 4);
}

static void set_packs_type_command_p1_and_value()
{
    Message m = set(0x29, 0, 3);
    CHECK(m.count == 3);
    CHECK(m.words[2] == word(1, 0x29, 0, 3));
}

static Message message(const std::vector<uint32_t> & words)
{
    Message m = {};
    for (uint32_t i = 0; i < words.size(); i++) {
        m.words[i] = words[i];
    }
    m.count = uint32_t(words.size());
    return m;
}

static void valid_message_accepts_what_the_senders_send()
{
    CHECK(validMessage(getAll()));
    CHECK(validMessage(set(0x29, 0, 3)));
    CHECK(validMessage(message({1, 0, word(2, 0x35, 1, 0), word(1, 1, 0, 0)})));
    CHECK(validMessage(message({1, 0, word(2, 0x32, 5, 1), word(2, 0x02, 0x58, 0)})));
}

static void valid_message_denies_update_and_dsp_halt_commands()
{
    for (uint8_t command : {0x60, 0x61, 0x62, 0x63, 0xd6, 0xd7}) {
        CHECK(!validMessage(set(command, 0, 0)));
        CHECK(!validMessage(message({1, 0, word(2, command, 0, 0), word(1, 0, 0, 0)})));
    }
}

static void valid_message_accepts_types_1_2_and_4_only()
{
    CHECK(!validMessage(message({1, 0, word(3, 0x29, 0, 0)})));
    CHECK(!validMessage(message({1, 0, word(5, 0x29, 0, 0)})));
    CHECK(!validMessage(message({1, 0, word(0, 0, 0, 0)})));
}

static void valid_message_requires_one_record_that_ends_in_the_last_word()
{
    CHECK(!validMessage(message({1, 0})));
    CHECK(!validMessage(message({1, 0, word(1, 0x29, 0, 1), word(1, 0x2a, 0, 3)})));
    CHECK(!validMessage(message({1, 0, word(4, 0, 0, 0), word(0, 0, 0, 0)})));
    CHECK(!validMessage(message({1, 0, word(2, 0x32, 5, 1), word(5, 0x02, 0x58, 0)})));
    CHECK(!validMessage(message({1, 0, word(2, 0x32, 5, 1), word(1, 0x02, 0, 0), word(0, 0, 0, 0)})));
}

static void valid_message_requires_zero_padding()
{
    CHECK(!validMessage(message({1, 0, word(2, 0x35, 1, 0), word(1, 1, 0x2a, 0)})));
    CHECK(!validMessage(message({1, 0, word(2, 0x35, 1, 0), word(1, 1, 0, 0x01)})));
}

static void rate_index_matches_the_psoc_table()
{
    CHECK(rateIndex(44100.0) == 0 && rateIndex(48000.0) == 1 && rateIndex(192000.0) == 5);
    CHECK(rateIndex(32000.0) == -1);
    CHECK(kSampleRates[3] == 96000.0);
}

static void report_packs_into_async_arguments()
{
    Report r = {2, 0x41, 1, 0, 3, {0xaa, 0xbb, 0xcc}};
    uint64_t args[kReportArguments] = {};
    pack(r, args);
    CHECK(args[0] == (2ull | 0x41ull << 8 | 1ull << 16 | 0ull << 24 | 3ull << 32));
    CHECK(args[1] == 0xccbbaa);
    CHECK(args[kReportArguments - 1] == 0);
}

int main()
{
    report_packs_into_async_arguments();
    rate_index_matches_the_psoc_table();
    type1_record_carries_one_value();
    type2_record_spans_words_by_its_length();
    record_past_the_message_end_is_truncated();
    unknown_type_stops_the_parse();
    get_all_is_one_type4_word_after_the_header();
    set_packs_type_command_p1_and_value();
    valid_message_accepts_what_the_senders_send();
    valid_message_denies_update_and_dsp_halt_commands();
    valid_message_accepts_types_1_2_and_4_only();
    valid_message_requires_one_record_that_ends_in_the_last_word();
    valid_message_requires_zero_padding();
    return finish();
}
