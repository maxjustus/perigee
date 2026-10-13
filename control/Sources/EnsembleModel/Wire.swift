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

func message(_ parameter: Parameter, _ target: Target, _ value: Int) -> [UInt32] {
    let bytes: [UInt8]
    switch parameter.wire {
    case .set:
        bytes = [1, parameter.command, target.p1, UInt8(value)]
    case .block(let count):
        let data = count == 2 ? [UInt8(value >> 8), UInt8(value & 0xFF)] : [UInt8(value)]
        bytes = [2, parameter.command, target.p1, target.p2, UInt8(count)] + data
    }
    let words = stride(from: 0, to: bytes.count, by: 4).map { start in
        bytes[start..<min(start + 4, bytes.count)].enumerated().reduce(UInt32(0)) {
            $0 | UInt32($1.element) << (8 * UInt32($1.offset))
        }
    }
    return [1, 0] + words
}

func value(_ parameter: Parameter, _ report: Report) -> Int? {
    switch parameter.wire {
    case .block(bytes: 2):
        return report.data.count >= 2 ? Int(report.data[0]) << 8 | Int(report.data[1]) : nil
    default:
        return report.data.first.map(Int.init)
    }
}
