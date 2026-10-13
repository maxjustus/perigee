import CoreAudio
import EnsembleIO
import EnsembleModel
import Foundation
import Network

final class Monitor: @unchecked Sendable {
    private let queue = DispatchQueue(label: "monitor")
    private let ready: DispatchSourceUserDataAdd
    private var listener: NWListener?
    private var clients: [ObjectIdentifier: (connection: NWConnection, channel: Int)] = [:]
    private var device = AudioObjectID(kAudioObjectUnknown)
    private var rate: UInt32 = 0
    private var channels = 0
    private var ring: SampleRing?
    private var proc: AudioDeviceIOProcID?

    init() {
        ready = DispatchSource.makeUserDataAddSource(queue: queue)
        ready.setEventHandler { [self] in publish() }
        ready.activate()
    }

    func start(port: UInt16) throws {
        let listener = try webSocketListener(port: port)
        listener.newConnectionHandler = { [self] connection in
            connection.stateUpdateHandler = { [self] state in
                if case .failed = state { connection.cancel() }
                if case .cancelled = state { select(connection, nil) }
            }
            connection.start(queue: queue)
            receive(connection)
        }
        listener.start(queue: queue)
        self.listener = listener
    }

    private func receive(_ connection: NWConnection) {
        connection.receiveMessage { [self] data, _, _, error in
            if let data, let request = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                select(connection, (request["channel"] as? Int).map { $0 - 1 })
            }
            if error == nil {
                receive(connection)
            } else {
                connection.cancel()
            }
        }
    }

    private func select(_ connection: NWConnection, _ channel: Int?) {
        clients[ObjectIdentifier(connection)] = channel.map { (connection, $0) }
        if clients.isEmpty {
            stop()
        } else if proc == nil {
            capture()
        }
    }

    // The first start blocks until the user answers the macOS microphone prompt.
    private func capture() {
        if device == kAudioObjectUnknown {
            guard let ensemble = findEnsemble() else {
                FileHandle.standardError.write(Data("ensemble-control: no CoreAudio device named Ensemble\n".utf8))
                return
            }
            device = ensemble
            var address = propertyAddress(kAudioDevicePropertyNominalSampleRate)
            AudioObjectAddPropertyListenerBlock(device, &address, queue) { [self] _, _ in readRate() }
            readRate()
            channels = channelCount(device, kAudioObjectPropertyScopeInput)
            ring = SampleRing(capacity: 16384 * channels)
        }
        // The IOProc runs on the device's IO thread. AudioDeviceStop on this queue waits for that thread,
        // so the IOProc must not wait for this queue.
        AudioDeviceCreateIOProcIDWithBlock(&proc, device, nil) { [ring, channels, ready] _, input, _, _, _ in
            guard let ring, let buffer = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input)).first,
                  Int(buffer.mNumberChannels) == channels, let samples = buffer.mData else {
                return
            }
            ring.write(UnsafeBufferPointer(start: samples.assumingMemoryBound(to: Float.self),
                                           count: Int(buffer.mDataByteSize) / MemoryLayout<Float>.size))
            ready.add(data: 1)
        }
        AudioDeviceStart(device, proc)
    }

    private func readRate() {
        rate = UInt32(property(device, kAudioDevicePropertyNominalSampleRate, kAudioObjectPropertyScopeGlobal, Float64(0)))
    }

    private func publish() {
        ring?.read { interleaved in
            for (connection, channel) in clients.values where (0..<channels).contains(channel) {
                let frame = monitorFrame(rate: rate, interleaved: interleaved, channels: channels, channel: channel)
                sendMessage(connection, frame, .binary)
            }
        }
    }

    private func stop() {
        guard let proc else {
            return
        }
        AudioDeviceStop(device, proc)
        AudioDeviceDestroyIOProcID(device, proc)
        self.proc = nil
    }
}
