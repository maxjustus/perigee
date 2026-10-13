import EnsembleModel
import Foundation
import IOKit

struct DeviceError: Error, CustomStringConvertible {
    let description: String
}

final class Device: Transport, @unchecked Sendable {
    private let service: io_service_t
    private let connect: io_connect_t
    private let port: IONotificationPortRef
    private var onReport: ((Report) -> Void)?
    private var onTerminated: (() -> Void)?

    init(queue: DispatchQueue) throws {
        service = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceNameMatching("EnsembleDriver"))
        guard service != 0 else {
            throw DeviceError(description: "no EnsembleDriver in the IORegistry")
        }
        var connect: io_connect_t = 0
        let kr = IOServiceOpen(service, mach_task_self_, 1, &connect)
        guard kr == KERN_SUCCESS else {
            throw DeviceError(description: String(format: "IOServiceOpen: %#x", kr))
        }
        self.connect = connect
        guard let port = IONotificationPortCreate(kIOMainPortDefault) else {
            throw DeviceError(description: "IONotificationPortCreate failed")
        }
        self.port = port
        IONotificationPortSetDispatchQueue(port, queue)
    }

    func watchTermination(_ onTerminated: @escaping () -> Void) throws {
        self.onTerminated = onTerminated
        let callback: IOServiceInterestCallback = { refcon, _, message, _ in
            guard let refcon, message == kIOMessageServiceIsTerminated else { return }
            Unmanaged<Device>.fromOpaque(refcon).takeUnretainedValue().onTerminated?()
        }
        var notification: io_object_t = 0
        let kr = IOServiceAddInterestNotification(port, service, kIOGeneralInterest, callback,
                                                  Unmanaged.passUnretained(self).toOpaque(), &notification)
        guard kr == KERN_SUCCESS else {
            throw DeviceError(description: String(format: "watch termination: %#x", kr))
        }
    }

    func send(_ words: [UInt32]) throws -> Bool {
        let kr = words.withUnsafeBytes {
            IOConnectCallStructMethod(connect, 0, $0.baseAddress, $0.count, nil, nil)
        }
        if kr == kIOReturnNoSpace {
            return false
        }
        guard kr == KERN_SUCCESS else {
            throw DeviceError(description: String(format: "send: %#x", kr))
        }
        return true
    }

    func mapMeters() throws -> UnsafeRawBufferPointer {
        var address: mach_vm_address_t = 0
        var size: mach_vm_size_t = 0
        let kr = IOConnectMapMemory64(connect, 0, mach_task_self_, &address, &size, IOOptionBits(kIOMapAnywhere))
        guard kr == KERN_SUCCESS, let base = UnsafeRawPointer(bitPattern: UInt(address)) else {
            throw DeviceError(description: String(format: "map meters: %#x", kr))
        }
        return UnsafeRawBufferPointer(start: base, count: Int(size))
    }

    func subscribe(_ onReport: @escaping (Report) -> Void) throws {
        self.onReport = onReport
        let machPort = IONotificationPortGetMachPort(port)
        var limits = mach_port_limits_t(mpl_qlimit: mach_port_msgcount_t(MACH_PORT_QLIMIT_MAX))
        withUnsafeMutablePointer(to: &limits) {
            $0.withMemoryRebound(to: integer_t.self, capacity: 1) {
                _ = mach_port_set_attributes(mach_task_self_, machPort, MACH_PORT_LIMITS_INFO, $0,
                                             mach_msg_type_number_t(MemoryLayout<mach_port_limits_t>.size / 4))
            }
        }
        let callback: IOAsyncCallback = { refcon, result, args, count in
            guard result == kIOReturnSuccess, let refcon, let args else { return }
            let device = Unmanaged<Device>.fromOpaque(refcon).takeUnretainedValue()
            let words = (0..<Int(count)).map { UInt64(UInt(bitPattern: args[$0])) }
            device.onReport?(Report(arguments: words))
        }
        var reference = [UInt64](repeating: 0, count: Int(kOSAsyncRef64Count))
        reference[Int(kIOAsyncCalloutFuncIndex)] = UInt64(UInt(bitPattern: unsafeBitCast(callback, to: UnsafeRawPointer.self)))
        reference[Int(kIOAsyncCalloutRefconIndex)] = UInt64(UInt(bitPattern: Unmanaged.passUnretained(self).toOpaque()))
        let kr = IOConnectCallAsyncScalarMethod(connect, 1, machPort, &reference, UInt32(kOSAsyncRef64Count),
                                                nil, 0, nil, nil)
        guard kr == KERN_SUCCESS else {
            throw DeviceError(description: String(format: "subscribe: %#x", kr))
        }
    }
}

// IOMessage.h defines it as iokit_common_msg(0x010), a macro that Swift does not import.
private let kIOMessageServiceIsTerminated: UInt32 = 0xE000_0010
