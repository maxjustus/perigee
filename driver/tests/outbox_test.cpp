#include <vector>

#include "check.h"
#include "Outbox.h"

using namespace Ensemble;

struct FakeMailbox {
    std::vector<uint32_t> * sent;
    uint32_t * room;

    bool send(const Message & message) const
    {
        if (*room == 0) {
            return false;
        }
        (*room)--;
        sent->push_back(message.words[2]);
        return true;
    }
};

static void flush_sends_in_order_until_the_ring_is_full()
{
    Outbox outbox = {};
    CHECK(outbox.push(set(1, 0, 1)) && outbox.push(set(2, 0, 2)) && outbox.push(set(3, 0, 3)));
    std::vector<uint32_t> sent;
    std::vector<uint32_t> reported;
    auto report = [&](const Message & m) { reported.push_back(m.words[2]); };
    uint32_t room = 2;
    outbox.flush(FakeMailbox{&sent, &room}, report);
    CHECK(sent.size() == 2 && sent[0] == set(1, 0, 1).words[2] && sent[1] == set(2, 0, 2).words[2]);
    CHECK(reported == sent);
    room = 8;
    outbox.flush(FakeMailbox{&sent, &room}, report);
    CHECK(sent.size() == 3 && sent[2] == set(3, 0, 3).words[2]);
    CHECK(reported == sent);
}

static void push_refuses_when_full()
{
    Outbox outbox = {};
    for (uint32_t i = 0; i < kOutboxCapacity; i++) {
        CHECK(outbox.push(getAll()));
    }
    CHECK(!outbox.push(getAll()));
}

static void a_limited_push_leaves_the_reserve_free()
{
    Outbox outbox = {};
    const uint32_t limit = kOutboxCapacity - kOutboxReserve;
    for (uint32_t i = 0; i < limit; i++) {
        CHECK(outbox.push(getAll(), limit));
    }
    CHECK(!outbox.push(getAll(), limit));
    for (uint32_t i = 0; i < kOutboxReserve; i++) {
        CHECK(outbox.push(getAll()));
    }
    CHECK(!outbox.push(getAll()));
}

int main()
{
    flush_sends_in_order_until_the_ring_is_full();
    push_refuses_when_full();
    a_limited_push_leaves_the_reserve_free();
    return finish();
}
