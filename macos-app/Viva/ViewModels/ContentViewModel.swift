import AVFoundation
import AppKit
import Combine
import Foundation
import SwiftUI

@MainActor
final class ContentViewModel: ObservableObject {
    @Published var textInput = ""
    @Published var isRecording = false
    @Published var isTranscribing = false
    @Published var isSendingToAI = false
    @Published var shareScreen = false
    @Published var agentResponse = ""

    let responseAudioPlayer: ResponseAudioPlayer

    private let recorder: AudioRecorder
    private let apiClient: VivaAPIClient
    private var aiRequestTask: Task<Void, Never>?
    private var activeVivaRequestID: String?
    private var cancellables = Set<AnyCancellable>()
    private var selectedTTSVoiceGender: VivaTTSVoiceGender {
        let rawValue = UserDefaults.standard.string(forKey: VivaUserDefaults.ttsVoiceGenderKey)
        return VivaTTSVoiceGender(rawValue: rawValue ?? "") ?? .female
    }

    convenience init() {
        self.init(
            recorder: AudioRecorder(),
            responseAudioPlayer: ResponseAudioPlayer(),
            apiClient: VivaAPIClient()
        )
    }

    init(
        recorder: AudioRecorder,
        responseAudioPlayer: ResponseAudioPlayer,
        apiClient: VivaAPIClient
    ) {
        self.recorder = recorder
        self.responseAudioPlayer = responseAudioPlayer
        self.apiClient = apiClient

        responseAudioPlayer.objectWillChange
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)
    }

    func requestAudioAccess() {
        AVCaptureDevice.requestAccess(for: .audio) { _ in }
    }

    func startRecording() {
        guard !isRecording else { return }
        recorder.startRecording()
        isRecording = recorder.isCurrentlyRecording

        if !isRecording {
            agentResponse = "Could not start recording."
        }
    }

    func stopRecording() {
        guard isRecording else { return }
        isRecording = false
        guard let url = recorder.stopRecording() else {
            textInput = "Could not find recorded audio."
            return
        }

        if UserDefaults.standard.bool(forKey: VivaUserDefaults.nativeAudioModeKey) {
            sendNativeAudio(fileURL: url, ttsEnabled: UserDefaults.standard.bool(forKey: VivaUserDefaults.playTTSAudioKey))
        } else {
            Task {
                await transcribeAudio(fileURL: url)
            }
        }
    }

    func sendToAI(ttsEnabled: Bool) {
        let currentText = textInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !currentText.isEmpty, !isSendingToAI else { return }
        let requestID = UUID().uuidString

        aiRequestTask = Task {
            isSendingToAI = true
            activeVivaRequestID = requestID
            agentResponse = ""
            responseAudioPlayer.stop()

            defer {
                if activeVivaRequestID == requestID {
                    isSendingToAI = false
                    activeVivaRequestID = nil
                    aiRequestTask = nil
                }
            }

            var screenshot: NSImage?
            if shareScreen {
                screenshot = try? await ScreenShotManager.captureMainDisplay()
            }

            do {
                try Task.checkCancellation()
                let response = try await apiClient.sendVivaRequest(
                    text: currentText,
                    image: screenshot,
                    requestID: requestID,
                    ttsEnabled: ttsEnabled,
                    ttsVoiceGender: selectedTTSVoiceGender
                )
                try Task.checkCancellation()

                textInput = ""
                await handleVivaResponse(response, ttsEnabled: ttsEnabled)
            } catch {
                let wasCancelled = Task.isCancelled || (error as? URLError)?.code == .cancelled
                agentResponse = wasCancelled ? "Request cancelled." : "Viva request failed: \(error.localizedDescription)"
            }
        }
    }

    func cancelAIRequest() {
        guard isSendingToAI, let requestID = activeVivaRequestID else { return }

        responseAudioPlayer.stop()
        aiRequestTask?.cancel()

        Task {
            do {
                try await apiClient.cancelVivaRequest(requestID: requestID)
            } catch {
                print("Cancel Request Error: \(error.localizedDescription)")
            }
        }
    }

    func stopResponseAudio() {
        responseAudioPlayer.stop()
    }

    private func sendNativeAudio(fileURL: URL, ttsEnabled: Bool) {
        guard !isSendingToAI else { return }
        let requestID = UUID().uuidString

        aiRequestTask = Task {
            isSendingToAI = true
            activeVivaRequestID = requestID
            textInput = ""
            agentResponse = ""
            responseAudioPlayer.stop()

            defer {
                if activeVivaRequestID == requestID {
                    isSendingToAI = false
                    activeVivaRequestID = nil
                    aiRequestTask = nil
                }
            }

            var screenshot: NSImage?
            if shareScreen {
                screenshot = try? await ScreenShotManager.captureMainDisplay()
            }

            do {
                try Task.checkCancellation()
                let response = try await apiClient.sendVivaNativeAudioRequest(
                    fileURL: fileURL,
                    image: screenshot,
                    requestID: requestID,
                    ttsEnabled: ttsEnabled,
                    ttsVoiceGender: selectedTTSVoiceGender
                )
                try Task.checkCancellation()

                await handleVivaResponse(response, ttsEnabled: ttsEnabled)
            } catch {
                let wasCancelled = Task.isCancelled || (error as? URLError)?.code == .cancelled
                agentResponse = wasCancelled ? "Request cancelled." : "Viva request failed: \(error.localizedDescription)"
            }
        }
    }

    private func handleVivaResponse(_ response: VivaResponse, ttsEnabled: Bool) async {
        agentResponse = response.text

        if let ttsError = response.ttsError {
            print("TTS Error: \(ttsError)")
        }

        if let audioURL = response.audioURL, ttsEnabled {
            await responseAudioPlayer.play(from: audioURL)
        }
    }

    private func transcribeAudio(fileURL: URL) async {
        isTranscribing = true
        defer { isTranscribing = false }

        do {
            let transcribedText = try await apiClient.transcribeAudio(fileURL: fileURL)
            textInput = transcribedText

            if !transcribedText.isEmpty {
                sendToAI(ttsEnabled: UserDefaults.standard.bool(forKey: VivaUserDefaults.playTTSAudioKey))
            }
        } catch {
            print("Transcription Error: \(error.localizedDescription)")
            textInput = "Error connecting to transcriber."
        }
    }
}
