#include <DriverKit/DriverKit.h>
#include <DriverKit/IOBufferMemoryDescriptor.h>
#include <DriverKit/IODMACommand.h>
#include <AudioDriverKit/AudioDriverKit.h>

#include "EnsembleDevice.h"
#include "Bar0.h"
#include "Registers.h"

using namespace Ensemble;

constexpr uint32_t kSafetyOffset = 64;

struct Ring {
    OSSharedPtr<IOBufferMemoryDescriptor> buffer;
    OSSharedPtr<IODMACommand> dma;
    OSSharedPtr<IOUserAudioStream> stream;
};

struct EnsembleDevice_IVars {
    OSSharedPtr<IOUserAudioDriver> driver;
    OSSharedPtr<IODispatchQueue> queue;
    OSSharedPtr<IOPCIDevice> pci;
    Bar0 bar0;
    Ring output;
    Ring input;
    OSSharedPtr<IOInterruptDispatchSource> wrap;
    OSSharedPtr<OSAction> wrap_action;
    uint64_t sample_time;
};

bool EnsembleDevice::init(IOUserAudioDriver * in_driver,
                          bool in_supports_prewarming,
                          OSString * in_device_uid,
                          OSString * in_model_uid,
                          OSString * in_manufacturer_uid,
                          uint32_t in_zero_timestamp_period)
{
    if (!super::init(in_driver, in_supports_prewarming, in_device_uid, in_model_uid,
                     in_manufacturer_uid, in_zero_timestamp_period)) {
        return false;
    }
    ivars = IONewZero(EnsembleDevice_IVars, 1);
    if (ivars == nullptr) {
        return false;
    }
    ivars->driver = OSSharedPtr(in_driver, OSRetain);
    ivars->queue = GetWorkQueue();
    return true;
}

void EnsembleDevice::free()
{
    if (ivars != nullptr) {
        ivars->wrap_action.reset();
        ivars->wrap.reset();
        ivars->input = {};
        ivars->output = {};
        ivars->pci.reset();
        ivars->queue.reset();
        ivars->driver.reset();
    }
    IOSafeDeleteNULL(ivars, EnsembleDevice_IVars, 1);
    super::free();
}

static IOUserAudioStreamBasicDescription format(uint32_t channels)
{
    return {
        kSampleRate,
        IOUserAudioFormatID::LinearPCM,
        static_cast<IOUserAudioFormatFlags>(IOUserAudioFormatFlags::FormatFlagIsSignedInteger |
                                            IOUserAudioFormatFlags::FormatFlagIsPacked),
        channels * 4,
        1,
        channels * 4,
        channels,
        32,
    };
}

// The FPGA takes one base address per ring, so the IOMMU must map each ring
// as one segment.
static kern_return_t makeRing(IOUserAudioDriver * driver, const Bar0 & bar0,
                              IOUserAudioStreamDirection direction, uint32_t channels,
                              uint64_t address_low, Ring * ring)
{
    const uint64_t bytes = uint64_t(channels) * kRingFrames * 4;
    IOBufferMemoryDescriptor * buffer = nullptr;
    kern_return_t ret = IOBufferMemoryDescriptor::Create(kIOMemoryDirectionInOut, bytes, 0, &buffer);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    ring->buffer = OSSharedPtr(buffer, OSNoRetain);
    ring->buffer->SetLength(bytes);

    IODMACommandSpecification spec = {};
    spec.maxAddressBits = 64;
    IODMACommand * dma = nullptr;
    ret = IODMACommand::Create(bar0.pci, kIODMACommandCreateNoOptions, &spec, &dma);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    ring->dma = OSSharedPtr(dma, OSNoRetain);
    uint64_t flags = 0;
    uint32_t count = 32;
    IOAddressSegment segments[32] = {};
    ret = ring->dma->PrepareForDMA(kIODMACommandPrepareForDMANoOptions, ring->buffer.get(), 0,
                                   bytes, &flags, &count, segments);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    if (count != 1 || segments[0].length != bytes) {
        return kIOReturnNoResources;
    }

    const uint64_t iova = segments[0].address;
    bar0.write(address_low, uint32_t(iova));
    bar0.write(address_low + 4, uint32_t(iova >> 32));
    if (bar0.read(address_low) != uint32_t(iova) ||
        bar0.read(address_low + 4) != uint32_t(iova >> 32)) {
        return kIOReturnIOError;
    }

    ring->stream = IOUserAudioStream::Create(driver, direction, ring->buffer.get());
    if (ring->stream.get() == nullptr) {
        return kIOReturnNoMemory;
    }
    auto stream_format = format(channels);
    ring->stream->SetAvailableStreamFormats(&stream_format, 1);
    ring->stream->SetCurrentStreamFormat(&stream_format);
    return kIOReturnSuccess;
}

