import tempfile

import gradio as gr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Frame / analysis parameters used by the FFT and spectrogram stages.
BLOCK_SIZE = 4096
HOP_SIZE = 2048
MAX_DISPLAY_FREQ = 5000
MIN_NOTE_FREQ = 50
MAX_NOTE_FREQ = 2000
RMS_THRESHOLD = 0.005


def frequency_to_note(freq):
    """Convert a frequency in Hz to the nearest equal-tempered note."""
    if freq <= 0 or not np.isfinite(freq):
        return "--", 0.0

    midi = 69 + 12 * np.log2(freq / 440.0)
    nearest = int(round(midi))
    note_names = [
        "C", "C#", "D", "D#", "E", "F",
        "F#", "G", "G#", "A", "A#", "B"
    ]
    note_name = note_names[nearest % 12]
    octave = nearest // 12 - 1
    target_freq = 440.0 * (2 ** ((nearest - 69) / 12))
    cents = 1200 * np.log2(freq / target_freq)
    return f"{note_name}{octave}", float(cents)


def parabolic_peak_interpolation(magnitude, peak_index, freq_resolution):
    """Estimate a peak's sub-bin location from its three neighboring bins."""
    if peak_index <= 0 or peak_index >= len(magnitude) - 1:
        return 0.0

    y1 = np.log(magnitude[peak_index - 1] + 1e-12)
    y2 = np.log(magnitude[peak_index] + 1e-12)
    y3 = np.log(magnitude[peak_index + 1] + 1e-12)
    denominator = y1 - 2 * y2 + y3

    if abs(denominator) < 1e-12:
        return 0.0

    delta = 0.5 * (y1 - y3) / denominator
    # Keep the estimate within the neighboring FFT bins.
    delta = float(np.clip(delta, -0.5, 0.5))
    return delta * freq_resolution


def audio_to_float(audio):
    if audio is None:
        raise gr.Error("Please upload a WAV/audio file or record audio first.")

    sample_rate, data = audio
    if data is None or len(data) == 0:
        raise gr.Error("The audio appears to be empty.")

    data = np.asarray(data)
    if data.ndim == 2:
        data = data.astype(np.float64).mean(axis=1)
    else:
        data = data.astype(np.float64)

    # Gradio commonly provides int16 samples; normalize integer audio to [-1, 1].
    if np.issubdtype(np.asarray(audio[1]).dtype, np.integer):
        original_dtype = np.asarray(audio[1]).dtype
        info = np.iinfo(original_dtype)
        scale = float(max(abs(info.min), info.max))
        data = data / scale
    elif np.max(np.abs(data)) > 1.5:
        data = data / max(float(np.max(np.abs(data))), 1.0)

    if not np.all(np.isfinite(data)):
        raise gr.Error("The audio contains invalid numeric values.")

    return int(sample_rate), data


