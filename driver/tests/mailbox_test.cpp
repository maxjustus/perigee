#include <cstdio>
#include <cstdlib>
#include <map>
#include <vector>

#include "Mailbox.h"

using namespace Ensemble;

static int failures = 0;

#define CHECK(condition)                                                   \
    do {                                                                   \
        if (!(condition)) {                                                \
            std::printf("%s:%d: CHECK(%s)\n", __FILE__, __LINE__, #condition); \
            failures++;                                                    \
        }                                                                  \
    } while (0)

struct FakeRegs {
    std::map<uint64_t, uint32_t> * values;

    uint32_t read(uint64_t offset) const { return (*values)[offset]; }
    void write(uint64_t offset, uint32_t value) const { (*values)[offset] = value; }
};

static void reset_clears_slots_and_indices_and_sets_the_reset_bit()
{
    std::map<uint64_t, uint32_t> r = {{kTxState + 4, 0x23}, {kRxWriteIndex, 5}, {kPsocEvent, 1}};
    Mailbox<FakeRegs> mailbox{{&r}};
    mailbox.reset();
    CHECK(r[kTxState + 4] == 0 && r[kRxWriteIndex] == 0 && r[kPsocEvent] == 0);
    CHECK(r[kGeneral] & kGeneralMailboxReset);
}

static void send_fills_the_write_slot_and_rings_the_doorbell()
{
    std::map<uint64_t, uint32_t> r = {{kTxWriteIndex, 2}, {kTxReadIndex, 2}};
    Mailbox<FakeRegs> mailbox{{&r}};
    CHECK(mailbox.send(set(0x29, 0, 1)));
    const uint64_t slot = kTxSlots + 2 * kSlotBytes;
    CHECK(r[slot] == 1 && r[slot + 4] == 0 && r[slot + 8] == 0x01002901);
    CHECK(r[kTxState + 2 * 4] == (kSlotFull | 3));
    CHECK(r[kTxWriteIndex] == 3);
    CHECK(r[kGeneral] & kGeneralDoorbell);
}

static void send_refuses_a_full_ring()
{
    std::map<uint64_t, uint32_t> r = {{kTxWriteIndex, 7}, {kTxReadIndex, 0}};
    Mailbox<FakeRegs> mailbox{{&r}};
    CHECK(!mailbox.send(getAll()));
    CHECK(r[kTxWriteIndex] == 7);
}

static void send_refuses_a_message_longer_than_a_slot()
{
    std::map<uint64_t, uint32_t> r = {{kTxWriteIndex, 0}, {kTxReadIndex, 0}};
    Mailbox<FakeRegs> mailbox{{&r}};
    Message message = getAll();
    message.count = kSlotWords + 1;
    CHECK(!mailbox.send(message));
    CHECK(r[kTxWriteIndex] == 0 && r.count(kTxSlots) == 0);
}

static void receive_reads_one_slot_and_frees_it()
{
    const uint64_t slot = kRxSlots + 6 * kSlotBytes;
    std::map<uint64_t, uint32_t> r = {
        {kRxWriteIndex, 7}, {kRxReadIndex, 6}, {kRxState + 6 * 4, kSlotFull | 3},
        {slot + 8, 0x01002901},
    };
    Mailbox<FakeRegs> mailbox{{&r}};
    std::vector<Report> reports;
    CHECK(mailbox.receive([&](const Report & report) { reports.push_back(report); }));
    CHECK(reports.size() == 1 && reports[0].command == 0x29 && reports[0].data[0] == 1);
    CHECK(r[kRxState + 6 * 4] == 0 && r[kRxReadIndex] == 7);
    CHECK(!mailbox.receive([&](const Report &) { failures++; }));
}

static void event_bit1_answers_the_handshake()
{
    std::map<uint64_t, uint32_t> r = {{kPsocEvent, 2}};
    Mailbox<FakeRegs> mailbox{{&r}};
    mailbox.serviceEvents();
    CHECK(r[kHandshake] == kHandshakeValue && r[kPsocEvent] == 0);
}

int main()
{
    reset_clears_slots_and_indices_and_sets_the_reset_bit();
    send_fills_the_write_slot_and_rings_the_doorbell();
    send_refuses_a_full_ring();
    send_refuses_a_message_longer_than_a_slot();
    receive_reads_one_slot_and_frees_it();
    event_bit1_answers_the_handshake();
    if (failures == 0) {
        std::printf("ok\n");
    }
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
