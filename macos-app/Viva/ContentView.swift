import SwiftUI
import AVFoundation
import AppKit
import Combine

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

// MARK: - Main View
struct ContentView: View {
    @StateObject private var recorder = AudioRecorder()
    
    // UI State
    @State private var textInput: String = ""
    @State private var isRecording = false
    @State private var isTranscribing = false
    @State private var isSendingToAI = false
    @State private var shareScreen: Bool = false
    
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
                Button(action: { sendToAI() }) {
                    ZStack {
                        Circle()
                            .fill(textInput.isEmpty ? Color.gray.opacity(0.15) : Color.blue)
                        
                        Image(systemName: "arrow.up")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(textInput.isEmpty ? .primary.opacity(0.4) : .white)
                    }
                    .frame(width: 32, height: 32)
                }
                .buttonStyle(.plain)
                .disabled(textInput.isEmpty || isTranscribing || isSendingToAI)
            }
            .padding(8)
            .background(
                Capsule()
                    .fill(.ultraThinMaterial)
            )
            .overlay(
                Capsule()
                    .strokeBorder(
                        isRecording || isTranscribing || isSendingToAI
                        ? AngularGradient(
                            gradient: Gradient(colors: [.blue, .purple, .pink, .orange, .blue]),
                            center: .center,
                            angle: .degrees(gradientRotation)
                          )
                        : AngularGradient(
                            gradient: Gradient(colors: [.gray.opacity(0.2)]),
                            center: .center,
                            angle: .degrees(0)
                          ),
                        lineWidth: 1.5
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
                    RoundedRectangle(cornerRadius: 12)
                        .fill(.ultraThinMaterial)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .strokeBorder(Color.gray.opacity(0.2), lineWidth: 1)
                )
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
        guard !textInput.isEmpty else { return }
        let currentText = textInput
        
        Task {
            isSendingToAI = true
            var screenshot: NSImage? = nil
            if shareScreen {
                screenshot = try? await ScreenShotManager.captureMainDisplay()
            }
            
            sendFinalPayloadToAI(text: currentText, image: screenshot)
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
                    self.textInput = text
                } else {
                    self.textInput = "Could not parse transcription."
                }
            }
        }.resume()
    }

    // MARK: - Networking Phase 2: AI Processing
    
    func sendFinalPayloadToAI(text: String, image: NSImage?) {
        let url = URL(string: "http://127.0.0.1:8000/viva")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        var body = Data()
        let boundaryPrefix = "--\(boundary)\r\n"
        
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
        
        URLSession.shared.dataTask(with: request) { data, _, _ in
            DispatchQueue.main.async {
                self.isSendingToAI = false
                self.textInput = ""
            }
        }.resume()
    }
}
