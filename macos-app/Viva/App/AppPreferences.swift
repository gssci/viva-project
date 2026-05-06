import Foundation

enum VivaUserDefaults {
    static let playTTSAudioKey = "playTTSAudio"
    static let nativeAudioModeKey = "nativeAudioMode"
}

extension Notification.Name {
    static let vivaTTSPlaybackDisabled = Notification.Name("vivaTTSPlaybackDisabled")
}

enum AppPreferences {
    static func registerDefaults() {
        UserDefaults.standard.register(defaults: [
            VivaUserDefaults.playTTSAudioKey: true,
            VivaUserDefaults.nativeAudioModeKey: false
        ])
    }
}
