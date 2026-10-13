public enum Kind: Equatable, Sendable {
    case bool
    case int(ClosedRange<Int>)
    case choice([String])
}

public enum Wire: Equatable, Sendable {
    case set
    case block(bytes: Int)
}

public struct Parameter: Sendable {
    public let path: String
    public let command: UInt8
    public let p1: UInt8
    public var p2: UInt8 = 0
    public var wire: Wire = .set
    public let kind: Kind
}

public let parameters: [Parameter] = clock + outputs + inputs + mixers

private let clock = [
    Parameter(path: "clock/sampleRate", command: 0x29, p1: 0,
              kind: .choice(["44100", "48000", "88200", "96000", "176400", "192000"])),
    Parameter(path: "clock/source", command: 0x2A, p1: 0,
              kind: .choice(["Internal", "Word Clock", "S/PDIF Coax", "Optical 1", "Optical 2"])),
    Parameter(path: "clock/wordClockTermination", command: 0x2B, p1: 0, kind: .bool),
]

private let outputs = [
    Parameter(path: "outputs/mainMode", command: 0x0F, p1: 0,
              kind: .choice(["Line", "Stereo", "2 Speaker Sets", "3 Speaker Sets", "5.1", "7.1", "9.1"])),
] + ["headphone1", "headphone2", "speaker"].enumerated().flatMap { index, name in
    [
        Parameter(path: "outputs/\(name)/attenuation", command: 0x11, p1: UInt8(index), kind: .int(0...64)),
        Parameter(path: "outputs/\(name)/mute", command: 0x12, p1: UInt8(index), kind: .bool),
        Parameter(path: "outputs/\(name)/dim", command: 0x13, p1: UInt8(index), kind: .bool),
        Parameter(path: "outputs/\(name)/mono", command: 0x14, p1: UInt8(index), kind: .bool),
    ]
}

private let inputs = (0..<8).flatMap { channel in
    let prefix = "inputs/analog/\(channel + 1)"
    let p1 = UInt8(channel)
    return [
        Parameter(path: "\(prefix)/type", command: 0x01, p1: p1,
                  kind: .choice(["+4dBu", "-10dBV", "Mic", "Instrument"])),
        Parameter(path: "\(prefix)/micGain", command: 0x02, p1: p1, kind: .int(0...75)),
        Parameter(path: "\(prefix)/softLimit", command: 0x04, p1: p1, kind: .bool),
        Parameter(path: "\(prefix)/phantom", command: 0x05, p1: p1, kind: .bool),
        Parameter(path: "\(prefix)/phase", command: 0x06, p1: p1, kind: .bool),
        Parameter(path: "\(prefix)/group", command: 0x07, p1: p1, kind: .int(0...5)),
        Parameter(path: "\(prefix)/highPass", command: 0x08, p1: p1, kind: .bool),
    ]
}

private let mixers = (0..<4).flatMap { mixer in
    (0..<48).flatMap { channel in
        let prefix = "mixers/\(mixer + 1)/channels/\(channel + 1)"
        let (p1, p2) = (UInt8(channel), UInt8(mixer))
        let strip = [
            Parameter(path: "\(prefix)/fader", command: 0x32, p1: p1, p2: p2, wire: .block(bytes: 2),
                      kind: .int(0...720)),
            Parameter(path: "\(prefix)/mute", command: 0x35, p1: p1, p2: p2, wire: .block(bytes: 1), kind: .bool),
        ]
        let pan = Parameter(path: "\(prefix)/pan", command: 0x33, p1: p1, p2: p2, wire: .block(bytes: 1),
                            kind: .int(0...127))
        return channel < 46 ? strip + [pan] : strip
    }
}
