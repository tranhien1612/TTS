"""Design tokens and centralized QSS stylesheet for Neu Audio Studio (Modern Light Theme)."""

# Color Tokens (Light Minimalist Theme)
BG_MAIN = "#F8FAFC"          # Slate 50 (Clean workspace background)
BG_SURFACE = "#FFFFFF"       # Pure White (Cards, sidebar, elevated surfaces)
BG_SUBTLE = "#F1F5F9"        # Slate 100 (Inputs, secondary buttons, subtle tags)
BG_HOVER = "#F8FAFC"         # Soft hover surface

ACCENT_PRIMARY = "#4F46E5"   # Indigo 600 (Main brand actions, sliders, active items)
ACCENT_HOVER = "#4338CA"     # Indigo 700 (Hover state for action buttons)
ACCENT_LIGHT = "#EEF2FF"     # Indigo 50 (Tint for active navigation and badges)
ACCENT_BORDER = "#C7D2FE"    # Indigo 200 (Subtle border for active elements)

TEXT_MAIN = "#0F172A"        # Slate 900 (High-contrast headings, body text)
TEXT_SECONDARY = "#334155"   # Slate 700 (Readable secondary text)
TEXT_MUTED = "#64748B"       # Slate 500 (Captions, subtitles, hints)
TEXT_WHITE = "#FFFFFF"       # White text on primary buttons

BORDER_COLOR = "#E2E8F0"     # Slate 200 (Crisp card borders and dividers)
BORDER_INPUT = "#CBD5E1"     # Slate 300 (Input and dropdown borders)
BORDER_FOCUS = "#4F46E5"     # Indigo 600 (Focus ring)

SUCCESS_COLOR = "#059669"    # Emerald 600
SUCCESS_BG = "#ECFDF5"       # Emerald 50
WARNING_COLOR = "#D97706"    # Amber 600
DANGER_COLOR = "#DC2626"     # Red 600

