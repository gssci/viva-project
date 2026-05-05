import Foundation

struct VivaResponse: Decodable {
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
