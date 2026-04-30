import SwiftUI
import AVFoundation
import AppKit
import Combine

private struct VivaResponse: Decodable {
    let text: String
    let processingTime: Double?
    let usedScreenshot: Bool?
    let audioURL: URL?
    let audioContentType: String?
    let ttsLanguage: String?
    let ttsVoice: String?
    let ttsProcessingTime: Double?
    let ttsError: String?

    private enum CodingKeys: String, CodingKey {
        case text
        case processingTime = "processing_time"
        case usedScreenshot = "used_screenshot"
        case audioURL = "audio_url"
        case audioContentType = "audio_content_type"
        case ttsLanguage = "tts_language"
        case ttsVoice = "tts_voice"
        case ttsProcessingTime = "tts_processing_time"
        case ttsError = "tts_error"
    }
}

// MARK: - Helper to convert NSImage to JPEG Data
extension NSImage {
    var jpegData: Data? {
        guard let tiffRepresentation = tiffRepresentation,
              let bitmapImage = NSBitmapImageRep(data: tiffRepresentation) else { return nil }
        return bitmapImage.representation(using: .jpeg, properties: [:])
    }
}

// MARK: - Audio Recorder Management
class AudioRecorder: NSObject, ObservableObject {
    var audioRecorder: AVAudioRecorder?
    var recordingURL: URL?
    
    @Published var isCurrentlyRecording: Bool = false
    
    override init() {
        super.init()
        let tempDir = FileManager.default.temporaryDirectory
        recordingURL = tempDir.appendingPathComponent("whisper_recording.wav")
    }
    
    func startRecording() {
        guard let url = recordingURL else { return }
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatLinearPCM),
            AVSampleRateKey: 16000.0,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false
        ]
        
        do {
            audioRecorder = try AVAudioRecorder(url: url, settings: settings)
            audioRecorder?.prepareToRecord()
            audioRecorder?.record()
            isCurrentlyRecording = true
        } catch {
            print("Failed to start recording: \(error.localizedDescription)")
        }
    }
    
    func stopRecording() -> URL? {
        audioRecorder?.stop()
        isCurrentlyRecording = false
        return recordingURL
    }
}

// MARK: - Response Audio Playback
@MainActor
class ResponseAudioPlayer: NSObject, ObservableObject, AVAudioPlayerDelegate {
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

        if isPaused {
            resume()
        } else {
            pause()
        }
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

private struct GlossyGlassCapsule: View {
    let isActive: Bool
    let rotation: Double

    var body: some View {
        Capsule()
            .fill(.regularMaterial)
            .overlay(
                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(0.30),
                                Color.white.opacity(0.12),
                                Color.black.opacity(0.05)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            )
            .overlay(
                Capsule()
                    .strokeBorder(neutralGlossGradient, lineWidth: isActive ? 1.8 : 1.1)
            )
            .shadow(color: .white.opacity(0.10), radius: 2, x: 0, y: -1)
            .shadow(color: .black.opacity(0.08), radius: 4, x: 0, y: 3)
    }

    private var neutralGlossGradient: AngularGradient {
        AngularGradient(
            gradient: Gradient(colors: [
                Color.white.opacity(isActive ? 0.78 : 0.42),
                Color.gray.opacity(isActive ? 0.18 : 0.12),
                Color.white.opacity(isActive ? 0.50 : 0.28),
                Color.black.opacity(isActive ? 0.12 : 0.06),
                Color.white.opacity(isActive ? 0.78 : 0.42)
            ]),
            center: .center,
            angle: .degrees(isActive ? rotation : 0)
        )
    }
}

private struct GlossyGlassRoundedRectangle: View {
    let isPlaying: Bool
    let rotation: Double

