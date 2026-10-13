public enum Kind: Equatable, Sendable {
    case bool
    case int(ClosedRange<Int>)
    case choice([Choice])
}

public struct Choice: Equatable, Sendable {
    public let name: String
    public let code: Int
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
    public var also: [UInt8] = []
    public var wire: Wire = .set
    public var reported: Wire?
    public var on = 1
    public let kind: Kind
}

public let parameters: [Parameter] = clock + outputs + frontPanel + routing + inputs + mixers

private func choices(_ names: [String]) -> Kind {
    .choice(names.enumerated().map { Choice(name: $0.element, code: $0.offset) })
}

private let clock = [
    Parameter(path: "clock/sampleRate", command: 0x29, p1: 0,
              kind: choices(["44100", "48000", "88200", "96000", "176400", "192000"])),
    Parameter(path: "clock/source", command: 0x2A, p1: 0,
              kind: choices(["Internal", "Word Clock", "S/PDIF Coax", "Optical 1", "Optical 2"])),
    Parameter(path: "clock/wordClockTermination", command: 0x2B, p1: 0, kind: .bool),
]

private let outputs: [Parameter] = [
    Parameter(path: "outputs/mainMode", command: 0x0F, p1: 0,
              kind: choices(["Line", "Stereo", "2 Speaker Sets", "3 Speaker Sets", "5.1", "7.1", "9.1"])),
    Parameter(path: "outputs/activeSpeakerSet", command: 0x10, p1: 0,
              kind: .choice([Choice(name: "A", code: 1), Choice(name: "B", code: 2), Choice(name: "C", code: 4)])),
] + monitors + lines + guitarOutputs

private let monitors: [Parameter] = ["headphone1", "headphone2", "speaker"].enumerated().flatMap { index, name in
    [
        Parameter(path: "outputs/\(name)/attenuation", command: 0x11, p1: UInt8(index), kind: .int(0...64)),
        Parameter(path: "outputs/\(name)/mute", command: 0x12, p1: UInt8(index), kind: .bool),
        Parameter(path: "outputs/\(name)/dim", command: 0x13, p1: UInt8(index), kind: .bool),
        Parameter(path: "outputs/\(name)/mono", command: 0x14, p1: UInt8(index), kind: .bool),
    ]
}

private let lines: [Parameter] = (0..<10).flatMap { line in
    [
        Parameter(path: "outputs/line/\(line + 1)/referenceLevel", command: 0x0D, p1: UInt8(line),
                  kind: choices(["+4dBu", "-10dBV"])),
        Parameter(path: "outputs/line/\(line + 1)/trim", command: 0x0E, p1: UInt8(line), kind: .int(0...120)),
    ]
}

private let guitarOutputs: [Parameter] = (0..<2).flatMap { guitar in
    [
        Parameter(path: "outputs/guitar/\(guitar + 1)/mode", command: 0x16, p1: UInt8(guitar),
                  kind: choices(["Thru", "From Software"])),
        Parameter(path: "outputs/guitar/\(guitar + 1)/attenuation", command: 0x1C, p1: UInt8(guitar),
                  kind: .int(0...64)),
        Parameter(path: "outputs/guitar/\(guitar + 1)/matchUnityGain", command: 0x1D, p1: UInt8(guitar),
                  kind: .bool),
        Parameter(path: "outputs/optical\(guitar + 1)/format", command: 0x1A, p1: UInt8(guitar),
                  kind: choices(["ADAT/SMUX", "S/PDIF"])),
    ]
}

private let frontPanel = [
    Parameter(path: "frontPanel/knobTarget", command: 0x20, p1: 0,
              kind: choices(["Headphone 1", "Headphone 2", "Speaker"])),
    Parameter(path: "frontPanel/encoderInput", command: 0x23, p1: 0,
              kind: .choice((0..<8).map { Choice(name: "Analog \($0 + 1)", code: $0) }
                  + [Choice(name: "Guitar 1", code: 10), Choice(name: "Guitar 2", code: 11)])),
    Parameter(path: "frontPanel/lockHome", command: 0x24, p1: 0, kind: .bool),
]

private let sourceChoices: [Choice] = playbackSources + inputSources + mixerSources
private let sources = Kind.choice(sourceChoices)

private let playbackSources: [Choice] = (0..<18).map {
    Choice(name: "Playback \(2 * $0 + 1)-\(2 * $0 + 2)", code: 0x30 + 2 * $0)
}

