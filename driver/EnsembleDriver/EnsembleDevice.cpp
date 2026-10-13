#include <DriverKit/DriverKit.h>
#include <DriverKit/IOBufferMemoryDescriptor.h>
#include <DriverKit/IODMACommand.h>
#include <AudioDriverKit/AudioDriverKit.h>

#include "EnsembleClockSource.h"
#include "EnsembleDevice.h"
#include "EnsemblePsoc.h"
#include "EnsembleVolume.h"
#include "Bar0.h"
#include "Controls.h"
#include "Registers.h"

using namespace Ensemble;

constexpr uint32_t kSafetyOffset = 64;
constexpr uint32_t kMeterHz = 30;
constexpr uint64_t kReportedRateChange = 0x1000;
constexpr double kInitialRate = 48000.0;

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
    OSSharedPtr<IOBufferMemoryDescriptor> meters;
    OSSharedPtr<IODMACommand> meter_dma;
    OSSharedPtr<IOInterruptDispatchSource> wrap;
    OSSharedPtr<OSAction> wrap_action;
    uint64_t sample_time;
    uint64_t wrap_time;
    mach_timebase_info_data_t timebase;
    OSSharedPtr<EnsemblePsoc> psoc;
    double reported_rate;
    OSSharedPtr<EnsembleVolume> volume;
    OSSharedPtr<EnsembleClockSource> clock_source;
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
    mach_timebase_info(&ivars->timebase);
    ivars->psoc = OSSharedPtr(OSTypeAlloc(EnsemblePsoc), OSNoRetain);
    return ivars->psoc.get() != nullptr && ivars->psoc->init();
}

void EnsembleDevice::free()
{
    if (ivars != nullptr) {
        ivars->clock_source.reset();
        ivars->volume.reset();
        ivars->psoc.reset();
        ivars->wrap_action.reset();
        ivars->wrap.reset();
        ivars->meter_dma.reset();
        ivars->meters.reset();
        ivars->input = {};
        ivars->output = {};
        ivars->pci.reset();
        ivars->queue.reset();
        ivars->driver.reset();
    }
    IOSafeDeleteNULL(ivars, EnsembleDevice_IVars, 1);
    super::free();
}

