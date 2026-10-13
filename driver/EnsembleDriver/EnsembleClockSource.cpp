#include <DriverKit/DriverKit.h>
#include <AudioDriverKit/AudioDriverKit.h>

#include "EnsembleClockSource.h"
#include "EnsembleDevice.h"

struct EnsembleClockSource_IVars {
    EnsembleDevice * device;
};

bool EnsembleClockSource::init(IOUserAudioDriver * in_driver,
                               bool in_is_settable,
                               IOUserAudioObjectPropertyElement in_control_element,
                               IOUserAudioObjectPropertyScope in_control_scope,
                               IOUserAudioClassID in_control_class_id)
{
    if (!super::init(in_driver, in_is_settable, in_control_element, in_control_scope,
                     in_control_class_id)) {
        return false;
    }
    ivars = IONewZero(EnsembleClockSource_IVars, 1);
    return ivars != nullptr;
}

void EnsembleClockSource::free()
{
    IOSafeDeleteNULL(ivars, EnsembleClockSource_IVars, 1);
    super::free();
}

void EnsembleClockSource::SetDevice(EnsembleDevice * device)
{
    ivars->device = device;
}

kern_return_t EnsembleClockSource::HandleChangeSelectedValues(const IOUserAudioSelectorValue * in_control_values,
                                                              size_t in_num_values)
{
    kern_return_t ret = super::HandleChangeSelectedValues(in_control_values, in_num_values);
    if (ret == kIOReturnSuccess && in_num_values == 1 && ivars->device != nullptr) {
        ivars->device->ClockSourceChanged(in_control_values[0]);
    }
    return ret;
}