    var body: some View {
        RoundedRectangle(cornerRadius: 14, style: .continuous)
            .fill(.regularMaterial)
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(0.24),
                                Color.white.opacity(0.10),
                                Color.black.opacity(0.04)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(
                        AngularGradient(
                            gradient: Gradient(colors: [
                                Color.white.opacity(0.22),
                                Color.gray.opacity(0.04),
                                Color.white.opacity(0.12),
                                Color.clear,
                                Color.white.opacity(0.22)
                            ]),
                            center: .center,
                            angle: .degrees(rotation)
                        )
                    )
                    .opacity(isPlaying ? 1 : 0)
                    .blendMode(.screen)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(
                        AngularGradient(
                            gradient: Gradient(colors: [
                                Color.white.opacity(isPlaying ? 0.62 : 0.36),
                                Color.gray.opacity(0.12),
                                Color.white.opacity(isPlaying ? 0.40 : 0.24),
                                Color.black.opacity(0.08),
                                Color.white.opacity(isPlaying ? 0.62 : 0.36)
                            ]),
                            center: .center,
                            angle: .degrees(isPlaying ? rotation : 0)
                        ),
                        lineWidth: isPlaying ? 1.35 : 1
                    )
            )
    }
}

private struct ResponseTextHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

private struct ResponseTextBox: View {
    let text: String
    let isPlaying: Bool
    let rotation: Double
    let togglePlayback: () -> Void

    @State private var measuredTextHeight: CGFloat = 0

    private let maxTextHeight: CGFloat = 62
    private var textViewportHeight: CGFloat {
        min(max(measuredTextHeight, 20), maxTextHeight)
    }
    private var shouldScroll: Bool {
        measuredTextHeight > maxTextHeight + 1
    }

    var body: some View {
        ScrollView(.vertical, showsIndicators: shouldScroll) {
            Text(text)
                .font(.callout)
                .foregroundColor(.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
                .background(
                    GeometryReader { proxy in
                        Color.clear.preference(key: ResponseTextHeightKey.self, value: proxy.size.height)
                    }
                )
                .frame(
                    maxWidth: .infinity,
                    minHeight: textViewportHeight,
                    alignment: shouldScroll ? .topLeading : .leading
                )
        }
        .frame(height: textViewportHeight, alignment: shouldScroll ? .top : .center)
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
            GlossyGlassRoundedRectangle(
                isPlaying: isPlaying,
                rotation: rotation
            )
        )
        .contentShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .onTapGesture(perform: togglePlayback)
        .onPreferenceChange(ResponseTextHeightKey.self) { measuredTextHeight = $0 }
    }
}

// MARK: - Main View
struct ContentView: View {
    @StateObject private var recorder = AudioRecorder()
    @StateObject private var responseAudioPlayer = ResponseAudioPlayer()
    @AppStorage(VivaUserDefaults.playTTSAudioKey) private var isTTSAudioEnabled = true
    
    // UI State
    @State private var textInput: String = ""
    @State private var isRecording = false
    @State private var isTranscribing = false
    @State private var isSendingToAI = false
    @State private var shareScreen: Bool = false
    @State private var agentResponse: String = ""
    @State private var aiRequestTask: Task<Void, Never>?
    @State private var activeVivaRequestID: String?
    
    // Allows us to auto-focus the text field so the cursor blinks immediately
    @FocusState private var isFocused: Bool
    
    // Animation State
    @State private var gradientRotation: Double = 0.0
    
    var body: some View {
        VStack(spacing: 8) {
            
            // MARK: - Main Liquid Glass Input Pill
            HStack(spacing: 8) {
                
                // 1. Mic Button
                ZStack {
                    Circle()
                        .fill(isRecording ? Color.red : Color.gray.opacity(0.15))
                    
                    Image(systemName: isRecording ? "waveform" : "mic.fill")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(isRecording ? .white : .primary.opacity(0.7))
                }
                .frame(width: 32, height: 32)
                .contentShape(Circle()) // Ensures the transparent parts are still clickable
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { _ in startRecording() }
                        .onEnded { _ in stopRecording() }
                )
                .help("Hold to speak")
                
                // 2. Screen Share Toggle
                Button(action: {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.6)) {
                        shareScreen.toggle()
                    }
                }) {
                    ZStack {
                        Circle()
                            .fill(shareScreen ? Color.purple : Color.gray.opacity(0.15))
                        
                        Image(systemName: shareScreen ? "macwindow.badge.plus" : "macwindow")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(shareScreen ? .white : .primary.opacity(0.7))
                    }
                    .frame(width: 32, height: 32)
                }
                .buttonStyle(.plain)
                .help("Share Screen Context")
                
