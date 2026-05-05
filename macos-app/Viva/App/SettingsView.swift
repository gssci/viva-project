import SwiftUI

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
