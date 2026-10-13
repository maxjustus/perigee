#ifndef Outbox_h
#define Outbox_h

#include "Protocol.h"

namespace Ensemble {

constexpr uint32_t kOutboxCapacity = 32;
// The user client fills the outbox only up to the reserve, so that the
// dext's own messages still fit while a client sends a burst.
constexpr uint32_t kOutboxReserve = 8;

struct Outbox {
    Message items[kOutboxCapacity];
    uint32_t head;
    uint32_t count;

    bool push(const Message & message, uint32_t limit = kOutboxCapacity)
    {
        if (count >= limit) {
            return false;
        }
        items[(head + count) % kOutboxCapacity] = message;
        count++;
        return true;
    }

    template <typename Mailbox, typename Sent>
    void flush(const Mailbox & mailbox, Sent && sent)
    {
        while (count > 0 && mailbox.send(items[head])) {
            sent(items[head]);
            head = (head + 1) % kOutboxCapacity;
            count--;
        }
    }
};

}

#endif
