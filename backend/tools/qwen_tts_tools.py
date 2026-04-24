import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load_model

def generate_expressive_speech():
    print("Downloading/Loading Qwen3-TTS model into MLX... (This may take a moment on the first run)")
    # We are using the 6-bit quantized version for an excellent balance of speed and memory on Mac
    model_id = "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-6bit"
    model = load_model(model_id)

    print("Generating audio...")
    
    # Qwen3-TTS yields chunks (great for streaming). We'll convert it to a list to grab the final audio.
    results = list(model.generate_custom_voice(
        text="This is incredible! The new model running on Apple Silicon is blazing fast and sounds so realistic.",
        speaker="Vivian",          # Pre-defined speaker profile
        language="English",
        instruct="Very happy, energetic, and slightly surprised." # Direct emotional control
    ))

    # The result contains the MLX array
    audio_mlx_array = results[0].audio
    
    # Convert the MLX array to a standard NumPy array so we can write it to a file
    audio_np = np.array(audio_mlx_array)
    
    # Standard sample rate for Qwen3-TTS outputs
    sample_rate = 24000 
    
    output_filename = "expressive_output.wav"
    sf.write(output_filename, audio_np, sample_rate)
    print(f"Success! Audio saved to {output_filename}")

if __name__ == "__main__":
    generate_expressive_speech()

# # Use the Base model for cloning
# model = load_model("mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16")

# results = list(model.generate(
#     text="Hello, I am now speaking with your voice.",
#     ref_audio="path_to_your_3_second_sample.wav", 
#     ref_text="Transcript of exactly what is said in the reference audio."
# ))