import CoreAudio
import EnsembleIO
import EnsembleModel
import Foundation

// Records channels of the record stream and writes them to stdout as interleaved little-endian float32
// frames. The output stays silent.
func capture(_ arguments: [String]) {
    let device = ensemble()
    let width = channelCount(device, kAudioObjectPropertyScopeInput)
    guard let seconds = arguments.first.flatMap(Double.init),
          case let channels = arguments.dropFirst().compactMap(Int.init), channels.allSatisfy((0..<width).contains)
    else {
        fail("usage: capture <seconds> <channel>..., each channel 0 to \(width - 1)", status: 2)
    }
    let rate = property(device, kAudioDevicePropertyNominalSampleRate, kAudioObjectPropertyScopeGlobal, Float64(0))
    let ring = SampleRing(capacity: Int((seconds + 1) * rate) * width)
    var procID: AudioDeviceIOProcID?
    AudioDeviceCreateIOProcIDWithBlock(&procID, device, nil) { _, input, _, output, _ in
        if let buffer = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input)).first,
           Int(buffer.mNumberChannels) == width, let samples = buffer.mData {
            ring.write(UnsafeBufferPointer(start: samples.assumingMemoryBound(to: Float.self),
                                           count: Int(buffer.mDataByteSize) / MemoryLayout<Float>.size))
        }
        for buffer in UnsafeMutableAudioBufferListPointer(output) {
            memset(buffer.mData, 0, Int(buffer.mDataByteSize))
        }
    }
    AudioDeviceStart(device, procID)
    RunLoop.main.run(until: Date().addingTimeInterval(seconds))
    AudioDeviceStop(device, procID)

    var frames: [Float] = []
    ring.read { interleaved in
        for frame in stride(from: 0, to: interleaved.count, by: width) {
            frames += channels.map { interleaved[frame + $0] }
        }
    }
    frames.withUnsafeBytes { FileHandle.standardOutput.write(Data($0)) }
}
