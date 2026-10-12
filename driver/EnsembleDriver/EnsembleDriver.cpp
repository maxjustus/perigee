#include <DriverKit/IOLib.h>
#include <DriverKit/OSDictionary.h>
#include <DriverKit/OSNumber.h>
#include <PCIDriverKit/PCIDriverKit.h>

#include "EnsembleDriver.h"

struct EnsembleDriver_IVars {
    IOPCIDevice * pci;
    uint8_t bar0;
};

bool EnsembleDriver::init()
{
    if (!super::init()) {
        return false;
    }
    ivars = IONewZero(EnsembleDriver_IVars, 1);
    return ivars != nullptr;
}

void EnsembleDriver::free()
{
    IOSafeDeleteNULL(ivars, EnsembleDriver_IVars, 1);
    super::free();
}

static void publish(IOService * service, const char * key, uint32_t value)
{
    OSDictionary * properties = OSDictionary::withCapacity(1);
    OSNumber * number = OSNumber::withNumber(value, 32);
    properties->setObject(key, number);
    service->SetProperties(properties);
    OSSafeReleaseNULL(number);
    OSSafeReleaseNULL(properties);
}

static kern_return_t attach(IOService * service, EnsembleDriver_IVars * ivars)
{
    kern_return_t ret = ivars->pci->GetBARInfo(kPCIMemoryRangeBAR0, &ivars->bar0);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    uint16_t command = 0;
    ivars->pci->ConfigurationRead16(kIOPCIConfigurationOffsetCommand, &command);
    ivars->pci->ConfigurationWrite16(kIOPCIConfigurationOffsetCommand,
                                     command | kIOPCICommandMemorySpace);
    uint32_t id = 0;
    ivars->pci->MemoryRead32(ivars->bar0, 0x00, &id);
    publish(service, "ID", id);
    return id == UINT32_MAX ? kIOReturnNoDevice : kIOReturnSuccess;
}

kern_return_t IMPL(EnsembleDriver, Start)
{
    kern_return_t ret = Start(provider, SUPERDISPATCH);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    IOPCIDevice * pci = OSDynamicCast(IOPCIDevice, provider);
    if (pci == nullptr) {
        return kIOReturnNoDevice;
    }
    ret = pci->Open(this, 0);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    ivars->pci = pci;
    ret = attach(this, ivars);
    if (ret != kIOReturnSuccess) {
        pci->Close(this, 0);
        ivars->pci = nullptr;
        return ret;
    }
    return RegisterService();
}

kern_return_t IMPL(EnsembleDriver, Stop)
{
    if (ivars->pci != nullptr) {
        ivars->pci->Close(this, 0);
        ivars->pci = nullptr;
    }
    return Stop(provider, SUPERDISPATCH);
}
