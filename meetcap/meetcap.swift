// meetcap: records a call as two 16 kHz mono WAVs from one ScreenCaptureKit stream: what the Mac plays (the
// other people) and the microphone (you). No bot joins the call and no audio driver is installed.
//
//   meetcap <them.wav> [<me.wav>]     records until it gets SIGINT or SIGTERM, then closes the files cleanly.
//
// Both tracks share the stream's clock, and any gap in either is filled with silence by its timestamp, so
// second 600 in one file is second 600 in the other.
//
// Once a second it prints "level <rms>" for the call side, so Hammerspoon can tell when the call has gone quiet.
// Five times a second it prints "lv <them> <me>", and it keeps them-live.raw (the call side as it arrives, 16 kHz
// mono 16-bit), for the pitch timer that listens for open questions.
// Rebuild: swiftc -O meetcap.swift -o meetcap

import AVFoundation
import Foundation
import ScreenCaptureKit

let RATE = 16000.0

/// One output file. Converts whatever arrives to 16 kHz mono and places it by its timestamp.
final class Track {
    private let url: URL
    private let target = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: RATE, channels: 1, interleaved: false)!
    private var file: AVAudioFile?
    private var converter: AVAudioConverter?
    private var written: Int64 = 0
    private var live: FileHandle?                    // them-live.raw: the same audio as it arrives, for the pitch timer

    init(url: URL, live: URL? = nil) {
        self.url = url
        if let live {
            FileManager.default.createFile(atPath: live.path, contents: nil)
            self.live = try? FileHandle(forWritingTo: live)
        }
    }

    private func appendLive(_ b: AVAudioPCMBuffer) {
        guard let live, let ch = b.floatChannelData?[0], b.frameLength > 0 else { return }
        var ints = [Int16](repeating: 0, count: Int(b.frameLength))
        for i in 0..<ints.count { ints[i] = Int16(max(-1, min(1, ch[i])) * 32767) }
        ints.withUnsafeBufferPointer { live.write(Data(buffer: $0)) }
    }

    /// `at` is where this buffer starts, in seconds since the recording began.
    func write(_ pcm: AVAudioPCMBuffer, at: Double) {
        if file == nil {
            let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: RATE,
                                           AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16,
                                           AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false]
            file = try? AVAudioFile(forWriting: url, settings: settings, commonFormat: .pcmFormatFloat32, interleaved: false)
        }
        if converter == nil || converter!.inputFormat != pcm.format {
            converter = AVAudioConverter(from: pcm.format, to: target)
        }
        guard let file, let converter else { return }

        // A gap of more than 50 ms means buffers were lost: fill it with silence so the clock stays true.
        let due = Int64(max(0, at) * RATE)
        if due - written > Int64(RATE / 20), let gap = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: AVAudioFrameCount(due - written)) {
            gap.frameLength = gap.frameCapacity          // freshly allocated, so already zeros
            try? file.write(from: gap)
            appendLive(gap)
            written += Int64(gap.frameLength)
        }

        let cap = AVAudioFrameCount(Double(pcm.frameLength) * RATE / pcm.format.sampleRate) + 64
        guard let out = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: cap) else { return }
        var fed = false
        var err: NSError?
        converter.convert(to: out, error: &err) { _, status in
            if fed { status.pointee = .noDataNow; return nil }
            fed = true; status.pointee = .haveData; return pcm
        }
        if err == nil, out.frameLength > 0 {
            try? file.write(from: out)
            appendLive(out)
            written += Int64(out.frameLength)
        }
    }

    func close() {
        file = nil                                  // closing the AVAudioFile finishes the WAV header
        try? live?.close(); live = nil
    }
}

final class Capture: NSObject, SCStreamOutput, SCStreamDelegate {
    private let them: Track
    private let me: Track?
    private var stream: SCStream?
    private var t0: Double?                          // stream time of the first buffer from either side
    private let lock = NSLock()
    private var sumSquares: Float = 0
    private var samples = 0
    private var lastReport = Date()
    // Five times a second, both sides' loudness ("lv <them> <me>"), for the live pitch timer.
    private var liveSq: [Float] = [0, 0], liveN: [Int] = [0, 0]
    private var lastLive = Date()

