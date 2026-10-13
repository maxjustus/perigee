// Records channels of the Ensemble record stream and writes them to stdout
// as interleaved little-endian float32 frames. The output stays silent.
// Usage: capture <seconds> <channel>...
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

let arguments = CommandLine.arguments.dropFirst()
guard let seconds = arguments.first.flatMap(Double.init) else {
    FileHandle.standardError.write("usage: capture <seconds> <channel>...\n".data(using: .utf8)!)
    exit(2)
}
let channels = arguments.dropFirst().compactMap(Int.init)
guard let device = findEnsemble() else {
    FileHandle.standardError.write("no device named Ensemble\n".data(using: .utf8)!)
    exit(1)
}

final class Recording: @unchecked Sendable {
    let lock = NSLock()
    var frames: [Float] = []
}
let recording = Recording()

var procID: AudioDeviceIOProcID?
AudioDeviceCreateIOProcIDWithBlock(&procID, device, nil) { _, input, _, output, _ in
    var buffers: [(samples: UnsafeMutablePointer<Float>, width: Int, first: Int)] = []
    var frames = 0
    for buffer in UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input)) {
        let width = Int(buffer.mNumberChannels)
        buffers.append((buffer.mData!.assumingMemoryBound(to: Float.self), width,
                        (buffers.last.map { $0.first + $0.width } ?? 0)))
        frames = Int(buffer.mDataByteSize) / 4 / width
    }
    var block: [Float] = []
    for frame in 0..<frames {
        for channel in channels {
            let buffer = buffers.last { $0.first <= channel }!
            block.append(buffer.samples[frame * buffer.width + channel - buffer.first])
        }
    }
    recording.lock.lock()
    recording.frames += block
    recording.lock.unlock()
    for buffer in UnsafeMutableAudioBufferListPointer(output) {
        memset(buffer.mData, 0, Int(buffer.mDataByteSize))
    }
}
AudioDeviceStart(device, procID)
RunLoop.main.run(until: Date().addingTimeInterval(seconds))
AudioDeviceStop(device, procID)

recording.lock.lock()
recording.frames.withUnsafeBytes { FileHandle.standardOutput.write(Data($0)) }
recording.lock.unlock()
