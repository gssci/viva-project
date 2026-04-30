import SwiftUI
import SwiftData
import AppKit

enum VivaUserDefaults {
    static let playTTSAudioKey = "playTTSAudio"
}

extension Notification.Name {
    static let vivaTTSPlaybackDisabled = Notification.Name("vivaTTSPlaybackDisabled")
}

@main
struct VivaApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    
    var body: some Scene {
        // Defines the standard macOS Settings window
        Settings {
            SettingsView()
        }
    }
}

// MARK: - Dummy Settings View
struct SettingsView: View {
    var body: some View {
        VStack(spacing: 20) {
            Text("Viva Settings")
                .font(.headline)
            Text("Add your API keys, shortcuts, or preferences here.")
                .foregroundColor(.secondary)
        }
        .padding(40)
        .frame(width: 350, height: 250)
    }
}

// MARK: - Custom Panel
class FloatingPanel: NSPanel {
    override var canBecomeKey: Bool { return true }
    override var canBecomeMain: Bool { return true }
}

// MARK: - App Delegate & Window Manager
class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var statusItem: NSStatusItem!
    var floatingPanel: FloatingPanel!
    var eventMonitor: Any?
    
    var sharedModelContainer: ModelContainer = {
        let schema = Schema([Item.self])
        let modelConfiguration = ModelConfiguration(schema: schema, isStoredInMemoryOnly: false)
        do {
            return try ModelContainer(for: schema, configurations: [modelConfiguration])
        } catch {
            fatalError("Could not create ModelContainer: \(error)")
        }
    }()

    func applicationDidFinishLaunching(_ notification: Notification) {
        UserDefaults.standard.register(defaults: [VivaUserDefaults.playTTSAudioKey: true])

        // 1. Setup the custom floating panel
        floatingPanel = FloatingPanel(
            contentRect: NSRect(x: 0, y: 0, width: 400, height: 240),
            styleMask: [.nonactivatingPanel, .borderless],
            backing: .buffered,
            defer: false
        )
        
        floatingPanel.isOpaque = false
        floatingPanel.backgroundColor = .clear
        floatingPanel.hasShadow = false
        floatingPanel.level = .floating
        floatingPanel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        floatingPanel.delegate = self
        
        let hostingView = NSHostingView(
            rootView: ContentView()
                .modelContainer(sharedModelContainer)
                .background(Color.clear)
        )
        floatingPanel.contentView = hostingView
        
        // 2. Create the Menu Bar Item
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "waveform.circle", accessibilityDescription: "Viva")
            
            // ---> NEW: Tell the button to listen for both Left and Right clicks <---
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
            button.action = #selector(handleMenuClick(_:))
        }
        
        // 3. Setup Global Click Monitor
        eventMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
            if let self = self, self.floatingPanel.isVisible {
                self.hidePanel()
            }
        }
    }
    
    // MARK: - Left vs Right Click Logic
    @objc func handleMenuClick(_ sender: NSStatusBarButton) {
        guard let event = NSApp.currentEvent else { return }
        
        if event.type == .rightMouseUp {
            // --- RIGHT CLICK: Show Context Menu ---
            let menu = NSMenu()

            let ttsItem = NSMenuItem(title: "Play TTS Audio", action: #selector(toggleTTSAudioPlayback(_:)), keyEquivalent: "")
            ttsItem.target = self
            ttsItem.state = UserDefaults.standard.bool(forKey: VivaUserDefaults.playTTSAudioKey) ? .on : .off
            menu.addItem(ttsItem)
            menu.addItem(NSMenuItem.separator())
            
            // Settings Option
            menu.addItem(NSMenuItem(title: "Settings...", action: #selector(openSettings), keyEquivalent: ","))
            menu.addItem(NSMenuItem.separator())
            
            // Quit Option (Standard AppKit terminate action)
            menu.addItem(NSMenuItem(title: "Quit Viva", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
            
            // Temporarily assign the menu to force it to pop up, then immediately remove it
            // so that the next left-click doesn't accidentally trigger the menu.
            statusItem.menu = menu
            statusItem.button?.performClick(nil)
            statusItem.menu = nil
            
        } else {
            // --- LEFT CLICK: Toggle the App Panel ---
            if floatingPanel.isVisible {
                hidePanel()
            } else {
                showPanel()
            }
        }
    }

    @objc func toggleTTSAudioPlayback(_ sender: NSMenuItem) {
        let isEnabled = !UserDefaults.standard.bool(forKey: VivaUserDefaults.playTTSAudioKey)
        UserDefaults.standard.set(isEnabled, forKey: VivaUserDefaults.playTTSAudioKey)
        sender.state = isEnabled ? .on : .off

        if !isEnabled {
            NotificationCenter.default.post(name: .vivaTTSPlaybackDisabled, object: nil)
        }
    }
    
    @objc func openSettings() {
        // This is the standard Apple internal selector to open a SwiftUI `Settings {}` scene
        NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
        
        // Bring the settings window to the absolute front
        NSApp.activate(ignoringOtherApps: true)
    }
    
    // MARK: - Panel Placement Logic
    func showPanel() {
        if let button = statusItem.button, let window = button.window {
            let buttonRect = window.convertToScreen(button.frame)
            let panelWidth = floatingPanel.frame.width
            
            let x = buttonRect.midX - (panelWidth / 2)
            let y = buttonRect.minY - floatingPanel.frame.height // Adjust margin here
            
            floatingPanel.setFrameOrigin(NSPoint(x: x, y: y))
        }
        
        floatingPanel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
    
    func hidePanel() {
        floatingPanel.orderOut(nil)
    }
    
    func windowDidResignKey(_ notification: Notification) {
        hidePanel()
    }
}
