import Foundation
import Testing

@testable import EnsembleModel

final class FakeTransport: Transport, @unchecked Sendable {
    var sent: [[UInt32]] = []
    var full = 0
    var attempts = 0
    var echo: ((Report) -> Void)?
    func send(_ words: [UInt32]) throws -> Bool {
        attempts += 1
        guard full == 0 else {
            full -= 1
            return false
        }
        sent.append(words)
        echo?(report(words))
        return true
    }
}

// The dext reports each message that it sends to the PSoC.
func report(_ words: [UInt32]) -> Report {
    let bytes = words.dropFirst(2).flatMap { word in (0..<4).map { UInt8(truncatingIfNeeded: word >> (8 * $0)) } }
    if bytes[0] == 1 {
        return Report(type: 1, command: bytes[1], p1: bytes[2], p2: 0, data: [bytes[3]])
    }
    return Report(type: 2, command: bytes[1], p1: bytes[2], p2: bytes[3], data: Array(bytes[5..<5 + Int(bytes[4])]))
}

final class Broadcasts: @unchecked Sendable {
    var texts: [String] = []
}

func object(_ text: String) -> [String: Any] {
    try! JSONSerialization.jsonObject(with: Data(text.utf8)) as! [String: Any]
}

func word(_ b0: UInt32, _ b1: UInt32, _ b2: UInt32, _ b3: UInt32) -> UInt32 {
    b0 | b1 << 8 | b2 << 16 | b3 << 24
}

func makeController(presets: URL = temporaryPresets()) -> (Controller, FakeTransport, Broadcasts) {
    let transport = FakeTransport()
    let broadcasts = Broadcasts()
    let controller = Controller(transport: transport, presets: presets, retryDelay: 0) {
        broadcasts.texts.append($0)
    }
    return (controller, transport, broadcasts)
}

func temporaryPresets() -> URL {
    FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        .appendingPathComponent("presets.json")
}

func call(_ controller: Controller, _ method: String, _ params: String) -> [String: Any] {
    object(controller.handle(#"{"jsonrpc":"2.0","id":1,"method":""# + method + #"","params":"# + params + "}")!)
}

@Test func parameterPathsAreUnique() {
    #expect(Set(parameters.map(\.path)).count == parameters.count)
}

@Test func speakerAttenuationMapsToCommand0x11Output2() {
    let p = parameters.first { $0.path == "outputs/speaker/attenuation" }!
    #expect(p.command == 0x11 && p.p1 == 2 && p.kind == .int(0...64))
}

@Test func setSendsATypeOneCommand() {
    let (controller, transport, _) = makeController()
    let response = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"outputs/speaker/mute":true}}"#)
    #expect(transport.sent == [[1, 0, 0x0102_1201]])
    #expect(object(response!)["result"] as? Bool == true)
}

@Test func setTakesChoicesByName() {
    let (controller, transport, _) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"clock/sampleRate":"96000"}}"#)
    #expect(transport.sent == [[1, 0, 0x0300_2901]])
}

@Test func setRejectsUnknownPathsAndBadValues() {
    let (controller, transport, _) = makeController()
    let unknown = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"nope":1}}"#)
    let range = controller.handle(#"{"jsonrpc":"2.0","id":2,"method":"set","params":{"outputs/speaker/attenuation":65}}"#)
    #expect((object(unknown!)["error"] as? [String: Any])?["code"] as? Int == -32602)
    #expect((object(range!)["error"] as? [String: Any])?["code"] as? Int == -32602)
    #expect(transport.sent.isEmpty)
}

