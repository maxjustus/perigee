public struct Report: Equatable, Sendable {
    public let type: UInt8
    public let command: UInt8
    public let p1: UInt8
    public let p2: UInt8
    public let data: [UInt8]

    public init(type: UInt8, command: UInt8, p1: UInt8, p2: UInt8, data: [UInt8]) {
        self.type = type
        self.command = command
        self.p1 = p1
        self.p2 = p2
        self.data = data
    }

    public init(arguments: [UInt64]) {
        let header = arguments.first ?? 0
        let byte = { (shift: UInt64) in UInt8(truncatingIfNeeded: header >> shift) }
        let length = min(Int(byte(32)), (arguments.count - 1) * 8)
        self.init(type: byte(0), command: byte(8), p1: byte(16), p2: byte(24),
                  data: (0..<length).map { UInt8(truncatingIfNeeded: arguments[1 + $0 / 8] >> (8 * UInt64($0 % 8))) })
    }
}

func setMessage(command: UInt8, p1: UInt8, value: UInt8) -> [UInt32] {
    [1, 0, 1 | UInt32(command) << 8 | UInt32(p1) << 16 | UInt32(value) << 24]
}
