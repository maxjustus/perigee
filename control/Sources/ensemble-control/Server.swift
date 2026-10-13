import EnsembleModel
import Foundation
import Network

final class Server: @unchecked Sendable {
    private let queue = DispatchQueue(label: "server")
    private var clients: [ObjectIdentifier: NWConnection] = [:]
    private var listeners: [NWListener] = []

    func start(controller: Controller, page: Data, httpPort: UInt16, webSocketPort: UInt16) throws {
        let webSocket = NWProtocolWebSocket.Options()
        webSocket.autoReplyPing = true
        let parameters = NWParameters.tcp
        parameters.defaultProtocolStack.applicationProtocols.insert(webSocket, at: 0)
        let rpc = try NWListener(using: parameters, on: NWEndpoint.Port(rawValue: webSocketPort)!)
        rpc.newConnectionHandler = { [self] connection in
            clients[ObjectIdentifier(connection)] = connection
            connection.stateUpdateHandler = { [self] state in
                if case .failed = state { drop(connection) }
                if case .cancelled = state { clients[ObjectIdentifier(connection)] = nil }
            }
            connection.start(queue: queue)
            receive(connection, controller)
        }

        let http = try NWListener(using: .tcp, on: NWEndpoint.Port(rawValue: httpPort)!)
        http.newConnectionHandler = { [self] connection in
            connection.start(queue: queue)
            connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { _, _, _, _ in
                let header = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                    + "Content-Length: \(page.count)\r\nConnection: close\r\n\r\n"
                connection.send(content: Data(header.utf8) + page, completion: .contentProcessed { _ in
                    connection.cancel()
                })
            }
        }

        listeners = [rpc, http]
        for listener in listeners {
            listener.start(queue: queue)
        }
    }

    func broadcast(_ text: String) {
        queue.async { [self] in
            for connection in clients.values {
                send(connection, text)
            }
        }
    }

    private func receive(_ connection: NWConnection, _ controller: Controller) {
        connection.receiveMessage { [self] data, context, _, error in
            if let data,
               let metadata = context?.protocolMetadata(definition: NWProtocolWebSocket.definition)
                as? NWProtocolWebSocket.Metadata,
               metadata.opcode == .text,
               let reply = controller.handle(String(decoding: data, as: UTF8.self)) {
                send(connection, reply)
            }
            if error == nil {
                receive(connection, controller)
            } else {
                drop(connection)
            }
        }
    }

    private func send(_ connection: NWConnection, _ text: String) {
        let metadata = NWProtocolWebSocket.Metadata(opcode: .text)
        let context = NWConnection.ContentContext(identifier: "text", metadata: [metadata])
        connection.send(content: Data(text.utf8), contentContext: context, isComplete: true,
                        completion: .contentProcessed { _ in })
    }

    private func drop(_ connection: NWConnection) {
        clients[ObjectIdentifier(connection)] = nil
        connection.cancel()
    }
}
