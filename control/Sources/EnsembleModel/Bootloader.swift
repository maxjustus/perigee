// A read-only session with the PSoC bootloader through the FPGA remote-I2C
// engine. The timing follows the vendor updater, docs/firmware/updater.md.

import Foundation

/// The driver calls that a session needs. `Device` conforms.
public protocol BootloaderLink: Transport {
    func bootloaderStatus() throws -> Int
    func enableSession(_ on: Bool) throws
    func writeI2c(_ packet: [UInt8]) throws
    func readI2c(count: Int) throws -> [UInt8]
}

public struct BootloaderSession {
    public static let application = 1
    public static let bootloader = 2

    // The vendor updater sleeps 28 ms after each write before it reads, and
    // polls the status up to 1000 times at 10 ms.
    static let replyDelay = 0.028
    static let statusPolls = 1000
    static let statusDelay = 0.01
    static let enterAttempts = 20
    static let enterDelay = 0.1

    // CY8C5268: four flash arrays of 256 rows, and 128 EEPROM rows.
    static let flashArrays = 4
    static let rowsPerArray = 256
    static let eepromArray: UInt8 = 0x40
    static let eepromRows = 128

    let link: BootloaderLink
    let pause: (Double) -> Void

    public init(link: BootloaderLink, pause: @escaping (Double) -> Void = Thread.sleep(forTimeInterval:)) {
        self.link = link
        self.pause = pause
    }

    /// Enters the bootloader, runs `body` with the Enter reply, and sends
    /// Exit on every path after the bootloader reports.
    public func run<T>(_ body: (BootloaderSession, [UInt8]) throws -> T) throws -> T {
        let status = try link.bootloaderStatus()
        guard status == Self.application else {
            throw BootloaderError.notApplication(status)
        }
        try link.enableSession(true)
        defer { try? link.enableSession(false) }
        guard try link.send(setMessage(command: 0x60, p1: 0, value: 0)) else {
            throw BootloaderError.outboxFull
        }
        try wait(for: Self.bootloader)
        let result = Result { try body(self, try enter()) }
        do {
            try leave()
        } catch {
            throw BootloaderError.exitFailed(exit: "\(error)", earlier: result.failure.map { "\($0)" })
        }
        return try result.get()
    }

    /// Exits a bootloader that an earlier session left running.
    public func recover() throws {
        let status = try link.bootloaderStatus()
        guard status == Self.bootloader else {
            throw BootloaderError.notBootloader(status)
        }
        try link.enableSession(true)
        defer { try? link.enableSession(false) }
        try leave()
    }

    /// Reads the size of each flash array and the checksum of every flash
    /// and EEPROM row, twice, in opposite orders. A reply read before the
    /// loader replaces it repeats the previous reply. The second pass
    /// exposes that.
    public func scan(identity: [UInt8]) throws -> BootloaderScan {
        let first = try pass(identity: identity, reversed: false)
        let second = try pass(identity: identity, reversed: true)
        let differences = zip(first.rows, second.rows).filter { $0 != $1 }.count
        guard first == second else {
            throw BootloaderError.unstable(rows: differences)
        }
        return first
    }

    private func pass(identity: [UInt8], reversed: Bool) throws -> BootloaderScan {
        var sizes = [[Int]](repeating: [], count: Self.flashArrays)
        let arrays = Array(0..<Self.flashArrays)
        for array in reversed ? arrays.reversed() : arrays {
            let size = try exchange(BootloaderPacket.reportSize, data: [UInt8(array)], replyLength: 4)
            sizes[array] = [Int(size[0]) | Int(size[1]) << 8, Int(size[2]) | Int(size[3]) << 8]
        }
        let targets = (0..<Self.flashArrays).flatMap { array in
            (0..<Self.rowsPerArray).map { (UInt8(array), $0) }
        } + (0..<Self.eepromRows).map { (Self.eepromArray, $0) }
        var sums = [UInt8](repeating: 0, count: targets.count)
        for index in reversed ? Array(targets.indices.reversed()) : Array(targets.indices) {
            let (array, row) = targets[index]
            sums[index] = try exchange(BootloaderPacket.rowChecksum,
                                       data: [array, UInt8(row & 0xff), UInt8(row >> 8)], replyLength: 1)[0]
        }
        let flash = stride(from: 0, to: Self.flashArrays * Self.rowsPerArray, by: Self.rowsPerArray).map {
            Array(sums[$0..<($0 + Self.rowsPerArray)])
        }
        return BootloaderScan(identity: identity, sizes: sizes, flash: flash,
                              eeprom: Array(sums[(Self.flashArrays * Self.rowsPerArray)...]))
    }

    private func enter() throws -> [UInt8] {
        var attempt = 1
        while true {
            do {
                return try exchange(BootloaderPacket.enter, replyLength: 8)
            } catch BootloaderError.status(let command, let status) {
                throw BootloaderError.status(command: command, status: status)
            } catch {
                if attempt == Self.enterAttempts {
                    throw error
                }
                attempt += 1
                pause(Self.enterDelay)
            }
        }
    }

    // Exit has no reply. The loader resets into the application.
    private func leave() throws {
        try link.writeI2c(BootloaderPacket.encode(command: BootloaderPacket.exit, data: [0]))
        try wait(for: Self.application)
    }