                // 3. Text Field (Seamless & Auto-Focusing)
                TextField("Ask Viva...", text: $textInput)
                    .textFieldStyle(.plain)
                    .font(.system(size: 15, weight: .regular))
                    .padding(.horizontal, 4)
                    .focused($isFocused) // Ties the focus state to the text field
                    .onSubmit { sendToAI() }
                    .disabled(isTranscribing || isSendingToAI)
                
                // 4. Send Button
                Button(action: { isSendingToAI ? cancelAIRequest() : sendToAI() }) {
                    ZStack {
                        Circle()
                            .fill(isSendingToAI ? Color.red : (textInput.isEmpty ? Color.gray.opacity(0.15) : Color.blue))
                        
                        Image(systemName: isSendingToAI ? "xmark" : "arrow.up")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(isSendingToAI || !textInput.isEmpty ? .white : .primary.opacity(0.4))
                    }
                    .frame(width: 32, height: 32)
                }
                .buttonStyle(.plain)
                .disabled((textInput.isEmpty && !isSendingToAI) || isTranscribing)
                .help(isSendingToAI ? "Cancel Request" : "Send")
            }
            .padding(8)
            .background(
                GlossyGlassCapsule(
                    isActive: isRecording || isTranscribing || isSendingToAI,
                    rotation: gradientRotation
                )
            )
            
            // MARK: - Dynamic Status Pill
            if isTranscribing || isSendingToAI {
                HStack(spacing: 8) {
                    ProgressView()
                        .controlSize(.small)
                    Text(isTranscribing ? "Transcribing audio..." : "Viva is thinking...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(.regularMaterial)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(Color.white.opacity(0.12))
                        )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .strokeBorder(Color.white.opacity(0.30), lineWidth: 1)
                )
                .transition(.move(edge: .top).combined(with: .opacity))
            }

            if !agentResponse.isEmpty {
                ResponseTextBox(
                    text: agentResponse,
                    isPlaying: responseAudioPlayer.isPlaying,
                    rotation: gradientRotation
                ) {
                    responseAudioPlayer.togglePaused()
                }
                .transition(.move(edge: .top).combined(with: .opacity))
            }
            
            // Hidden Shortcut
            Button(action: { isRecording ? stopRecording() : startRecording() }) { Text("") }
            .keyboardShortcut("r", modifiers: .shift)
            .opacity(0).frame(width: 0, height: 0)
            
        }
        .padding(12)
        .frame(width: 360)
        .animation(.spring(response: 0.4, dampingFraction: 0.8), value: isTranscribing || isSendingToAI)
        .animation(.easeInOut(duration: 0.35), value: responseAudioPlayer.isPlaying)
        .onAppear {
            AVCaptureDevice.requestAccess(for: .audio) { _ in }
            withAnimation(.linear(duration: 3.0).repeatForever(autoreverses: false)) {
                gradientRotation = 360.0
            }
        }
        // Auto-focus the text field whenever the window becomes active
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            isFocused = true
        }
        .onReceive(NotificationCenter.default.publisher(for: .vivaTTSPlaybackDisabled)) { _ in
            responseAudioPlayer.stop()
        }
        .onChange(of: isTTSAudioEnabled) { _, isEnabled in
            if !isEnabled {
                responseAudioPlayer.stop()
            }
        }
    }
    
    // MARK: - Action Logic
    
    func startRecording() {
        guard !isRecording else { return }
        isRecording = true
        recorder.startRecording()
    }
    
    func stopRecording() {
        guard isRecording else { return }
        isRecording = false
        if let url = recorder.stopRecording() {
            transcribeAudio(fileURL: url)
        }
    }

    func sendToAI() {
        let currentText = textInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !currentText.isEmpty, !isSendingToAI else { return }
        let requestID = UUID().uuidString
        
        aiRequestTask = Task {
            await MainActor.run {
                isSendingToAI = true
                activeVivaRequestID = requestID
                agentResponse = ""
                responseAudioPlayer.stop()
            }

            defer {
                Task { @MainActor in
                    if activeVivaRequestID == requestID {
                        isSendingToAI = false
                        activeVivaRequestID = nil
                        aiRequestTask = nil
                    }
                }
            }

            var screenshot: NSImage? = nil
            if shareScreen {
                screenshot = try? await ScreenShotManager.captureMainDisplay()
            }

            do {
                try Task.checkCancellation()
                let response = try await sendFinalPayloadToAI(text: currentText, image: screenshot, requestID: requestID)
                try Task.checkCancellation()
                await MainActor.run {
                    textInput = ""
                    agentResponse = response.text
                }

                if let ttsError = response.ttsError {
                    print("TTS Error: \(ttsError)")
                }

                if let audioURL = response.audioURL, isTTSAudioEnabled {
                    await responseAudioPlayer.play(from: audioURL)
                }
            } catch {
                let wasCancelled = Task.isCancelled || (error as? URLError)?.code == .cancelled
                await MainActor.run {
                    agentResponse = wasCancelled ? "Request cancelled." : "Viva request failed: \(error.localizedDescription)"
                }
            }
        }
    }

    func cancelAIRequest() {
        guard isSendingToAI, let requestID = activeVivaRequestID else { return }

        responseAudioPlayer.stop()
        aiRequestTask?.cancel()

        Task {
            do {
                try await cancelVivaRequest(requestID: requestID)
            } catch {
                print("Cancel Request Error: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Networking Phase 1: Transcribe
    
    func transcribeAudio(fileURL: URL) {
        isTranscribing = true
        
        let url = URL(string: "http://127.0.0.1:8000/transcribe")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        var body = Data()
        let boundaryPrefix = "--\(boundary)\r\n"
        
        if let audioData = try? Data(contentsOf: fileURL) {
            body.append(boundaryPrefix.data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"file\"; filename=\"input.wav\"\r\n".data(using: .utf8)!)
            body.append("Content-Type: audio/wav\r\n\r\n".data(using: .utf8)!)
            body.append(audioData)
            body.append("\r\n".data(using: .utf8)!)
        }
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body
        
        URLSession.shared.dataTask(with: request) { data, _, error in
            DispatchQueue.main.async {
                self.isTranscribing = false
                
                if let error = error {
                    print("Transcription Error: \(error.localizedDescription)")
                    self.textInput = "Error connecting to transcriber."
                    return
                }
                
                if let data = data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let text = json["text"] as? String {
                    let transcribedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
                    self.textInput = transcribedText

                    if !transcribedText.isEmpty {
                        DispatchQueue.main.async {
                            self.sendToAI()
                        }
                    }
                } else {
                    self.textInput = "Could not parse transcription."
                }
            }
        }.resume()
    }

    // MARK: - Networking Phase 2: AI Processing
    
    private func sendFinalPayloadToAI(text: String, image: NSImage?, requestID: String) async throws -> VivaResponse {
        let url = URL(string: "http://127.0.0.1:8000/viva")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        var body = Data()
        let boundaryPrefix = "--\(boundary)\r\n"
        
        body.append(boundaryPrefix.data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"request_id\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(requestID)\r\n".data(using: .utf8)!)

        body.append(boundaryPrefix.data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"tts_enabled\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(isTTSAudioEnabled)\r\n".data(using: .utf8)!)

        body.append(boundaryPrefix.data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"text\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(text)\r\n".data(using: .utf8)!)
        
        if let image = image, let imageData = image.jpegData {
            body.append(boundaryPrefix.data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"screenshot\"; filename=\"screen.jpg\"\r\n".data(using: .utf8)!)
            body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
            body.append(imageData)
            body.append("\r\n".data(using: .utf8)!)
        }
        
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              200..<300 ~= httpResponse.statusCode else {
            throw URLError(.badServerResponse)
        }

        return try JSONDecoder().decode(VivaResponse.self, from: data)
    }

    private func cancelVivaRequest(requestID: String) async throws {
        let url = URL(string: "http://127.0.0.1:8000/viva/cancel/\(requestID)")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              200..<300 ~= httpResponse.statusCode else {
            throw URLError(.badServerResponse)
        }
    }
}
