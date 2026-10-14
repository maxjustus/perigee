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
    /// I2C transfer require. The driver refuses it while audio runs or while
    /// another client holds it.
    public func enableSession(_ on: Bool) throws {
        var value: UInt64 = on ? 1 : 0
        let kr = IOConnectCallScalarMethod(connect, selectorSession, &value, 1, nil, nil)
        guard kr == KERN_SUCCESS else {
            throw DeviceError(description: String(format: "session: %#x", kr))
        }
    }

    /// The PSoC state in INFO bits 7:6: 1 for the application, 2 for the
    /// bootloader.
    public func bootloaderStatus() throws -> Int {
        var status: UInt64 = 0
        var count: UInt32 = 1
        let kr = IOConnectCallScalarMethod(connect, selectorBootloaderStatus, nil, 0, &status, &count)
        guard kr == KERN_SUCCESS else {
            throw DeviceError(description: String(format: "bootloader status: %#x", kr))
        }
        return Int(status)
    }

    /// Writes one packet through the FPGA remote-I2C engine.
    public func writeI2c(_ packet: [UInt8]) throws {
        let request = [UInt8(0)] + packet
        let kr = request.withUnsafeBytes {
            IOConnectCallStructMethod(connect, selectorI2c, $0.baseAddress, $0.count, nil, nil)
        }
        guard kr == KERN_SUCCESS else {
            throw DeviceError(description: String(format: "I2C write: %#x", kr))
        }
    }

    /// Reads `count` bytes, at most 255, through the FPGA remote-I2C engine.
    public func readI2c(count: Int) throws -> [UInt8] {
        let request = [UInt8(1), UInt8(count)]
        var reply = [UInt8](repeating: 0, count: count)
        var size = count
        let kr = request.withUnsafeBytes { input in
            reply.withUnsafeMutableBytes { output in
                IOConnectCallStructMethod(connect, selectorI2c, input.baseAddress, input.count,
                                          output.baseAddress, &size)
            }
        }
        guard kr == KERN_SUCCESS, size == count else {
            throw DeviceError(description: String(format: "I2C read: %#x, %d bytes", kr, size))
        }
        return reply
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
private let selectorBootloaderStatus: UInt32 = 4
private let memoryMeters: UInt32 = 0

// IOMessage.h defines it as iokit_common_msg(0x010), a macro that Swift does not import.
private let kIOMessageServiceIsTerminated: UInt32 = 0xE000_0010