@Test func reportUpdatesStateAndBroadcastsTheChange() {
    let (controller, _, broadcasts) = makeController()
    controller.receive(Report(type: 1, command: 0x11, p1: 2, p2: 0, data: [47]))
    let changed = object(broadcasts.texts.last!)
    #expect(changed["method"] as? String == "changed")
    #expect((changed["params"] as? [String: Any])?["outputs/speaker/attenuation"] as? Int == 47)
    let response = controller.handle(#"{"jsonrpc":"2.0","id":3,"method":"get"}"#)
    #expect((object(response!)["result"] as? [String: Any])?["outputs/speaker/attenuation"] as? Int == 47)
}

@Test func unchangedReportIsNotBroadcast() {
    let (controller, _, broadcasts) = makeController()
    controller.receive(Report(type: 1, command: 0x12, p1: 2, p2: 0, data: [1]))
    controller.receive(Report(type: 1, command: 0x12, p1: 2, p2: 0, data: [1]))
    #expect(broadcasts.texts.count == 1)
}

@Test func unmappedReportIsBroadcastRaw() {
    let (controller, _, broadcasts) = makeController()
    controller.receive(Report(type: 2, command: 0x40, p1: 5, p2: 1, data: [2, 0x58]))
    let report = object(broadcasts.texts.last!)
    #expect(report["method"] as? String == "report")
    #expect((report["params"] as? [String: Any])?["data"] as? [Int] == [2, 0x58])
}

@Test func aPsocRestartIsBroadcast() {
    let (controller, _, broadcasts) = makeController()
    controller.receive(Report(type: 5, command: 0, p1: 0, p2: 0, data: []))
    #expect(broadcasts.texts.count == 1)
    #expect(object(broadcasts.texts[0])["method"] as? String == "restarted")
}

@Test func rawSendPassesWordsThrough() {
    let (controller, transport, _) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":4,"method":"raw.send","params":{"words":[1,0,4]}}"#)
    #expect(transport.sent == [[1, 0, 4]])
}

@Test func sendRetriesWhileTheDriverOutboxIsFull() {
    let (controller, transport, _) = makeController()
    transport.full = 2
    let response = controller.handle(#"{"jsonrpc":"2.0","id":4,"method":"raw.send","params":{"words":[1,0,4]}}"#)
    #expect(object(response!)["result"] as? Bool == true)
    #expect(transport.sent == [[1, 0, 4]] && transport.attempts == 3)
}

@Test func sendFailsWhenTheDriverOutboxStaysFull() {
    let (controller, transport, _) = makeController()
    transport.full = .max
    let response = controller.handle(#"{"jsonrpc":"2.0","id":4,"method":"raw.send","params":{"words":[1,0,4]}}"#)
    #expect((object(response!)["error"] as? [String: Any])?["code"] as? Int == -32000)
    #expect(transport.sent.isEmpty && transport.attempts == 100)
}

@Test func describeListsKindsAndRanges() {
    let (controller, _, _) = makeController()
    let response = controller.handle(#"{"jsonrpc":"2.0","id":5,"method":"describe"}"#)
    let list = object(response!)["result"] as! [[String: Any]]
    let source = list.first { $0["path"] as? String == "clock/source" }!
    #expect(source["kind"] as? String == "choice")
    #expect((source["choices"] as? [String])?.first == "Internal")
}

@Test func unknownMethodIsAnError() {
    let (controller, _, _) = makeController()
    let response = controller.handle(#"{"jsonrpc":"2.0","id":6,"method":"nope"}"#)
    #expect((object(response!)["error"] as? [String: Any])?["code"] as? Int == -32601)
}

@Test func malformedRequestsAreErrors() {
    let (controller, _, _) = makeController()
    func code(_ text: String) -> Int? {
        (object(controller.handle(text)!)["error"] as? [String: Any])?["code"] as? Int
    }
    #expect(code("{") == -32700)
    #expect(code("[]") == -32600)
    #expect(code(#"{"jsonrpc":"2.0","id":7}"#) == -32600)
    #expect(code(#"{"id":7,"method":"get"}"#) == -32600)
}

@Test func setRejectsValuesOfTheWrongJsonType() {
    let (controller, transport, _) = makeController()
    for params in [#"{"outputs/speaker/mute":1}"#, #"{"outputs/speaker/attenuation":true}"#,
                   #"{"outputs/speaker/attenuation":2.0}"#] {
        let response = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":"# + params + "}")
        #expect((object(response!)["error"] as? [String: Any])?["code"] as? Int == -32602)
    }
    let raw = controller.handle(#"{"jsonrpc":"2.0","id":2,"method":"raw.send","params":{"words":[true,0,4]}}"#)
    #expect((object(raw!)["error"] as? [String: Any])?["code"] as? Int == -32602)
    #expect(transport.sent.isEmpty)
}

@Test func rawSendRejectsMoreThan29Words() {
    let (controller, transport, _) = makeController()
    let words = Array(repeating: "0", count: 30).joined(separator: ",")
    let raw = controller.handle(#"{"jsonrpc":"2.0","id":2,"method":"raw.send","params":{"words":["# + words + "]}}")
    #expect((object(raw!)["error"] as? [String: Any])?["code"] as? Int == -32602)
    #expect(transport.sent.isEmpty)
}

@Test func mixerFaderSendsATypeTwoBlockBigEndian() {
    let (controller, transport, _) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"mixers/2/channels/31/fader":700}}"#)
    #expect(transport.sent == [[1, 0, word(2, 0x32, 30, 1), word(2, 0x02, 0xBC, 0)]])
}

@Test func mixerMuteSendsAOneByteBlock() {
    let (controller, transport, _) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"mixers/1/channels/9/mute":true}}"#)
    #expect(transport.sent == [[1, 0, word(2, 0x35, 8, 0), word(1, 1, 0, 0)]])
}

@Test func mixerReportMatchesChannelAndMixer() {
    let (controller, _, broadcasts) = makeController()
    controller.receive(Report(type: 2, command: 0x32, p1: 30, p2: 1, data: [0x02, 0x58]))
    let changed = object(broadcasts.texts.last!)
    #expect((changed["params"] as? [String: Any])?["mixers/2/channels/31/fader"] as? Int == 600)
}

@Test func mixerPansCoverChannelsBeforeTheMaster() {
    #expect(parameters.filter { $0.path.hasSuffix("/pan") }.count == 4 * 45)
}

@Test func routingSendsTheSourceCodeForANamedDestination() {
    let (controller, transport, _) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"routing/line1-2":"Mixer 1"}}"#)
    _ = controller.handle(#"{"jsonrpc":"2.0","id":2,"method":"set","params":{"routing/optical15-16":"Optical 1-2"}}"#)
    #expect(transport.sent == [[1, 0, word(1, 0x15, 0, 0x60)], [1, 0, word(1, 0x15, 14, 0x10)]])
}

@Test func routingReportShowsTheSourceName() {
    let (controller, _, broadcasts) = makeController()
    controller.receive(Report(type: 1, command: 0x15, p1: 16, p2: 0, data: [0x64]))
    let changed = object(broadcasts.texts.last!)
    #expect((changed["params"] as? [String: Any])?["routing/headphone2"] as? String == "Mixer 3")
}

@Test func captureSendsTheSourceCodeForAComputerInputPair() {
    let (controller, transport, _) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"capture/1-2":"Mixer 2"}}"#)
    _ = controller.handle(#"{"jsonrpc":"2.0","id":2,"method":"set","params":{"capture/29-30":"Playback 3-4"}}"#)
    #expect(transport.sent == [[1, 0, word(1, 0x09, 0, 0x62)], [1, 0, word(1, 0x09, 14, 0x32)]])
}

// The unit always records Mixer 1 on pair 15 and FX Send on pair 16 (0x14058).
@Test func captureCoversOnlyTheRemappablePairs() {
    let pairs = parameters.filter { $0.command == 0x09 }.map(\.p1)
    #expect(pairs == Array(0...14))
}

@Test func captureReportShowsTheSourceName() {
    let (controller, _, broadcasts) = makeController()
    controller.receive(Report(type: 1, command: 0x09, p1: 6, p2: 0, data: [0x54]))
    let changed = object(broadcasts.texts.last!)
    #expect((changed["params"] as? [String: Any])?["capture/13-14"] as? String == "S/PDIF Coax")
}

@Test func unknownSourceCodeStaysANumber() {
    let (controller, _, broadcasts) = makeController()
    controller.receive(Report(type: 1, command: 0x15, p1: 0, p2: 0, data: [0x7F]))
    let changed = object(broadcasts.texts.last!)
    #expect((changed["params"] as? [String: Any])?["routing/line1-2"] as? Int == 0x7F)
}

@Test func pairLinkWritesBothChannelsWithThePairCode() {
    let (controller, transport, broadcasts) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"inputs/analog/3-4/link":true}}"#)
    #expect(transport.sent == [[1, 0, word(1, 0x07, 2, 2)], [1, 0, word(1, 0x07, 3, 2)]])
    controller.receive(Report(type: 1, command: 0x07, p1: 3, p2: 0, data: [2]))
    let changed = object(broadcasts.texts.last!)
    #expect((changed["params"] as? [String: Any])?["inputs/analog/3-4/link"] as? Bool == true)
}

