import Foundation
import Synchronization

public func monitorFrame(rate: UInt32, interleaved: UnsafeBufferPointer<Float>, channels: Int, channel: Int) -> Data {
    var frame = Data(capacity: 4 + 2 * interleaved.count / channels)
    withUnsafeBytes(of: rate.littleEndian) { frame.append(contentsOf: $0) }
    for index in stride(from: channel, to: interleaved.count, by: channels) {
        let sample = Int16(max(-32768, min(32767, (interleaved[index] * 32768).rounded())))
        withUnsafeBytes(of: sample.littleEndian) { frame.append(contentsOf: $0) }
    }
    return frame
}

// One CoreAudio IO thread writes and one queue reads. write neither allocates
// nor locks, so it is safe on the IO thread.
public final class SampleRing: @unchecked Sendable {
    private let storage: UnsafeMutableBufferPointer<Float>
    private let written = Atomic<Int>(0)
    private var position = 0

    public init(capacity: Int) {
        storage = .allocate(capacity: capacity)
    }

    deinit {
        storage.deallocate()
    }

    public func write(_ samples: UnsafeBufferPointer<Float>) {
        let end = written.load(ordering: .relaxed)
        var copied = 0
        while copied < samples.count {
            let start = (end + copied) % storage.count
            let count = min(samples.count - copied, storage.count - start)
            _ = UnsafeMutableBufferPointer(rebasing: storage[start..<start + count])
                .initialize(from: UnsafeBufferPointer(rebasing: samples[copied..<copied + count]))
            copied += count
        }
        written.store(end + samples.count, ordering: .releasing)
    }

    // Drops the samples that the writer overwrote before this read.
    public func read(_ segment: (UnsafeBufferPointer<Float>) -> Void) {
        let end = written.load(ordering: .acquiring)
        if end - position > storage.count {
            position = end
        }
        while position < end {
            let start = position % storage.count
            let count = min(end - position, storage.count - start)
            segment(UnsafeBufferPointer(rebasing: storage[start..<start + count]))
            position += count
        }
    }
}