GLOBAL_STYLESHEET = f"""
/* Global Reset and Window */
QWidget {{
    color: {TEXT_MAIN};
    font-family: 'Segoe UI', 'Inter', -apple-system, sans-serif;
    font-size: 14px;
    selection-background-color: {ACCENT_LIGHT};
    selection-color: {ACCENT_PRIMARY};
}}

QMainWindow, QWidget#rootWidget, QStackedWidget {{
    background-color: {BG_MAIN};
}}

QLabel {{
    background-color: transparent;
    color: {TEXT_MAIN};
}}

QRadioButton {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    font-size: 13px;
    font-weight: 500;
    spacing: 8px;
}}

QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 2px solid {BORDER_INPUT};
    background-color: {BG_SURFACE};
}}

QRadioButton::indicator:hover {{
    border-color: {ACCENT_PRIMARY};
}}

QRadioButton::indicator:checked {{
    border: 2px solid {ACCENT_PRIMARY};
    background-color: {ACCENT_PRIMARY};
}}

QCheckBox {{
    background-color: transparent;
    color: {TEXT_MAIN};
}}

QScrollArea {{
    background-color: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

/* Sidebar Container */
#sidebarFrame {{
    background-color: {BG_SURFACE};
    border-right: 1px solid {BORDER_COLOR};
    border-radius: 0px;
}}

/* App Title / Brand in Sidebar */
#appTitle {{
    color: {TEXT_MAIN};
    font-size: 18px;
    font-weight: bold;
    padding-bottom: 2px;
}}

/* Navigation Buttons */
QPushButton[class="nav-btn"], QPushButton.nav-btn {{
    background-color: transparent;
    color: {TEXT_MUTED};
    font-size: 14px;
    font-weight: 600;
    text-align: left;
    padding: 10px 14px;
    border-radius: 8px;
    border: 1px solid transparent;
}}

QPushButton[class="nav-btn"]:hover, QPushButton.nav-btn:hover {{
    background-color: {BG_MAIN};
    color: {TEXT_MAIN};
}}

QPushButton[class="nav-btn"][active="true"], QPushButton.nav-btn[active="true"] {{
    background-color: {ACCENT_LIGHT};
    color: {ACCENT_PRIMARY};
    font-weight: bold;
    border: 1px solid {ACCENT_BORDER};
}}

/* Card Container */
QFrame[class="card"], QFrame.card {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER_COLOR};
    border-radius: 12px;
}}

/* Typography Classes */
QLabel[class="header-title"], QLabel.header-title {{
    color: {TEXT_MAIN};
    font-size: 18px;
    font-weight: bold;
}}

QLabel[class="section-title"], QLabel.section-title {{
    color: {TEXT_MAIN};
    font-size: 15px;
    font-weight: 600;
}}

QLabel[class="caption"], QLabel.caption {{
    color: {TEXT_MUTED};
    font-size: 12px;
    font-weight: 500;
    background-color: transparent;
}}

QLabel[class="badge"], QLabel.badge {{
    background-color: {BG_SUBTLE};
    color: {TEXT_MUTED};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 4px 9px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel[class="badge-accent"], QLabel.badge-accent {{
    background-color: {ACCENT_LIGHT};
    color: {ACCENT_PRIMARY};
    border: 1px solid {ACCENT_BORDER};
    border-radius: 6px;
    padding: 4px 9px;
    font-size: 11px;
    font-weight: 600;
}}

/* Text Input & Text Area */
QTextEdit, QPlainTextEdit, QLineEdit {{
    background-color: {BG_SURFACE};
    color: {TEXT_MAIN};
    border: 1px solid {BORDER_INPUT};
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 14px;
}}

QTextEdit:focus, QPlainTextEdit:focus, QLineEdit:focus {{
    border: 1.5px solid {ACCENT_PRIMARY};
    background-color: {BG_SURFACE};
    color: {TEXT_MAIN};
}}

/* Dropdowns / ComboBox */
QComboBox {{
    background-color: {BG_SURFACE};
    color: {TEXT_MAIN};
    border: 1px solid {BORDER_INPUT};
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 22px;
    font-size: 14px;
}}

QComboBox:hover {{
    border: 1px solid {TEXT_MUTED};
}}

QComboBox:focus {{
    border: 1.5px solid {ACCENT_PRIMARY};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid {BORDER_COLOR};
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background-color: {BG_MAIN};
}}

/* Opaque ComboBox popup container and view */
QComboBox QFrame {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER_INPUT};
    border-radius: 8px;
}}

QComboBox QAbstractItemView, QComboBox QListView {{
    background-color: {BG_SURFACE};
    color: {TEXT_MAIN};
    border: 1px solid {BORDER_INPUT};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {ACCENT_LIGHT};
    selection-color: {ACCENT_PRIMARY};
    outline: none;
}}

QComboBox QAbstractItemView::item, QComboBox QListView::item {{
    background-color: {BG_SURFACE};
    padding: 8px 12px;
    border-radius: 6px;
    color: {TEXT_MAIN};
    min-height: 24px;
}}

QComboBox QAbstractItemView::item:hover, QComboBox QListView::item:hover {{
    background-color: {BG_SUBTLE};
    color: {TEXT_MAIN};
}}

QComboBox QAbstractItemView::item:selected, QComboBox QListView::item:selected {{
    background-color: {ACCENT_LIGHT};
    color: {ACCENT_PRIMARY};
    font-weight: 600;
}}

/* Sliders */
QSlider:horizontal {{
    min-height: 24px;
}}

QSlider::groove:horizontal {{
    height: 6px;
    background-color: {BORDER_COLOR};
    border-radius: 3px;
}}

QSlider::sub-page:horizontal {{
    background-color: {ACCENT_PRIMARY};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background-color: {BG_SURFACE};
    border: 2px solid {ACCENT_PRIMARY};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {ACCENT_LIGHT};
    border-color: {ACCENT_HOVER};
}}

/* Push Buttons - Default Fallback */
QPushButton {{
    background-color: {BG_SURFACE};
    color: {TEXT_MAIN};
    font-size: 13px;
    font-weight: 600;
    padding: 8px 16px;
    border-radius: 8px;
    border: 1px solid {BORDER_INPUT};
}}

QPushButton:hover {{
    background-color: {ACCENT_LIGHT};
    border-color: {ACCENT_PRIMARY};
    color: {ACCENT_PRIMARY};
}}

QPushButton:pressed {{
    background-color: #E0E7FF;
}}

QPushButton:disabled {{
    background-color: {BG_MAIN};
    color: {TEXT_MUTED};
    border-color: {BORDER_COLOR};
}}

/* Primary Buttons */
QPushButton[class="primary-btn"], QPushButton.primary-btn, #btnSynthesize, QPushButton#btnSynthesize {{
    background-color: {ACCENT_PRIMARY};
    color: {TEXT_WHITE};
    font-size: 14px;
    font-weight: 700;
    padding: 10px 22px;
    border-radius: 8px;
    border: 1px solid {ACCENT_HOVER};
}}

QPushButton[class="primary-btn"]:hover, QPushButton.primary-btn:hover, #btnSynthesize:hover, QPushButton#btnSynthesize:hover {{
    background-color: {ACCENT_HOVER};
    color: {TEXT_WHITE};
    border-color: #3730A3;
}}

QPushButton[class="primary-btn"]:pressed, QPushButton.primary-btn:pressed, #btnSynthesize:pressed, QPushButton#btnSynthesize:pressed {{
    background-color: #3730A3;
    color: {TEXT_WHITE};
}}

QPushButton[class="primary-btn"]:disabled, QPushButton.primary-btn:disabled, #btnSynthesize:disabled, QPushButton#btnSynthesize:disabled {{
    background-color: #CBD5E1;
    color: #64748B;
    border-color: #CBD5E1;
}}

/* Secondary Buttons */
QPushButton[class="secondary-btn"], QPushButton.secondary-btn {{
    background-color: {BG_SURFACE};
    color: {TEXT_MAIN};
    font-size: 13px;
    font-weight: 600;
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid {BORDER_INPUT};
}}

QPushButton[class="secondary-btn"]:hover, QPushButton.secondary-btn:hover {{
    background-color: {ACCENT_LIGHT};
    border-color: {ACCENT_PRIMARY};
    color: {ACCENT_PRIMARY};
}}

QPushButton[class="secondary-btn"]:pressed, QPushButton.secondary-btn:pressed {{
    background-color: #E0E7FF;
}}

QPushButton[class="secondary-btn"]:disabled, QPushButton.secondary-btn:disabled {{
    background-color: {BG_MAIN};
    color: {TEXT_MUTED};
    border-color: {BORDER_COLOR};
}}

/* Icon Buttons */
QPushButton[class="icon-btn"], QPushButton.icon-btn {{
    background-color: {BG_SURFACE};
    color: {TEXT_MAIN};
    border: 1px solid {BORDER_INPUT};
    border-radius: 8px;
    min-width: 36px;
    min-height: 36px;
    font-size: 14px;
}}

QPushButton[class="icon-btn"]:hover, QPushButton.icon-btn:hover {{
    background-color: {ACCENT_LIGHT};
    border-color: {ACCENT_PRIMARY};
    color: {ACCENT_PRIMARY};
}}

/* Sliders */
QSlider {{
    background-color: transparent;
}}

QSlider::groove:horizontal {{
    height: 6px;
    background: {BORDER_COLOR};
    border-radius: 3px;
}}

QSlider::sub-page:horizontal {{
    background: {ACCENT_PRIMARY};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: {BG_SURFACE};
    border: 2px solid {ACCENT_PRIMARY};
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}}

QSlider::handle:horizontal:hover {{
    background: {ACCENT_LIGHT};
    border-color: {ACCENT_HOVER};
}}

/* Progress Bar */
QProgressBar {{
    background-color: {BG_SUBTLE};
    border: 1px solid {BORDER_COLOR};
    border-radius: 5px;
    text-align: center;
    color: {TEXT_MAIN};
    font-size: 12px;
    min-height: 5px;
    max-height: 5px;
}}

QProgressBar::chunk {{
    background-color: {ACCENT_PRIMARY};
    border-radius: 4px;
}}

/* Sleek Scrollbars */
QScrollBar:vertical {{
    background: {BG_MAIN};
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background: {BORDER_INPUT};
    min-height: 20px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background: {TEXT_MUTED};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: {BG_MAIN};
    height: 8px;
    margin: 0px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background: {BORDER_INPUT};
    min-width: 20px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {TEXT_MUTED};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* Tooltips */
QToolTip {{
    background-color: {TEXT_MAIN};
    color: {TEXT_WHITE};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}
"""

