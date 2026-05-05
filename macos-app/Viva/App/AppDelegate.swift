import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private var statusItem: NSStatusItem!
    private var floatingPanel: FloatingPanel!
    private var eventMonitor: Any?

    func applicationDidFinishLaunching(_ notification: Notification) {
        AppPreferences.registerDefaults()
        configureFloatingPanel()
        configureStatusItem()
        configureGlobalClickMonitor()
    }

    @objc private func handleMenuClick(_ sender: NSStatusBarButton) {
        guard let event = NSApp.currentEvent else { return }

        if event.type == .rightMouseUp {
            showContextMenu()
        } else {
            floatingPanel.isVisible ? hidePanel() : showPanel()
        }
    }

    @objc private func toggleTTSAudioPlayback(_ sender: NSMenuItem) {
        let isEnabled = !UserDefaults.standard.bool(forKey: VivaUserDefaults.playTTSAudioKey)
        UserDefaults.standard.set(isEnabled, forKey: VivaUserDefaults.playTTSAudioKey)
        sender.state = isEnabled ? .on : .off

        if !isEnabled {
            NotificationCenter.default.post(name: .vivaTTSPlaybackDisabled, object: nil)
        }
    }

    @objc private func openSettings() {
        NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func windowDidResignKey(_ notification: Notification) {
        hidePanel()
    }

    private func configureFloatingPanel() {
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
        floatingPanel.contentView = NSHostingView(
            rootView: ContentView()
                .background(Color.clear)
        )
    }

    private func configureStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        guard let button = statusItem.button else { return }

        button.image = NSImage(systemSymbolName: "waveform.circle", accessibilityDescription: "Viva")
        button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        button.action = #selector(handleMenuClick(_:))
    }

    private func configureGlobalClickMonitor() {
        eventMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
            guard let self, self.floatingPanel.isVisible else { return }
            self.hidePanel()
        }
    }

    private func showContextMenu() {
        let menu = NSMenu()

        let ttsItem = NSMenuItem(title: "Play TTS Audio", action: #selector(toggleTTSAudioPlayback(_:)), keyEquivalent: "")
        ttsItem.target = self
        ttsItem.state = UserDefaults.standard.bool(forKey: VivaUserDefaults.playTTSAudioKey) ? .on : .off
        menu.addItem(ttsItem)
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Settings...", action: #selector(openSettings), keyEquivalent: ","))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit Viva", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))

        statusItem.menu = menu
        statusItem.button?.performClick(nil)
        statusItem.menu = nil
    }

    private func showPanel() {
        if let button = statusItem.button, let window = button.window {
            let buttonRect = window.convertToScreen(button.frame)
            let panelWidth = floatingPanel.frame.width
            let x = buttonRect.midX - (panelWidth / 2)
            let y = buttonRect.minY - floatingPanel.frame.height

            floatingPanel.setFrameOrigin(NSPoint(x: x, y: y))
        }

        floatingPanel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func hidePanel() {
        floatingPanel.orderOut(nil)
    }
}
