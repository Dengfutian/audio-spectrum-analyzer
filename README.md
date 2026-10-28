---
title: Audio Spectrum Analyzer
emoji: 🎵
colorFrom: indigo
colorTo: purple
sdk: gradio
app_file: app.py
pinned: false
---

# Audio Spectrum Analyzer

An interactive signal-processing application that analyses an audio clip and visualises it in three complementary views: a **time-domain waveform**, a **frequency-domain FFT spectrum**, and a **spectrogram**. It also estimates the dominant pitch, converts it to the nearest musical note, and exports frame-level numerical results as CSV.

The project was built as an engineering portfolio piece to demonstrate how a continuous real-world signal (sound) is converted into discrete data, how the Fast Fourier Transform reveals its frequency content, and how a simple interpolation step improves measurement resolution beyond the raw FFT grid.

**Live demo:** not deployed yet. A hosted Gradio instance is planned on Hugging Face Spaces, and the link will be added here once it is available. See [Deploying a shareable demo](#deploying-a-shareable-demo).

## Table of contents

- [Motivation](#motivation)
- [Features](#features)
- [Signal-processing pipeline](#signal-processing-pipeline)
- [Why resolution matters](#why-resolution-matters)
- [Project structure](#project-structure)
- [Requirements](#requirements)
- [Running locally](#running-locally)
- [Verification and testing](#verification-and-testing)
- [Reading the output](#reading-the-output)
- [Screenshots](#screenshots)
- [Deploying a shareable demo](#deploying-a-shareable-demo)
- [Limitations](#limitations)
- [Possible future work](#possible-future-work)
- [Related projects](#related-projects)
- [License](#license)

## Motivation

Sound is a continuous pressure wave. A computer cannot process a continuous signal directly, so the signal is first **sampled** at a fixed rate (for example 44 100 samples per second) and stored as an array of numbers. Once the signal is discrete, digital signal processing can answer questions that are difficult to answer by ear alone:

- Which frequencies are present, and which one dominates?
- How does the frequency content change over time?
- How far is a played note from the exact equal-tempered pitch?

This application answers those questions with standard DSP building blocks implemented in NumPy, and presents the results through a Gradio web interface.

## Features

| Feature | Description |
| --- | --- |
| Audio input | Upload an audio file or record a short clip with the browser microphone |
| Mono conversion | Multi-channel audio is averaged to a single channel before analysis |
| Amplitude normalisation | Integer PCM samples are scaled to the range `[-1, 1]` |
| Time-domain waveform | Amplitude plotted against time |
| FFT spectrum | Average magnitude spectrum, displayed in relative decibels |
| Spectrogram | Frequency content over time, computed from overlapping frames |
| Pitch estimation | Dominant frequency, nearest equal-tempered note, and offset in cents |
| Parabolic peak interpolation | Sub-bin refinement of the FFT peak |
| CSV export | Frame-level table with RMS, FFT-bin frequency, refined frequency, note, and cents offset |

## Signal-processing pipeline

The analysis runs in the following order (`app.py`):

1. **Input handling and type conversion** — Gradio returns a tuple `(sample_rate, samples)`. The array is converted to `float64`. If it is two-dimensional, the channels are averaged to mono. Integer PCM data is divided by the maximum representable value of its dtype so that amplitude always lies in `[-1, 1]`.
2. **Framing** — The signal is split into overlapping frames of `4096` samples with a hop size of `2048` samples (50 % overlap). Overlapping frames produce a smoother spectrogram than non-overlapping frames. Incomplete final frames are zero-padded.
3. **DC removal and windowing** — Each frame has its mean removed, then is multiplied by a Hann window. Windowing reduces spectral leakage caused by the implicit rectangular truncation of a finite frame.
4. **Real FFT** — `numpy.fft.rfft` computes the magnitude spectrum of each frame. Because the input is real-valued, only the non-redundant half of the spectrum is needed.
5. **Peak search** — Within a configurable band (`50 Hz – 2000 Hz`, and never above the Nyquist frequency), the bin with the largest magnitude is selected. Frames whose RMS falls below the threshold are skipped, which suppresses silence and background noise.
6. **Parabolic peak interpolation** — The true peak generally lies between two FFT bins. A parabola is fitted through the log-magnitudes of the peak bin and its two neighbours, and the vertex position refines the frequency estimate.
7. **Frequency-to-note conversion** — The refined frequency is mapped to a MIDI number using `midi = 69 + 12 * log2(f / 440)`, rounded to the nearest semitone, and converted to a note name plus an offset in **cents** (100 cents = 1 semitone).
8. **Visualisation and export** — Matplotlib renders the three plots, and pandas writes a CSV containing one row per analysed frame.

## Why resolution matters

The spacing between adjacent FFT bins is

```
frequency resolution = sample_rate / block_size
```

With a 44 100 Hz sample rate and a 4096-sample block, the resolution is about **10.77 Hz**. The raw FFT can therefore only report the peak to the nearest 10.77 Hz, which is far too coarse for musical tuning: near A4 (440 Hz), one semitone is only about 26 Hz wide, so a 10.77 Hz grid gives only two or three samples per semitone.

Parabolic interpolation uses the shape of the peak — the relative heights of the three bins around it — to estimate where the continuous peak lies between bins. It does not create new information, but it extracts the sub-bin position already implied by the windowed spectrum, which typically reduces the error by roughly an order of magnitude for an isolated, steady tone.

## Project structure

```
audio-spectrum-analyzer/
├── app.py                                 # Gradio UI + DSP pipeline
├── requirements.txt                       # Python dependencies
├── README.md                              # This document
├── LICENSE                                # MIT License
├── .gitignore                             # Files excluded from version control
├── examples/
│   └── A4_440Hz_reference_tone.wav        # 3.0 s, mono, 16-bit, 44 100 Hz reference tone
└── screenshots/                           # Reserved for UI captures (not committed yet)
```

## Requirements

- Python 3.10 or newer (developed and verified on Python 3.10)
- `gradio>=6.0,<7.0`
- `numpy>=1.26,<3.0`
- `matplotlib>=3.8,<4.0`
- `pandas>=2.1,<3.0`

## Running locally

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

If PowerShell blocks the activation script, run this once in the same terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

Then open the local URL printed in the terminal (by default `http://127.0.0.1:7860`).

## Verification and testing

### Reference-tone test

The repository includes a synthetic reference tone, `examples/A4_440Hz_reference_tone.wav`:

- Format: WAV, mono, 16-bit PCM
- Sample rate: 44 100 Hz
- Duration: 3.00 s (132 300 samples)
- Nominal frequency: 440 Hz (A4)

**Measured result** — uploading this file and pressing **Analyze audio** produced:

| Quantity | Value |
| --- | --- |
| Frames analysed | 65 |
| FFT bin spacing | 10.7666 Hz |
| Nearest FFT bin to the peak | 441.43 Hz (**+1.43 Hz** error) |
| Refined frequency (parabolic interpolation) | 439.89 Hz (**−0.11 Hz**, **−0.43 cents** error) |
| Estimated note | A4, detected in 65 of 65 frames |

This comparison is the practical justification for the interpolation step: the raw bin alone is off by 1.43 Hz, while the interpolated estimate lands within about a tenth of a hertz of the nominal 440 Hz.

### How to reproduce

1. Start the app (`python app.py`).
2. Upload `examples/A4_440Hz_reference_tone.wav`.
3. Press **Analyze audio**.
4. Compare the reported refined frequency with the nominal 440 Hz, then download the CSV and inspect the per-frame values.

### Additional checks performed

- Empty / missing input raises a user-visible error instead of crashing.
- Very short clips (below 0.02 s) are rejected with a clear message.
- Stereo input is correctly reduced to mono, and `float32` input is handled without extra scaling.
- `frequency_to_note(440.0)` returns `('A4', 0.0)`, and `frequency_to_note(261.6256)` returns `C4` with an offset of approximately 0 cents.
- The application starts and serves HTTP `200` at `http://127.0.0.1:7860` on Windows with Python 3.10.

### How to keep an honest test log

For an engineering portfolio, record results in a table rather than prose:

| Date | Input | Ground truth | FFT bin (Hz) | Refined (Hz) | Error (Hz) | Error (cents) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| YYYY-MM-DD | `A4_440Hz_reference_tone.wav` | 440.00 | 441.43 | 439.89 | −0.11 | −0.43 | Steady synthetic tone |

Change one variable at a time (block size, hop size, window type, noise level) and record the effect. Also note the cases that fail — for example, the final frame of the reference tone reads 439.33 Hz because zero-padding at the end of the clip distorts the windowed spectrum. Documenting known error sources is more credible than reporting only best-case numbers.

## Reading the output

| Output | Meaning |
| --- | --- |
| **Waveform** | Amplitude versus time. Useful for spotting silence, clipping, and overall envelope. |
| **FFT spectrum** | Average magnitude across all frames, in dB relative to the largest value. Peaks correspond to dominant frequencies. |
| **Spectrogram** | Frequency (vertical) over time (horizontal), with colour representing magnitude. Horizontal bands are steady tones. |
| **CSV** | One row per frame: `time_s`, `rms`, `fft_bin_frequency_hz`, `refined_frequency_hz`, `note`, `cents_offset`. |

## Screenshots

No screenshots are committed yet, because they have not been captured. To document the interface, add these captures to `screenshots/`:

1. `01_upload.png` — the input area with an audio file loaded, before analysis.
2. `02_waveform.png` — the Waveform tab for the reference tone.
3. `03_spectrum.png` — the FFT Spectrum tab, showing the clear peak near 440 Hz.
4. `04_spectrogram.png` — the Spectrogram tab, showing a stable horizontal band.
5. `05_summary.png` — the analysis summary block reporting `A4` and the refined frequency.

Capture them only after running the app yourself; do not use images that do not come from your own run.

## Deploying a shareable demo

The GitHub repository stores source code only. To obtain a public URL, deploy to **Hugging Face Spaces**:

1. Create an account at <https://huggingface.co> and generate an access token under **Settings → Access Tokens** (write scope). Never commit the token; keep it in your local credential store.
2. Create a new Space, choose **Gradio** as the SDK, and name it `audio-spectrum-analyzer`.
3. Upload `app.py`, `requirements.txt`, `README.md`, and `examples/`. The YAML block at the top of `README.md` supplies the Space metadata.
4. Wait for the build to finish, then open the Space URL and test with the reference tone.
5. Keep the Space **Private** until you have reviewed everything it exposes, then switch it to **Public** only when you are comfortable.

Before making anything public, re-read the [Limitations](#limitations) section and make sure the description matches what the demo actually does.

## Limitations

- The web version analyses an **uploaded or browser-recorded clip after you press "Analyze audio"**. It is not a continuous live-spectrum stream.
- The pitch result is a **single dominant-frequency estimate**. It is not chord recognition or polyphonic transcription.
- Accuracy depends on the recording quality, background noise, and the harmonic content of the source. Treat the reading as an estimate, not a calibrated laboratory measurement.
- The fixed `50 Hz – 2000 Hz` search band means very low bass or very high content outside that range is ignored for pitch estimation (it is still visible in the plots).
- The first and last frames are affected by edge effects and zero-padding, so their estimates are less reliable than those from the middle of a clip.
- `RMS_THRESHOLD` is a fixed heuristic; quiet passages may be reported as "no dominant pitch".

## Possible future work

- Autocorrelation-based or YIN pitch detection for comparison with the FFT approach
- Harmonic product spectrum to reduce octave errors
- Configurable block size so users can see the resolution/accuracy trade-off directly
- Peak-picking for multiple simultaneous notes
- A live-streaming mode using `gradio`'s streaming audio input

## Related projects

This repository is part of a small portfolio of Python engineering projects:

| Project | Description |
| --- | --- |
| [career](https://github.com/Dengfutian/career) | Embodied-AI / robotics job-market analysis & visualization: 51job CSV → SQLite → FastAPI analytics → ECharts dashboard |
| [jobcrawler](https://github.com/Dengfutian/jobcrawler) | 51job Selenium crawler: multi-keyword, multi-city, resumable, anti-detection, CSV output |
| [face-search](https://github.com/Dengfutian/face-search) | Classroom face recognition & photo-face detection service (InsightFace / ONNX Runtime / Faiss) |

Together they cover one pipeline end to end: **data collection → data analysis → applied AI → low-level signal processing**.

## License

Released under the MIT License — see [LICENSE](LICENSE).