# Direct stylesheets for explicit assignment to guarantee 100% render accuracy
PRIMARY_BUTTON_STYLE = f"""
QPushButton {{
    background-color: {ACCENT_PRIMARY};
    color: {TEXT_WHITE};
    font-size: 14px;
    font-weight: 700;
    padding: 10px 22px;
    border-radius: 8px;
    border: 1px solid {ACCENT_HOVER};
}}
QPushButton:hover {{
    background-color: {ACCENT_HOVER};
    color: {TEXT_WHITE};
    border-color: #3730A3;
}}
QPushButton:pressed {{
    background-color: #3730A3;
    color: {TEXT_WHITE};
}}
QPushButton:disabled {{
    background-color: #CBD5E1;
    color: #64748B;
    border-color: #CBD5E1;
}}
"""

SECONDARY_BUTTON_STYLE = f"""
QPushButton {{
    background-color: {BG_SURFACE};
    color: {TEXT_MAIN};
    font-size: 13px;
    font-weight: 600;
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid {BORDER_INPUT};
}}
QPushButton:hover {{
    background-color: {ACCENT_LIGHT};
    border-color: {ACCENT_PRIMARY};
    color: {ACCENT_PRIMARY};
}}
QPushButton:pressed {{
    background-color: #E0E7FF;
}}
QPushButton:disabled {{
    background-color: {BG_MAIN};
    color: {TEXT_MUTED};
    border-color: {BORDER_COLOR};
}}
"""

