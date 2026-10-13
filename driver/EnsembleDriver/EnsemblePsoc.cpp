#include <DriverKit/DriverKit.h>
#include <DriverKit/OSArray.h>

#include "EnsembleDevice.h"
#include "EnsemblePsoc.h"
#include "EnsembleUserClient.h"
#include "Bar0.h"
#include "Controls.h"
#include "Mailbox.h"
#include "Outbox.h"

using namespace Ensemble;

constexpr uint64_t kPollPeriodNs = 10000000;

struct EnsemblePsoc_IVars {
    EnsembleDevice * device;
    OSSharedPtr<IODispatchQueue> queue;
    Mailbox<Bar0> mailbox;
    Outbox outbox;
    OSSharedPtr<IOTimerDispatchSource> timer;
    OSSharedPtr<OSAction> action;
    uint64_t period;
    OSSharedPtr<OSArray> listeners;
    Monitors monitors;
};

bool EnsemblePsoc::init()
{
    if (!super::init()) {
        return false;
    }
    ivars = IONewZero(EnsemblePsoc_IVars, 1);
    if (ivars == nullptr) {
        return false;
    }
    ivars->listeners = OSSharedPtr(OSArray::withCapacity(2), OSNoRetain);
    return ivars->listeners.get() != nullptr;
}

void EnsemblePsoc::free()
{
    if (ivars != nullptr) {
        ivars->listeners.reset();
        ivars->action.reset();
        ivars->timer.reset();
        ivars->queue.reset();
    }
    IOSafeDeleteNULL(ivars, EnsemblePsoc_IVars, 1);
    super::free();
}

kern_return_t EnsemblePsoc::Start(EnsembleDevice * device, IOPCIDevice * pci, uint8_t bar0,
                                  IODispatchQueue * queue)
{
    ivars->device = device;
    ivars->queue = OSSharedPtr(queue, OSRetain);
    ivars->mailbox = {{pci, bar0}};
    IOTimerDispatchSource * timer = nullptr;
    kern_return_t ret = IOTimerDispatchSource::Create(queue, &timer);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    ivars->timer = OSSharedPtr(timer, OSNoRetain);
    OSAction * action = nullptr;
    ret = CreateActionPollOccurred(0, &action);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    ivars->action = OSSharedPtr(action, OSNoRetain);
    ivars->timer->SetHandler(ivars->action.get());
    mach_timebase_info_data_t timebase;
    mach_timebase_info(&timebase);
    ivars->period = kPollPeriodNs * timebase.denom / timebase.numer;
    return Resume();
}

kern_return_t EnsemblePsoc::Resume()
{
    ivars->mailbox.reset();
    ivars->outbox.push(getAll());
    ivars->timer->WakeAtTime(kIOTimerClockMachAbsoluteTime, mach_absolute_time() + ivars->period, 0);
    return ivars->timer->SetEnable(true);
}

void EnsemblePsoc::Stop()
{
    if (ivars->timer.get() != nullptr) {
        ivars->timer->SetEnable(false);
    }
}

void EnsemblePsoc::Send(const Message & message)
{
    const Message copy = message;
    ivars->queue->DispatchAsync(^{
        ivars->outbox.push(copy);
    });
}

void EnsemblePsoc::SetMonitorAttenuation(uint8_t attenuation)
{
    ivars->queue->DispatchAsync(^{
        ivars->monitors.request(attenuation);
    });
}

void EnsemblePsoc::AddListener(EnsembleUserClient * listener)
{
    auto retained = OSSharedPtr(listener, OSRetain);
    ivars->queue->DispatchAsync(^{
        OSArray * listeners = ivars->listeners.get();
        if (listeners->getNextIndexOfObject(retained.get(), 0) == -1U) {
            listeners->setObject(retained.get());
        }
    });
}

void EnsemblePsoc::RemoveListener(EnsembleUserClient * listener)
{
    auto retained = OSSharedPtr(listener, OSRetain);
    ivars->queue->DispatchAsync(^{
        const uint32_t index = ivars->listeners->getNextIndexOfObject(retained.get(), 0);
        if (index != -1U) {
            ivars->listeners->removeObject(index);
        }
    });
}

void IMPL(EnsemblePsoc, PollOccurred)
{
    const Mailbox<Bar0> & mailbox = ivars->mailbox;
    if (mailbox.serviceEvents()) {
        ivars->outbox.push(getAll());
    }
    ivars->monitors.apply([&](uint8_t output, uint8_t value) {
        return ivars->outbox.push(set(kCommandOutputAttenuation, output, value));
    });
    auto handle = [&](const Report & report) {
        OSArray * listeners = ivars->listeners.get();
        for (uint32_t i = 0; i < listeners->getCount(); i++) {
            OSDynamicCast(EnsembleUserClient, listeners->getObject(i))->Report(report);
        }
        if (report.command == kCommandOutputAttenuation && report.p1 < kMonitorOutputs) {
            ivars->monitors.report(report.p1, report.data[0]);
        }
        ivars->device->Reported(report);
    };
    ivars->outbox.flush(mailbox, [&](const Message & sent) { parseMessage(sent.words, sent.count, handle); });
    while (mailbox.receive(handle)) {
    }
    ivars->timer->WakeAtTime(kIOTimerClockMachAbsoluteTime, time + ivars->period, 0);
}
