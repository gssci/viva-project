import Darwin
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
        guard let process else { return }

        let processID = process.processIdentifier
        Self.sendSignal(SIGTERM, toProcessTreeRootedAt: processID)

        let timeout = Date().addingTimeInterval(3)
        while process.isRunning && Date() < timeout {
            Thread.sleep(forTimeInterval: 0.05)
        }

        if process.isRunning {
            Self.sendSignal(SIGKILL, toProcessTreeRootedAt: processID)
            process.waitUntilExit()
        }

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
        environment["VIVA_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier)
        return environment
    }

    private static func sendSignal(_ signal: Int32, toProcessTreeRootedAt processID: Int32) {
        let descendants = descendantProcessIDs(of: processID)
        for childProcessID in descendants.reversed() {
            kill(childProcessID, signal)
        }
        kill(processID, signal)
    }

    private static func descendantProcessIDs(of processID: Int32) -> [Int32] {
        let directChildren = childProcessIDs(of: processID)
        return directChildren + directChildren.flatMap { descendantProcessIDs(of: $0) }
    }

    private static func childProcessIDs(of processID: Int32) -> [Int32] {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        process.arguments = ["-P", String(processID)]

        let outputPipe = Pipe()
        process.standardOutput = outputPipe
        process.standardError = Pipe()

        do {
            try process.run()
        } catch {
            return []
        }

        process.waitUntilExit()
        let output = outputPipe.fileHandleForReading.readDataToEndOfFile()
        guard let text = String(data: output, encoding: .utf8) else { return [] }

        return text
            .split(whereSeparator: \.isNewline)
            .compactMap { Int32($0.trimmingCharacters(in: .whitespacesAndNewlines)) }
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
