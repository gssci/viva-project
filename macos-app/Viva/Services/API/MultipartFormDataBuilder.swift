import Foundation

struct MultipartFormDataBuilder {
    let boundary: String
    private var body = Data()

    init(boundary: String = UUID().uuidString) {
        self.boundary = boundary
    }

    mutating func appendField(name: String, value: String) {
        appendBoundary()
        body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
        body.append("\(value)\r\n")
    }

    mutating func appendFile(name: String, filename: String, contentType: String, data: Data) {
        appendBoundary()
        body.append("Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n")
        body.append("Content-Type: \(contentType)\r\n\r\n")
        body.append(data)
        body.append("\r\n")
    }

    func build() -> Data {
        var finalizedBody = body
        finalizedBody.append("--\(boundary)--\r\n")
        return finalizedBody
    }

    private mutating func appendBoundary() {
        body.append("--\(boundary)\r\n")
    }
}

private extension Data {
    mutating func append(_ string: String) {
        append(Data(string.utf8))
    }
}
