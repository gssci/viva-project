import Foundation

enum VivaUserDefaults {
    static let playTTSAudioKey = "playTTSAudio"
    static let nativeAudioModeKey = "nativeAudioMode"
    static let ttsVoiceGenderKey = "ttsVoiceGender"
    static let ttsSpeechRateKey = "ttsSpeechRate"
}

enum VivaTTSVoiceGender: String, CaseIterable {
    case female
    case male

    var menuTitle: String {
        switch self {
        case .female:
            return "Female Voice"
        case .male:
            return "Male Voice"
        }
    }
}

enum VivaTTSSpeechRate: String, CaseIterable {
    case normal = "1.0"
    case fast = "1.2"
    case faster = "1.5"
    case fastest = "2.0"

    var value: Float {
        Float(rawValue) ?? 1.0
    }

    var menuTitle: String {
        switch self {
        case .normal:
            return "1x"
        case .fast:
            return "1.2x"
        case .faster:
            return "1.5x"
        case .fastest:
            return "2x"
        }
    }

    static var selected: VivaTTSSpeechRate {
        let rawValue = UserDefaults.standard.string(forKey: VivaUserDefaults.ttsSpeechRateKey)
        return VivaTTSSpeechRate(rawValue: rawValue ?? "") ?? .normal
    }
}

extension Notification.Name {
    static let vivaTTSPlaybackDisabled = Notification.Name("vivaTTSPlaybackDisabled")
    static let vivaTTSSpeechRateChanged = Notification.Name("vivaTTSSpeechRateChanged")
}

enum AppPreferences {
    static func registerDefaults() {
        UserDefaults.standard.register(defaults: [
            VivaUserDefaults.playTTSAudioKey: true,
            VivaUserDefaults.nativeAudioModeKey: false,
            VivaUserDefaults.ttsVoiceGenderKey: VivaTTSVoiceGender.female.rawValue,
            VivaUserDefaults.ttsSpeechRateKey: VivaTTSSpeechRate.normal.rawValue
        ])
    }
}
