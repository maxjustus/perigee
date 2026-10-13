import CoreAudio

public func findEnsemble() -> AudioObjectID? {
    let system = AudioObjectID(kAudioObjectSystemObject)
    var address = propertyAddress(kAudioHardwarePropertyDevices)
    var size: UInt32 = 0
    AudioObjectGetPropertyDataSize(system, &address, 0, nil, &size)
    var devices = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
    AudioObjectGetPropertyData(system, &address, 0, nil, &size, &devices)
    return devices.first { stringProperty($0, kAudioObjectPropertyName) == "Ensemble" }
}

public func propertyAddress(_ selector: AudioObjectPropertySelector,
                            _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal,
                            element: AudioObjectPropertyElement = kAudioObjectPropertyElementMain)
    -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: selector, mScope: scope, mElement: element)
}

public func property<T>(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector,
                        _ scope: AudioObjectPropertyScope, _ initial: T,
                        element: AudioObjectPropertyElement = kAudioObjectPropertyElementMain) -> T {
    var value = initial
    var size = UInt32(MemoryLayout<T>.size)
    var address = propertyAddress(selector, scope, element: element)
    withUnsafeMutableBytes(of: &value) {
        _ = AudioObjectGetPropertyData(object, &address, 0, nil, &size, $0.baseAddress!)
    }
    return value
}

public func stringProperty(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector,
                           _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal,
                           element: AudioObjectPropertyElement = kAudioObjectPropertyElementMain) -> String {
    let value: Unmanaged<CFString>? = property(object, selector, scope, nil, element: element)
    return value?.takeRetainedValue() as String? ?? ""
}

public func channelNames(_ device: AudioObjectID, _ scope: AudioObjectPropertyScope) -> [String] {
    (0..<channelCount(device, scope)).map {
        stringProperty(device, kAudioObjectPropertyElementName, scope, element: UInt32($0 + 1))
    }
}

public func channelCount(_ device: AudioObjectID, _ scope: AudioObjectPropertyScope) -> Int {
    var address = propertyAddress(kAudioDevicePropertyStreamConfiguration, scope)
    var size: UInt32 = 0
    AudioObjectGetPropertyDataSize(device, &address, 0, nil, &size)
    let list = UnsafeMutableRawPointer.allocate(byteCount: Int(size), alignment: MemoryLayout<AudioBufferList>.alignment)
    defer { list.deallocate() }
    AudioObjectGetPropertyData(device, &address, 0, nil, &size, list)
    return UnsafeMutableAudioBufferListPointer(list.assumingMemoryBound(to: AudioBufferList.self))
        .reduce(0) { $0 + Int($1.mNumberChannels) }
}
