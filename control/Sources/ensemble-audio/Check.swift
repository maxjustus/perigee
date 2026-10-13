import CoreAudio
import EnsembleIO
import Foundation

// Prints the device properties, then runs 5 s of IO with silent output.
func check(_ arguments: [String]) {
    let device = ensemble()
    if let rate = arguments.first.flatMap(Float64.init) {
        var value = rate
        var address = propertyAddress(kAudioDevicePropertyNominalSampleRate)
        let status = AudioObjectSetPropertyData(device, &address, 0, nil, UInt32(MemoryLayout<Float64>.size), &value)
        print("set rate \(rate): status \(status)")
        RunLoop.main.run(until: Date().addingTimeInterval(1))
    }
    let input = kAudioObjectPropertyScopeInput, output = kAudioObjectPropertyScopeOutput
    print("device \(device) uid \(stringProperty(device, kAudioDevicePropertyDeviceUID))")
    print("inputs \(channelCount(device, input)) outputs \(channelCount(device, output))")
    print("rate \(property(device, kAudioDevicePropertyNominalSampleRate, kAudioObjectPropertyScopeGlobal, Float64(0)))")
    print("safety offset in \(property(device, kAudioDevicePropertySafetyOffset, input, UInt32(0)))"
        + " out \(property(device, kAudioDevicePropertySafetyOffset, output, UInt32(0)))")
    print("clock stable \(property(device, 0x63737462 /* cstb, AudioServerPlugIn.h */, kAudioObjectPropertyScopeGlobal, UInt32(0)))")
    print("latency in \(latency(device, input)) out \(latency(device, output))")

    let stats = Stats()
    var overload = propertyAddress(kAudioDeviceProcessorOverload)
    AudioObjectAddPropertyListenerBlock(device, &overload, DispatchQueue.main) { _, _ in
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
        fail("no IO cycles")
    }
    var timebase = mach_timebase_info()
    mach_timebase_info(&timebase)
    let seconds = Double(stats.last.mHostTime - first.mHostTime) * Double(timebase.numer) / Double(timebase.denom) / 1e9
    let frames = stats.last.mSampleTime - first.mSampleTime
    print(String(format: "cycles %d, %.0f frames in %.3f s = %.1f frames/s", stats.cycles, frames, seconds, frames / seconds))
    print("overloads \(stats.overloads), input peak \(stats.peak)")
}

private func latency(_ device: AudioObjectID, _ scope: AudioObjectPropertyScope) -> UInt32 {
    let stream: AudioObjectID = property(device, kAudioDevicePropertyStreams, scope, 0)
    return property(device, kAudioDevicePropertyLatency, scope, UInt32(0))
        + property(stream, kAudioStreamPropertyLatency, kAudioObjectPropertyScopeGlobal, UInt32(0))
}

private final class Stats: @unchecked Sendable {
    var first: AudioTimeStamp?
    var last = AudioTimeStamp()
    var cycles = 0
    var overloads = 0
    var peak: Float = 0
}