    init(them: URL, me: URL?) {
        self.them = Track(url: them, live: them.deletingLastPathComponent().appendingPathComponent("them-live.raw"))
        self.me = me.map { Track(url: $0) }
    }

    func start() async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard let display = content.displays.first else {
            throw NSError(domain: "meetcap", code: 1, userInfo: [NSLocalizedDescriptionKey: "no display"])
        }
        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.sampleRate = Int(RATE)
        config.channelCount = 1
        config.captureMicrophone = me != nil          // the default input device, same as the call uses
        // Audio is all that's wanted; the smallest, slowest video keeps the cost near zero.
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        let s = SCStream(filter: filter, configuration: config, delegate: self)
        let queue = DispatchQueue(label: "meetcap.audio")   // one queue, so the two tracks never race
        try s.addStreamOutput(self, type: .audio, sampleHandlerQueue: queue)
        if me != nil { try s.addStreamOutput(self, type: .microphone, sampleHandlerQueue: queue) }
        try await s.startCapture()
        stream = s
    }

    func stop() async {
        try? await stream?.stopCapture()
        lock.withLock { them.close(); me?.close() }
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio || type == .microphone, sb.isValid, let desc = sb.formatDescription,
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(desc),
              let format = AVAudioFormat(streamDescription: asbd) else { return }
        let track = type == .audio ? them : me
        guard let track else { return }
        let pts = sb.presentationTimeStamp.seconds
        lock.lock(); defer { lock.unlock() }
        if t0 == nil { t0 = pts }
        let at = pts - t0!
        try? sb.withAudioBufferList { list, _ in
            guard let pcm = AVAudioPCMBuffer(pcmFormat: format, bufferListNoCopy: list.unsafePointer) else { return }
            track.write(pcm, at: at)
            if let ch = pcm.floatChannelData?[0] {
                let k = type == .audio ? 0 : 1
                for i in 0..<Int(pcm.frameLength) { liveSq[k] += ch[i] * ch[i] }
                liveN[k] += Int(pcm.frameLength)
            }
            if Date().timeIntervalSince(lastLive) >= 0.2 {
                let rms = (0..<2).map { liveN[$0] > 0 ? (liveSq[$0] / Float(liveN[$0])).squareRoot() : 0 }
                print(String(format: "lv %.5f %.5f", rms[0], rms[1]))
                fflush(stdout)
                liveSq = [0, 0]; liveN = [0, 0]; lastLive = Date()
            }
            guard type == .audio else { return }
            if let ch = pcm.floatChannelData?[0] {
                for i in 0..<Int(pcm.frameLength) { sumSquares += ch[i] * ch[i] }
                samples += Int(pcm.frameLength)
            }
            if Date().timeIntervalSince(lastReport) >= 1, samples > 0 {
                print(String(format: "level %.5f", (sumSquares / Float(samples)).squareRoot()))
                fflush(stdout)
                sumSquares = 0; samples = 0; lastReport = Date()
            }
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        FileHandle.standardError.write("meetcap stopped: \(error.localizedDescription)\n".data(using: .utf8)!)
        lock.withLock { them.close(); me?.close() }
        exit(2)
    }
}

let args = CommandLine.arguments
guard args.count == 2 || args.count == 3 else {
    FileHandle.standardError.write("usage: meetcap <them.wav> [<me.wav>]\n".data(using: .utf8)!)
    exit(64)
}
let capture = Capture(them: URL(fileURLWithPath: args[1]), me: args.count == 3 ? URL(fileURLWithPath: args[2]) : nil)

// Stop cleanly on Ctrl-C or kill, so the files are always playable.
var sources: [DispatchSourceSignal] = []
for sig in [SIGINT, SIGTERM] {
    signal(sig, SIG_IGN)
    let src = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    src.setEventHandler { Task { await capture.stop(); exit(0) } }
    src.resume()
    sources.append(src)
}

Task {
    do { try await capture.start() } catch {
        FileHandle.standardError.write("meetcap could not start: \(error.localizedDescription)\n".data(using: .utf8)!)
        exit(1)
    }
}
dispatchMain()
