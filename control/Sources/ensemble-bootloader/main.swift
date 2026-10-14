// The read-only bootloader session in docs/firmware/bootloader-options.md.
//
// Usage: ensemble-bootloader status | check | scan [--json FILE] | exit
//
// status prints the PSoC state: 1 for the application, 2 for the
// bootloader. check enters the bootloader, prints the Enter reply, and
// exits. scan also reads the flash layout and every flash and EEPROM row
// checksum, twice. exit returns a unit that an earlier session left in the
// bootloader to its application.

import EnsembleIO
import EnsembleModel
import Foundation

struct UsageError: Error, CustomStringConvertible {
    let description = "usage: ensemble-bootloader status | check | scan [--json FILE] | exit"
}

func run() throws {
    let arguments = Array(CommandLine.arguments.dropFirst())
    let device = try Device(queue: DispatchQueue(label: "ensemble-bootloader"))
    let session = BootloaderSession(link: device)
    let json = arguments.count == 3 && arguments[1] == "--json" ? arguments[2] : nil
    switch arguments.first {
    case "status" where arguments.count == 1:
        print(try device.bootloaderStatus())
    case "check" where arguments.count == 1:
        let identity = try session.run { _, identity in identity }
        print(identity.map { String(format: "%02x", $0) }.joined(separator: " "))
    case "scan" where arguments.count == 1 || json != nil:
        FileHandle.standardError.write(Data("scan: 2 passes of 1156 reads, about 2 minutes\n".utf8))
        try session.run { session, identity in
            let encoder = JSONEncoder()
            encoder.outputFormatting = .sortedKeys
            let data = try encoder.encode(try session.scan(identity: identity))
            if let json {
                try data.write(to: URL(fileURLWithPath: json))
            } else {
                print(String(decoding: data, as: UTF8.self))
            }
        }
    case "exit" where arguments.count == 1:
        try session.recover()
    default:
        throw UsageError()
    }
}

do {
    try run()
} catch {
    FileHandle.standardError.write(Data("error: \(error)\n".utf8))
    exit(1)
}
