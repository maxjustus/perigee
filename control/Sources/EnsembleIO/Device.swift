import EnsembleModel
import Foundation
import IOKit

struct DeviceError: Error, CustomStringConvertible {
    let description: String
}

public final class Device: Transport, @unchecked Sendable {
    private let service: io_service_t
    private let connect: io_connect_t
    private let port: IONotificationPortRef
    private var onReport: ((Report) -> Void)?
    private var onTerminated: (() -> Void)?
    private var onI2c: ((Bool, [UInt8]) -> Void)?

    public init(queue: DispatchQueue) throws {
        service = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceNameMatching("EnsembleDriver"))
        guard service != 0 else {
            throw DeviceError(description: "no EnsembleDriver in the IORegistry")
        }
        var connect: io_connect_t = 0
        let kr = IOServiceOpen(service, mach_task_self_, clientType, &connect)
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

    public func watchTermination(_ onTerminated: @escaping () -> Void) throws {
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

    public func send(_ words: [UInt32]) throws -> Bool {
        let kr = words.withUnsafeBytes {
            IOConnectCallStructMethod(connect, selectorSend, $0.baseAddress, $0.count, nil, nil)
        }
        if kr == kIOReturnNoSpace {
            return false
        }
        guard kr == KERN_SUCCESS else {
            throw DeviceError(description: String(format: "send: %#x", kr))
        }
        return true
    }

    public func mapMeters() throws -> UnsafeRawBufferPointer {
        var address: mach_vm_address_t = 0
        var size: mach_vm_size_t = 0
        let kr = IOConnectMapMemory64(connect, memoryMeters, mach_task_self_, &address, &size, IOOptionBits(kIOMapAnywhere))
        guard kr == KERN_SUCCESS, let base = UnsafeRawPointer(bitPattern: UInt(address)) else {
            throw DeviceError(description: String(format: "map meters: %#x", kr))
        }
        return UnsafeRawBufferPointer(start: base, count: Int(size))
    }

    /// Opens or closes the session that the bootloader entry gate and the
    /// I2C transfer require. Zero closes it.
    public func enableSession(_ on: Bool) throws {
        var value: UInt64 = on ? 1 : 0
        let kr = IOConnectCallScalarMethod(connect, selectorSession, &value, 1, nil, nil)
        guard kr == KERN_SUCCESS else {
            throw DeviceError(description: String(format: "session: %#x", kr))
        }
    }

    /// One remote-I2C transfer. A write sends `payload`; a read asks for
    /// `count` bytes. Returns the busy flag and the read bytes.
    public func transfer(direction: UInt8, payload: [UInt8] = [], count: UInt16 = 0) throws
        -> (busy: Bool, data: [UInt8]) {
        var request: [UInt8] = [direction]
        if direction == 1 {
            request += [UInt8(count & 0xff), UInt8(count >> 8)]
        } else {
            request += payload
        }
        guard request.count <= 1025 else {
            throw DeviceError(description: "transfer too long")
        }

        let handler = Unmanaged.passRetained(TransferHandler())
        let callback: IOAsyncCallback = { refcon, result, args, argCount in
            guard result == kIOReturnSuccess, let refcon, let args, argCount > 0 else { return }
            let head = UInt64(UInt(bitPattern: args[0]))
            let busy = (head >> 40) & 1 == 1
            let length = Int((head >> 8) & 0x3ff)
            var data: [UInt8] = []
            data.reserveCapacity(length)
            for i in 0..<length where 1 + i / 8 < argCount {
                let word = UInt64(UInt(bitPattern: args[1 + i / 8]))
                data.append(UInt8(truncatingIfNeeded: word >> (8 * UInt64(i % 8))))
            }
            Unmanaged<TransferHandler>.fromOpaque(refcon).takeUnretainedValue().call(busy, data)
        }
        var reference = [UInt64](repeating: 0, count: Int(kOSAsyncRef64Count))
        reference[Int(kIOAsyncCalloutFuncIndex)] =
            UInt64(UInt(bitPattern: unsafeBitCast(callback, to: UnsafeRawPointer.self)))
        reference[Int(kIOAsyncCalloutRefconIndex)] = UInt64(UInt(bitPattern: handler.toOpaque()))
        let machPort = IONotificationPortGetMachPort(port)
        let kr = request.withUnsafeBytes { input in
            IOConnectCallAsyncStructMethod(connect, selectorI2c, machPort, &reference,
                                           UInt32(kOSAsyncRef64Count),
                                           input.baseAddress, input.count, nil, nil)
        }
        guard kr == KERN_SUCCESS else {
            handler.release()
            throw DeviceError(description: String(format: "transfer: %#x", kr))
        }
        let (busy, data) = handler.takeRetainedValue().wait()
        return (busy, data)
    }

    public func subscribe(_ onReport: @escaping (Report) -> Void) throws {
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
        let kr = IOConnectCallAsyncScalarMethod(connect, selectorSubscribe, machPort, &reference, UInt32(kOSAsyncRef64Count),
                                                nil, 0, nil, nil)
        guard kr == KERN_SUCCESS else {
            throw DeviceError(description: String(format: "subscribe: %#x", kr))
        }
    }
}

// These match EnsembleUserClient.cpp. EnsembleDriver.cpp opens that client for any type but the HAL's.
private let clientType: UInt32 = 1
private let selectorSend: UInt32 = 0
private let selectorSubscribe: UInt32 = 1
private let selectorSession: UInt32 = 2
private let selectorI2c: UInt32 = 3
private let memoryMeters: UInt32 = 0

// IOMessage.h defines it as iokit_common_msg(0x010), a macro that Swift does not import.
private let kIOMessageServiceIsTerminated: UInt32 = 0xE000_0010


/// Holds the one in-flight I2C completion and its result.
final class TransferHandler {
    private let semaphore = DispatchSemaphore(value: 0)
    private var box: (Bool, [UInt8]) = (false, [])

    func call(_ busy: Bool, _ data: [UInt8]) {
        box = (busy, data)
        semaphore.signal()
    }

    func wait() -> (Bool, [UInt8]) {
        semaphore.wait()
        return box
    }
}
