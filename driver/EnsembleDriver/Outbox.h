#ifndef Outbox_h
#define Outbox_h

#include "Protocol.h"

namespace Ensemble {

constexpr uint32_t kOutboxCapacity = 32;

struct Outbox {
    Message items[kOutboxCapacity];
    uint32_t head;
    uint32_t count;

    bool push(const Message & message)
    {
        if (count == kOutboxCapacity) {
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
