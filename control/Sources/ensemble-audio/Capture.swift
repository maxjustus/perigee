import CoreAudio
import Foundation

// Records channels of the record stream and writes them to stdout as interleaved little-endian float32
// frames. The output stays silent.
func capture(_ arguments: [String]) {
    guard let seconds = arguments.first.flatMap(Double.init) else {
        fail("usage: capture <seconds> <channel>...", status: 2)
    }
    let channels = arguments.dropFirst().compactMap(Int.init)
    let device = ensemble()
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
}

private final class Recording: @unchecked Sendable {
    let lock = NSLock()
    var frames: [Float] = []
}
