// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "EnsembleControl",
    platforms: [.macOS(.v14)],
    targets: [
        .target(name: "EnsembleModel"),
        .executableTarget(name: "ensemble-control", dependencies: ["EnsembleModel"], resources: [.copy("Public")]),
        .testTarget(name: "EnsembleModelTests", dependencies: ["EnsembleModel"]),
    ]
)
