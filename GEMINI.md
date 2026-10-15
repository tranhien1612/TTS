# GEMINI.md - System Architecture & Design Specification

## 1. Project Overview

* **Project Name:** Neu Audio Studio (VieNeu Core)
* **Goal:** Build a lightweight, modern, minimalist desktop application for Text-to-Speech (TTS) with instant voice cloning, easily expandable to Speech-to-Text (STT) and other multi-modal audio features.
* **Core Technology Stack:** Python 3.11+, PyQt6 (UI framework), VieNeu Model Core (AI inference).

## 2. System Architecture & Directory Structure

To ensure clean code maintainability, scalability, and easy management, the project follows a modular architecture separating business logic, AI engines, and user interface into dedicated subdirectories.

```
neu_audio_studio/
│
├── models/                # AI Model weight files
│   ├── __init__.py
│   ├── vieneu/            # VieNeu TTS ONNX weights
│   └── whisper-large-v3-turbo/ # Whisper Large-v3-Turbo INT8 weights
│
├── core/                  # Shared system logic & utilities
│   ├── __init__.py
│   ├── config.py          # App settings, paths, model parameters
│   ├── model_manager.py   # Model verification & automated download
│   ├── worker.py          # QThread asynchronous background runners
│   └── mic_recorder.py    # Microphone realtime streaming capture worker
│
├── engines/               # AI Model integration wrappers
│   ├── __init__.py
│   ├── base_engine.py     # Abstract base class for AI models
│   ├── tts_engine.py      # VieNeu TTS wrapper (Text -> Audio + Voice Clone)
│   └── stt_engine.py      # Whisper-Large-v3-Turbo STT wrapper (INT8 CPU)
│
├── ui/                    # Presentation Layer (PyQt6)
│   ├── __init__.py
│   ├── styles.py          # Centralized QSS stylesheet & design tokens
│   ├── main_window.py     # Root window, sidebar layout, and view router
│   ├── views/             # Individual application screens
│   │   ├── __init__.py
│   │   ├── tts_view.py    # TTS & Voice Cloning interface
│   │   └── stt_view.py    # STT placeholder interface
│   └── components/        # Reusable custom UI components (cards, players)
│       └── __init__.py
│
├── assets/                # Static assets
│   ├── icons/             # App and navigation icons (.png / .svg)
├── tests/                 # Unit & integration smoke tests
│   ├── __init__.py
│   ├── test_smoke.py      # Assert-based system self-check
│   └── test_qss.py        # Stylesheet pixel verification
│
├── main.py                # Application entry point
└── requirements.txt       # Project dependencies
```

## 3. UI/UX Design System & Format Specifications

The application adopts a **Modern Light Minimalist** design system to ensure a clean, high-contrast, professional, and comfortable user experience.

### 3.1. Color Palette (Light Theme Tokens)
* **Background Main (`--bg-main`):** `#F8FAFC` (Slate 50) - Clean, soft off-white workspace canvas.
* **Background Surface (`--bg-surface`):** `#FFFFFF` (Pure White) - Cards, sidebar, containers, and elevated surfaces.
* **Background Input / Subtle (`--bg-subtle`):** `#F1F5F9` (Slate 100) - Input fill and secondary button background.
* **Primary Accent (`--accent-primary`):** `#4F46E5` (Indigo 600) - Primary brand action buttons, active navigation, indicators.
* **Primary Hover (`--accent-hover`):** `#4338CA` (Indigo 700) - Interactive hover state.
* **Primary Light (`--accent-light`):** `#EEF2FF` (Indigo 50) - Active tab fill and accent badge tint.
* **Text Primary (`--text-main`):** `#0F172A` (Slate 900) - High-contrast headers, labels, and input text.
* **Text Secondary (`--text-muted`):** `#64748B` (Slate 500) - Subtitles, hints, and placeholder text.
* **Border / Divider (`--border-color`):** `#E2E8F0` (Slate 200) - Subtle separation lines and card borders.
* **Border Focus (`--border-focus`):** `#4F46E5` (Indigo 600) - Focus outline for active inputs.

### 3.2. Typography & Fonts
* **Font Family:** `Segoe UI`, `Inter`, `sans-serif` (Cross-platform native smooth rendering).
* **Font Sizes & Weights:**
  * **App Title / Header 1:** `18px - 20px`, Bold (`QFont.Weight.Bold`)
  * **Section Title / Header 2:** `15px - 16px`, SemiBold (`QFont.Weight.SemiBold`)
  * **Body Text / Inputs:** `14px`, Regular (`QFont.Weight.Normal`)
  * **Labels / Captions:** `12px`, Medium (`QFont.Weight.Medium`)

### 3.3. Component Geometry & Layout Rules
* **Border Radius:**
  * Cards / Containers: `12px`
  * Inputs / Buttons / Dropdowns: `8px`
* **Spacing / Padding:**
  * Window Margins: `24px` padding around main views.
  * Card Inner Padding: `20px` internal padding.
  * Widget Spacing: `12px` to `16px` gap between vertical elements.
* **Sidebar Specification:**
  * Fixed width: `220px`.
  * Padding: `12px` horizontal, `20px` vertical.

### 3.4. Performance & Lightweight Principles
1. **Asynchronous Execution:** Heavy tasks (such as AI model inference via VieNeu) **must** run inside a `QThread` (`core/worker.py`) to prevent UI freezing and ensure responsiveness.
2. **Lazy Loading:** AI models should be loaded on-demand or initialized in background threads to reduce startup latency.
3. **Clean Styling:** Use native PyQt stylesheet injection via a central `styles.py` module to maintain low memory overhead.