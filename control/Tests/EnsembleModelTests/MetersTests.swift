import Foundation
import Testing

@testable import EnsembleModel

func meterBytes() -> [UInt8] {
    var bytes = [UInt8](repeating: 0, count: 0xB4)
    bytes[0] = 7
    func put(_ offset: Int, _ value: UInt16) {
        bytes[offset] = UInt8(value & 0xFF)
        bytes[offset + 1] = UInt8(value >> 8)
    }
    put(0x04, 0x1234)
    put(0x04 + 29 * 2, 1)
    put(0x40, 0x0102)
    put(0xA4 + 7 * 2, 0xFFFF)
    return bytes
}

@Test func metersFollowTheVendorBufferLayout() {
    let meters = Meters(bytes: meterBytes())!
    #expect(meters.sequence == 7)
    #expect(meters.inputs.count == 30 && meters.inputs[0] == 0x1234 && meters.inputs[29] == 1)
    #expect(meters.outputs.count == 30 && meters.outputs[0] == 0x0102)
    #expect(meters.mixers.count == 8 && meters.mixers[7] == 0xFFFF)
}

@Test func shortBufferHasNoMeters() {
    #expect(Meters(bytes: [UInt8](repeating: 0, count: 0xB3)) == nil)
}

@Test func metersAreBroadcastAsANotification() {
    let (controller, _, broadcasts) = makeController()
    controller.meters(Meters(bytes: meterBytes())!)
    let message = object(broadcasts.texts.last!)
    #expect(message["method"] as? String == "meters")
    let params = message["params"] as? [String: Any]
    #expect(params.map { Set($0.keys) } == ["inputs", "outputs", "headphones", "playback", "mixers"])
    #expect((params?["inputs"] as? [Int])?.first == 0x1234)
}
