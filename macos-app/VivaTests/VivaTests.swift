import Foundation
import Testing
@testable import Viva

struct VivaTests {
    @Test func multipartBuilderIncludesFieldsFilesAndClosingBoundary() throws {
        var builder = MultipartFormDataBuilder(boundary: "boundary")
        builder.appendField(name: "text", value: "hello")
        builder.appendFile(name: "file", filename: "input.wav", contentType: "audio/wav", data: Data([0x01, 0x02]))

        let body = builder.build()
        let string = String(decoding: body, as: UTF8.self)

        #expect(string.contains("--boundary\r\n"))
        #expect(string.contains("Content-Disposition: form-data; name=\"text\"\r\n\r\nhello\r\n"))
        #expect(string.contains("Content-Disposition: form-data; name=\"file\"; filename=\"input.wav\"\r\n"))
        #expect(string.contains("Content-Type: audio/wav\r\n\r\n"))
        #expect(string.hasSuffix("--boundary--\r\n"))
    }

    @Test func vivaResponseDecodesSnakeCaseAPIFields() throws {
        let json = """
        {
            "text": "Done",
            "processing_time": 1.25,
            "used_screenshot": true,
            "audio_url": "http://127.0.0.1:8000/audio/result.wav",
            "audio_content_type": "audio/wav",
            "tts_language": "en",
            "tts_voice": "alloy",
            "tts_processing_time": 0.5,
            "tts_error": "warning"
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(VivaResponse.self, from: json)

        #expect(response.text == "Done")
        #expect(response.processingTime == 1.25)
        #expect(response.usedScreenshot == true)
        #expect(response.audioURL?.absoluteString == "http://127.0.0.1:8000/audio/result.wav")
        #expect(response.audioContentType == "audio/wav")
        #expect(response.ttsLanguage == "en")
        #expect(response.ttsVoice == "alloy")
        #expect(response.ttsProcessingTime == 0.5)
        #expect(response.ttsError == "warning")
    }
}
