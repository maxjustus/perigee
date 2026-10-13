// Plays a constant value on one channel of the Ensemble playback stream and
// silence on the others.
// Usage: play <seconds> <channel> <value>
import CoreAudio
import Foundation

func address(_ selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal,
                               mElement: kAudioObjectPropertyElementMain)
}

func name(_ object: AudioObjectID) -> String {
    var value: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    var addr = address(kAudioObjectPropertyName)
    AudioObjectGetPropertyData(object, &addr, 0, nil, &size, &value)
    return value?.takeRetainedValue() as String? ?? ""
}

func findEnsemble() -> AudioObjectID? {
    var addr = address(kAudioHardwarePropertyDevices)
    var size: UInt32 = 0
    AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size)
    var ids = [AudioObjectID](repeating: 0, count: Int(size) / 4)
    AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &ids)
    return ids.first { name($0) == "Ensemble" }
}

let arguments = Array(CommandLine.arguments.dropFirst())
guard arguments.count == 3, let seconds = Double(arguments[0]), let channel = Int(arguments[1]),
      let value = Float(arguments[2]), abs(value) <= 0.75
else {
    FileHandle.standardError.write("usage: play <seconds> <channel> <value>, |value| <= 0.75\n".data(using: .utf8)!)
    exit(2)
}
guard let device = findEnsemble() else {
    FileHandle.standardError.write("no device named Ensemble\n".data(using: .utf8)!)
    exit(1)
}

var procID: AudioDeviceIOProcID?
AudioDeviceCreateIOProcIDWithBlock(&procID, device, nil) { _, _, _, output, _ in
    var first = 0
    for buffer in UnsafeMutableAudioBufferListPointer(output) {
        let width = Int(buffer.mNumberChannels)
        let samples = buffer.mData!.assumingMemoryBound(to: Float.self)
        let frames = Int(buffer.mDataByteSize) / 4 / width
        memset(buffer.mData, 0, Int(buffer.mDataByteSize))
        if (first..<first + width).contains(channel) {
            for frame in 0..<frames {
                samples[frame * width + channel - first] = value
            }
        }
        first += width
    }
}
AudioDeviceStart(device, procID)
RunLoop.main.run(until: Date().addingTimeInterval(seconds))
AudioDeviceStop(device, procID)
