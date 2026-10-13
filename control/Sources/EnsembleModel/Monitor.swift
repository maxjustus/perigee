import Foundation

public func monitorFrame(rate: UInt32, interleaved: UnsafeBufferPointer<Float>, channels: Int, channel: Int) -> Data {
    var frame = Data(capacity: 4 + 2 * interleaved.count / channels)
    withUnsafeBytes(of: rate.littleEndian) { frame.append(contentsOf: $0) }
    for index in stride(from: channel, to: interleaved.count, by: channels) {
        let sample = Int16(max(-32768, min(32767, (interleaved[index] * 32768).rounded())))
        withUnsafeBytes(of: sample.littleEndian) { frame.append(contentsOf: $0) }
    }
    return frame
}
