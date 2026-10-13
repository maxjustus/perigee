#include <DriverKit/DriverKit.h>
#include <AudioDriverKit/AudioDriverKit.h>

#include "EnsembleDevice.h"
#include "EnsembleVolume.h"

struct EnsembleVolume_IVars {
    EnsembleDevice * device;
};

bool EnsembleVolume::init(IOUserAudioDriver * in_driver,
                          bool in_is_settable,
                          float in_decibel_value,
                          IOUserAudioLevelControlRange in_decibel_range,
                          IOUserAudioObjectPropertyElement in_control_element,
                          IOUserAudioObjectPropertyScope in_control_scope,
                          IOUserAudioClassID in_control_class_id)
{
    if (!super::init(in_driver, in_is_settable, in_decibel_value, in_decibel_range,
                     in_control_element, in_control_scope, in_control_class_id)) {
        return false;
    }
    ivars = IONewZero(EnsembleVolume_IVars, 1);
    return ivars != nullptr;
}

void EnsembleVolume::free()
{
    IOSafeDeleteNULL(ivars, EnsembleVolume_IVars, 1);
    super::free();
}

void EnsembleVolume::SetDevice(EnsembleDevice * device)
{
    ivars->device = device;
}

kern_return_t EnsembleVolume::HandleChangeDecibelValue(float in_decibel_value)
{
    kern_return_t ret = super::HandleChangeDecibelValue(in_decibel_value);
    if (ret == kIOReturnSuccess && ivars->device != nullptr) {
        ivars->device->VolumeChanged(GetDecibelValue());
    }
    return ret;
}

kern_return_t EnsembleVolume::HandleChangeScalarValue(float in_scalar_value)
{
    kern_return_t ret = super::HandleChangeScalarValue(in_scalar_value);
    if (ret == kIOReturnSuccess && ivars->device != nullptr) {
        ivars->device->VolumeChanged(GetDecibelValue());
    }
    return ret;
}
