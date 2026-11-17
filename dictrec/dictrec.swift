// dictrec: the microphone recorder behind Fn dictation. Replaces ffmpeg, which took about half a
// second to start listening, so the first words of every dictation were lost.
//
// It stays running (Hammerspoon starts it once) and takes one command per line on stdin:
//   start <file.wav>   turn the mic on and record to a 16 kHz mono WAV. Prints "on <ms>" when sound is flowing.
//   stop               keep recording TAIL seconds more (the last word), then close the file. Prints "done <file>".
//   cancel             stop now and delete the file. Prints "cancelled".
// The mic is only on between start and stop/cancel, so the orange dot shows only while you dictate.
// Rebuild: swiftc -O dictrec.swift -o dictrec
//
// it always uses the MacBook's own microphone, not whatever macOS calls the default. With Bluetooth
// WH-1000XM4 headphones as the default, the recorder crashed (the headphones change format when their mic turns
// on), and a Bluetooth headset mic is narrow, muffled audio that Whisper mishears ("Nova's night was gone").
// Only if the Mac has no built-in mic (lid closed on a monitor, say) does it fall back to the default one.

import AVFoundation
import CoreAudio
import Foundation

/// The MacBook's own microphone, or nil if there isn't one to use.
func builtInMic() -> AudioDeviceID? {
    var addr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDevices,
                                          mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var size: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size) == noErr else { return nil }
    var ids = [AudioDeviceID](repeating: 0, count: Int(size) / MemoryLayout<AudioDeviceID>.size)
    guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &ids) == noErr else { return nil }
    for id in ids {
        var t: UInt32 = 0, ts = UInt32(4)
        var ta = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyTransportType,
                                            mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        guard AudioObjectGetPropertyData(id, &ta, 0, nil, &ts, &t) == noErr, t == kAudioDeviceTransportTypeBuiltIn else { continue }
        var sa = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyStreams,
                                            mScope: kAudioDevicePropertyScopeInput, mElement: kAudioObjectPropertyElementMain)
        var ss: UInt32 = 0
        if AudioObjectGetPropertyDataSize(id, &sa, 0, nil, &ss) == noErr, ss > 0 { return id }
    }
    return nil
}

let RATE = 16000.0
let TAIL = 0.3
setvbuf(stdout, nil, _IOLBF, 0)

