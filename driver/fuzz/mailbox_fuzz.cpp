#include <cstdlib>
#include <cstring>

#include "Mailbox.h"

using namespace Ensemble;

struct Input {
    const uint8_t * data;
    size_t size;
};

// The PSoC controls every value that the dext reads. A bad value must not
// move an access outside the RX ring.
struct FuzzRegs {
    Input * input;

    uint32_t read(uint64_t offset) const
    {
        if (offset != kRxWriteIndex && offset != kRxReadIndex &&
            (offset < kRxSlots || offset >= kRxState + 4 * kSlotCount)) {
            std::abort();
        }
        uint32_t value = 0;
        if (input->size >= 4) {
            std::memcpy(&value, input->data, 4);
            input->data += 4;
            input->size -= 4;
        } else {
            input->size = 0;
        }
        return value;
    }

    void write(uint64_t offset, uint32_t value) const
    {
        const bool state = offset >= kRxState && offset < kRxState + 4 * kSlotCount;
        if (!state && !(offset == kRxReadIndex && value < kSlotCount)) {
            std::abort();
        }
    }
};

extern "C" int LLVMFuzzerTestOneInput(const uint8_t * data, size_t size)
{
    Input input = {data, size};
    Mailbox<FuzzRegs> mailbox{{&input}};
    while (input.size > 0) {
        mailbox.receive([](const Report & r) {
            if (r.length > kMaxReportData) {
                std::abort();
            }
        });
    }
    return 0;
}
