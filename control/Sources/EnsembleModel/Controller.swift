import Foundation

public protocol Transport: Sendable {
    /// Returns false if the driver outbox is full.
    func send(_ words: [UInt32]) throws -> Bool
}

struct RPCError: Error {
    let code: Int
    let message: String

    static func invalidParams(_ message: String) -> RPCError { RPCError(code: -32602, message: message) }
}

public final class Controller: @unchecked Sendable {
    private let transport: Transport
    private let retryDelay: TimeInterval
    private let broadcast: @Sendable (String) -> Void
    private let byPath = Dictionary(uniqueKeysWithValues: parameters.map { ($0.path, $0) })
    private let byKey = Dictionary(grouping: parameters.flatMap { parameter in
        keys(parameter).map { (key: $0, parameter: parameter) }
    }, by: \.key).mapValues { $0.map(\.parameter) }
    private let leadsByStereo = Dictionary(grouping: parameters.filter { $0.pair?.leads == true }) { $0.pair!.stereo }
    private let lock = NSLock()
    private var values: [String: Int] = [:]

    public init(transport: Transport, retryDelay: TimeInterval = 0.01,
                broadcast: @escaping @Sendable (String) -> Void) {
        self.transport = transport
        self.retryDelay = retryDelay
        self.broadcast = broadcast
    }

    public func handle(_ text: String) -> String? {
        guard let json = try? JSONSerialization.jsonObject(with: Data(text.utf8), options: .fragmentsAllowed) else {
            return reply(NSNull(), .failure(RPCError(code: -32700, message: "parse error")))
        }
        guard let request = json as? [String: Any], request["jsonrpc"] as? String == "2.0",
              let method = request["method"] as? String
        else {
            return reply(NSNull(), .failure(RPCError(code: -32600, message: "invalid request")))
        }
        let result: Result<Any, RPCError>
        do {
            result = .success(try call(method, request["params"]))
        } catch let error as RPCError {
            result = .failure(error)
        } catch {
            result = .failure(RPCError(code: -32000, message: "\(error)"))
        }
        guard let id = request["id"] else {
            return nil
        }
        return reply(id, result)
    }

    private func reply(_ id: Any, _ result: Result<Any, RPCError>) -> String {
        switch result {
        case .success(let value):
            return encode(["jsonrpc": "2.0", "id": id, "result": value])
        case .failure(let error):
            return encode(["jsonrpc": "2.0", "id": id, "error": ["code": error.code, "message": error.message]])
        }
    }

    public func receive(_ report: Report) {
        if report.type == 5 {
            broadcast(notification("restarted", [:]))
            return
        }
        let matches = byKey[Key(report)] ?? []
        guard !matches.isEmpty else {
            broadcast(notification("report", [
                "type": Int(report.type), "command": Int(report.command), "p1": Int(report.p1),
                "p2": Int(report.p2), "data": report.data.map(Int.init),
            ]))
            return
        }
        let changes: [String: Any] = lock.withLock {
            var changes: [String: Any] = [:]
            for parameter in matches {
                if let value = value(parameter, report), values.updateValue(value, forKey: parameter.path) != value {
                    changes[parameter.path] = json(value, parameter.kind)
                }
            }
            return changes
        }
        if !changes.isEmpty {
            broadcast(notification("changed", changes))
        }
    }

    public func meters(_ meters: Meters) {
        broadcast(notification("meters", [
            "inputs": meters.inputs.map(Int.init), "outputs": meters.outputs.map(Int.init),
            "outputGroup": meters.outputGroup.map(Int.init), "group2": meters.group2.map(Int.init),
            "mixers": meters.mixers.map(Int.init),
        ]))
    }

    private func call(_ method: String, _ params: Any?) throws -> Any {
        switch method {
        case "describe":
            return parameters.map(describe)
        case "get":
            return lock.withLock {
                Dictionary(uniqueKeysWithValues: values.map { ($0.key, json($0.value, byPath[$0.key]!.kind)) })
            }
        case "set":
            guard let changes = params as? [String: Any] else {
                throw RPCError.invalidParams("set takes an object of path: value")
            }
            let messages = try changes.flatMap { path, value in
                guard let parameter = byPath[path] else {
                    throw RPCError.invalidParams("unknown path \(path)")
                }
                let wire = try encodeValue(value, parameter)
                return lock.withLock { writes(parameter, wire) }.flatMap { parameter, value in
                    sendTargets(parameter).map { message(parameter, $0, value) }
                }
            }
            try messages.forEach(send)
            return true
        case "raw.send":
            guard let items = (params as? [String: Any])?["words"] as? [Any],
                  case let words = items.compactMap({ integer($0).flatMap { UInt32(exactly: $0) } }),
                  words.count == items.count, (3...30).contains(words.count)
            else {
                throw RPCError.invalidParams("raw.send takes words: 3 to 30 unsigned 32-bit integers")
            }
            try send(words)
            return true
        default:
            throw RPCError(code: -32601, message: "unknown method \(method)")
        }
    }