def analyze_audio(audio):
    sample_rate, data = audio_to_float(audio)
    duration = len(data) / sample_rate

    if duration < 0.02:
        raise gr.Error("Please provide a slightly longer audio recording.")

    # Prepare overlapping frames. Padding the last frame lets us analyze the tail.
    window = np.hanning(BLOCK_SIZE)
    starts = list(range(0, len(data), HOP_SIZE))
    freq_axis = np.fft.rfftfreq(BLOCK_SIZE, d=1.0 / sample_rate)
    freq_resolution = sample_rate / BLOCK_SIZE
    frame_magnitudes = []
    rows = []
    waveform_times = np.arange(len(data)) / sample_rate

    for start in starts:
        frame = data[start:start + BLOCK_SIZE]
        if len(frame) < BLOCK_SIZE:
            frame = np.pad(frame, (0, BLOCK_SIZE - len(frame)))

        signal = frame - np.mean(frame)
        rms = float(np.sqrt(np.mean(signal ** 2)))
        windowed = signal * window
        magnitude = np.abs(np.fft.rfft(windowed))
        frame_magnitudes.append(magnitude)

        search_mask = (
            (freq_axis >= MIN_NOTE_FREQ)
            & (freq_axis <= min(MAX_NOTE_FREQ, sample_rate / 2))
        )
        search_indices = np.where(search_mask)[0]

        raw_peak_freq = 0.0
        refined_peak_freq = 0.0
        note = "--"
        cents = 0.0

        if len(search_indices) and rms > RMS_THRESHOLD:
            local_peak = int(np.argmax(magnitude[search_indices]))
            peak_index = int(search_indices[local_peak])
            raw_peak_freq = float(freq_axis[peak_index])
            refined_peak_freq = raw_peak_freq + parabolic_peak_interpolation(
                magnitude, peak_index, freq_resolution
            )
            note, cents = frequency_to_note(refined_peak_freq)

        rows.append({
            "time_s": round(start / sample_rate, 4),
            "rms": round(rms, 6),
            "fft_bin_frequency_hz": round(raw_peak_freq, 4),
            "refined_frequency_hz": round(refined_peak_freq, 4),
            "note": note,
            "cents_offset": round(float(cents), 4),
        })

    all_magnitudes = np.vstack(frame_magnitudes)
    mean_magnitude = np.mean(all_magnitudes, axis=0)
    spectrum_db = 20 * np.log10(mean_magnitude + 1e-12)
    spectrum_db -= np.max(spectrum_db)

    # Normalize the spectrogram against one global maximum to preserve relative changes.
    spectrogram_db = 20 * np.log10(all_magnitudes + 1e-12)
    spectrogram_db -= np.max(spectrogram_db)

    # Dominant note estimate for the whole clip, based on the mean spectrum.
    note_mask = (
        (freq_axis >= MIN_NOTE_FREQ)
        & (freq_axis <= min(MAX_NOTE_FREQ, sample_rate / 2))
    )
    note_indices = np.where(note_mask)[0]
    clip_rms = float(np.sqrt(np.mean((data - np.mean(data)) ** 2)))
    raw_peak_freq = 0.0
    refined_peak_freq = 0.0
    note = "--"
    cents = 0.0

    if len(note_indices) and clip_rms > RMS_THRESHOLD:
        peak_index = int(note_indices[np.argmax(mean_magnitude[note_indices])])
        raw_peak_freq = float(freq_axis[peak_index])
        refined_peak_freq = raw_peak_freq + parabolic_peak_interpolation(
            mean_magnitude, peak_index, freq_resolution
        )
        note, cents = frequency_to_note(refined_peak_freq)

    # Waveform figure: downsample long clips for a responsive page.
    max_wave_points = 12000
    stride = max(1, int(np.ceil(len(data) / max_wave_points)))
    fig_wave, ax = plt.subplots(figsize=(10, 3))
    ax.plot(waveform_times[::stride], data[::stride], linewidth=0.7)
    ax.set_title("Time-Domain Waveform")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.grid(True, alpha=0.25)
    fig_wave.tight_layout()

    # Average FFT spectrum.
    display_mask = freq_axis <= min(MAX_DISPLAY_FREQ, sample_rate / 2)
    fig_spec, ax = plt.subplots(figsize=(10, 3.4))
    ax.plot(freq_axis[display_mask], spectrum_db[display_mask], linewidth=0.8)
    ax.set_title("Frequency Spectrum (mean FFT magnitude)")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Relative magnitude (dB)")
    ax.set_ylim(-90, 3)
    ax.grid(True, alpha=0.25)
    fig_spec.tight_layout()

    # Spectrogram / waterfall-style view.
    time_axis = np.asarray(starts, dtype=float) / sample_rate
    fig_specgram, ax = plt.subplots(figsize=(10, 3.6))
    spec_mask = freq_axis <= min(MAX_DISPLAY_FREQ, sample_rate / 2)
    if len(time_axis) > 1:
        extent = [
            float(time_axis[0]),
            float(time_axis[-1] + HOP_SIZE / sample_rate),
            float(freq_axis[spec_mask][0]),
            float(freq_axis[spec_mask][-1]),
        ]
    else:
        extent = [
            0.0,
            BLOCK_SIZE / sample_rate,
            float(freq_axis[spec_mask][0]),
            float(freq_axis[spec_mask][-1]),
        ]
    ax.imshow(
        spectrogram_db[:, spec_mask].T,
        origin="lower",
        aspect="auto",
        extent=extent,
        cmap="magma",
        vmin=-80,
        vmax=0,
        interpolation="nearest",
    )
    ax.set_title("Spectrogram (frequency over time)")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")
    fig_specgram.tight_layout()

    if refined_peak_freq > 0:
        tuning = "in tune" if abs(cents) < 5 else (
            f"{cents:+.1f} cents sharp" if cents > 0 else f"{cents:+.1f} cents flat"
        )
        summary = (
            f"### Analysis result\n"
            f"- **Duration:** {duration:.2f} s\n"
            f"- **Sample rate:** {sample_rate:,} Hz\n"
            f"- **Frames analyzed:** {len(starts)}\n"
            f"- **Dominant pitch estimate:** {note}\n"
            f"- **Refined frequency:** {refined_peak_freq:.2f} Hz "
            f"(nearest FFT bin: {raw_peak_freq:.2f} Hz)\n"
            f"- **Tuning offset:** {tuning}\n\n"
            f"*This is a dominant-frequency estimate, not full polyphonic/chord transcription.*"
        )
    else:
        summary = (
            f"### Analysis result\n"
            f"- **Duration:** {duration:.2f} s\n"
            f"- **Sample rate:** {sample_rate:,} Hz\n"
            f"- **Frames analyzed:** {len(starts)}\n"
            f"- No stable dominant pitch was detected above the current amplitude threshold."
        )

    df = pd.DataFrame(rows)
    temp = tempfile.NamedTemporaryFile(
        mode="w", suffix="_audio_analysis.csv", delete=False,
        newline="", encoding="utf-8-sig"
    )
    temp.close()
    df.to_csv(temp.name, index=False)

    return summary, fig_wave, fig_spec, fig_specgram, temp.name


