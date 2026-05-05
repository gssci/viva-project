import AVFoundation
import Combine
import Foundation

@MainActor
final class ResponseAudioPlayer: NSObject, ObservableObject, AVAudioPlayerDelegate {
    private var audioPlayer: AVAudioPlayer?
    @Published private(set) var isPlaying = false
    @Published private(set) var isPaused = false
    @Published private(set) var hasPlayableAudio = false

    func play(from url: URL) async {
        do {
            stop()

            let (data, response) = try await URLSession.shared.data(from: url)
            guard let httpResponse = response as? HTTPURLResponse,
                  200..<300 ~= httpResponse.statusCode else {
                throw URLError(.badServerResponse)
            }

            let player = try AVAudioPlayer(data: data)
            audioPlayer = player
            player.delegate = self
            player.prepareToPlay()
            hasPlayableAudio = true
            isPaused = false
            isPlaying = player.play()
        } catch {
            stop()
            print("TTS Playback Error: \(error.localizedDescription)")
        }
    }

    func togglePaused() {
        guard hasPlayableAudio else { return }
        isPaused ? resume() : pause()
    }

    func pause() {
        guard let audioPlayer, audioPlayer.isPlaying else { return }
        audioPlayer.pause()
        isPlaying = false
        isPaused = true
    }

    func resume() {
        guard let audioPlayer, isPaused else { return }
        isPaused = false
        isPlaying = audioPlayer.play()
    }

    func stop() {
        audioPlayer?.stop()
        audioPlayer = nil
        hasPlayableAudio = false
        isPlaying = false
        isPaused = false
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
}
