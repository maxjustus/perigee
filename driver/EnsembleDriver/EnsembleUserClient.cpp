#include <DriverKit/DriverKit.h>
#include <DriverKit/OSData.h>

#include "EnsembleDevice.h"
#include "EnsembleDriver.h"
#include "EnsemblePsoc.h"
#include "EnsembleUserClient.h"

#include "I2c.h"

using namespace Ensemble;

constexpr uint64_t kMemoryMeters = 0;

enum Selector : uint64_t {
    kSelectorSend = 0,
    kSelectorSubscribe = 1,
    // A client opts in per connection before the bootloader-entry command
    // or an I2C transfer passes. Zero closes the session.
    kSelectorSession = 2,
    kSelectorI2c = 3,
};

struct EnsembleUserClient_IVars {
    OSSharedPtr<EnsembleDevice> device;
    OSSharedPtr<OSAction> reports;
    bool session = false;
};

// One remote-I2C transfer on the calling thread. Returns true when the
// engine stays busy, which means the reply bytes are absent.
static bool i2cTransfer(EnsembleDevice * device, bool read, uint32_t bytes,
                        const uint8_t * out, uint8_t * in)
{
    device->WriteRegister(Ensemble::kI2cControlRegister, Ensemble::kI2cEnablePre);
    device->WriteRegister(Ensemble::kI2cControlRegister, Ensemble::kI2cEnable);
    if (!read) {
        const uint32_t words = Ensemble::i2cWindowWords(bytes);
        for (uint32_t i = 0; i < words; i++) {
            uint32_t word = 0;
            for (uint32_t b = 0; b < 4 && i * 4 + b < bytes; b++) {
                word |= uint32_t(out[i * 4 + b]) << (8 * b);
            }
            device->WriteRegister(Ensemble::kI2cWindow + 4 * i, word);
        }
    }
    const uint32_t control =
        Ensemble::i2cControl(device->ReadRegister(Ensemble::kI2cControlRegister), bytes, read);
    device->WriteRegister(Ensemble::kI2cControlRegister, control);
    IOSleep(Ensemble::i2cDelayMilliseconds(bytes));
    bool busy = true;
    for (uint32_t attempt = 0; attempt < Ensemble::kI2cPollTries; attempt++) {
        if ((device->ReadRegister(Ensemble::kI2cControlRegister) & Ensemble::kI2cBusyBit) == 0) {
            busy = false;
            break;
        }
        IOSleep(Ensemble::kI2cPollSleepMilliseconds);
    }
    if (read) {
        const uint32_t words = Ensemble::i2cWindowWords(bytes);
        for (uint32_t i = 0; i < words; i++) {
            const uint32_t word = device->ReadRegister(Ensemble::kI2cWindow + 4 * i);
            for (uint32_t b = 0; b < 4 && i * 4 + b < bytes; b++) {
                in[i * 4 + b] = uint8_t(word >> (8 * b));
            }
        }
    }
    device->WriteRegister(Ensemble::kI2cControlRegister, 0);
    return busy;
}

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
            input->getLength() > kSendSlotWords * 4) {
            return kIOReturnBadArgument;
        }
        Message message = {};
        message.count = uint32_t(input->getLength() / 4);
        memcpy(message.words, input->getBytesNoCopy(), input->getLength());
        if (!validMessage(message, ivars->session)) {
            return kIOReturnBadArgument;
        }
        return ivars->device->GetPsoc()->Send(message);
    }
    case kSelectorSession: {
        if (arguments->scalarInputCount != 1 || arguments->scalarInput[0] > 1) {
            return kIOReturnBadArgument;
        }
        ivars->session = arguments->scalarInput[0] != 0;
        return kIOReturnSuccess;
    }
    case kSelectorI2c: {
        if (!ivars->session || arguments->completion == nullptr) {
            return kIOReturnBadArgument;
        }
        OSData * input = arguments->structureInput;
        if (input == nullptr) {
            return kIOReturnBadArgument;
        }
        const uint8_t * request = static_cast<const uint8_t *>(input->getBytesNoCopy());
        uint32_t bytes = 0;
        bool read = false;
        if (input->getLength() >= 3 && request[0] == 1) {
            read = true;
            bytes = uint32_t(request[1]) | uint32_t(request[2]) << 8;
        } else if (input->getLength() >= 2 && request[0] == 0) {
            bytes = uint32_t(input->getLength()) - 1;
        }
        if (!Ensemble::validI2cLength(bytes)) {
            return kIOReturnBadArgument;
        }
        uint8_t in[Ensemble::kI2cMaxBytes] = {};
        const bool busy = i2cTransfer(ivars->device.get(), read, bytes, request + 1, in);
        uint64_t args[Ensemble::kI2cArguments];
        Ensemble::packI2c(read, busy, in, read ? bytes : 0, args);
        AsyncCompletion(arguments->completion, kIOReturnSuccess, args, Ensemble::kI2cArguments);
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