APP_CSS = """
.main-title {text-align:center;}
.subtle {opacity:0.8;}
"""

with gr.Blocks(title="Audio Spectrum Analyzer") as demo:
    gr.Markdown(
        """
        # 🎵 Audio Spectrum Analyzer
        <div class="subtle">A Python-based signal-processing demo using FFT, windowing, and parabolic peak interpolation.</div>

        Upload an audio file or record a short clip with your browser microphone, then click **Analyze audio**.
        This public demo analyzes the recorded/uploaded clip after submission; the original desktop app remains the version for continuous live-microphone visualization.
        """
    )

    with gr.Row():
        audio_input = gr.Audio(
            sources=["upload", "microphone"],
            type="numpy",
            label="Upload or record audio"
        )

    analyze_button = gr.Button("Analyze audio", variant="primary")
    summary_output = gr.Markdown()

    with gr.Tab("Waveform"):
        waveform_output = gr.Plot(label="Time-domain waveform")
    with gr.Tab("FFT Spectrum"):
        spectrum_output = gr.Plot(label="Frequency spectrum")
    with gr.Tab("Spectrogram"):
        spectrogram_output = gr.Plot(label="Spectrogram")
    csv_output = gr.File(label="Download frame-by-frame CSV results")

    analyze_button.click(
        fn=analyze_audio,
        inputs=[audio_input],
        outputs=[
            summary_output,
            waveform_output,
            spectrum_output,
            spectrogram_output,
            csv_output,
        ],
    )

    gr.Markdown(
        """
        ---
        **How to read the plots**
        - **Waveform:** amplitude changes over time.
        - **FFT spectrum:** which frequencies are strongest.
        - **Spectrogram:** how frequency content changes over time.
        - **CSV:** frame-level RMS, FFT-bin frequency, refined frequency, estimated note, and cents offset.

        **Method notes:** 4096-sample Hann-windowed frames, 2048-sample hop, NumPy real FFT, and parabolic peak interpolation.
        """
    )

if __name__ == "__main__":
    # Gradio 6 expects theme/css on launch() rather than on Blocks().
    demo.launch(theme=gr.themes.Soft(), css=APP_CSS)
