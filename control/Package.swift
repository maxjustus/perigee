// swift-tools-version:6.0
import Foundation
import PackageDescription

let infoPlist = URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Info.plist").path

let package = Package(
    name: "EnsembleControl",
    platforms: [.macOS(.v15)],
    targets: [
        .target(name: "EnsembleModel"),
        .target(name: "EnsembleIO", dependencies: ["EnsembleModel"]),
        .executableTarget(name: "ensemble-control", dependencies: ["EnsembleIO", "EnsembleModel"],
                          resources: [.copy("Public")],
                          linkerSettings: [.unsafeFlags(["-Xlinker", "-sectcreate", "-Xlinker", "__TEXT",
                                                         "-Xlinker", "__info_plist", "-Xlinker", infoPlist])]),
        .executableTarget(name: "ensemblectl", dependencies: ["EnsembleIO", "EnsembleModel"]),
        .testTarget(name: "EnsembleModelTests", dependencies: ["EnsembleModel"]),
    ]
)
