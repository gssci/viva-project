import AppKit
import SwiftUI

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

struct ContentView: View {
    @StateObject private var viewModel = ContentViewModel()
    @AppStorage(VivaUserDefaults.playTTSAudioKey) private var isTTSAudioEnabled = true
    @FocusState private var isFocused: Bool
    @State private var gradientRotation = 0.0

    var body: some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                microphoneButton
                screenShareButton

                TextField("Ask Viva...", text: $viewModel.textInput)
                    .textFieldStyle(.plain)
                    .font(.system(size: 15, weight: .regular))
                    .padding(.horizontal, 4)
                    .focused($isFocused)
                    .onSubmit { viewModel.sendToAI(ttsEnabled: isTTSAudioEnabled) }
                    .disabled(viewModel.isTranscribing || viewModel.isSendingToAI)

                sendButton
            }
            .padding(8)
            .background(
                GlossyGlassCapsule(
                    isActive: viewModel.isRecording || viewModel.isTranscribing || viewModel.isSendingToAI,
                    rotation: gradientRotation
                )
            )

            if viewModel.isTranscribing || viewModel.isSendingToAI {
                statusPill
                    .transition(.move(edge: .top).combined(with: .opacity))
            }

            if !viewModel.agentResponse.isEmpty {
                ResponseTextBox(
                    text: viewModel.agentResponse,
                    isPlaying: viewModel.responseAudioPlayer.isPlaying,
                    rotation: gradientRotation
                ) {
                    viewModel.responseAudioPlayer.togglePaused()
                }
                .transition(.move(edge: .top).combined(with: .opacity))
            }

            Button(action: { viewModel.isRecording ? viewModel.stopRecording() : viewModel.startRecording() }) {
                Text("")
            }
            .keyboardShortcut("r", modifiers: .shift)
            .opacity(0)
            .frame(width: 0, height: 0)
        }
        .padding(12)
        .frame(width: 360)
        .animation(.spring(response: 0.4, dampingFraction: 0.8), value: viewModel.isTranscribing || viewModel.isSendingToAI)
        .animation(.easeInOut(duration: 0.35), value: viewModel.responseAudioPlayer.isPlaying)
        .onAppear {
            viewModel.requestAudioAccess()
            withAnimation(.linear(duration: 3.0).repeatForever(autoreverses: false)) {
                gradientRotation = 360.0
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            isFocused = true
        }
        .onReceive(NotificationCenter.default.publisher(for: .vivaTTSPlaybackDisabled)) { _ in
            viewModel.stopResponseAudio()
        }
        .onChange(of: isTTSAudioEnabled) { _, isEnabled in
            if !isEnabled {
                viewModel.stopResponseAudio()
            }
        }
    }

    private var microphoneButton: some View {
        ZStack {
            Circle()
                .fill(viewModel.isRecording ? Color.red : Color.gray.opacity(0.15))

            Image(systemName: viewModel.isRecording ? "waveform" : "mic.fill")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(viewModel.isRecording ? .white : .primary.opacity(0.7))
        }
        .frame(width: 32, height: 32)
        .contentShape(Circle())
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in viewModel.startRecording() }
                .onEnded { _ in viewModel.stopRecording() }
        )
        .help("Hold to speak")
    }

    private var screenShareButton: some View {
        Button(action: {
            withAnimation(.spring(response: 0.3, dampingFraction: 0.6)) {
                viewModel.shareScreen.toggle()
            }
        }) {
            ZStack {
                Circle()
                    .fill(viewModel.shareScreen ? Color.purple : Color.gray.opacity(0.15))

                Image(systemName: viewModel.shareScreen ? "macwindow.badge.plus" : "macwindow")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(viewModel.shareScreen ? .white : .primary.opacity(0.7))
            }
            .frame(width: 32, height: 32)
        }
        .buttonStyle(.plain)
        .help("Share Screen Context")
    }

    private var sendButton: some View {
        Button(action: {
            viewModel.isSendingToAI ? viewModel.cancelAIRequest() : viewModel.sendToAI(ttsEnabled: isTTSAudioEnabled)
        }) {
            ZStack {
                Circle()
                    .fill(viewModel.isSendingToAI ? Color.red : (viewModel.textInput.isEmpty ? Color.gray.opacity(0.15) : Color.blue))

                Image(systemName: viewModel.isSendingToAI ? "xmark" : "arrow.up")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(viewModel.isSendingToAI || !viewModel.textInput.isEmpty ? .white : .primary.opacity(0.4))
            }
            .frame(width: 32, height: 32)
        }
        .buttonStyle(.plain)
        .disabled((viewModel.textInput.isEmpty && !viewModel.isSendingToAI) || viewModel.isTranscribing)
        .help(viewModel.isSendingToAI ? "Cancel Request" : "Send")
    }

    private var statusPill: some View {
        HStack(spacing: 8) {
            ProgressView()
                .controlSize(.small)
            Text(viewModel.isTranscribing ? "Transcribing audio..." : "Viva is thinking...")
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
    }
}
