// Checks the Ensemble CoreAudio device: properties, then 5 s of IO.
// Usage: swift driver/check.swift [sample rate to set first]
import CoreAudio
import Foundation

func address(_ selector: AudioObjectPropertySelector,
             _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: selector, mScope: scope, mElement: kAudioObjectPropertyElementMain)
}

func get<T>(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector,
            _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal, _ initial: T) -> T {
    var value = initial
    var size = UInt32(MemoryLayout<T>.size)
    var addr = address(selector, scope)
    withUnsafeMutableBytes(of: &value) {
        _ = AudioObjectGetPropertyData(object, &addr, 0, nil, &size, $0.baseAddress!)
    }
    return value
}

func string(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector) -> String {
    let value: Unmanaged<CFString>? = get(object, selector, kAudioObjectPropertyScopeGlobal, nil)
    return value?.takeRetainedValue() as String? ?? ""
}

func name(_ object: AudioObjectID) -> String {
    string(object, kAudioObjectPropertyName)
}

func channels(_ device: AudioObjectID, _ scope: AudioObjectPropertyScope) -> Int {
    var addr = address(kAudioDevicePropertyStreamConfiguration, scope)
    var size: UInt32 = 0
    AudioObjectGetPropertyDataSize(device, &addr, 0, nil, &size)
    let list = UnsafeMutableRawPointer.allocate(byteCount: Int(size), alignment: 16)
    defer { list.deallocate() }
    AudioObjectGetPropertyData(device, &addr, 0, nil, &size, list)
    let buffers = UnsafeMutableAudioBufferListPointer(list.assumingMemoryBound(to: AudioBufferList.self))
    return buffers.reduce(0) { $0 + Int($1.mNumberChannels) }
}

func latency(_ device: AudioObjectID, _ scope: AudioObjectPropertyScope) -> UInt32 {
    let stream: AudioObjectID = get(device, kAudioDevicePropertyStreams, scope, 0)
    return get(device, kAudioDevicePropertyLatency, scope, UInt32(0))
        + get(stream, kAudioStreamPropertyLatency, kAudioObjectPropertyScopeGlobal, UInt32(0))
}

func findEnsemble() -> AudioObjectID? {
    var addr = address(kAudioHardwarePropertyDevices)
    var size: UInt32 = 0
    AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size)
    var ids = [AudioObjectID](repeating: 0, count: Int(size) / 4)
    AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &ids)
    return ids.first { name($0) == "Ensemble" }
}

guard let device = findEnsemble() else {
    print("no device named Ensemble")
    exit(1)
}
if let rate = CommandLine.arguments.dropFirst().first.flatMap(Float64.init) {
    var value = rate
    var addr = address(kAudioDevicePropertyNominalSampleRate)
    let status = AudioObjectSetPropertyData(device, &addr, 0, nil, UInt32(MemoryLayout<Float64>.size), &value)
    print("set rate \(rate): status \(status)")
    RunLoop.main.run(until: Date().addingTimeInterval(1))
}
let uid = string(device, kAudioDevicePropertyDeviceUID)
print("device \(device) uid \(uid)")
print("inputs \(channels(device, kAudioObjectPropertyScopeInput)) outputs \(channels(device, kAudioObjectPropertyScopeOutput))")
print("rate \(get(device, kAudioDevicePropertyNominalSampleRate, kAudioObjectPropertyScopeGlobal, Float64(0)))")
print("safety offset in \(get(device, kAudioDevicePropertySafetyOffset, kAudioObjectPropertyScopeInput, UInt32(0)))"
    + " out \(get(device, kAudioDevicePropertySafetyOffset, kAudioObjectPropertyScopeOutput, UInt32(0)))")
print("clock stable \(get(device, 0x63737462 /* cstb, AudioServerPlugIn.h */, kAudioObjectPropertyScopeGlobal, UInt32(0)))")
print("latency in \(latency(device, kAudioObjectPropertyScopeInput)) out \(latency(device, kAudioObjectPropertyScopeOutput))")

final class Stats {
    var first: AudioTimeStamp?
    var last = AudioTimeStamp()
    var cycles = 0
    var overloads = 0
    var peak: Float = 0
}
let stats = Stats()

var overloadAddr = address(kAudioDeviceProcessorOverload)
AudioObjectAddPropertyListenerBlock(device, &overloadAddr, DispatchQueue.main) { _, _ in
    stats.overloads += 1
}

var procID: AudioDeviceIOProcID?
AudioDeviceCreateIOProcIDWithBlock(&procID, device, nil) { now, input, _, output, _ in
    if stats.first == nil { stats.first = now.pointee }
    stats.last = now.pointee
    stats.cycles += 1
    for buffer in UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input)) {
        let samples = buffer.mData!.assumingMemoryBound(to: Float.self)
        for i in 0..<Int(buffer.mDataByteSize) / 4 { stats.peak = max(stats.peak, abs(samples[i])) }
    }
    for buffer in UnsafeMutableAudioBufferListPointer(output) {
        memset(buffer.mData, 0, Int(buffer.mDataByteSize))
    }
}
AudioDeviceStart(device, procID)
RunLoop.main.run(until: Date().addingTimeInterval(5))
AudioDeviceStop(device, procID)

guard let first = stats.first else {
    print("no IO cycles")
    exit(1)
}
var timebase = mach_timebase_info()
mach_timebase_info(&timebase)
let seconds = Double(stats.last.mHostTime - first.mHostTime) * Double(timebase.numer) / Double(timebase.denom) / 1e9
let frames = stats.last.mSampleTime - first.mSampleTime
print(String(format: "cycles %d, %.0f frames in %.3f s = %.1f frames/s", stats.cycles, frames, seconds, frames / seconds))
print("overloads \(stats.overloads), input peak \(stats.peak)")