private let inputSources: [Choice] = (0..<4).map { Choice(name: "Analog \(2 * $0 + 1)-\(2 * $0 + 2)", code: 2 * $0) }
    + [Choice(name: "Front Panel Mic", code: 0x08), Choice(name: "Guitar 1-2", code: 0x0A),
       Choice(name: "S/PDIF Coax", code: 0x54)]
    + (0..<8).map { Choice(name: "Optical \(2 * $0 + 1)-\(2 * $0 + 2)", code: 0x10 + 2 * $0) }

private let mixerSources: [Choice] = ["Mixer 1", "Mixer 2", "Mixer 3", "FX Send"].enumerated().map {
    Choice(name: $1, code: 0x60 + 2 * $0)
}

private let destinations = ["line1-2", "line3-4", "line5-6", "line7-8", "line9-10", "guitar1-2", "spdif"]
    + (0..<8).map { "optical\(2 * $0 + 1)-\(2 * $0 + 2)" } + ["headphone1", "headphone2"]

private let routing = destinations.enumerated().map { pair, name in
    Parameter(path: "routing/\(name)", command: 0x15, p1: UInt8(pair), kind: sources)
}

private let inputs = (0..<8).flatMap { channel in
    let prefix = "inputs/analog/\(channel + 1)"
    let p1 = UInt8(channel)
    let types = ["+4dBu", "-10dBV", "Mic", "Instrument"]
    let analog = [
        Parameter(path: "\(prefix)/type", command: 0x01, p1: p1, kind: choices(channel < 4 ? types : Array(types.prefix(3)))),
        Parameter(path: "\(prefix)/micGain", command: 0x02, p1: p1, kind: .int(0...75)),
        Parameter(path: "\(prefix)/softLimit", command: 0x04, p1: p1, kind: .bool),
        Parameter(path: "\(prefix)/phantom", command: 0x05, p1: p1, kind: .bool),
        Parameter(path: "\(prefix)/phase", command: 0x06, p1: p1, kind: .bool),
        Parameter(path: "\(prefix)/highPass", command: 0x08, p1: p1, kind: .bool),
    ]
    let instrument = Parameter(path: "\(prefix)/instrumentGain", command: 0x03, p1: p1, kind: .int(0...65))
    return channel < 4 ? analog + [instrument] : analog
} + (0..<4).map { pair in
    Parameter(path: "inputs/analog/\(2 * pair + 1)-\(2 * pair + 2)/link", command: 0x07, p1: UInt8(2 * pair),
              also: [UInt8(2 * pair + 1)], on: pair + 1, kind: .bool)
} + [
    Parameter(path: "inputs/frontMic/gain", command: 0x02, p1: 8, kind: .int(0...40)),
    Parameter(path: "inputs/guitar/1-2/link", command: 0x07, p1: 10, also: [11], on: 6, kind: .bool),
    Parameter(path: "inputs/insert/1", command: 0x0A, p1: 0, kind: .bool),
    Parameter(path: "inputs/insert/2", command: 0x0A, p1: 1, kind: .bool),
] + (0..<2).map { guitar in
    Parameter(path: "inputs/guitar/\(guitar + 1)/gain", command: 0x03, p1: UInt8(10 + guitar), kind: .int(0...45))
}

private let mixers = (0..<4).flatMap { mixer in
    (0..<48).filter { $0 != 9 }.flatMap { channel in
        let prefix = "mixers/\(mixer + 1)/channels/\(channel + 1)"
        let (p1, p2) = (UInt8(channel), UInt8(mixer))
        var strip = [
            Parameter(path: "\(prefix)/fader", command: 0x32, p1: p1, p2: p2, wire: .block(bytes: 2),
                      kind: .int(0...720)),
            Parameter(path: "\(prefix)/mute", command: 0x35, p1: p1, p2: p2, wire: .block(bytes: 1), kind: .bool),
        ]
        if channel < 46 {
            strip.append(Parameter(path: "\(prefix)/pan", command: 0x33, p1: p1, p2: p2, wire: .block(bytes: 1),
                                   kind: .int(0...127)))
        }
        if mixer == 0 && channel < 47 {
            strip.append(Parameter(path: "\(prefix)/solo", command: 0x34, p1: p1, wire: .block(bytes: 1),
                                   reported: .set, kind: .bool))
        }
        if mixer == 0 && channel < 46 {
            strip.append(Parameter(path: "\(prefix)/soloSafe", command: 0x3A, p1: p1, wire: .block(bytes: 1),
                                   reported: .set, kind: .bool))
        }
        return strip
    }
}
