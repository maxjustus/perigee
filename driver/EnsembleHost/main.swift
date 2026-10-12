import Foundation
import SystemExtensions

let driverID = "dev.ensemble.Host.Driver"

final class Delegate: NSObject, OSSystemExtensionRequestDelegate {
    func request(
        _ request: OSSystemExtensionRequest,
        actionForReplacingExtension existing: OSSystemExtensionProperties,
        withExtension ext: OSSystemExtensionProperties
    ) -> OSSystemExtensionRequest.ReplacementAction {
        print("replacing \(existing.bundleVersion) with \(ext.bundleVersion)")
        return .replace
    }

    func requestNeedsUserApproval(_ request: OSSystemExtensionRequest) {
        print("approve the driver in System Settings > General > Login Items & Extensions")
    }

    func request(
        _ request: OSSystemExtensionRequest,
        didFinishWithResult result: OSSystemExtensionRequest.Result
    ) {
        print(result == .completed ? "done" : "done after reboot")
        exit(0)
    }

    func request(_ request: OSSystemExtensionRequest, didFailWithError error: Error) {
        print("failed: \(error.localizedDescription)")
        exit(1)
    }
}

let request: OSSystemExtensionRequest
switch CommandLine.arguments.dropFirst().first {
case "activate":
    request = .activationRequest(forExtensionWithIdentifier: driverID, queue: .main)
case "deactivate":
    request = .deactivationRequest(forExtensionWithIdentifier: driverID, queue: .main)
default:
    print("usage: EnsembleHost activate|deactivate")
    exit(2)
}
let delegate = Delegate()
request.delegate = delegate
OSSystemExtensionManager.shared.submitRequest(request)
dispatchMain()
