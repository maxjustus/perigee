// The read-only bootloader session, R7 in docs/firmware/bootloader-options.md.
//
// Usage: ensemble-bootloader [--dry-run] [--json FILE]
//
// The session enters the PSoC bootloader, reads its identity and flash
// layout, fingerprints every row by checksum, probes the command set with
// deliberately wrong payload lengths, and exits back into the application.
// It sends no write-capable bootloader command. The one device state it
// changes is the four-byte EEPROM restart marker, which the application
// clears on the next boot.

import EnsembleIO
import EnsembleModel
import Foundation

struct SessionError: Error, CustomStringConvertible {
    let description: String
}

/// One bootloader exchange over the FPGA remote-I2C engine: write the
/// command packet, then read the reply the loader put in the window.
func exchange(_ device: Device, _ command: UInt8, data: [UInt8] = [],
              replyCount: Int) throws -> (status: UInt8, data: [UInt8]) {
    let packet = BootloaderPacket.encode(command: command, data: data)
    let wrote = try device.transfer(direction: 0, payload: packet)
    if wrote.busy {
        throw SessionError(description: "write stayed busy for command \(String(command, radix: 16))")
    }
    let read = try device.transfer(direction: 1, count: UInt16(replyCount))
    if read.busy {
        throw SessionError(description: "read stayed busy for command \(String(command, radix: 16))")
    }
    return try BootloaderPacket.parse(read.data)
}

func enter(_ device: Device, attempts: Int = 10) throws -> (status: UInt8, data: [UInt8]) {
    for attempt in 1...attempts {
        do {
            return try exchange(device, BootloaderPacket.enter, replyCount: 15)
        } catch {
            if attempt == attempts {
                throw error
            }
            Thread.sleep(forTimeInterval: 1.0)
        }
    }
    fatalError("unreachable")
}

func be16(_ data: [UInt8], _ index: Int) -> Int {
    Int(data[index]) | Int(data[index + 1]) << 8
}

func run() throws {
    let arguments = CommandLine.arguments.dropFirst()
    let dryRun = arguments.contains("--dry-run")
    let outIndex = arguments.firstIndex(of: "--json")
    let jsonPath = outIndex.map { arguments[arguments.index(after: $0)] }

    var report: [String: Any] = ["timestamp": ISO8601DateFormatter().string(from: Date())]

    if dryRun {
        var plan: [[String: Any]] = []
        plan.append(["step": "enter", "packet": BootloaderPacket.encode(command: BootloaderPacket.enter)
            .map { String(format: "%02x", $0) }.joined(separator: " ")])
        for array in [0, 1, 2, 3, 0x40] {
            plan.append(["step": "report-size", "array": array,
                         "packet": BootloaderPacket.encode(command: BootloaderPacket.reportSize,
                                                           data: [UInt8(array)])
                            .map { String(format: "%02x", $0) }.joined(separator: " ")])
        }
        for command in [UInt8(0x31), 0x33, 0x34, 0x35, 0x36, 0x3c, 0x45] {
            plan.append(["step": "probe", "command": String(command, radix: 16),
                         "packet": BootloaderPacket.encode(command: command, data: [0, 0])
                            .map { String(format: "%02x", $0) }.joined(separator: " ")])
        }
        plan.append(["step": "exit",
                     "packet": BootloaderPacket.encode(command: BootloaderPacket.exit)
                        .map { String(format: "%02x", $0) }.joined(separator: " ")])
        report["plan"] = plan
        print(String(data: try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]),
                     encoding: .utf8)!)
        return
    }

    let device = try Device(queue: DispatchQueue(label: "ensemble-bootloader"))
    defer { try? device.enableSession(false) }

    // Step 1: request the bootloader. This writes the EEPROM restart marker
    // and resets the PSoC. The loader then waits for commands forever.
    try device.enableSession(true)
    guard try device.send([1, 0, 0x00006001]) else {
        throw SessionError(description: "the mailbox queue was full")
    }
    Thread.sleep(forTimeInterval: 2.5)

    // Step 2: enter and read the loader identity.
    let entered = try enter(device)
    report["enter"] = ["status": entered.status, "siliconId": entered.data.prefix(4)
        .map { String(format: "%02x", $0) }.joined(),
        "data": entered.data.map { Int($0) }]
    if entered.status != 0 {
        throw SessionError(description: "enter refused, status \(entered.status). A security key may be active.")
    }

    // Step 3: flash layout per array, including the EEPROM array 0x40.
    var layouts: [String: Any] = [:]
    var rows: [Int: [Int]] = [:]
    for array in [0, 1, 2, 3, 0x40] {
        let layout = try exchange(device, BootloaderPacket.reportSize, data: [UInt8(array)], replyCount: 11)
        let start = be16(layout.data, 0)
        let end = be16(layout.data, 2)
        layouts["\(array)"] = ["status": layout.status, "startRow": start, "endRow": end]
        rows[array] = Array(start..<max(start, end))
    }
    report["layouts"] = layouts
    report["note"] = "endRow is exclusive for a full array, inclusive for the last partial array"

    // Step 4: fingerprint every readable row by its computed checksum.
    var checksums: [String: [Int]] = [:]
    for (array, rowList) in rows.sorted(by: { $0.key < $1.key }) {
        var values: [Int] = []
        for row in rowList {
            let reply = try exchange(device, BootloaderPacket.getRowChecksum,
                                      data: [UInt8(array), UInt8(row & 0xff), UInt8(row >> 8)],
                                      replyCount: 8)
            values.append(reply.data.first.map(Int.init) ?? 255)
        }
        checksums["\(array)"] = values
        FileHandle.standardError.write("array \(array): \(values.count) rows\n".data(using: .utf8)!)
    }
    report["rowChecksums"] = checksums

    // Step 5: probe the command set. Every probe carries a two-byte
    // payload, which no handler guard accepts: the guards expect zero,
    // one, or three bytes. A disabled command answers 0x05, an enabled
    // one answers 0x03. No probe can act.
    var probes: [String: Any] = [:]
    for command in [UInt8(0x31), 0x33, 0x34, 0x35, 0x36, 0x3c, 0x45] {
        let reply = try exchange(device, command, data: [0, 0], replyCount: 7)
        probes[String(command, radix: 16)] = ["status": reply.status, "data": reply.data.map { Int($0) }]
    }
    report["probes"] = probes

    // Step 6: exit back into the application.
    let exitReply = try exchange(device, BootloaderPacket.exit, replyCount: 7)
    report["exit"] = ["status": exitReply.status]

    let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
    if let jsonPath {
        try data.write(to: URL(fileURLWithPath: jsonPath))
    }
    print(String(data: data, encoding: .utf8)!)
}


do {
    try run()
} catch {
    FileHandle.standardError.write("error: \(error)\n".data(using: .utf8)!)
    exit(1)
}