import EnsembleModel
import Foundation

let httpPort: UInt16 = 8737
let webSocketPort: UInt16 = 8738
var poller: MeterPoller?

do {
    let device = try Device()
    let server = Server()
    let controller = Controller(transport: device) { server.broadcast($0) }
    try device.subscribe(queue: DispatchQueue(label: "reports")) { controller.receive($0) }
    let page = try Data(contentsOf: Bundle.module.url(forResource: "index", withExtension: "html",
                                                      subdirectory: "Public")!)
    try server.start(controller: controller, page: page, httpPort: httpPort, webSocketPort: webSocketPort)
    poller = MeterPoller(buffer: try device.mapMeters()) { controller.meters($0) }
    try device.send([1, 0, 4])
    print("ensemble-control: http://\(ProcessInfo.processInfo.hostName):\(httpPort)")
} catch {
    FileHandle.standardError.write(Data("ensemble-control: \(error)\n".utf8))
    exit(1)
}
dispatchMain()