static kern_return_t findMSI(IOPCIDevice * pci, uint32_t * index)
{
    for (uint32_t i = 0;; i++) {
        uint64_t type = 0;
        kern_return_t ret = IOInterruptDispatchSource::GetInterruptType(pci, i, &type);
        if (ret != kIOReturnSuccess) {
            return ret;
        }
        if (type & kIOInterruptTypePCIMessaged) {
            *index = i;
            return kIOReturnSuccess;
        }
    }
}

kern_return_t EnsembleDevice::Attach(IOPCIDevice * pci, uint8_t bar0)
{
    ivars->pci = OSSharedPtr(pci, OSRetain);
    ivars->bar0 = {pci, bar0};
    const Bar0 & regs = ivars->bar0;

    kern_return_t ret = makeRing(ivars->driver.get(), regs, IOUserAudioStreamDirection::Output,
                                 kOutputChannels, kOutputAddressLow, &ivars->output);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    ret = makeRing(ivars->driver.get(), regs, IOUserAudioStreamDirection::Input,
                   kInputChannels, kInputAddressLow, &ivars->input);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    regs.write(kNumberOfChannels, ((kInputChannels / 2) << 16) | (kOutputChannels / 2));
    regs.write(kSampleDepth, kDepth - 1);
    regs.write(kOutputBufferSize, kOutputChannels * kRingFrames);
    regs.write(kInputBufferSize, kInputChannels * kRingFrames);

    double rate = kSampleRate;
    SetAvailableSampleRates(&rate, 1);
    SetSampleRate(rate);
    SetTransportType(IOUserAudioTransportType::Thunderbolt);
    SetOutputSafetyOffset(kSafetyOffset);
    SetInputSafetyOffset(kSafetyOffset);
    AddStream(ivars->output.stream.get());
    AddStream(ivars->input.stream.get());

    uint32_t msi = 0;
    ret = findMSI(pci, &msi);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    IOInterruptDispatchSource * wrap = nullptr;
    ret = IOInterruptDispatchSource::Create(pci, msi, ivars->queue.get(), &wrap);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    ivars->wrap = OSSharedPtr(wrap, OSNoRetain);
    OSAction * action = nullptr;
    ret = CreateActionWrapOccurred(0, &action);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    ivars->wrap_action = OSSharedPtr(action, OSNoRetain);
    ivars->wrap->SetHandler(ivars->wrap_action.get());
    return ivars->wrap->SetEnableWithCompletion(true, nullptr);
}

void EnsembleDevice::Detach()
{
    const Bar0 & regs = ivars->bar0;
    regs.write(kGeneral, regs.read(kGeneral) & ~kGeneralAudioRun);
    regs.write(kInterrupt, regs.read(kInterrupt) & ~kInterruptWrap);
    if (ivars->wrap.get() != nullptr) {
        ivars->wrap->SetEnableWithCompletion(false, nullptr);
    }
    Ring * rings[] = {&ivars->output, &ivars->input};
    for (Ring * ring : rings) {
        if (ring->dma.get() != nullptr) {
            ring->dma->CompleteDMA(kIODMACommandCompleteDMANoOptions);
        }
    }
}

static void zero(IOBufferMemoryDescriptor * buffer)
{
    IOAddressSegment range = {};
    buffer->GetAddressRange(&range);
    bzero(reinterpret_cast<void *>(range.address), range.length);
}

kern_return_t EnsembleDevice::StartIO(IOUserAudioStartStopFlags in_flags)
{
    __block kern_return_t ret = kIOReturnSuccess;
    ivars->queue->DispatchSync(^{
        ret = super::StartIO(in_flags);
        if (ret != kIOReturnSuccess) {
            return;
        }
        const Bar0 & regs = ivars->bar0;
        zero(ivars->output.buffer.get());
        zero(ivars->input.buffer.get());
        ivars->sample_time = 0;
        regs.write(kGeneral, regs.read(kGeneral) | kGeneralAudioArmAndRun);
        UpdateCurrentZeroTimestamp(0, mach_absolute_time());
        regs.write(kInterrupt, regs.read(kInterrupt) | kInterruptWrap);
    });
    return ret;
}

kern_return_t EnsembleDevice::StopIO(IOUserAudioStartStopFlags in_flags)
{
    __block kern_return_t ret = kIOReturnSuccess;
    ivars->queue->DispatchSync(^{
        const Bar0 & regs = ivars->bar0;
        regs.write(kInterrupt, regs.read(kInterrupt) & ~kInterruptWrap);
        regs.write(kGeneral, regs.read(kGeneral) & ~kGeneralAudioRun);
        ret = super::StopIO(in_flags);
    });
    return ret;
}

void IMPL(EnsembleDevice, WrapOccurred)
{
    ivars->sample_time += count * kRingFrames;
    UpdateCurrentZeroTimestamp(ivars->sample_time, time);
}
