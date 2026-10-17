import CoreAudio
import EnsembleIO
import EnsembleModel
import Foundation

let httpPort: UInt16 = 8737
let webSocketPort: UInt16 = 8738
let monitorPort: UInt16 = 8739
var poller: MeterPoller?
let monitor = Monitor()

do {
    let device = try Device(queue: DispatchQueue(label: "device"))
    try device.watchTermination {
        FileHandle.standardError.write(Data("ensemble-control: EnsembleDriver terminated\n".utf8))
        exit(0)
    }
    let server = Server()
    let presets = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("ensemble-control/presets.json")
    let controller = Controller(transport: device, presets: presets) { server.broadcast($0) }
    try device.subscribe { controller.receive($0) }
    // The page is read on each request, so `make dev` can point ENSEMBLE_WEB_PAGE at the page that it rebuilds.
    let pageURL = ProcessInfo.processInfo.environment["ENSEMBLE_WEB_PAGE"].map { URL(fileURLWithPath: $0) }
        ?? Bundle.module.url(forResource: "index", withExtension: "html", subdirectory: "Public")!
    _ = try String(contentsOf: pageURL, encoding: .utf8)
    try server.start(controller: controller, page: {
        let page = (try? String(contentsOf: pageURL, encoding: .utf8)) ?? ""
        return Data(page.replacingOccurrences(of: "@RPC_PORT@", with: "\(webSocketPort)")
            .replacingOccurrences(of: "@MONITOR_PORT@", with: "\(monitorPort)")
            .replacingOccurrences(of: "@CAPTURE_NAMES@", with: captureNames()).utf8)
    }, httpPort: httpPort, webSocketPort: webSocketPort)
    try monitor.start(port: monitorPort)
    poller = MeterPoller(buffer: try device.mapMeters()) { controller.meters($0) }
    try controller.send(getAll)
    print("ensemble-control: http://\(ProcessInfo.processInfo.hostName):\(httpPort)")
} catch {
    FileHandle.standardError.write(Data("ensemble-control: \(error)\n".utf8))
    exit(1)
}
dispatchMain()

func captureNames() -> String {
    let names = findEnsemble().map { channelNames($0, kAudioObjectPropertyScopeInput) } ?? []
    let json = try! JSONSerialization.data(withJSONObject: names, options: .withoutEscapingSlashes)
    return String(decoding: json, as: UTF8.self)
}