@Test func soloIsSentAsABlockAndReportedAsTypeOne() {
    let (controller, transport, broadcasts) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"mixers/1/channels/1/solo":true}}"#)
    #expect(transport.sent == [[1, 0, word(2, 0x34, 0, 0), word(1, 1, 0, 0)]])
    controller.receive(Report(type: 1, command: 0x34, p1: 0, p2: 3, data: [1]))
    let changed = object(broadcasts.texts.last!)
    #expect((changed["params"] as? [String: Any])?["mixers/1/channels/1/solo"] as? Bool == true)
}

@Test func mixersSkipTheSecondFrontMicChannel() {
    #expect(!parameters.contains { $0.path.hasPrefix("mixers/1/channels/10/") })
    #expect(parameters.filter { $0.path.hasSuffix("/fader") }.count == 4 * 47)
}

@Test func gainsFollowTheVendorLimits() {
    func kind(_ path: String) -> Kind? { parameters.first { $0.path == path }?.kind }
    #expect(kind("inputs/analog/1/micGain") == .int(0...75))
    #expect(kind("inputs/analog/4/instrumentGain") == .int(0...65))
    #expect(kind("inputs/analog/5/instrumentGain") == nil)
    #expect(kind("inputs/frontMic/gain") == .int(0...40))
    #expect(parameters.first { $0.path == "inputs/guitar/2/gain" }?.p1 == 11)
}