    private func wait(for expected: Int) throws {
        var status = try link.bootloaderStatus()
        for _ in 1..<Self.statusPolls where status != expected {
            pause(Self.statusDelay)
            status = try link.bootloaderStatus()
        }
        guard status == expected else {
            throw BootloaderError.timeout(expected: expected, last: status)
        }
    }

    private func exchange(_ command: UInt8, data: [UInt8] = [], replyLength: Int) throws -> [UInt8] {
        try link.writeI2c(BootloaderPacket.encode(command: command, data: data))
        pause(Self.replyDelay)
        let bytes = try link.readI2c(count: BootloaderPacket.overhead + replyLength)
        guard let reply = try? BootloaderPacket.parse(bytes) else {
            throw BootloaderError.badReply(command: command, bytes: bytes)
        }
        guard reply.status == 0 else {
            throw BootloaderError.status(command: command, status: reply.status)
        }
        guard reply.data.count == replyLength else {
            throw BootloaderError.shortReply(command: command, length: reply.data.count)
        }
        return reply.data
    }
}

/// Row checksums are the loader's 8-bit row sums, negated. `sizes` holds the
/// first and last row that each flash array reports for an application.
public struct BootloaderScan: Codable, Equatable {
    public let identity: [UInt8]
    public let sizes: [[Int]]
    public let flash: [[UInt8]]
    public let eeprom: [UInt8]

    var rows: [UInt8] {
        flash.flatMap { $0 } + eeprom
    }
}

public enum BootloaderError: Error, Equatable, CustomStringConvertible {
    case notApplication(Int)
    case notBootloader(Int)
    case outboxFull
    case timeout(expected: Int, last: Int)
    case status(command: UInt8, status: UInt8)
    case badReply(command: UInt8, bytes: [UInt8])
    case shortReply(command: UInt8, length: Int)
    case unstable(rows: Int)
    case exitFailed(exit: String, earlier: String?)

    public var description: String {
        switch self {
        case .notApplication(let status):
            return "PSoC status \(status), not 1 (application). If it is 2, run `ensemble-bootloader exit`."
        case .notBootloader(let status):
            return "PSoC status \(status), not 2 (bootloader)"
        case .outboxFull:
            return "the driver outbox is full"
        case .timeout(let expected, let last):
            return "PSoC status stayed \(last), not \(expected)"
        case .status(let command, let status):
            return String(format: "command 0x%02x returned status 0x%02x", command, status)
        case .badReply(let command, let bytes):
            return String(format: "command 0x%02x got no valid reply: ", command) +
                bytes.map { String(format: "%02x", $0) }.joined(separator: " ")
        case .shortReply(let command, let length):
            return String(format: "command 0x%02x returned %d data bytes", command, length)
        case .unstable(let rows):
            return "\(rows) row checksums differ between the two passes"
        case .exitFailed(let exit, let earlier):
            return "Exit failed: \(exit). Earlier error: \(earlier ?? "none"). " +
                "If the status reads 2, run `ensemble-bootloader exit`. If not, power-cycle the unit."
        }
    }
}

extension Result {
    var failure: Failure? {
        if case .failure(let error) = self {
            return error
        }
        return nil
    }
}

// The Cypress bootloader wire protocol, from cybtldr_command.c: every
// packet carries start and stop markers, a two-byte data length, and a
// two-byte additive checksum over the bytes before the checksum itself.

public enum BootloaderPacketError: Error, Equatable {
    case badMarker
    case badLength
    case badChecksum
}

public enum BootloaderPacket {
    public static let start: UInt8 = 0x01
    public static let stop: UInt8 = 0x17

    // Every packet holds four header bytes and three trailer bytes.
    public static let overhead = 7

    public static let enter: UInt8 = 0x38
    public static let reportSize: UInt8 = 0x32
    public static let rowChecksum: UInt8 = 0x3a
    public static let exit: UInt8 = 0x3b

    public static func checksum(_ bytes: ArraySlice<UInt8>) -> UInt16 {
        var sum: UInt16 = 0
        for byte in bytes {
            sum = sum &+ UInt16(byte)
        }
        return ~sum &+ 1
    }

    /// One command packet. `data` is the command payload, never a record.
    public static func encode(command: UInt8, data: [UInt8] = []) -> [UInt8] {
        var packet: [UInt8] = [start, command, UInt8(data.count), UInt8(data.count >> 8)]
        packet += data
        let sum = checksum(packet[...])
        packet += [UInt8(sum & 0xff), UInt8(sum >> 8), stop]
        return packet
    }

    /// One reply packet: `[start][status][length][data][checksum][stop]`.
    /// A read can return more bytes than the reply. The header length
    /// decides where the reply ends. Returns the status and the data.
    public static func parse(_ reply: [UInt8]) throws -> (status: UInt8, data: [UInt8]) {
        guard reply.count >= overhead, reply[0] == start else {
            throw BootloaderPacketError.badMarker
        }
        let length = Int(reply[2]) | Int(reply[3]) << 8
        guard reply.count >= overhead + length else {
            throw BootloaderPacketError.badLength
        }
        guard reply[overhead + length - 1] == stop else {
            throw BootloaderPacketError.badMarker
        }
        let sum = checksum(reply[..<(4 + length)])
        guard reply[4 + length] == UInt8(sum & 0xff), reply[5 + length] == UInt8(sum >> 8) else {
            throw BootloaderPacketError.badChecksum
        }
        return (reply[1], Array(reply[4..<(4 + length)]))
    }
}