final class Recorder: NSObject, AVCaptureAudioDataOutputSampleBufferDelegate {
    // AVCaptureSession, not AVAudioEngine: the engine insists on the Mac's default input (your Bluetooth
    // headphones) and crashed when pointed at the built-in mic. A capture session takes a named device.
    private let session = AVCaptureSession()
    private var file: AVAudioFile?
    private var converter: AVAudioConverter?
    private var path = ""
    private var startedAt = Date()
    private var announced = false
    private var take = 0                        // ignores a late tail-stop from an earlier dictation
    private var stopping = false                // a stop is waiting out its tail
    let q = DispatchQueue(label: "dictrec")
    private let target = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: RATE, channels: 1, interleaved: false)!

    func setUp() {
        q.async {
            let devices = AVCaptureDevice.DiscoverySession(deviceTypes: [.microphone], mediaType: .audio,
                                                           position: .unspecified).devices
            let builtIn = devices.first { d in
                guard let id = builtInMic() else { return false }
                var uid: CFString = "" as CFString, size = UInt32(MemoryLayout<CFString>.size)
                var a = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyDeviceUID,
                                                   mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
                guard AudioObjectGetPropertyData(id, &a, 0, nil, &size, &uid) == noErr else { return false }
                return d.uniqueID == (uid as String)
            }
            guard let mic = builtIn ?? AVCaptureDevice.default(for: .audio),
                  let input = try? AVCaptureDeviceInput(device: mic) else { print("error no microphone"); return }
            self.session.beginConfiguration()
            if self.session.canAddInput(input) { self.session.addInput(input) }
            let out = AVCaptureAudioDataOutput()
            out.audioSettings = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: RATE, AVNumberOfChannelsKey: 1,
                                 AVLinearPCMBitDepthKey: 32, AVLinearPCMIsFloatKey: true,
                                 AVLinearPCMIsNonInterleaved: true, AVLinearPCMIsBigEndianKey: false]
            out.setSampleBufferDelegate(self, queue: self.q)
            if self.session.canAddOutput(out) { self.session.addOutput(out) }
            self.session.commitConfiguration()
            // The very first start takes half a second; do it now (nothing is saved) so your first dictation is quick.
            self.session.startRunning(); self.session.stopRunning()
            print("mic \(mic.localizedName)")
        }
    }

    func captureOutput(_ output: AVCaptureOutput, didOutput sb: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard file != nil, let desc = sb.formatDescription,
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(desc),
              let format = AVAudioFormat(streamDescription: asbd) else { return }
        let frames = AVAudioFrameCount(CMSampleBufferGetNumSamples(sb))
        guard let pcm = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames) else { return }
        pcm.frameLength = frames
        guard CMSampleBufferCopyPCMDataIntoAudioBufferList(sb, at: 0, frameCount: Int32(frames),
                                                           into: pcm.mutableAudioBufferList) == noErr else { return }
        write(pcm)
    }

    func start(_ p: String) {
        q.async {
            if self.stopping {                      // pressed again during the last one's tail: finish it now
                let old = self.path
                self.closeNow(delete: false)
                print("done \(old)")
            } else { self.closeNow(delete: false) }
            self.stopping = false
            self.take += 1
            self.path = p
            self.startedAt = Date()
            self.announced = false
            try? FileManager.default.removeItem(atPath: p)
            let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: RATE,
                                           AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16,
                                           AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false]
            self.file = try? AVAudioFile(forWriting: URL(fileURLWithPath: p), settings: settings,
                                         commonFormat: .pcmFormatFloat32, interleaved: false)
            self.converter = nil
            if !self.session.isRunning { self.session.startRunning() }
        }
    }

    private func write(_ pcm: AVAudioPCMBuffer) {
        guard let file else { return }
        if converter == nil || converter!.inputFormat != pcm.format {
            converter = AVAudioConverter(from: pcm.format, to: target)
        }
        guard let converter else { return }
        if !announced {
            announced = true
            print("on \(Int(Date().timeIntervalSince(startedAt) * 1000))")
        }
        let cap = AVAudioFrameCount(Double(pcm.frameLength) * RATE / pcm.format.sampleRate) + 64
        guard let out = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: cap) else { return }
        var fed = false
        var err: NSError?
        converter.convert(to: out, error: &err) { _, status in
            if fed { status.pointee = .noDataNow; return nil }
            fed = true; status.pointee = .haveData; return pcm
        }
        if err == nil, out.frameLength > 0 { try? file.write(from: out) }
    }

    func stop() {
        q.async {
            let mine = self.take
            self.stopping = true
            self.q.asyncAfter(deadline: .now() + TAIL) {
                guard mine == self.take, self.file != nil else { return }
                let p = self.path
                self.stopping = false
                self.closeNow(delete: false)
                print("done \(p)")
            }
        }
    }

    func cancel() {
        q.async {
            self.take += 1
            self.stopping = false
            self.closeNow(delete: true)
            print("cancelled")
        }
    }

    private func closeNow(delete: Bool) {
        if session.isRunning { session.stopRunning() }
        file = nil                                  // closing the AVAudioFile finishes the WAV header
        converter = nil
        if delete, !path.isEmpty { try? FileManager.default.removeItem(atPath: path) }
    }
}

let rec = Recorder()
rec.setUp()
DispatchQueue.global().async {
    while let line = readLine() {
        let parts = line.split(separator: " ", maxSplits: 1).map(String.init)
        switch parts.first {
        case "start" where parts.count == 2: rec.start(parts[1])
        case "stop": rec.stop()
        case "cancel": rec.cancel()
        default: break
        }
    }
    exit(0)                                         // Hammerspoon went away
}
dispatchMain()
