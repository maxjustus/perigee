// Talks to EnsembleDriver through its user client.
// Usage: ensemblectl getall | ensemblectl set <command> <p1> <value>
import EnsembleIO
import EnsembleModel
import Foundation

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data("ensemblectl: \(message)\n".utf8))
    exit(1)
}

func number(_ text: String) -> UInt8? {
    text.hasPrefix("0x") ? UInt8(text.dropFirst(2), radix: 16) : UInt8(text)
}

func describe(_ report: Report) -> String {
    String(format: "type %d cmd %#04x p1 %d p2 %d len %d data ", report.type, report.command, report.p1, report.p2,
           report.data.count) + report.data.map { String(format: "%02x", $0) }.joined()
}

let arguments = Array(CommandLine.arguments.dropFirst())
let words: [UInt32]
switch arguments.first {
case "getall" where arguments.count == 1:
    words = getAll
case "set" where arguments.count == 4:
    let numbers = arguments.dropFirst().compactMap(number)
    guard numbers.count == 3 else { fail("set takes <command> <p1> <value>, each 0 to 255") }
    words = setMessage(command: numbers[0], p1: numbers[1], value: numbers[2])
default:
    fail("usage: ensemblectl getall | ensemblectl set <command> <p1> <value>")
}
let device: Device
do {
    device = try Device(queue: .main)
    try device.subscribe { print(describe($0)) }
    guard try device.send(words) else { fail("driver outbox full") }
} catch {
    fail("\(error)")
}
DispatchQueue.main.asyncAfter(deadline: .now() + 2) { exit(0) }
dispatchMain()