@Test func preFaderIsABlockPerMixerReportedAsTypeOne() {
    let (controller, transport, broadcasts) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"mixers/2/preFader":false}}"#)
    #expect(transport.sent == [[1, 0, word(2, 0x90, 1, 0), word(1, 0, 0, 0)]])
    controller.receive(Report(type: 1, command: 0x90, p1: 3, p2: 2, data: [1]))
    let changed = object(broadcasts.texts.last!)
    #expect((changed["params"] as? [String: Any])?["mixers/4/preFader"] as? Bool == true)
}

@Test func insertsBelongToAnalog1And2AndMetersHaveHoldTimes() {
    #expect(parameters.first { $0.path == "inputs/analog/2/insert" }?.p1 == 1)
    #expect(parameters.first { $0.path == "meters/peakHold" }?.kind
        == .choice([Choice(name: "Off", code: 0), Choice(name: "2 Seconds", code: 1),
                    Choice(name: "Infinite", code: 2)]))
}

@Test func channelEnableWritesAllFourMixersAndReadsOneReport() {
    let (controller, transport, broadcasts) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"mixers/channels/33/enabled":true}}"#)
    #expect(transport.sent == (0..<4).map { [1, 0, word(2, 0x38, 32, $0), word(1, 1, 0, 0)] })
    controller.receive(Report(type: 1, command: 0x38, p1: 32, p2: 7, data: [1]))
    let changed = object(broadcasts.texts.last!)
    #expect((changed["params"] as? [String: Any])?["mixers/channels/33/enabled"] as? Bool == true)
}

@Test func stereoWritesThePairInAllFourMixers() {
    let (controller, transport, broadcasts) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"mixers/channels/31/stereo":true}}"#)
    #expect(transport.sent == (0..<4).map { [1, 0, word(2, 0x39, 30, $0), word(1, 1, 0, 0)] })
    controller.receive(Report(type: 1, command: 0x39, p1: 30, p2: 0, data: [1]))
    let changed = object(broadcasts.texts.last!)
    #expect((changed["params"] as? [String: Any])?["mixers/channels/31/stereo"] as? Bool == true)
}

