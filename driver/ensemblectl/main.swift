// Talks to EnsembleDriver through its user client.
// Usage: ensemblectl getall | ensemblectl set <command> <p1> <value>
import Foundation
import IOKit

let selectorSend: UInt32 = 0
let selectorSubscribe: UInt32 = 1
let clientType: UInt32 = 1

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data("ensemblectl: \(message)\n".utf8))
    exit(1)
}

func open() -> io_connect_t {
    let service = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceNameMatching("EnsembleDriver"))
    guard service != 0 else { fail("no EnsembleDriver in the IORegistry") }
    defer { IOObjectRelease(service) }
    var connect: io_connect_t = 0
    let kr = IOServiceOpen(service, mach_task_self_, clientType, &connect)
    guard kr == KERN_SUCCESS else { fail(String(format: "IOServiceOpen: %#x", kr)) }
    return connect
}

func send(_ connect: io_connect_t, _ words: [UInt32]) {
    let kr = words.withUnsafeBytes {
        IOConnectCallStructMethod(connect, selectorSend, $0.baseAddress, $0.count, nil, nil)
    }
    guard kr == KERN_SUCCESS else { fail(String(format: "send: %#x", kr)) }
}

func subscribe(_ connect: io_connect_t) {
    guard let port = IONotificationPortCreate(kIOMainPortDefault) else { fail("IONotificationPortCreate") }
    IONotificationPortSetDispatchQueue(port, .main)
    let machPort = IONotificationPortGetMachPort(port)
    var limits = mach_port_limits_t(mpl_qlimit: mach_port_msgcount_t(MACH_PORT_QLIMIT_MAX))
    withUnsafeMutablePointer(to: &limits) {
        $0.withMemoryRebound(to: integer_t.self, capacity: 1) {
            _ = mach_port_set_attributes(mach_task_self_, machPort, MACH_PORT_LIMITS_INFO, $0,
                                         mach_msg_type_number_t(MemoryLayout<mach_port_limits_t>.size / MemoryLayout<integer_t>.size))
        }
    }
    let callback: IOAsyncCallback = { _, result, args, count in
        guard result == kIOReturnSuccess, let args, count >= 1 else { return }
        let word = { (i: Int) in UInt64(UInt(bitPattern: args[i])) }
        let header = word(0)
        let length = Int((header >> 32) & 0xFF)
        let data = (0..<length).map { i in String(format: "%02x", (word(1 + i / 8) >> (8 * UInt64(i % 8))) & 0xFF) }
        print(String(format: "type %d cmd %#04x p1 %d p2 %d len %d data ",
                     header & 0xFF, (header >> 8) & 0xFF, (header >> 16) & 0xFF, (header >> 24) & 0xFF, length)
              + data.joined())
    }
    var reference = [UInt64](repeating: 0, count: Int(kOSAsyncRef64Count))
    reference[Int(kIOAsyncCalloutFuncIndex)] = UInt64(UInt(bitPattern: unsafeBitCast(callback, to: UnsafeRawPointer.self)))
    let kr = IOConnectCallAsyncScalarMethod(connect, selectorSubscribe, machPort, &reference,
                                            UInt32(kOSAsyncRef64Count), nil, 0, nil, nil)
    guard kr == KERN_SUCCESS else { fail(String(format: "subscribe: %#x", kr)) }
}

func number(_ text: String) -> UInt32? {
    text.hasPrefix("0x") ? UInt32(text.dropFirst(2), radix: 16) : UInt32(text)
}

func set(_ command: UInt32, _ p1: UInt32, _ value: UInt32) -> [UInt32] {
    [1, 0, 1 | command << 8 | p1 << 16 | value << 24]
}

let arguments = Array(CommandLine.arguments.dropFirst())
let connect = open()
switch arguments.first {
case "getall":
    subscribe(connect)
    send(connect, [1, 0, 4])
case "set" where arguments.count == 4:
    let numbers = arguments.dropFirst().compactMap(number)
    guard numbers.count == 3 else { fail("set takes <command> <p1> <value>") }
    subscribe(connect)
    send(connect, set(numbers[0], numbers[1], numbers[2]))
default:
    fail("usage: ensemblectl getall | ensemblectl set <command> <p1> <value>")
}
DispatchQueue.main.asyncAfter(deadline: .now() + 2) { exit(0) }
dispatchMain()
