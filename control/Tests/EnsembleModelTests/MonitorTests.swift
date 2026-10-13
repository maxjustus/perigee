import Foundation
import Testing

@testable import EnsembleModel

@Test func monitorFrameHoldsTheRateThenOneChannelAsInt16() {
    let interleaved: [Float] = [0.1, 0.5, 0.2, -0.5, 0.3, 1.0]
    let frame = interleaved.withUnsafeBufferPointer { monitorFrame(rate: 48000, interleaved: $0, channels: 2, channel: 1) }
    #expect(Array(frame) == [0x80, 0xBB, 0x00, 0x00, 0x00, 0x40, 0x00, 0xC0, 0xFF, 0x7F])
}

@Test func monitorFrameClipsOutOfRangeSamples() {
    let interleaved: [Float] = [2, -2]
    let frame = interleaved.withUnsafeBufferPointer { monitorFrame(rate: 0, interleaved: $0, channels: 1, channel: 0) }
    #expect(Array(frame.dropFirst(4)) == [0xFF, 0x7F, 0x00, 0x80])
}