@Test func theEchoOfASentBlockUpdatesAParameterThatReportsAsASet() {
    let (controller, _, broadcasts) = makeController()
    controller.receive(Report(type: 2, command: 0x39, p1: 30, p2: 2, data: [1]))
    let changed = object(broadcasts.texts.last!)
    #expect((changed["params"] as? [String: Any])?["mixers/channels/31/stereo"] as? Bool == true)
}

@Test func aStereoPairLinksTheControlsOfBothChannels() {
    let (controller, transport, _) = makeController()
    controller.receive(Report(type: 1, command: 0x39, p1: 30, p2: 0, data: [1]))
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"mixers/2/channels/32/mute":true}}"#)
    #expect(transport.sent == [[1, 0, word(2, 0x35, 31, 1), word(1, 1, 0, 0)],
                               [1, 0, word(2, 0x35, 30, 1), word(1, 1, 0, 0)]])
}

@Test func aMonoChannelMovesAlone() {
    let (controller, transport, _) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"mixers/2/channels/32/mute":true}}"#)
    #expect(transport.sent == [[1, 0, word(2, 0x35, 31, 1), word(1, 1, 0, 0)]])
}

@Test func stereoCopiesTheFirstChannelToItsPartner() {
    let (controller, transport, _) = makeController()
    controller.receive(Report(type: 2, command: 0x35, p1: 30, p2: 0, data: [1]))
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"mixers/channels/31/stereo":true}}"#)
    #expect(transport.sent.contains([1, 0, word(2, 0x35, 31, 0), word(1, 1, 0, 0)]))
}

@Test func setWritesStereoFlagsBeforeTheControlsThatTheyLink() {
    let (controller, transport, _) = makeController()
    transport.echo = { controller.receive($0) }
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":"#
        + #"{"mixers/1/channels/31/fader":700,"mixers/channels/31/stereo":true}}"#)
    #expect(Array(transport.sent.suffix(2)) == [[1, 0, word(2, 0x32, 30, 0), word(2, 0x02, 0xBC, 0)],
                                                [1, 0, word(2, 0x32, 31, 0), word(2, 0x02, 0xBC, 0)]])
}

@Test func setStopsWhenAStereoFlagIsNotReported() {
    let (controller, transport, _) = makeController()
    let response = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":"#
        + #"{"mixers/1/channels/31/fader":700,"mixers/channels/31/stereo":true}}"#)
    #expect((object(response!)["error"] as? [String: Any])?["code"] as? Int == -32000)
    #expect(transport.sent == (0..<4).map { [1, 0, word(2, 0x39, 30, $0), word(1, 1, 0, 0)] })
}

@Test func theFrontMicHasNoStereoPair() {
    let (controller, transport, _) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":1,"method":"set","params":{"mixers/channels/9/stereo":true}}"#)
    #expect(transport.sent.isEmpty)
}

@Test func speakerSourceWritesTheRouteOfEachSpeakerSet() {
    let (controller, transport, _) = makeController()
    let set = #"{"jsonrpc":"2.0","id":1,"method":"set","params":{"outputs/speakerSource":"Mixer 1"}}"#
    _ = controller.handle(set)
    #expect(transport.sent == [[1, 0, word(1, 0x15, 0, 0x60)]])
    controller.receive(Report(type: 1, command: 0x0F, p1: 0, p2: 0, data: [2]))
    _ = controller.handle(set)
    controller.receive(Report(type: 1, command: 0x0F, p1: 0, p2: 0, data: [3]))
    _ = controller.handle(set)
    let expected: [[UInt32]] = [0, 1, 0, 1, 2].map { [1, 0, word(1, 0x15, $0, 0x60)] }
    #expect(Array(transport.sent.dropFirst()) == expected)
}

@Test func speakerSourceFollowsTheSetARoute() {
    let (controller, _, broadcasts) = makeController()
    controller.receive(Report(type: 1, command: 0x15, p1: 0, p2: 0, data: [0x62]))
    let params = object(broadcasts.texts.last!)["params"] as? [String: Any]
    #expect(params?["outputs/speakerSource"] as? String == "Mixer 2")
    #expect(params?["routing/line1-2"] as? String == "Mixer 2")
}

