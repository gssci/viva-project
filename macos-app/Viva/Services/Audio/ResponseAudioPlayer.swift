import AVFoundation
import Combine
import Foundation

@MainActor
final class ResponseAudioPlayer: NSObject, ObservableObject, AVAudioPlayerDelegate {
    private static let streamingPCMContentType = "application/vnd.viva.pcm-f32"
    private static let pcmBytesPerFrame = MemoryLayout<Float>.size
    private static let schedulingChunkByteCount = 16 * 1024

    private var audioPlayer: AVAudioPlayer?
    private var audioEngine: AVAudioEngine?
    private var playerNode: AVAudioPlayerNode?
    private var timePitchUnit: AVAudioUnitTimePitch?
    private var streamTask: Task<Void, Never>?
    private var playbackID = UUID()
    private var scheduledBufferCount = 0
    private var streamDidEnd = false

    @Published private(set) var isPlaying = false
    @Published private(set) var isPaused = false
    @Published private(set) var hasPlayableAudio = false

    override init() {
        super.init()
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(speechRateChanged),
            name: .vivaTTSSpeechRateChanged,
            object: nil
        )
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    func play(from url: URL) async {
        stop()

        let currentPlaybackID = UUID()
        playbackID = currentPlaybackID

        do {
            let (bytes, response) = try await URLSession.shared.bytes(from: url)
            guard playbackID == currentPlaybackID else { return }
            guard let httpResponse = response as? HTTPURLResponse,
                  200..<300 ~= httpResponse.statusCode else {
                throw URLError(.badServerResponse)
            }

            if isStreamingPCMResponse(httpResponse) {
                try prepareStreamingPCMPlayback(from: httpResponse)
                streamTask = Task { [weak self] in
                    await self?.consumeStreamingPCM(
                        bytes,
                        playbackID: currentPlaybackID
                    )
                }
            } else {
                try await playBufferedAudio(
                    bytes,
                    playbackID: currentPlaybackID
                )
            }
        } catch {
            guard playbackID == currentPlaybackID else { return }
            stop()
            print("TTS Playback Error: \(error.localizedDescription)")
        }
    }

    func togglePaused() {
        guard hasPlayableAudio else { return }
        isPaused ? resume() : pause()
    }

    func pause() {
        guard hasPlayableAudio else { return }
        audioPlayer?.pause()
        playerNode?.pause()
        isPlaying = false
        isPaused = true
    }

    func resume() {
        guard hasPlayableAudio, isPaused else { return }
        isPaused = false

        if let audioPlayer {
            isPlaying = audioPlayer.play()
        } else if let playerNode {
            playerNode.play()
            isPlaying = playerNode.isPlaying
        }
    }

    func stop() {
        streamTask?.cancel()
        streamTask = nil
        audioPlayer?.stop()
        audioPlayer = nil
        playerNode?.stop()
        audioEngine?.stop()
        playerNode = nil
        timePitchUnit = nil
        audioEngine = nil
        scheduledBufferCount = 0
        streamDidEnd = false
        hasPlayableAudio = false
        isPlaying = false
        isPaused = false
        playbackID = UUID()
    }

    private func isStreamingPCMResponse(_ response: HTTPURLResponse) -> Bool {
        let contentType = response.value(forHTTPHeaderField: "Content-Type") ?? ""
        return contentType
            .lowercased()
            .contains(Self.streamingPCMContentType)
    }

    private func prepareStreamingPCMPlayback(from response: HTTPURLResponse) throws {
        let sampleRate = Double(
            response.value(forHTTPHeaderField: "X-Audio-Sample-Rate") ?? ""
        ) ?? 24_000
        guard let format = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: sampleRate,
            channels: 1,
            interleaved: false
        ) else {
            throw URLError(.cannotDecodeContentData)
        }

        let engine = AVAudioEngine()
        let node = AVAudioPlayerNode()
        let timePitch = AVAudioUnitTimePitch()
        timePitch.rate = VivaTTSSpeechRate.selected.value

        engine.attach(node)
        engine.attach(timePitch)
        engine.connect(node, to: timePitch, format: format)
        engine.connect(timePitch, to: engine.mainMixerNode, format: format)
        try engine.start()

