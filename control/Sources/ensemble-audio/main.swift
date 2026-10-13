// Tests the CoreAudio device "Ensemble".
// Usage: ensemble-audio check [sample rate to set first]
//        ensemble-audio play <seconds> <channel> <value>
//        ensemble-audio capture <seconds> <channel>...
import CoreAudio
import EnsembleIO
import Foundation

let arguments = Array(CommandLine.arguments.dropFirst(2))
switch CommandLine.arguments.dropFirst().first {
case "check":
    check(arguments)
case "play":
    play(arguments)
case "capture":
    capture(arguments)
default:
    fail("usage: ensemble-audio check [rate] | play <seconds> <channel> <value> | capture <seconds> <channel>...",
         status: 2)
}

func fail(_ message: String, status: Int32 = 1) -> Never {
    FileHandle.standardError.write(Data("ensemble-audio: \(message)\n".utf8))
    exit(status)
}

func ensemble() -> AudioObjectID {
    guard let device = findEnsemble() else {
        fail("no device named Ensemble")
    }
    return device
}