@Test func savedPresetsAreListedAndBroadcastByName() {
    let (controller, _, broadcasts) = makeController()
    _ = call(controller, "presets.save", #"{"name":"Tracking"}"#)
    _ = call(controller, "presets.save", #"{"name":"Mix"}"#)
    #expect(call(controller, "presets.list", "null")["result"] as? [String] == ["Mix", "Tracking"])
    let presets = object(broadcasts.texts.last!)
    #expect(presets["method"] as? String == "presets")
    #expect((presets["params"] as? [String: Any])?["names"] as? [String] == ["Mix", "Tracking"])
}

@Test func loadMutesTheMonitorsWhileItSendsTheValuesThatDiffer() {
    let (controller, transport, _) = makeController()
    controller.receive(Report(type: 1, command: 0x11, p1: 2, p2: 0, data: [47]))
    for (output, mute) in [(0, 0), (1, 1), (2, 0)] as [(UInt8, UInt8)] {
        controller.receive(Report(type: 1, command: 0x12, p1: output, p2: 0, data: [mute]))
    }
    _ = call(controller, "presets.save", #"{"name":"A"}"#)
    controller.receive(Report(type: 1, command: 0x11, p1: 2, p2: 0, data: [10]))
    let result = call(controller, "presets.load", #"{"name":"A"}"#)["result"] as? [String: Any]
    #expect(result?["skipped"] as? [String] == [])
    let mutes = { (values: [UInt32]) in values.enumerated().map { [1, 0, word(1, 0x12, UInt32($0), $1)] } }
    #expect(transport.sent == mutes([1, 1, 1]) + [[1, 0, word(1, 0x11, 2, 47)]] + mutes([0, 1, 0]))
}

@Test func loadSkipsAndReportsPathsThatItCannotSet() throws {
    let presets = temporaryPresets()
    try FileManager.default.createDirectory(at: presets.deletingLastPathComponent(), withIntermediateDirectories: true)
    try Data(#"{"A":{"nope":1,"routing/line1-2":127,"outputs/speaker/mute":true}}"#.utf8).write(to: presets)
    let (controller, transport, _) = makeController(presets: presets)
    let result = call(controller, "presets.load", #"{"name":"A"}"#)["result"] as? [String: Any]
    #expect(result?["skipped"] as? [String] == ["nope", "routing/line1-2"])
    #expect(transport.sent == [[1, 0, 0x0102_1201]])
}

@Test func aPresetLeavesOutTheSampleRateAndTheSpeakerSourceAlias() throws {
    let presets = temporaryPresets()
    let (controller, _, _) = makeController(presets: presets)
    controller.receive(Report(type: 1, command: 0x29, p1: 0, p2: 0, data: [3]))
    controller.receive(Report(type: 1, command: 0x15, p1: 0, p2: 0, data: [0x60]))
    _ = call(controller, "presets.save", #"{"name":"A"}"#)
    let saved = try JSONSerialization.jsonObject(with: Data(contentsOf: presets)) as? [String: [String: String]]
    #expect(saved == ["A": ["routing/line1-2": "Mixer 1"]])
}

@Test func deletedAndUnknownPresetsCannotBeLoaded() {
    let (controller, _, _) = makeController()
    _ = call(controller, "presets.save", #"{"name":"A"}"#)
    _ = call(controller, "presets.delete", #"{"name":"A"}"#)
    #expect(call(controller, "presets.list", "null")["result"] as? [String] == [])
    let error = call(controller, "presets.load", #"{"name":"A"}"#)["error"] as? [String: Any]
    #expect(error?["code"] as? Int == -32602)
    let unnamed = call(controller, "presets.save", #"{"name":""}"#)["error"] as? [String: Any]
    #expect(unnamed?["code"] as? Int == -32602)
}

@Test func reportDecodesFromAsyncArguments() {
    let args: [UInt64] = [2 | 0x41 << 8 | 0 << 16 | 0 << 24 | 3 << 32, 0xccbbaa]
    let report = Report(arguments: args)
    #expect(report == Report(type: 2, command: 0x41, p1: 0, p2: 0, data: [0xaa, 0xbb, 0xcc]))
}
