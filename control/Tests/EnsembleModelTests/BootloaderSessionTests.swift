import Testing

@testable import EnsembleModel

// A PSoC with the reference Cypress loader behind the dext gates.
final class FakeLoader: BootloaderLink, @unchecked Sendable {
    var status = BootloaderSession.application
    var session = false
    var commands: [UInt8] = []
    var packets: [[UInt8]] = []
    var statusReads = 0
    var entryReads = 0
    var failRow: Int?
    var enterStatus: UInt8 = 0
    var silent = false
    var staleOnce: (array: UInt8, row: Int)?
    var exitWorks = true
    private var reply: [UInt8] = []

    func bootloaderStatus() throws -> Int {
        statusReads += 1
        if status == 0 && statusReads > entryReads {
            status = BootloaderSession.bootloader
        }
        return status
    }

    func enableSession(_ on: Bool) throws {
        session = on
    }

    func send(_ words: [UInt32]) throws -> Bool {
        if session && words == setMessage(command: 0x60, p1: 0, value: 0) {
            status = 0
            statusReads = 0
        }
        return true
    }

    func writeI2c(_ packet: [UInt8]) throws {
        guard session, status == BootloaderSession.bootloader else {
            throw FakeError.notReady
        }
        let (command, data) = try BootloaderPacket.parse(packet)
        commands.append(command)
        packets.append(packet)
        switch command {
        case BootloaderPacket.enter where silent:
            break
        case BootloaderPacket.enter:
            reply = BootloaderPacket.encode(command: enterStatus,
                                            data: enterStatus == 0 ? [0x69, 0xf0, 0x12, 0x2e, 0, 1, 0x1e, 1] : [])
        case BootloaderPacket.reportSize:
            reply = BootloaderPacket.encode(command: 0, data: data[0] == 0 ? [0, 1, 0xff, 0] : [0, 0, 0xff, 0])
        case BootloaderPacket.rowChecksum:
            let row = Int(data[1]) | Int(data[2]) << 8
            if let stale = staleOnce, stale.array == data[0], stale.row == row {
                staleOnce = nil
            } else if row == failRow {
                reply = BootloaderPacket.encode(command: 0x0a)
            } else {
                reply = BootloaderPacket.encode(command: 0, data: [checksum(data[0], row)])
            }
        case BootloaderPacket.exit:
            if exitWorks {
                status = BootloaderSession.application
            }
        default:
            throw FakeError.notReady
        }
    }

    func readI2c(count: Int) throws -> [UInt8] {
        Array((reply + [UInt8](repeating: 0xff, count: count)).prefix(count))
    }
}

enum FakeError: Error {
    case notReady
    case body
}

func checksum(_ array: UInt8, _ row: Int) -> UInt8 {
    UInt8(truncatingIfNeeded: Int(array) * 7 + row)
}

func session(_ loader: FakeLoader) -> BootloaderSession {
    BootloaderSession(link: loader, pause: { _ in })
}

@Test func runEntersPassesTheIdentityAndExits() throws {
    let loader = FakeLoader()
    loader.entryReads = 3
    let identity = try session(loader).run { _, identity in identity }
    #expect(identity == [0x69, 0xf0, 0x12, 0x2e, 0, 1, 0x1e, 1])
    #expect(loader.commands == [BootloaderPacket.enter, BootloaderPacket.exit])
    #expect(loader.packets.last == BootloaderPacket.encode(command: BootloaderPacket.exit, data: [0]))
    #expect(loader.status == BootloaderSession.application)
    #expect(!loader.session)
}

@Test func runRefusesAUnitOutsideTheApplication() {
    let loader = FakeLoader()
    loader.status = BootloaderSession.bootloader
    #expect(throws: BootloaderError.notApplication(BootloaderSession.bootloader)) {
        try session(loader).run { _, _ in }
    }
    #expect(loader.commands.isEmpty)
}

