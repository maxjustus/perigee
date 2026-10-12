#include <os/log.h>

#include <DriverKit/DriverKit.h>
#include <DriverKit/OSDictionary.h>
#include <DriverKit/OSNumber.h>
#include <DriverKit/OSString.h>
#include <AudioDriverKit/AudioDriverKit.h>
#include <PCIDriverKit/PCIDriverKit.h>

#include "EnsembleDevice.h"
#include "EnsembleDriver.h"
#include "Registers.h"

using namespace Ensemble;

struct EnsembleDriver_IVars {
    Bar0 bar0;
    OSSharedPtr<EnsembleDevice> device;
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
    if (ivars != nullptr) {
        ivars->device.reset();
    }
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

static kern_return_t attach(IOService * service, Bar0 * bar0)
{
    kern_return_t ret = bar0->pci->GetBARInfo(kPCIMemoryRangeBAR0, &bar0->index);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    uint16_t command = 0;
    bar0->pci->ConfigurationRead16(kIOPCIConfigurationOffsetCommand, &command);
    bar0->pci->ConfigurationWrite16(kIOPCIConfigurationOffsetCommand,
                                    command | kIOPCICommandMemorySpace | kIOPCICommandBusLead);
    uint32_t id = bar0->read(kID);
    publish(service, "ID", id);
    return id == UINT32_MAX ? kIOReturnNoDevice : kIOReturnSuccess;
}

static kern_return_t addDevice(EnsembleDriver * driver, EnsembleDriver_IVars * ivars)
{
    char uid[32];
    snprintf(uid, sizeof(uid), "Ensemble-%08x%08x", ivars->bar0.read(kUniqueIDHigh),
             ivars->bar0.read(kUniqueIDLow));
    auto device_uid = OSSharedPtr(OSString::withCString(uid), OSNoRetain);
    auto model_uid = OSSharedPtr(OSString::withCString("Ensemble Thunderbolt"), OSNoRetain);
    auto manufacturer = OSSharedPtr(OSString::withCString("Apogee Electronics"), OSNoRetain);
    auto name = OSSharedPtr(OSString::withCString("Ensemble"), OSNoRetain);

    ivars->device = OSSharedPtr(OSTypeAlloc(EnsembleDevice), OSNoRetain);
    if (ivars->device.get() == nullptr ||
        !ivars->device->init(driver, false, device_uid.get(), model_uid.get(),
                             manufacturer.get(), kRingFrames)) {
        return kIOReturnNoMemory;
    }
    ivars->device->SetName(name.get());
    kern_return_t ret = ivars->device->Attach(ivars->bar0.pci, ivars->bar0.index);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    return driver->AddObject(ivars->device.get());
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
    ivars->bar0.pci = pci;
    ret = attach(this, &ivars->bar0);
    if (ret == kIOReturnSuccess) {
        ret = addDevice(this, ivars);
    }
    if (ret != kIOReturnSuccess) {
        os_log(OS_LOG_DEFAULT, "EnsembleDriver: start failed %#x", ret);
        if (ivars->device.get() != nullptr) {
            ivars->device->Detach();
            ivars->device.reset();
        }
        pci->Close(this, 0);
        ivars->bar0.pci = nullptr;
        return ret;
    }
    return RegisterService();
}

kern_return_t IMPL(EnsembleDriver, Stop)
{
    if (ivars->device.get() != nullptr) {
        ivars->device->Detach();
        RemoveObject(ivars->device.get());
        ivars->device.reset();
    }
    if (ivars->bar0.pci != nullptr) {
        ivars->bar0.pci->Close(this, 0);
        ivars->bar0.pci = nullptr;
    }
    return Stop(provider, SUPERDISPATCH);
}
