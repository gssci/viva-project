import AppKit
import Foundation

struct VivaAPIClient {
    var baseURL = URL(string: "http://127.0.0.1:8000")!
    var session = URLSession.shared
    var requestTimeout: TimeInterval = 120

    func transcribeAudio(fileURL: URL) async throws -> String {
        let audioData = try Data(contentsOf: fileURL)
        var builder = MultipartFormDataBuilder()
        builder.appendFile(name: "file", filename: "input.wav", contentType: "audio/wav", data: audioData)

        var request = multipartRequest(path: "/transcribe", boundary: builder.boundary)
        request.httpBody = builder.build()

        let data = try await perform(request)
        let response = try JSONDecoder().decode(TranscriptionResponse.self, from: data)
        return response.text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func sendVivaRequest(text: String, image: NSImage?, requestID: String, ttsEnabled: Bool) async throws -> VivaResponse {
        var builder = MultipartFormDataBuilder()
        builder.appendField(name: "request_id", value: requestID)
        builder.appendField(name: "tts_enabled", value: "\(ttsEnabled)")
        builder.appendField(name: "text", value: text)

        if let imageData = image?.jpegData {
            builder.appendFile(name: "screenshot", filename: "screen.jpg", contentType: "image/jpeg", data: imageData)
        }

        var request = multipartRequest(path: "/viva", boundary: builder.boundary)
        request.timeoutInterval = requestTimeout
        request.httpBody = builder.build()

        let data = try await perform(request)
        return try JSONDecoder().decode(VivaResponse.self, from: data)
    }

    func sendVivaNativeAudioRequest(fileURL: URL, image: NSImage?, requestID: String, ttsEnabled: Bool) async throws -> VivaResponse {
        let audioData = try Data(contentsOf: fileURL)
        var builder = MultipartFormDataBuilder()
        builder.appendField(name: "request_id", value: requestID)
        builder.appendField(name: "tts_enabled", value: "\(ttsEnabled)")
        builder.appendFile(name: "file", filename: "input.wav", contentType: "audio/wav", data: audioData)

        if let imageData = image?.jpegData {
            builder.appendFile(name: "screenshot", filename: "screen.jpg", contentType: "image/jpeg", data: imageData)
        }

        var request = multipartRequest(path: "/viva/native-audio", boundary: builder.boundary)
        request.timeoutInterval = requestTimeout
        request.httpBody = builder.build()

        let data = try await perform(request)
        return try JSONDecoder().decode(VivaResponse.self, from: data)
    }

    func cancelVivaRequest(requestID: String) async throws {
        var request = URLRequest(url: baseURL.appending(path: "/viva/cancel/\(requestID)"))
        request.httpMethod = "POST"
        _ = try await perform(request)
    }

    private func multipartRequest(path: String, boundary: String) -> URLRequest {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        return request
    }

    private func perform(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              200..<300 ~= httpResponse.statusCode else {
            throw URLError(.badServerResponse)
        }
        return data
    }
}

private struct TranscriptionResponse: Decodable {
    let text: String
}
