#include <map>
#include <vector>

#include "check.h"
#include "Mailbox.h"

using namespace Ensemble;

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

static void send_refuses_a_message_longer_than_29_words()
{
    std::map<uint64_t, uint32_t> r = {{kTxWriteIndex, 0}, {kTxReadIndex, 0}};
    Mailbox<FakeRegs> mailbox{{&r}};
    Message message = getAll();
    message.count = 30;
    CHECK(!mailbox.send(message));
    CHECK(r[kTxWriteIndex] == 0 && r.count(kTxSlots) == 0);
    message.count = 29;
    CHECK(mailbox.send(message));
    CHECK(r[kTxState] == (kSlotFull | 29));
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

static void event_bit0_reports_a_restart_and_leaves_the_reset_to_the_caller()
{
    std::map<uint64_t, uint32_t> r = {{kPsocEvent, 1}, {kTxWriteIndex, 5}};
    Mailbox<FakeRegs> mailbox{{&r}};
    CHECK(mailbox.serviceEvents());
    CHECK(r[kTxWriteIndex] == 5 && r[kPsocEvent] == 0);
}

static void rejoin_restarts_on_an_event_or_a_return_to_the_application()
{
    Rejoin heard = {kStatusApplication, true, 0};
    CHECK(heard.poll(kStatusApplication, false, 100, 10) == Resync::None);
    CHECK(heard.poll(kStatusApplication, true, 100, 10) == Resync::Restart);
    Rejoin loader = {kStatusBootloader, true, 0};
    CHECK(loader.poll(kStatusBootloader, false, 100, 10) == Resync::None);
    CHECK(loader.poll(kStatusApplication, false, 101, 10) == Resync::Restart);
}

static void rejoin_retries_each_period_until_the_psoc_answers()
{
    Rejoin rejoin = {kStatusApplication, true, 0};
    CHECK(rejoin.poll(kStatusApplication, true, 100, 10) == Resync::Restart);
    CHECK(rejoin.poll(kStatusApplication, false, 109, 10) == Resync::None);
    CHECK(rejoin.poll(kStatusApplication, false, 110, 10) == Resync::Retry);
    CHECK(rejoin.poll(kStatusApplication, false, 119, 10) == Resync::None);
    CHECK(rejoin.poll(kStatusApplication, false, 120, 10) == Resync::Retry);
    rejoin.heard = true;
    CHECK(rejoin.poll(kStatusApplication, false, 200, 10) == Resync::None);
}

static void rejoin_waits_outside_the_application()
{
    Rejoin rejoin = {kStatusApplication, false, 0};
    CHECK(rejoin.poll(kStatusBootloader, false, 100, 10) == Resync::None);
    CHECK(rejoin.poll(0, false, 200, 10) == Resync::None);
    CHECK(rejoin.poll(3, false, 300, 10) == Resync::None);
}

int main()
{
    reset_clears_slots_and_indices_and_sets_the_reset_bit();
    send_fills_the_write_slot_and_rings_the_doorbell();
    send_refuses_a_full_ring();
    send_refuses_a_message_longer_than_29_words();
    receive_reads_one_slot_and_frees_it();
    event_bit1_answers_the_handshake();
    event_bit0_reports_a_restart_and_leaves_the_reset_to_the_caller();
    rejoin_restarts_on_an_event_or_a_return_to_the_application();
    rejoin_retries_each_period_until_the_psoc_answers();
    rejoin_waits_outside_the_application();
    return finish();
}
