public struct Meters: Equatable, Sendable {
    public static let bytes = 0xB4

    public let sequence: UInt8
    public let inputs: [UInt16]
    public let outputs: [UInt16]
    public let outputGroup: [UInt16]
    public let group2: [UInt16]
    public let mixers: [UInt16]

    public init?(bytes: [UInt8]) {
        guard bytes.count >= Meters.bytes else {
            return nil
        }
        func values(_ offset: Int, _ count: Int) -> [UInt16] {
            (0..<count).map { UInt16(bytes[offset + 2 * $0]) | UInt16(bytes[offset + 2 * $0 + 1]) << 8 }
        }
        sequence = bytes[0]
        inputs = values(0x04, 30)
        outputs = values(0x40, 30)
        outputGroup = values(0x7C, 4)
        group2 = values(0x84, 16)
        mixers = values(0xA4, 8)
    }
}