        audioEngine = engine
        playerNode = node
        timePitchUnit = timePitch
        hasPlayableAudio = true
        isPaused = false
        isPlaying = false
    }

    private func consumeStreamingPCM(
        _ bytes: URLSession.AsyncBytes,
        playbackID: UUID
    ) async {
        var pendingData = Data()
        pendingData.reserveCapacity(Self.schedulingChunkByteCount)

        do {
            for try await byte in bytes {
                try Task.checkCancellation()
                guard self.playbackID == playbackID else { return }

                pendingData.append(byte)
                if pendingData.count >= Self.schedulingChunkByteCount {
                    schedulePlayablePCMBytes(
                        from: &pendingData,
                        playbackID: playbackID
                    )
                }
            }

            schedulePlayablePCMBytes(
                from: &pendingData,
                playbackID: playbackID
            )

            if !pendingData.isEmpty {
                print("Dropped partial PCM frame: \(pendingData.count) bytes")
            }

            markStreamEnded(playbackID: playbackID)
        } catch {
            guard !Task.isCancelled, self.playbackID == playbackID else { return }
            stop()
            print("TTS Stream Error: \(error.localizedDescription)")
        }
    }

    private func schedulePlayablePCMBytes(
        from pendingData: inout Data,
        playbackID: UUID
    ) {
        let playableByteCount = pendingData.count - (pendingData.count % Self.pcmBytesPerFrame)
        guard playableByteCount > 0 else { return }

        let chunk = Data(pendingData.prefix(playableByteCount))
        pendingData.removeFirst(playableByteCount)
        schedulePCMData(chunk, playbackID: playbackID)
    }

    private func schedulePCMData(_ data: Data, playbackID: UUID) {
        guard self.playbackID == playbackID,
              let playerNode else {
            return
        }

        let format = playerNode.outputFormat(forBus: 0)
        let frameCount = data.count / Self.pcmBytesPerFrame
        guard frameCount > 0,
              let buffer = AVAudioPCMBuffer(
                pcmFormat: format,
                frameCapacity: AVAudioFrameCount(frameCount)
              ),
              let channelData = buffer.floatChannelData?[0] else {
            return
        }

        buffer.frameLength = AVAudioFrameCount(frameCount)
        data.withUnsafeBytes { rawBuffer in
            let destination = UnsafeMutableRawBufferPointer(
                start: channelData,
                count: data.count
            )
            _ = rawBuffer.copyBytes(to: destination)
        }

        scheduledBufferCount += 1
        playerNode.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
            Task { @MainActor in
                self?.bufferFinished(playbackID: playbackID)
            }
        }

        if !isPaused, !playerNode.isPlaying {
            playerNode.play()
            isPlaying = playerNode.isPlaying
        }
    }

    private func bufferFinished(playbackID: UUID) {
        guard self.playbackID == playbackID else { return }
        scheduledBufferCount = max(0, scheduledBufferCount - 1)
        finishStreamPlaybackIfNeeded(playbackID: playbackID)
    }

    private func markStreamEnded(playbackID: UUID) {
        guard self.playbackID == playbackID else { return }
        streamDidEnd = true
        finishStreamPlaybackIfNeeded(playbackID: playbackID)
    }

    private func finishStreamPlaybackIfNeeded(playbackID: UUID) {
        guard self.playbackID == playbackID,
              streamDidEnd,
              scheduledBufferCount == 0 else {
            return
        }

        playerNode?.stop()
        audioEngine?.stop()
        playerNode = nil
        timePitchUnit = nil
        audioEngine = nil
        streamTask = nil
        streamDidEnd = false
        hasPlayableAudio = false
        isPlaying = false
        isPaused = false
    }

    private func playBufferedAudio(
        _ bytes: URLSession.AsyncBytes,
        playbackID: UUID
    ) async throws {
        var data = Data()
        for try await byte in bytes {
            try Task.checkCancellation()
            guard self.playbackID == playbackID else { return }
            data.append(byte)
        }

        guard self.playbackID == playbackID else { return }

        let player = try AVAudioPlayer(data: data)
        player.enableRate = true
        player.rate = VivaTTSSpeechRate.selected.value
        audioPlayer = player
        player.delegate = self
        player.prepareToPlay()
        hasPlayableAudio = true
        isPaused = false
        isPlaying = player.play()
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in
            if self.audioPlayer === player {
                self.audioPlayer = nil
                self.hasPlayableAudio = false
                self.isPlaying = false
                self.isPaused = false
            }
        }
    }

    @objc private func speechRateChanged() {
        let rate = VivaTTSSpeechRate.selected.value
        audioPlayer?.rate = rate
        timePitchUnit?.rate = rate
    }
}
