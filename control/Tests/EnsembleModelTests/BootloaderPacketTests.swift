import XCTest
@testable import EnsembleModel

final class BootloaderPacketTests: XCTestCase {
    func test_encode_matches_the_reference_checksum() {
        // Enter, no data. The reference tool computes this packet.
        let packet = BootloaderPacket.encode(command: BootloaderPacket.enter)
        XCTAssertEqual(packet, [0x01, 0x38, 0x00, 0x00, 0xc7, 0xff, 0x17])
    }

    func test_checksum_is_the_two_complement_of_the_sum() {
        XCTAssertEqual(BootloaderPacket.checksum([0x01, 0x38, 0x00, 0x00]), 0xffc7)
        XCTAssertEqual(BootloaderPacket.checksum([UInt8]()[...]), 0)
    }

    func test_encode_carries_data_and_length() {
        let packet = BootloaderPacket.encode(command: 0x3a, data: [0x00, 0x05, 0x00])
        XCTAssertEqual(packet[2], 3)
        XCTAssertEqual(packet[3], 0)
        XCTAssertEqual(Array(packet[4...6]), [0x00, 0x05, 0x00])
        XCTAssertEqual(packet.last, BootloaderPacket.stop)
    }

    func test_parse_accepts_a_well_formed_reply() throws {
        // 15-byte Enter reply: status 0, eight data bytes.
        var reply: [UInt8] = [0x01, 0x00, 0x08, 0x00, 0x69, 0xf0, 0x12, 0x2e,
                              0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x17]
        let sum = BootloaderPacket.checksum(reply[0..<12])
        reply[12] = UInt8(sum & 0xff)
        reply[13] = UInt8(sum >> 8)
        let parsed = try BootloaderPacket.parse(reply)
        XCTAssertEqual(parsed.status, 0)
        XCTAssertEqual(parsed.data, [0x69, 0xf0, 0x12, 0x2e, 0x00, 0x00, 0x01, 0x00])
    }

    func test_parse_rejects_broken_replies() {
        var reply: [UInt8] = [0x01, 0x00, 0x01, 0x00, 0x2a, 0x00, 0x00, 0x17]
        let sum = BootloaderPacket.checksum(reply[0..<5])
        reply[5] = UInt8(sum & 0xff) ^ 1
        reply[6] = UInt8(sum >> 8)
        XCTAssertThrowsError(try BootloaderPacket.parse(reply)) { error in
            XCTAssertEqual(error as? BootloaderPacketError, .badChecksum)
        }
        XCTAssertThrowsError(try BootloaderPacket.parse([0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x17])) { error in
            XCTAssertEqual(error as? BootloaderPacketError, .badMarker)
        }
        XCTAssertThrowsError(try BootloaderPacket.parse([0x01, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x17])) { error in
            XCTAssertEqual(error as? BootloaderPacketError, .badLength)
        }
    }

    func test_probes_carry_wrong_lengths() {
        // A two-byte payload cannot satisfy any handler guard in the
        // reference loader: the guards expect zero, one, or three bytes.
        for command in [UInt8(0x31), 0x33, 0x34, 0x35, 0x36, 0x3c, 0x45] {
            let packet = BootloaderPacket.encode(command: command, data: [0, 0])
            XCTAssertEqual(packet[2], 2)
        }
    }
}