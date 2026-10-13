import EnsembleModel
import Foundation

final class MeterPoller: @unchecked Sendable {
    private let timer = DispatchSource.makeTimerSource(queue: DispatchQueue(label: "meters"))
    private var sequence: UInt8?

    init(buffer: UnsafeRawBufferPointer, publish: @escaping @Sendable (Meters) -> Void) {
        timer.schedule(deadline: .now(), repeating: .milliseconds(10))
        timer.setEventHandler { [self] in
            guard buffer[0] != sequence, let meters = Meters(bytes: Array(buffer.prefix(Meters.bytes))) else {
                return
            }
            sequence = meters.sequence
            publish(meters)
        }
        timer.resume()
    }
}
