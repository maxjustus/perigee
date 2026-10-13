import Foundation

public protocol Transport: Sendable {
    func send(_ words: [UInt32]) throws
}

struct RPCError: Error {
    let code: Int
    let message: String

    static func invalidParams(_ message: String) -> RPCError { RPCError(code: -32602, message: message) }
}

public final class Controller: @unchecked Sendable {
    private let transport: Transport
    private let broadcast: @Sendable (String) -> Void
    private let byPath = Dictionary(uniqueKeysWithValues: parameters.map { ($0.path, $0) })
    private let byKey = Dictionary(parameters.flatMap { parameter in
        targets(parameter).map { (Key(parameter, $0), parameter) }
    }, uniquingKeysWith: { first, _ in first })
    private let lock = NSLock()
    private var values: [String: Int] = [:]

    public init(transport: Transport, broadcast: @escaping @Sendable (String) -> Void) {
        self.transport = transport
        self.broadcast = broadcast
    }

    public func handle(_ text: String) -> String? {
        guard let request = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any],
              let method = request["method"] as? String
        else {
            return encode(["jsonrpc": "2.0", "id": NSNull(), "error": ["code": -32700, "message": "parse error"]])
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
        switch result {
        case .success(let value):
            return encode(["jsonrpc": "2.0", "id": id, "result": value])
        case .failure(let error):
            return encode(["jsonrpc": "2.0", "id": id, "error": ["code": error.code, "message": error.message]])
        }
    }

    public func receive(_ report: Report) {
        guard let parameter = byKey[Key(report)], let value = value(parameter, report) else {
            broadcast(notification("report", [
                "type": Int(report.type), "command": Int(report.command), "p1": Int(report.p1),
                "p2": Int(report.p2), "data": report.data.map(Int.init),
            ]))
            return
        }
        let old = lock.withLock { values.updateValue(value, forKey: parameter.path) }
        if old != value {
            broadcast(notification("changed", [parameter.path: json(value, parameter.kind)]))
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
                return targets(parameter).map { message(parameter, $0, wire) }
            }
            try messages.forEach(transport.send)
            return true
        case "raw.send":
            guard let words = (params as? [String: Any])?["words"] as? [Int], (3...30).contains(words.count),
                  words.allSatisfy({ UInt32(exactly: $0) != nil })
            else {
                throw RPCError.invalidParams("raw.send takes words: 3 to 30 unsigned 32-bit integers")
            }
            try transport.send(words.map { UInt32($0) })
            return true
        default:
            throw RPCError(code: -32601, message: "unknown method \(method)")
        }
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

    init(_ parameter: Parameter, _ target: Target) {
        block = (parameter.reported ?? parameter.wire) != .set
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
        if let flag = value as? Bool {
            return flag ? parameter.on : 0
        }
    case .int(let range):
        if let number = value as? Int, range.contains(number) {
            return number
        }
    case .choice(let choices):
        if let name = value as? String, let choice = choices.first(where: { $0.name == name }) {
            return choice.code
        }
    }
    throw RPCError.invalidParams("bad value for \(parameter.path)")
}

private func encode(_ object: [String: Any]) -> String {
    let data = (try? JSONSerialization.data(withJSONObject: object)) ?? Data()
    return String(decoding: data, as: UTF8.self)
}