    // The dext empties its outbox every 10 ms, so 100 attempts wait about 1 s.
    public func send(_ words: [UInt32]) throws {
        for attempt in 1...100 {
            if try transport.send(words) {
                return
            }
            if attempt < 100 {
                Thread.sleep(forTimeInterval: retryDelay)
            }
        }
        throw RPCError(code: -32000, message: "driver outbox full")
    }

    // The caller holds the lock.
    private func writes(_ parameter: Parameter, _ value: Int) -> [(Parameter, Int)] {
        var writes = [(parameter, value)]
        if let pair = parameter.pair, values[pair.stereo] ?? 0 != 0, let partner = byPath[pair.partner] {
            writes.append((partner, value))
        }
        if value != 0 {
            for lead in leadsByStereo[parameter.path] ?? [] {
                if let current = values[lead.path], let partner = byPath[lead.pair!.partner] {
                    writes.append((partner, current))
                }
            }
        }
        return writes
    }

    private func sendTargets(_ parameter: Parameter) -> [Target] {
        guard parameter.perSpeakerSet else {
            return targets(parameter)
        }
        let mode = lock.withLock { values["outputs/mainMode"] }
        let sets = mode == 2 ? 2 : mode == 3 ? 3 : 1
        return (0..<sets).map { Target(p1: parameter.p1 + UInt8($0), p2: 0) }
    }

    private func notification(_ method: String, _ params: [String: Any]) -> String {
        encode(["jsonrpc": "2.0", "method": method, "params": params])
    }
}

private struct Key: Hashable {
    let block: Bool
    let command: UInt8
    let p1: UInt8
    let p2: UInt8

    init(_ parameter: Parameter, _ target: Target, block: Bool) {
        self.block = block
        command = parameter.command
        p1 = target.p1
        p2 = block ? target.p2 : 0
    }

    init(_ report: Report) {
        block = report.type == 2
        command = report.command
        p1 = report.p1
        p2 = block ? report.p2 : 0
    }
}

// The dext reports each sent message, so a parameter also matches its own
// wire format when the PSoC reports it in another one.
private func keys(_ parameter: Parameter) -> [Key] {
    let formats = Set([parameter.wire, parameter.reported ?? parameter.wire].map { $0 != .set })
    return targets(parameter).flatMap { target in formats.map { Key(parameter, target, block: $0) } }
}

private func targets(_ parameter: Parameter) -> [Target] {
    [Target(p1: parameter.p1, p2: parameter.p2)] + parameter.also
}

private func describe(_ parameter: Parameter) -> [String: Any] {
    switch parameter.kind {
    case .bool:
        return ["path": parameter.path, "kind": "bool"]
    case .int(let range):
        return ["path": parameter.path, "kind": "int", "min": range.lowerBound, "max": range.upperBound]
    case .choice(let choices):
        return ["path": parameter.path, "kind": "choice", "choices": choices.map(\.name)]
    }
}

private func json(_ value: Int, _ kind: Kind) -> Any {
    switch kind {
    case .bool:
        return value != 0
    case .int:
        return value
    case .choice(let choices):
        return choices.first { $0.code == value }?.name ?? value
    }
}

private func encodeValue(_ value: Any, _ parameter: Parameter) throws -> Int {
    switch parameter.kind {
    case .bool:
        if let flag = boolean(value) {
            return flag ? parameter.on : 0
        }
    case .int(let range):
        if let number = integer(value), range.contains(number) {
            return number
        }
    case .choice(let choices):
        if let name = value as? String, let choice = choices.first(where: { $0.name == name }) {
            return choice.code
        }
    }
    throw RPCError.invalidParams("bad value for \(parameter.path)")
}

// JSONSerialization returns every JSON number and boolean as an NSNumber, and
// NSNumber bridges to both Bool and Int.
private func boolean(_ value: Any) -> Bool? {
    guard let number = value as? NSNumber, CFGetTypeID(number) == CFBooleanGetTypeID() else {
        return nil
    }
    return number.boolValue
}

private func integer(_ value: Any) -> Int? {
    guard let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID(),
          !CFNumberIsFloatType(number as CFNumber)
    else {
        return nil
    }
    return Int(exactly: number)
}

private func encode(_ object: [String: Any]) -> String {
    let data = (try? JSONSerialization.data(withJSONObject: object)) ?? Data()
    return String(decoding: data, as: UTF8.self)
}
