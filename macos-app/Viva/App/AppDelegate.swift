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

    @objc private func toggleNativeAudioMode(_ sender: NSMenuItem) {
        let isEnabled = !UserDefaults.standard.bool(forKey: VivaUserDefaults.nativeAudioModeKey)
        UserDefaults.standard.set(isEnabled, forKey: VivaUserDefaults.nativeAudioModeKey)
        sender.state = isEnabled ? .on : .off
    }

    @objc private func selectTTSVoiceGender(_ sender: NSMenuItem) {
        guard let voiceGender = sender.representedObject as? String else { return }
        UserDefaults.standard.set(voiceGender, forKey: VivaUserDefaults.ttsVoiceGenderKey)
    }

    @objc private func selectTTSSpeechRate(_ sender: NSMenuItem) {
        guard let speechRate = sender.representedObject as? String else { return }
        UserDefaults.standard.set(speechRate, forKey: VivaUserDefaults.ttsSpeechRateKey)
        NotificationCenter.default.post(name: .vivaTTSSpeechRateChanged, object: nil)
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

        let nativeAudioItem = NSMenuItem(title: "Native Audio Mode", action: #selector(toggleNativeAudioMode(_:)), keyEquivalent: "")
        nativeAudioItem.target = self
        nativeAudioItem.state = UserDefaults.standard.bool(forKey: VivaUserDefaults.nativeAudioModeKey) ? .on : .off
        menu.addItem(nativeAudioItem)

        menu.addItem(ttsVoiceGenderMenuItem())
        menu.addItem(ttsSpeechRateMenuItem())
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Settings...", action: #selector(openSettings), keyEquivalent: ","))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit Viva", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))

        statusItem.menu = menu
        statusItem.button?.performClick(nil)
        statusItem.menu = nil
    }

    private func ttsVoiceGenderMenuItem() -> NSMenuItem {
        let item = NSMenuItem(title: "TTS Voice", action: nil, keyEquivalent: "")
        let submenu = NSMenu()
        let selectedVoiceGender = UserDefaults.standard.string(forKey: VivaUserDefaults.ttsVoiceGenderKey) ?? VivaTTSVoiceGender.female.rawValue

        for voiceGender in VivaTTSVoiceGender.allCases {
            let voiceItem = NSMenuItem(
                title: voiceGender.menuTitle,
                action: #selector(selectTTSVoiceGender(_:)),
                keyEquivalent: ""
            )
            voiceItem.target = self
            voiceItem.representedObject = voiceGender.rawValue
            voiceItem.state = selectedVoiceGender == voiceGender.rawValue ? .on : .off
            submenu.addItem(voiceItem)
        }

        item.submenu = submenu
        return item
    }

    private func ttsSpeechRateMenuItem() -> NSMenuItem {
        let item = NSMenuItem(title: "Speech Rate", action: nil, keyEquivalent: "")
        let submenu = NSMenu()
        let selectedSpeechRate = VivaTTSSpeechRate.selected.rawValue

        for speechRate in VivaTTSSpeechRate.allCases {
            let rateItem = NSMenuItem(
                title: speechRate.menuTitle,
                action: #selector(selectTTSSpeechRate(_:)),
                keyEquivalent: ""
            )
            rateItem.target = self
            rateItem.representedObject = speechRate.rawValue
            rateItem.state = selectedSpeechRate == speechRate.rawValue ? .on : .off
            submenu.addItem(rateItem)
        }

        item.submenu = submenu
        return item
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
