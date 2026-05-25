import Foundation

final class BackendLauncher {
    static let shared = BackendLauncher()

    private var process: Process?

    private init() {}

    func start() {
        guard process == nil else { return }

        guard let backendDirectory = Self.resolveBackendDirectory() else {
            print("Backend Launcher Error: Could not find backend directory.")
            return
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/make")
        process.arguments = ["backend"]
        process.currentDirectoryURL = backendDirectory
        process.environment = Self.processEnvironment()

        let outputPipe = Pipe()
        process.standardOutput = outputPipe
        process.standardError = outputPipe
        outputPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard !data.isEmpty, let output = String(data: data, encoding: .utf8) else { return }
            print("Backend: \(output.trimmingCharacters(in: .whitespacesAndNewlines))")
        }

        process.terminationHandler = { [weak self, weak outputPipe] process in
            outputPipe?.fileHandleForReading.readabilityHandler = nil
            print("Backend process exited with status \(process.terminationStatus).")
            if self?.process === process {
                self?.process = nil
            }
        }

        do {
            self.process = process
            try process.run()
            print("Backend launcher started in \(backendDirectory.path).")
        } catch {
            self.process = nil
            outputPipe.fileHandleForReading.readabilityHandler = nil
            print("Backend Launcher Error: \(error.localizedDescription)")
        }
    }

    func stop() {
        guard let process, process.isRunning else { return }
        process.terminate()
        self.process = nil
    }

    private static func processEnvironment() -> [String: String] {
        var environment = ProcessInfo.processInfo.environment
        let pathEntries = [
            environment["PATH"],
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin"
        ]
        environment["PATH"] = pathEntries.compactMap { $0 }.joined(separator: ":")
        return environment
    }

    private static func resolveBackendDirectory() -> URL? {
        if let configuredPath = ProcessInfo.processInfo.environment["VIVA_BACKEND_DIR"], !configuredPath.isEmpty {
            let configuredURL = URL(fileURLWithPath: configuredPath)
            if isBackendDirectory(configuredURL) {
                return configuredURL
            }
        }

        if let sourceURL = backendDirectoryFromSourcePath() {
            return sourceURL
        }

        var searchURL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        for _ in 0..<8 {
            let candidate = searchURL.appendingPathComponent("backend")
            if isBackendDirectory(candidate) {
                return candidate
            }
            searchURL.deleteLastPathComponent()
        }

        return nil
    }

    private static func backendDirectoryFromSourcePath(filePath: String = #filePath) -> URL? {
        var searchURL = URL(fileURLWithPath: filePath)
        while searchURL.path != "/" {
            if searchURL.lastPathComponent == "macos-app" {
                let backendURL = searchURL.deletingLastPathComponent().appendingPathComponent("backend")
                return isBackendDirectory(backendURL) ? backendURL : nil
            }
            searchURL.deleteLastPathComponent()
        }
        return nil
    }

    private static func isBackendDirectory(_ url: URL) -> Bool {
        FileManager.default.fileExists(atPath: url.appendingPathComponent("Makefile").path)
            && FileManager.default.fileExists(atPath: url.appendingPathComponent("pyproject.toml").path)
            && FileManager.default.fileExists(atPath: url.appendingPathComponent(".venv").path)
    }
}
