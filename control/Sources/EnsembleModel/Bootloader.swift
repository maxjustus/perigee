// The Cypress bootloader wire protocol, from cybtldr_command.c: every
// packet carries start and stop markers, a two-byte data length, and a
// two-byte additive checksum over the bytes before the checksum itself.

import Foundation

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
    public static let getRowChecksum: UInt8 = 0x3a
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