static IOUserAudioStreamBasicDescription format(uint32_t channels, double rate)
{
    return {
        rate,
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

// The FPGA takes one base address per buffer, so the IOMMU must map each
// buffer as one segment.
static kern_return_t mapForDMA(const Bar0 & bar0, IOBufferMemoryDescriptor * buffer, uint64_t bytes,
                               uint64_t address_low, OSSharedPtr<IODMACommand> * dma)
{
    IODMACommandSpecification spec = {};
    spec.maxAddressBits = 64;
    IODMACommand * command = nullptr;
    kern_return_t ret = IODMACommand::Create(bar0.pci, kIODMACommandCreateNoOptions, &spec, &command);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    *dma = OSSharedPtr(command, OSNoRetain);
    uint64_t flags = 0;
    uint32_t count = 32;
    IOAddressSegment segments[32] = {};
    ret = command->PrepareForDMA(kIODMACommandPrepareForDMANoOptions, buffer, 0, bytes, &flags, &count,
                                 segments);
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
    return kIOReturnSuccess;
}

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
    ret = mapForDMA(bar0, buffer, bytes, address_low, &ring->dma);
    if (ret != kIOReturnSuccess) {
        return ret;
    }

    ring->stream = IOUserAudioStream::Create(driver, direction, ring->buffer.get());
    if (ring->stream.get() == nullptr) {
        return kIOReturnNoMemory;
    }
    IOUserAudioStreamBasicDescription formats[kSampleRateCount];
    for (uint32_t i = 0; i < kSampleRateCount; i++) {
        formats[i] = format(channels, kSampleRates[i]);
    }
    ring->stream->SetAvailableStreamFormats(formats, kSampleRateCount);
    ring->stream->SetCurrentStreamFormat(&formats[rateIndex(kInitialRate)]);
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
    regs.write(kSampleDepth, kMaxDepth - 1);
    regs.write(kOutputBufferSize, kOutputChannels * kRingFrames);
    regs.write(kInputBufferSize, kInputChannels * kRingFrames);
    ret = startMeters();
    if (ret != kIOReturnSuccess) {
        return ret;
    }

    SetAvailableSampleRates(kSampleRates, kSampleRateCount);
    SetSampleRate(kInitialRate);
    SetTransportType(IOUserAudioTransportType::Thunderbolt);
    SetOutputSafetyOffset(kSafetyOffset);
    SetInputSafetyOffset(kSafetyOffset);
    AddStream(ivars->output.stream.get());
    AddStream(ivars->input.stream.get());
    nameChannels(IOUserAudioObjectPropertyScope::Input, true, kInputChannels);
    nameChannels(IOUserAudioObjectPropertyScope::Output, false, kOutputChannels);
    ret = addVolume();
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    ret = addClockSource();
    if (ret != kIOReturnSuccess) {
        return ret;
    }

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
    ret = ivars->wrap->SetEnableWithCompletion(true, nullptr);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    return ivars->psoc->Start(this, pci, bar0, ivars->queue.get());
}

kern_return_t EnsembleDevice::startMeters()
{
    const Bar0 & regs = ivars->bar0;
    const uint32_t count = regs.read(kNumHostMeters) & 0xFFFF;
    const uint64_t bytes = meterBufferBytes(count);
    IOBufferMemoryDescriptor * buffer = nullptr;
    kern_return_t ret = IOBufferMemoryDescriptor::Create(kIOMemoryDirectionIn, bytes, 0, &buffer);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    ivars->meters = OSSharedPtr(buffer, OSNoRetain);
    ivars->meters->SetLength(bytes);
    ret = mapForDMA(regs, buffer, bytes, kMeterAddressLow, &ivars->meter_dma);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    regs.write(kNumHostMeters, count << 16);
    regs.write(kMeterTimer, meterTimer(kMeterHz, regs.read(kGeneral)));
    regs.write(kGeneral, regs.read(kGeneral) | kGeneralMeterArmAndRun);
    return kIOReturnSuccess;
}

IOMemoryDescriptor * EnsembleDevice::Meters()
{
    return ivars->meters.get();
}

kern_return_t EnsembleDevice::addVolume()
{
    ivars->volume = OSSharedPtr(OSTypeAlloc(EnsembleVolume), OSNoRetain);
    if (ivars->volume.get() == nullptr ||
        !ivars->volume->init(ivars->driver.get(), true, 0.0f,
                             {decibels(kMaxAttenuation), decibels(0)},
                             IOUserAudioObjectPropertyElementMain,
                             IOUserAudioObjectPropertyScope::Output,
                             IOUserAudioClassID::VolumeControl)) {
        return kIOReturnNoMemory;
    }
    ivars->volume->SetDevice(this);
    return AddControl(ivars->volume.get());
}

void EnsembleDevice::nameChannels(IOUserAudioObjectPropertyScope scope, bool input, uint32_t count)
{
    for (uint32_t i = 0; i < count; i++) {
        char name[32];
        channelName(input, i, name, sizeof(name));
        auto string = OSSharedPtr(OSString::withCString(name), OSNoRetain);
        SetElementName(i + 1, scope, string.get());
    }
}

kern_return_t EnsembleDevice::addClockSource()
{
    ivars->clock_source = OSSharedPtr(OSTypeAlloc(EnsembleClockSource), OSNoRetain);
    if (ivars->clock_source.get() == nullptr ||
        !ivars->clock_source->init(ivars->driver.get(), true, IOUserAudioObjectPropertyElementMain,
                                   IOUserAudioObjectPropertyScope::Global,
                                   IOUserAudioClassID::ClockSourceControl)) {
        return kIOReturnNoMemory;
    }
    IOUserAudioSelectorValueDescription sources[kClockSourceCount];
    for (uint32_t i = 0; i < kClockSourceCount; i++) {
        sources[i] = {i, OSSharedPtr(OSString::withCString(kClockSourceNames[i]), OSNoRetain)};
    }
    ivars->clock_source->AddControlValueDescriptions(sources, kClockSourceCount);
    const IOUserAudioSelectorValue internal = 0;
    ivars->clock_source->SetCurrentSelectedValues(&internal, 1);
    ivars->clock_source->SetDevice(this);
    return AddControl(ivars->clock_source.get());
}

void EnsembleDevice::ClockSourceChanged(uint64_t source)
{
    if (source < kClockSourceCount) {
        ivars->psoc->Send(set(kCommandClockSource, 0, uint8_t(source)));
    }
}

void EnsembleDevice::VolumeChanged(float in_decibels)
{
    ivars->psoc->SetMonitorAttenuation(attenuation(in_decibels));
}

EnsemblePsoc * EnsembleDevice::Psoc()
{
    return ivars->psoc.get();
}

void EnsembleDevice::Reported(const Report & report)
{
    if (report.command == kCommandSampleRate && report.data[0] < kSampleRateCount) {
        const double rate = kSampleRates[report.data[0]];
        if (rate != GetSampleRate()) {
            ivars->reported_rate = rate;
            RequestDeviceConfigurationChange(kReportedRateChange, nullptr);
        }
    } else if (report.command == kCommandOutputAttenuation && report.p1 == kSpeaker) {
        ivars->volume->SetDecibelValue(decibels(report.data[0]));
    } else if (report.command == kCommandClockSource && report.data[0] < kClockSourceCount) {
        const IOUserAudioSelectorValue source = report.data[0];
        ivars->clock_source->SetCurrentSelectedValues(&source, 1);
    }
}

void EnsembleDevice::Detach()
{
    ivars->psoc->Stop();
    const Bar0 & regs = ivars->bar0;
    regs.write(kGeneral, regs.read(kGeneral) & ~(kGeneralAudioRun | kGeneralMeterRun));
    regs.write(kInterrupt, regs.read(kInterrupt) & ~kInterruptWrap);
    if (ivars->wrap.get() != nullptr) {
        ivars->wrap->SetEnableWithCompletion(false, nullptr);
    }
    IODMACommand * commands[] = {ivars->output.dma.get(), ivars->input.dma.get(), ivars->meter_dma.get()};
    for (IODMACommand * command : commands) {
        if (command != nullptr) {
            command->CompleteDMA(kIODMACommandCompleteDMANoOptions);
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
        regs.write(kSampleDepth, depthFor(GetSampleRate()) - 1);
        regs.write(kGeneral, regs.read(kGeneral) | kGeneralAudioArmAndRun);
        ivars->wrap_time = mach_absolute_time();
        UpdateCurrentZeroTimestamp(0, ivars->wrap_time);
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
    const uint64_t elapsed = (time - ivars->wrap_time) * ivars->timebase.numer / ivars->timebase.denom;
    const uint64_t wraps = wrapsIn(elapsed, GetSampleRate());
    if (wraps == 0) {
        return;
    }
    ivars->sample_time += wraps * kRingFrames;
    ivars->wrap_time = time;
    UpdateCurrentZeroTimestamp(ivars->sample_time, time);
}

kern_return_t EnsembleDevice::HandleChangeSampleRate(double in_sample_rate)
{
    const int index = rateIndex(in_sample_rate);
    if (index < 0) {
        return kIOReturnBadArgument;
    }
    ivars->psoc->Send(set(kCommandSampleRate, 0, uint8_t(index)));
    return applyRate(in_sample_rate);
}

kern_return_t EnsembleDevice::PerformDeviceConfigurationChange(uint64_t change_action,
                                                               OSObject * in_change_info)
{
    if (change_action == kReportedRateChange) {
        return applyRate(ivars->reported_rate);
    }
    return super::PerformDeviceConfigurationChange(change_action, in_change_info);
}

kern_return_t EnsembleDevice::applyRate(double rate)
{
    kern_return_t ret = SetSampleRate(rate);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    ivars->output.stream->DeviceSampleRateChanged(rate);
    return ivars->input.stream->DeviceSampleRateChanged(rate);
}
