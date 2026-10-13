#include <DriverKit/DriverKit.h>
#include <DriverKit/OSData.h>

#include "EnsembleDevice.h"
#include "EnsembleDriver.h"
#include "EnsemblePsoc.h"
#include "EnsembleUserClient.h"

using namespace Ensemble;

constexpr uint64_t kMemoryMeters = 0;

enum Selector : uint64_t {
    kSelectorSend = 0,
    kSelectorSubscribe = 1,
};

struct EnsembleUserClient_IVars {
    OSSharedPtr<EnsembleDevice> device;
    OSSharedPtr<OSAction> reports;
};

bool EnsembleUserClient::init()
{
    if (!super::init()) {
        return false;
    }
    ivars = IONewZero(EnsembleUserClient_IVars, 1);
    return ivars != nullptr;
}

void EnsembleUserClient::free()
{
    if (ivars != nullptr) {
        ivars->reports.reset();
        ivars->device.reset();
    }
    IOSafeDeleteNULL(ivars, EnsembleUserClient_IVars, 1);
    super::free();
}

kern_return_t IMPL(EnsembleUserClient, Start)
{
    kern_return_t ret = Start(provider, SUPERDISPATCH);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    EnsembleDriver * driver = OSDynamicCast(EnsembleDriver, provider);
    if (driver == nullptr || driver->GetDevice() == nullptr) {
        return kIOReturnNotAttached;
    }
    ivars->device = OSSharedPtr(driver->GetDevice(), OSRetain);
    return kIOReturnSuccess;
}

kern_return_t IMPL(EnsembleUserClient, Stop)
{
    if (ivars->device.get() != nullptr) {
        ivars->device->GetPsoc()->RemoveListener(this);
    }
    return Stop(provider, SUPERDISPATCH);
}

kern_return_t EnsembleUserClient::ExternalMethod(uint64_t selector,
                                                 IOUserClientMethodArguments * arguments,
                                                 const IOUserClientMethodDispatch * dispatch,
                                                 OSObject * target,
                                                 void * reference)
{
    switch (selector) {
    case kSelectorSend: {
        OSData * input = arguments->structureInput;
        if (input == nullptr || input->getLength() % 4 != 0 || input->getLength() < 12 ||
            input->getLength() > kSlotWords * 4) {
            return kIOReturnBadArgument;
        }
        Message message = {};
        message.count = uint32_t(input->getLength() / 4);
        memcpy(message.words, input->getBytesNoCopy(), input->getLength());
        ivars->device->GetPsoc()->Send(message);
        return kIOReturnSuccess;
    }
    case kSelectorSubscribe:
        if (arguments->completion == nullptr) {
            return kIOReturnBadArgument;
        }
        ivars->reports = OSSharedPtr(arguments->completion, OSRetain);
        ivars->device->GetPsoc()->AddListener(this);
        return kIOReturnSuccess;
    default:
        return super::ExternalMethod(selector, arguments, dispatch, target, reference);
    }
}

kern_return_t IMPL(EnsembleUserClient, CopyClientMemoryForType)
{
    IOMemoryDescriptor * meters = ivars->device->GetMeters();
    if (type != kMemoryMeters || meters == nullptr) {
        return kIOReturnBadArgument;
    }
    meters->retain();
    *memory = meters;
    *options = kIOUserClientMemoryReadOnly;
    return kIOReturnSuccess;
}

void EnsembleUserClient::Report(const Ensemble::Report & report)
{
    if (ivars->reports.get() == nullptr) {
        return;
    }
    IOUserClientAsyncArgumentsArray args = {};
    pack(report, args);
    AsyncCompletion(ivars->reports.get(), kIOReturnSuccess, args, kReportArguments);
}
