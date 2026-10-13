#include <cstdio>
#include <cstdlib>
#include <vector>

#include "Outbox.h"

using namespace Ensemble;

static int failures = 0;

#define CHECK(condition)                                                   \
    do {                                                                   \
        if (!(condition)) {                                                \
            std::printf("%s:%d: CHECK(%s)\n", __FILE__, __LINE__, #condition); \
            failures++;                                                    \
        }                                                                  \
    } while (0)

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
    uint32_t room = 2;
    outbox.flush(FakeMailbox{&sent, &room});
    CHECK(sent.size() == 2 && sent[0] == set(1, 0, 1).words[2] && sent[1] == set(2, 0, 2).words[2]);
    room = 8;
    outbox.flush(FakeMailbox{&sent, &room});
    CHECK(sent.size() == 3 && sent[2] == set(3, 0, 3).words[2]);
}

static void push_refuses_when_full()
{
    Outbox outbox = {};
    for (uint32_t i = 0; i < kOutboxCapacity; i++) {
        CHECK(outbox.push(getAll()));
    }
    CHECK(!outbox.push(getAll()));
}

int main()
{
    flush_sends_in_order_until_the_ring_is_full();
    push_refuses_when_full();
    if (failures == 0) {
        std::printf("ok\n");
    }
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
