import CoreAudio
import Foundation

// Plays a constant value on one channel of the playback stream and silence on the others.
func play(_ arguments: [String]) {
    guard arguments.count == 3, let seconds = Double(arguments[0]), let channel = Int(arguments[1]),
          let value = Float(arguments[2]), abs(value) <= 0.75
    else {
        fail("usage: play <seconds> <channel> <value>, |value| <= 0.75", status: 2)
    }
    let device = ensemble()
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
}
