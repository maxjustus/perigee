#ifndef Bar0_h
#define Bar0_h

#include <PCIDriverKit/PCIDriverKit.h>

namespace Ensemble {

struct Bar0 {
    IOPCIDevice * pci;
    uint8_t index;

    uint32_t read(uint64_t offset) const
    {
        uint32_t value = 0;
        pci->MemoryRead32(index, offset, &value);
        return value;
    }

    void write(uint64_t offset, uint32_t value) const
    {
        pci->MemoryWrite32(index, offset, value);
    }
};

}

#endif
