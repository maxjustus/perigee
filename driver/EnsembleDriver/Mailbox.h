#ifndef Mailbox_h
#define Mailbox_h

#include "Protocol.h"
#include "Registers.h"

namespace Ensemble {

// Regs needs read(offset) and write(offset, value). All calls must come
// from one queue: send and reset modify GENERAL with read-modify-write.
template <typename Regs>
struct Mailbox {
    Regs regs;

    void reset() const
    {
        for (uint32_t i = 0; i < kSlotCount; i++) {
            regs.write(kTxState + 4 * i, 0);
        }
        const uint64_t cleared[] = {kTxWriteIndex, kTxReadIndex, kRxWriteIndex,
                                    kRxReadIndex, kPsocEvent, kHandshake};
        for (uint64_t offset : cleared) {
            regs.write(offset, 0);
        }
        regs.write(kGeneral, regs.read(kGeneral) | kGeneralMailboxReset);
    }

    bool send(const Message & message) const
    {
        const uint32_t write = regs.read(kTxWriteIndex);
        const uint32_t read = regs.read(kTxReadIndex);
        if (write >= kSlotCount || read >= kSlotCount || (write + 1) % kSlotCount == read) {
            return false;
        }
        const uint64_t slot = kTxSlots + write * kSlotBytes;
        for (uint32_t i = 0; i < message.count; i++) {
            regs.write(slot + 4 * i, message.words[i]);
        }
        regs.write(kTxState + 4 * write, kSlotFull | message.count);
        regs.write(kTxWriteIndex, (write + 1) % kSlotCount);
        regs.write(kGeneral, regs.read(kGeneral) | kGeneralDoorbell);
        return true;
    }

    template <typename Emit>
    bool receive(Emit && emit) const
    {
        const uint32_t write = regs.read(kRxWriteIndex);
        const uint32_t read = regs.read(kRxReadIndex);
        if (write == read || write >= kSlotCount || read >= kSlotCount) {
            return false;
        }
        const uint32_t state = regs.read(kRxState + 4 * read);
        if (!(state & kSlotFull)) {
            return false;
        }
        uint32_t count = state & kSlotLength;
        count = count < kSlotWords ? count : kSlotWords;
        uint32_t words[kSlotWords] = {};
        const uint64_t slot = kRxSlots + read * kSlotBytes;
        for (uint32_t i = 0; i < count; i++) {
            words[i] = regs.read(slot + 4 * i);
        }
        regs.write(kRxState + 4 * read, 0);
        regs.write(kRxReadIndex, (read + 1) % kSlotCount);
        parseMessage(words, count, emit);
        return true;
    }

    // Returns true if the PSoC restarted. Its message state is then reset.
    bool serviceEvents() const
    {
        const uint32_t event = regs.read(kPsocEvent);
        if (event == 0 || event == UINT32_MAX) {
            return false;
        }
        if (event & 2) {
            regs.write(kHandshake, kHandshakeValue);
        }
        regs.write(kPsocEvent, 0);
        if (event & 1) {
            reset();
            return true;
        }
        return false;
    }
};

}

#endif