@Test func runStopsWhenTheBootloaderNeverReports() {
    let loader = FakeLoader()
    loader.entryReads = Int.max
    #expect(throws: BootloaderError.timeout(expected: BootloaderSession.bootloader, last: 0)) {
        try session(loader).run { _, _ in }
    }
    #expect(loader.commands.isEmpty)
    #expect(!loader.session)
}

@Test func runExitsAfterAFailure() {
    let loader = FakeLoader()
    #expect(throws: FakeError.body) {
        try session(loader).run { _, _ in throw FakeError.body }
    }
    #expect(loader.commands.last == BootloaderPacket.exit)
    #expect(loader.status == BootloaderSession.application)
}

@Test func anEnterErrorIsNotRetried() {
    let loader = FakeLoader()
    loader.enterStatus = 0x04
    #expect(throws: BootloaderError.status(command: BootloaderPacket.enter, status: 0x04)) {
        try session(loader).run { _, _ in }
    }
    #expect(loader.commands == [BootloaderPacket.enter, BootloaderPacket.exit])
}

@Test func aBrokenReplyNamesTheCommandAndItsBytes() {
    let loader = FakeLoader()
    loader.silent = true
    #expect(throws: BootloaderError.badReply(command: BootloaderPacket.enter, bytes: [UInt8](repeating: 0xff, count: 15))) {
        try session(loader).run { _, _ in }
    }
    #expect(loader.commands.filter { $0 == BootloaderPacket.enter }.count == 20)
    #expect(loader.commands.last == BootloaderPacket.exit)
}

@Test func aFailedExitNamesTheEarlierError() {
    let loader = FakeLoader()
    loader.exitWorks = false
    let exit = BootloaderError.timeout(expected: BootloaderSession.application, last: BootloaderSession.bootloader)
    #expect(throws: BootloaderError.exitFailed(exit: exit.description, earlier: "body")) {
        try session(loader).run { _, _ in throw FakeError.body }
    }
}

@Test func scanReadsEveryRowInTwoOppositePasses() throws {
    let loader = FakeLoader()
    let scan = try session(loader).run { session, identity in try session.scan(identity: identity) }
    let rows = loader.packets.filter { $0[1] == BootloaderPacket.rowChecksum }
    #expect(rows.count == 2 * (4 * 256 + 128))
    #expect(Array(rows[0][4...6]) == [0, 0, 0])
    #expect(Array(rows[rows.count / 2][4...6]) == [0x40, 127, 0])
    #expect(scan.sizes == [[256, 255], [0, 255], [0, 255], [0, 255]])
    #expect(scan.flash.map(\.count) == [256, 256, 256, 256])
    #expect(scan.flash[3][255] == checksum(3, 255))
    #expect(scan.eeprom.count == 128)
    #expect(scan.eeprom[127] == checksum(0x40, 127))
}

@Test func scanRejectsAStaleReply() {
    let loader = FakeLoader()
    loader.staleOnce = (array: 2, row: 9)
    #expect(throws: BootloaderError.unstable(rows: 1)) {
        try session(loader).run { session, identity in try session.scan(identity: identity) }
    }
    #expect(loader.commands.last == BootloaderPacket.exit)
}

@Test func aRowErrorStopsTheScan() {
    let loader = FakeLoader()
    loader.failRow = 17
    #expect(throws: BootloaderError.status(command: BootloaderPacket.rowChecksum, status: 0x0a)) {
        try session(loader).run { session, identity in try session.scan(identity: identity) }
    }
    #expect(loader.commands.last == BootloaderPacket.exit)
}

@Test func recoverExitsAUnitInTheBootloader() throws {
    let loader = FakeLoader()
    loader.status = BootloaderSession.bootloader
    try session(loader).recover()
    #expect(loader.commands == [BootloaderPacket.exit])
    #expect(loader.status == BootloaderSession.application)
    #expect(!loader.session)
}

@Test func recoverRefusesAUnitInTheApplication() {
    let loader = FakeLoader()
    #expect(throws: BootloaderError.notBootloader(BootloaderSession.application)) {
        try session(loader).recover()
    }
}
