import Foundation
import Testing

@testable import EnsembleModel

final class FakeTransport: Transport, @unchecked Sendable {
    var sent: [[UInt32]] = []
    func send(_ words: [UInt32]) throws { sent.append(words) }
}

final class Broadcasts: @unchecked Sendable {
    var texts: [String] = []
}

func object(_ text: String) -> [String: Any] {
    try! JSONSerialization.jsonObject(with: Data(text.utf8)) as! [String: Any]
}

func makeController() -> (Controller, FakeTransport, Broadcasts) {
    let transport = FakeTransport()
    let broadcasts = Broadcasts()
    let controller = Controller(transport: transport) { broadcasts.texts.append($0) }
    return (controller, transport, broadcasts)
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
    controller.receive(Report(type: 2, command: 0x32, p1: 5, p2: 1, data: [2, 0x58]))
    let report = object(broadcasts.texts.last!)
    #expect(report["method"] as? String == "report")
    #expect((report["params"] as? [String: Any])?["data"] as? [Int] == [2, 0x58])
}

@Test func rawSendPassesWordsThrough() {
    let (controller, transport, _) = makeController()
    _ = controller.handle(#"{"jsonrpc":"2.0","id":4,"method":"raw.send","params":{"words":[1,0,4]}}"#)
    #expect(transport.sent == [[1, 0, 4]])
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

@Test func reportDecodesFromAsyncArguments() {
    let args: [UInt64] = [2 | 0x41 << 8 | 0 << 16 | 0 << 24 | 3 << 32, 0xccbbaa]
    let report = Report(arguments: args)
    #expect(report == Report(type: 2, command: 0x41, p1: 0, p2: 0, data: [0xaa, 0xbb, 0xcc]))
}
