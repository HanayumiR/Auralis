from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from mutagen import File as MutagenFile
from mutagen.mp4 import MP4, MP4Cover
from PIL import Image, ImageOps
from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QSettings, QThread, QTimer, Qt, Signal, QSize
from PySide6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent, QFont, QIcon, QKeySequence, QLinearGradient, QPainter, QPixmap, QUndoStack, QUndoCommand
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QDoubleSpinBox,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "Auralis"
APP_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = APP_DIR / "ALAC Output"
ASSET_DIR = APP_DIR / "assets"
SETTINGS_ORG = "Auralis"
SETTINGS_APP = "Auralis"

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

MB_BASE = "https://musicbrainz.org/ws/2"
CAA_BASE = "https://coverartarchive.org"
HTTP_HEADERS = {
    "User-Agent": "Auralis/0.2 (local desktop app; https://musicbrainz.org/doc/MusicBrainz_API)",
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
}

def load_themes() -> Dict[str, dict]:
    themes: Dict[str, dict] = {}
    themes_dir = APP_DIR / "Resources" / "themes"
    if themes_dir.exists():
        for theme_path in sorted(themes_dir.glob("*.json")):
            theme_name = theme_path.stem
            try:
                with theme_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
               
                if "backdrop" in data:
                    data["backdrop"] = tuple(data["backdrop"])
                if "bands" in data:
                    data["bands"] = tuple(data["bands"])
                themes[theme_name] = data
            except Exception:
                pass
    if not themes:
        
        themes["Default"] = {
            "text": "#173144",
            "muted": "#527383",
            "shell": "rgba(236, 249, 255, 0.56)",
            "card": "rgba(239, 251, 255, 0.46)",
            "field": "rgba(255, 255, 255, 0.50)",
            "accent": "rgba(24, 157, 176, 0.92)",
            "accent_hover": "rgba(41, 184, 204, 0.96)",
            "chunk": "#31bfd1",
            "backdrop": ("#daf5ff", "#a0d6eb", "#25465e"),
            "bands": ("rgba(255, 255, 255, 94)", "rgba(183, 233, 255, 112)", "rgba(91, 167, 208, 86)"),
        }
    return themes


THEMES = load_themes()


def load_presets() -> Dict[str, Optional[Tuple[float, float]]]:
    presets: Dict[str, Optional[Tuple[float, float]]] = {}
    
    for presets_dir_name in ("Presets", "presets"):
        presets_dir = APP_DIR / "Resources" / presets_dir_name
        if presets_dir.exists():
            for preset_path in sorted(presets_dir.glob("*.json")):
                try:
                    with preset_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    display_name: str = data.get("display_name") or preset_path.stem
                    lufs = data.get("loudness_lufs")
                    tp = data.get("true_peak_db")
                    if lufs is not None and tp is not None:
                        presets[display_name] = (float(lufs), float(tp))
                    else:
                        presets[display_name] = None
                except Exception:
                    pass
            break
  
    if NO_OP_PRESET_KEY not in presets:
        ordered: Dict[str, Optional[Tuple[float, float]]] = {NO_OP_PRESET_KEY: None}
        ordered.update(presets)
        presets = ordered
    return presets


LANGUAGE_TITLE_KEY = "language_title"


def load_language_resources() -> Tuple[Dict[str, str], Dict[str, Dict[str, object]]]:
    languages: Dict[str, str] = {}
    ui_text: Dict[str, Dict[str, object]] = {}
    language_dir = APP_DIR / "Resources" / "Languages"
    for language_path in sorted(language_dir.glob("*.json")):
        language_code = language_path.stem
        with language_path.open("r", encoding="utf-8") as language_file:
            language_text = json.load(language_file)
        language_title = str(language_text.get(LANGUAGE_TITLE_KEY, language_code)).strip() or language_code
        if language_title in languages:
            language_title = f"{language_title} ({language_code})"
        languages[language_title] = language_code
        ui_text[language_code] = language_text
    if not languages:
        raise RuntimeError(f"No language files were found in {language_dir}")
    return languages, ui_text


LANGUAGES, UI_TEXT = load_language_resources()
DEFAULT_LANGUAGE_CODE = "ja" if "ja" in UI_TEXT else next(iter(UI_TEXT))
DEFAULT_LANGUAGE_NAME = next(
    (language_name for language_name, language_code in LANGUAGES.items() if language_code == DEFAULT_LANGUAGE_CODE),
    next(iter(LANGUAGES)),
)


def resolve_language_name(language_setting: str) -> str:
    if language_setting in LANGUAGES:
        return language_setting
    for language_name, language_code in LANGUAGES.items():
        if language_setting == language_code:
            return language_name
    return DEFAULT_LANGUAGE_NAME


LOSSLESS_CODECS = {
    "alac",
    "als",
    "ape",
    "flac",
    "mlp",
    "shorten",
    "tak",
    "tta",
    "truehd",
    "wavpack",
}

LOSSY_CODECS = {
    "aac",
    "ac3",
    "amr_nb",
    "amr_wb",
    "dca",
    "dts",
    "eac3",
    "mp1",
    "mp2",
    "mp3",
    "mp4a",
    "musepack7",
    "musepack8",
    "opus",
    "vorbis",
    "wma",
    "wmav1",
    "wmav2",
}

TAG_FIELDS = [
    "title",
    "artist",
    "album",
    "albumartist",
    "date",
    "tracknumber",
    "discnumber",
    "genre",
    "composer",
    "comment",
]


@dataclass
class AudioInfo:
    codec: str
    sample_rate: int
    bit_depth: int
    channels: int
    duration: float
    format_name: str
    quality_label: str


@dataclass
class TrackItemState:
    path: Path
    info: AudioInfo
    tags: Dict[str, str] = field(default_factory=dict)
    cover_data: Optional[bytes] = None
    cover_mime: Optional[str] = None
    status: str = "待機"
    error: str = ""
    output_path: Optional[Path] = None
    mb_release_id: Optional[str] = None
    mb_release_group_id: Optional[str] = None


@dataclass
class ReleaseCandidate:
    release_id: str
    title: str
    artist: str
    date: str
    country: str
    score: int
    release_group_id: str = ""

    def label(self) -> str:
        bits = [self.artist, self.title]
        suffix = " / ".join(x for x in [self.date, self.country, f"{self.score}%"] if x)
        return " - ".join(x for x in bits if x) + (f" ({suffix})" if suffix else "")


@dataclass
class CoverArtCandidate:
    label: str
    data: bytes
    mime: str
    width: int = 0
    height: int = 0


@dataclass
class ConversionSettings:
    normalize: bool = False
    loudness_lufs: float = -14.0
    true_peak_db: float = -1.0



NO_OP_PRESET_KEY = "変更なし"


def fallback_theme() -> dict:
    """Return the first available theme. Never hardcodes a theme name."""
    return THEMES[next(iter(THEMES))]


class AppBackdrop(QWidget):
    def __init__(self):
        super().__init__()
        self.theme = fallback_theme()

    def set_theme(self, theme: dict) -> None:
        self.theme = theme
        self.update()

    def theme_color(self, value: str) -> QColor:
        rgba_match = re.match(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", value)
        if rgba_match:
            r, g, b, a = rgba_match.groups()
            alpha_val = float(a)
            if alpha_val <= 1.0 and "." in a:
                alpha_val = int(alpha_val * 255)
            else:
                alpha_val = int(alpha_val)
            return QColor(int(r), int(g), int(b), alpha_val)
        return QColor(value)

    def paintEvent(self, event):  
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        _fb = fallback_theme()
        backdrop = self.theme.get("backdrop", _fb["backdrop"])
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, self.theme_color(backdrop[0]))
        gradient.setColorAt(0.42, self.theme_color(backdrop[1]))
        gradient.setColorAt(1.0, self.theme_color(backdrop[2]))
        painter.fillRect(rect, gradient)

        for i, color_value in enumerate(self.theme.get("bands", _fb["bands"])):
            band = rect.adjusted(-120 + i * 120, 36 + i * 62, 180 - i * 80, -rect.height() // 3 + i * 34)
            painter.setBrush(self.theme_color(color_value))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(band, 8, 8)


class MetadataWorker(QThread):
    results_ready = Signal(list)
    detail_ready = Signal(dict, bytes, str)
    failed = Signal(str)

    def __init__(self, mode: str, query: str = "", release_id: str = "", release_group_id: str = ""):
        super().__init__()
        self.mode = mode
        self.query = query
        self.release_id = release_id
        self.release_group_id = release_group_id

    def run(self) -> None:
        try:
            if self.mode == "search":
                self.results_ready.emit(search_musicbrainz_releases(self.query))
            elif self.mode == "detail":
                release = lookup_musicbrainz_release(self.release_id)
                cover_data, cover_mime = fetch_cover_art(self.release_id, self.release_group_id)
                self.detail_ready.emit(release, cover_data or b"", cover_mime or "")
        except Exception as exc:
            self.failed.emit(str(exc))


class ConversionWorker(QThread):
    track_progress = Signal(int, int, str)
    track_done = Signal(int, bool, str)
    log_line = Signal(str)
    done = Signal()

    def __init__(self, tracks: List[TrackItemState], output_dir: Path, settings: ConversionSettings):
        super().__init__()
        self.tracks = tracks
        self.output_dir = output_dir
        self.settings = settings
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for index, track in enumerate(self.tracks):
            if self._cancel:
                self.log_line.emit("変換を停止しました。")
                break
            try:
                self.track_progress.emit(index, 0, "変換中")
                output_path = unique_output_path(self.output_dir, track.path.stem)
                convert_to_alac(
                    track,
                    output_path,
                    self.settings,
                    lambda pct: self.track_progress.emit(index, pct, "変換中"),
                )
                write_mp4_tags(output_path, track.tags, track.cover_data, track.cover_mime, track)
                track.output_path = output_path
                track.status = "完了"
                self.track_progress.emit(index, 100, "完了")
                self.track_done.emit(index, True, str(output_path))
            except Exception as exc:
                track.status = "エラー"
                track.error = str(exc)
                self.track_done.emit(index, False, str(exc))
        self.done.emit()


class CoverLabel(QLabel):
    def __init__(self):
        super().__init__()
        self._data: Optional[bytes] = None
        self.setMinimumSize(220, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAlignment(Qt.AlignCenter)
        self.setText(getattr(self, "placeholder_text", "No Artwork"))

    def set_cover(self, data: Optional[bytes]) -> None:
        self._data = data
        self.refresh()

    def resizeEvent(self, event):  
        self.refresh()
        super().resizeEvent(event)

    def refresh(self) -> None:
        if not self._data:
            self.setPixmap(QPixmap())
            self.setText(getattr(self, "placeholder_text", "No Artwork"))
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(self._data):
            self.setPixmap(QPixmap())
            self.setText("COVER ERROR")
            return
        size = self.size() - QSize(12, 12)
        self.setText("")
        self.setPixmap(pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))


class CoverCandidateDialog(QDialog):
    def __init__(self, parent: QWidget, candidates: List[CoverArtCandidate]):
        super().__init__(parent)
        self.setWindowTitle("Artwork Candidates")
        self.selected: Optional[CoverArtCandidate] = None
        self.resize(720, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        title = QLabel("Artwork Candidates")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        for index, candidate in enumerate(candidates):
            button = QPushButton(candidate.label)
            button.setObjectName("artCandidateButton")
            button.setMinimumSize(170, 190)
            button.setIconSize(QSize(144, 144))
            pixmap = QPixmap()
            pixmap.loadFromData(candidate.data)
            if not pixmap.isNull():
                button.setIcon(QIcon(pixmap.scaled(144, 144, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            button.clicked.connect(lambda _checked=False, item=candidate: self.choose(item))
            grid.addWidget(button, index // 3, index % 3)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    def choose(self, candidate: CoverArtCandidate) -> None:
        self.selected = candidate
        self.accept()


class PreferencesDialog(QDialog):
    def __init__(self, parent: QWidget, theme_name: str, language_name: str, first_run: bool = False):
        super().__init__(parent)
        get_text = parent.ui_text if hasattr(parent, "ui_text") else lambda k: k
        title_text = get_text("settings") if get_text("settings") != "settings" else "Settings"
        self.setWindowTitle(title_text if not first_run else "Initial Setup")
        self.setModal(True)
        self.resize(420, 220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        
        select_display = get_text("select_display_settings") if get_text("select_display_settings") != "select_display_settings" else "Please select display settings"
        title = QLabel(select_display if first_run else title_text)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        form = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.setCurrentText(theme_name if theme_name in THEMES else next(iter(THEMES)))
        self.language_combo = QComboBox()
        self.language_combo.addItems(LANGUAGES.keys())
        self.language_combo.setCurrentText(resolve_language_name(language_name))
        
        lbl_theme = get_text("theme_color") if get_text("theme_color") != "theme_color" else "Theme Color"
        lbl_lang = get_text("language") if get_text("language") != "language" else "Language"
        form.addRow(lbl_theme, self.theme_combo)
        form.addRow(lbl_lang, self.language_combo)
        layout.addLayout(form)

        lbl_note = get_text("settings_saved_next_launch") if get_text("settings_saved_next_launch") != "settings_saved_next_launch" else "Settings will be saved for next launch."
        note = QLabel(lbl_note)
        note.setObjectName("latestLog")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_ok = get_text("ok") if get_text("ok") != "ok" else "OK"
        btn_cancel = get_text("cancel") if get_text("cancel") != "cancel" else "Cancel"
        buttons.button(QDialogButtonBox.Ok).setText(btn_ok)
        buttons.button(QDialogButtonBox.Cancel).setText(btn_cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> Tuple[str, str]:
        return self.theme_combo.currentText(), self.language_combo.currentText()



class AddTracksCommand(QUndoCommand):
    def __init__(self, main_window, new_tracks, start_index):
        super().__init__("曲の追加")
        self.mw = main_window
        self.new_tracks = new_tracks
        self.start_index = start_index

    def redo(self):
        for i, track in enumerate(self.new_tracks):
            idx = self.start_index + i
            self.mw.tracks.insert(idx, track)
            self.mw.table.insertRow(idx)
            
            values = [
                track.path.name,
                track.info.codec.upper(),
                track.info.quality_label,
                format_duration(track.info.duration),
                "",
                "",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.mw.table.setItem(idx, col, item)
            
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(0)
            self.mw.table.setCellWidget(idx, 4, progress)
            
            remove_button = QPushButton("×")
            remove_button.setObjectName("rowRemoveButton")
            remove_button.setFixedSize(28, 28)
            remove_button.clicked.connect(lambda _checked=False, button=remove_button: self.mw.remove_row_for_button(button))
            remove_holder = QWidget()
            remove_holder.setObjectName("rowRemoveHolder")
            remove_layout = QHBoxLayout(remove_holder)
            remove_layout.setContentsMargins(0, 0, 0, 0)
            remove_layout.setSpacing(0)
            remove_layout.addStretch(1)
            remove_layout.addWidget(remove_button, 0, Qt.AlignCenter)
            remove_layout.addStretch(1)
            self.mw.table.setCellWidget(idx, 5, remove_holder)
            self.mw.table.setRowHeight(idx, 38)
            
        self.mw.update_status()

    def undo(self):
        for _ in self.new_tracks:
            self.mw._do_remove_track_at(self.start_index)

class RemoveTrackCommand(QUndoCommand):
    def __init__(self, main_window, row, track):
        super().__init__("曲の削除")
        self.mw = main_window
        self.row = row
        self.track = track

    def redo(self):
        self.mw._do_remove_track_at(self.row)

    def undo(self):
        cmd = AddTracksCommand(self.mw, [self.track], self.row)
        cmd.redo()

class ClearQueueCommand(QUndoCommand):
    def __init__(self, main_window, old_tracks):
        super().__init__("キューのクリア")
        self.mw = main_window
        self.old_tracks = old_tracks

    def redo(self):
        self.mw._do_clear_queue()

    def undo(self):
        cmd = AddTracksCommand(self.mw, self.old_tracks, 0)
        cmd.redo()

class EditTagsCommand(QUndoCommand):
    def __init__(self, main_window, track_index, old_tags, new_tags):
        super().__init__("メタデータの編集")
        self.mw = main_window
        self.track_index = track_index
        self.old_tags = old_tags.copy()
        self.new_tags = new_tags.copy()

    def _apply(self, tags):
        if 0 <= self.track_index < len(self.mw.tracks):
            self.mw.tracks[self.track_index].tags = tags.copy()
            if self.mw.current_row == self.track_index:
                self.mw.load_track_into_form(self.mw.tracks[self.track_index])
            self.mw.refresh_table_labels()

    def redo(self):
        self._apply(self.new_tags)

    def undo(self):
        self._apply(self.old_tags)

class ApplyReleaseCommand(QUndoCommand):
    def __init__(self, main_window, track_index, release, cover_data, cover_mime):
        super().__init__("メタデータ一括反映")
        self.mw = main_window
        self.track_index = track_index
        self.release = release
        self.cover_data = cover_data
        self.cover_mime = cover_mime
        
       
        t = self.mw.tracks[self.track_index]
        self.old_tags = t.tags.copy()
        self.old_cover_data = t.cover_data
        self.old_cover_mime = t.cover_mime

    def redo(self):
        if 0 <= self.track_index < len(self.mw.tracks):
            t = self.mw.tracks[self.track_index]
            apply_release_to_track(self.release, t, queue_index=None)
            if self.cover_data:
                t.cover_data = self.cover_data
                t.cover_mime = self.cover_mime
            if self.mw.current_row == self.track_index:
                self.mw.load_track_into_form(t)
            self.mw.refresh_table_labels()

    def undo(self):
        if 0 <= self.track_index < len(self.mw.tracks):
            t = self.mw.tracks[self.track_index]
            t.tags = self.old_tags.copy()
            t.cover_data = self.old_cover_data
            t.cover_mime = self.old_cover_mime
            if self.mw.current_row == self.track_index:
                self.mw.load_track_into_form(t)
            self.mw.refresh_table_labels()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        if sys.platform == "darwin":
            self.setUnifiedTitleAndToolBarOnMac(True)
        icon_path = app_asset_path("Auralis.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1240, 720)
        self.setAcceptDrops(True)
        self.tracks: List[TrackItemState] = []
        self.current_row = -1
        self.candidates: List[ReleaseCandidate] = []
        self.release_detail: Optional[dict] = None
        self.release_cover_data: Optional[bytes] = None
        self.release_cover_mime: str = ""
        self.metadata_worker: Optional[MetadataWorker] = None
        self.conversion_worker: Optional[ConversionWorker] = None
        self.loading_form = False
        self.auto_apply_metadata = True
        self.undo_stack = QUndoStack(self)
        self.action_hint_effect: Optional[QGraphicsOpacityEffect] = None
        self.action_hint_animation: Optional[QPropertyAnimation] = None
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.theme_name = str(self.settings.value("theme", next(iter(THEMES))))
       
        _legacy_theme_names = {"雪解け硝子", "Aero Aqua"}
        if self.theme_name in _legacy_theme_names or self.theme_name not in THEMES:
            self.theme_name = next(iter(THEMES))
        self.language_name = resolve_language_name(str(self.settings.value("language", DEFAULT_LANGUAGE_CODE)))

        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.build_ui()
        self.build_menus()
        self.apply_style()
        self.update_status()
        self.log(self.ui_text("ready"))
        QTimer.singleShot(0, self.integrate_macos_titlebar)
        if not self.settings.value("setup_complete", False, type=bool):
            QTimer.singleShot(80, self.show_initial_preferences)

    def build_ui(self) -> None:
        root = AppBackdrop()
        self.root_backdrop = root
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 12, 16, 16)
        root_layout.setSpacing(12)

        shell = QFrame()
        shell.setObjectName("shell")
        shell.setMinimumSize(1040, 660)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(14, 14, 14, 14)
        shell_layout.setSpacing(10)

        top = QHBoxLayout()
        status_box = QVBoxLayout()
        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("statusLabel")
        self.status_detail_label = QLabel("Queue: 0")
        self.status_detail_label.setObjectName("statusDetail")
        status_box.addWidget(self.status_label)
        status_box.addWidget(self.status_detail_label)
        self.latest_log_label = QLabel("")
        self.latest_log_label.setObjectName("latestLog")
        self.latest_log_label.setMinimumWidth(260)
        status_box.addWidget(self.latest_log_label)
        top.addLayout(status_box)
        top.addStretch(1)

        self.output_dir_edit = QLineEdit(str(DEFAULT_OUTPUT_DIR))
        self.output_dir_edit.setMinimumWidth(250)
        self.output_dir_edit.setMaximumWidth(310)
        self.output_label = QLabel("Output")
        browse_out = QPushButton("Change Output")
        self.browse_out_button = browse_out
        browse_out.clicked.connect(self.choose_output_dir)
        self.auto_lookup_check = QCheckBox("Auto Search")
        self.auto_lookup_check.setChecked(True)

        add_button = QPushButton("+")
        add_button.setObjectName("addButton")
        add_button.setFixedSize(62, 62)
        self.add_button = add_button
        self.add_button.installEventFilter(self)
        add_button.clicked.connect(self.choose_files)
        self.action_hint = QLabel("")
        self.action_hint.setObjectName("actionHint")
        self.action_hint.setAlignment(Qt.AlignCenter)
        self.action_hint.setFixedSize(210, 36)
        self.action_hint_effect = QGraphicsOpacityEffect(self.action_hint)
        self.action_hint_effect.setOpacity(0.0)
        self.action_hint.setGraphicsEffect(self.action_hint_effect)
        self.action_hint_animation = QPropertyAnimation(self.action_hint_effect, b"opacity", self)
        self.action_hint_animation.setDuration(180)
        self.action_hint_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.convert_button = QPushButton("▶")
        self.convert_button.setObjectName("convertButton")
        self.convert_button.setFixedSize(62, 62)
        self.convert_button.installEventFilter(self)
        self.convert_button.clicked.connect(self.start_conversion)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(self.output_label)
        controls.addWidget(self.output_dir_edit)
        controls.addWidget(browse_out)
        controls.addWidget(self.auto_lookup_check)
        top.addLayout(controls)

        convert_box = QVBoxLayout()
        convert_box.setSpacing(5)
        convert_box.setAlignment(Qt.AlignRight | Qt.AlignTop)
        round_buttons = QHBoxLayout()
        round_buttons.setSpacing(10)
        round_buttons.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self.undo_button = QPushButton("←")
        self.undo_button.setObjectName("undoButton")
        self.undo_button.setFixedSize(44, 44)
        self.undo_button.setToolTip("Undo")
        self.redo_button = QPushButton("→")
        self.redo_button.setObjectName("redoButton")
        self.redo_button.setFixedSize(44, 44)
        self.redo_button.setToolTip("Redo")
        
        self.undo_button.clicked.connect(self.undo_stack.undo)
        self.redo_button.clicked.connect(self.undo_stack.redo)
        self.undo_button.setEnabled(False)
        self.redo_button.setEnabled(False)
        self.undo_stack.canUndoChanged.connect(self.undo_button.setEnabled)
        self.undo_stack.canRedoChanged.connect(self.redo_button.setEnabled)
        
        round_buttons.addWidget(self.undo_button, 0, Qt.AlignVCenter)
        round_buttons.addWidget(self.redo_button, 0, Qt.AlignVCenter)
        round_buttons.addWidget(add_button, 0, Qt.AlignVCenter)
        round_buttons.addWidget(self.convert_button, 0, Qt.AlignVCenter)
        convert_box.addLayout(round_buttons)
        convert_box.addWidget(self.action_hint, 0, Qt.AlignRight)
        top.addLayout(convert_box)
        shell_layout.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_card = QFrame()
        left_card.setProperty("card", True)
        left_card.setMinimumWidth(500)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(self.ui_text("headers"))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 72)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 150)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 64)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 82)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 34)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setMinimumHeight(220)
        self.table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        left_layout.addWidget(self.table, 1)

        queue_footer = QHBoxLayout()
        queue_footer.addStretch(1)
        clear_queue_button = QPushButton("Clear Queue")
        self.clear_queue_button = clear_queue_button
        clear_queue_button.clicked.connect(self.clear_queue)
        queue_footer.addWidget(clear_queue_button)
        left_layout.addLayout(queue_footer)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(66)
        self.log_view.setMaximumHeight(200)
        left_layout.addWidget(self.log_view, 0)

        right_card = QWidget()
        right_card.setMinimumWidth(640)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        meta_group = QFrame()
        meta_group.setProperty("section", True)
        meta_layout = QVBoxLayout(meta_group)
        meta_layout.setContentsMargins(12, 12, 12, 12)
        meta_layout.setSpacing(10)
        search_title = QLabel("Auto Search")
        self.search_title = search_title
        search_title.setObjectName("sectionTitle")
        meta_layout.addWidget(search_title)
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Artist / Album / Title")
        search_button = QPushButton("Search")
        self.search_button = search_button
        search_button.clicked.connect(self.search_metadata)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(search_button)
        meta_layout.addLayout(search_row)

        candidate_row = QHBoxLayout()
        self.candidate_combo = QComboBox()
        self.apply_candidate_button = QPushButton("選択曲へ反映")
        self.apply_candidate_button.clicked.connect(self.apply_candidate_to_current)
        self.apply_album_button = QPushButton("全体へ反映")
        self.apply_album_button.clicked.connect(self.apply_candidate_to_queue)
        clear_metadata_button = QPushButton("曲情報を削除")
        self.clear_metadata_button = clear_metadata_button
        clear_metadata_button.clicked.connect(self.clear_current_metadata)
        candidate_row.addWidget(self.candidate_combo, 1)
        candidate_row.addWidget(self.apply_candidate_button)
        candidate_row.addWidget(self.apply_album_button)
        candidate_row.addWidget(clear_metadata_button)
        meta_layout.addLayout(candidate_row)
        right_layout.addWidget(meta_group)

        editor_frame = QFrame()
        editor_frame.setProperty("section", True)
        editor_layout = QVBoxLayout(editor_frame)
        editor_layout.setContentsMargins(12, 12, 12, 12)
        editor_layout.setSpacing(10)
        editor_title = QLabel("曲情報")
        self.editor_title = editor_title
        editor_title.setObjectName("sectionTitle")
        editor_layout.addWidget(editor_title)

        form_grid = QGridLayout()
        form_grid.setHorizontalSpacing(10)
        form_grid.setVerticalSpacing(9)
        self.fields: Dict[str, QLineEdit] = {}
        self.field_labels: Dict[str, QLabel] = {}
        labels = {
            "title": "タイトル",
            "artist": "アーティスト",
            "album": "アルバム",
            "albumartist": "アルバムアーティスト",
            "date": "年",
            "tracknumber": "トラック",
            "discnumber": "ディスク",
            "genre": "ジャンル",
            "composer": "作曲",
            "comment": "コメント",
        }
        positions = [
            ("title", 0, 0),
            ("artist", 1, 0),
            ("album", 2, 0),
            ("albumartist", 3, 0),
            ("date", 4, 0),
            ("tracknumber", 0, 2),
            ("discnumber", 1, 2),
            ("genre", 2, 2),
            ("composer", 3, 2),
            ("comment", 4, 2),
        ]
        for key, row, col in positions:
            label = QLabel(labels[key])
            self.field_labels[key] = label
            edit = QLineEdit()
            edit.setMinimumHeight(34)
            edit.textChanged.connect(self.sync_form_to_track)
            self.fields[key] = edit
            form_grid.addWidget(label, row, col)
            form_grid.addWidget(edit, row, col + 1)
        editor_layout.addLayout(form_grid)
        right_layout.addWidget(editor_frame)

        media_settings_row = QHBoxLayout()
        media_settings_row.setSpacing(10)
        cover_frame = QFrame()
        cover_frame.setProperty("section", True)
        cover_frame.setMinimumWidth(280)
        cover_row = QVBoxLayout(cover_frame)
        cover_row.setContentsMargins(12, 12, 12, 12)
        cover_row.setSpacing(10)
        cover_title = QLabel("アートワーク")
        self.cover_title = cover_title
        cover_title.setObjectName("sectionTitle")
        cover_row.addWidget(cover_title)
        cover_content = QHBoxLayout()
        cover_content.setSpacing(10)
        self.cover_label = CoverLabel()
        self.cover_label.setMinimumSize(170, 150)
        self.cover_label.setMaximumHeight(210)
        cover_content.addWidget(self.cover_label, 1)

        cover_buttons = QVBoxLayout()
        cover_buttons.setSpacing(8)
        load_cover = QPushButton("追加")
        self.load_cover_button = load_cover
        load_cover.clicked.connect(self.load_cover_file)
        cover_candidates = QPushButton("候補")
        self.cover_candidates_button = cover_candidates
        cover_candidates.clicked.connect(self.show_cover_candidates)
        crop_square = QPushButton("正方形クロップ")
        self.crop_square_button = crop_square
        crop_square.clicked.connect(self.crop_cover_square)
        clear_cover = QPushButton("削除")
        self.clear_cover_button = clear_cover
        clear_cover.clicked.connect(self.clear_cover)
        for button in [load_cover, clear_cover, crop_square, cover_candidates]:
            button.setMinimumHeight(32)
            cover_buttons.addWidget(button)
        self.cover_info_label = QLabel("")
        self.cover_info_label.setWordWrap(True)
        cover_buttons.addWidget(self.cover_info_label)
        cover_buttons.addStretch(1)
        cover_content.addLayout(cover_buttons)
        cover_row.addLayout(cover_content, 1)
        media_settings_row.addWidget(cover_frame, 1)

        settings_frame = QFrame()
        settings_frame.setProperty("section", True)
        settings_layout_outer = QVBoxLayout(settings_frame)
        settings_layout_outer.setContentsMargins(12, 12, 12, 12)
        settings_layout_outer.setSpacing(10)
        conversion_title = QLabel("音量変換")
        self.conversion_title = conversion_title
        conversion_title.setObjectName("sectionTitle")
        settings_layout_outer.addWidget(conversion_title)
        settings_layout = QGridLayout()
        settings_layout.setHorizontalSpacing(10)
        settings_layout.setVerticalSpacing(8)
        self.preset_combo = QComboBox()
        self.loudness_presets = load_presets()
        self.preset_combo.addItems(self.loudness_presets.keys())
        self.preset_combo.currentTextChanged.connect(self.apply_loudness_preset)
        self.loudness_spin = QDoubleSpinBox()
        self.loudness_spin.setRange(-30.0, -5.0)
        self.loudness_spin.setDecimals(1)
        self.loudness_spin.setSingleStep(0.5)
        self.loudness_spin.setSuffix(" LUFS")
        self.loudness_spin.setValue(-14.0)
        self.loudness_spin.valueChanged.connect(self.mark_custom_loudness)
        self.true_peak_spin = QDoubleSpinBox()
        self.true_peak_spin.setRange(-9.0, 0.0)
        self.true_peak_spin.setDecimals(1)
        self.true_peak_spin.setSingleStep(0.1)
        self.true_peak_spin.setSuffix(" dBTP")
        self.true_peak_spin.setValue(-1.0)
        self.true_peak_spin.valueChanged.connect(self.mark_custom_loudness)
        self.preset_label = QLabel("プリセット")
        self.loudness_label = QLabel("ラウドネス値")
        self.true_peak_label = QLabel("トゥルーピーク")
        settings_layout.addWidget(self.preset_label, 0, 0)
        settings_layout.addWidget(self.preset_combo, 0, 1)
        settings_layout.addWidget(self.loudness_label, 1, 0)
        settings_layout.addWidget(self.loudness_spin, 1, 1)
        settings_layout.addWidget(self.true_peak_label, 2, 0)
        settings_layout.addWidget(self.true_peak_spin, 2, 1)
        settings_layout.setColumnStretch(1, 1)
        settings_layout_outer.addLayout(settings_layout)
        settings_layout_outer.addStretch(1)
        media_settings_row.addWidget(settings_frame, 1)
        right_layout.addLayout(media_settings_row, 1)
        self.apply_loudness_preset(NO_OP_PRESET_KEY)

        splitter.addWidget(left_card)
        splitter.addWidget(right_card)
        splitter.setSizes([620, 650])
        shell_layout.addWidget(splitter, 1)

        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setFrameShape(QFrame.NoFrame)
        page_scroll.setWidget(shell)
        root_layout.addWidget(page_scroll, 1)
        self.setCentralWidget(root)
        self.retranslate_ui()

    def build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("ファイル")
        self.file_menu = file_menu
        add_action = QAction("曲を追加", self)
        self.add_action = add_action
        add_action.setShortcut(QKeySequence.Open)
        add_action.triggered.connect(self.choose_files)
        file_menu.addAction(add_action)

        output_action = QAction("出力先変更", self)
        self.output_action = output_action
        output_action.triggered.connect(self.choose_output_dir)
        file_menu.addAction(output_action)

        file_menu.addSeparator()
        clear_queue_action = QAction("キューをクリア", self)
        self.clear_queue_action = clear_queue_action
        clear_queue_action.triggered.connect(self.clear_queue)
        file_menu.addAction(clear_queue_action)

        file_menu.addSeparator()
        quit_action = QAction("終了", self)
        self.quit_action = quit_action
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        run_menu = self.menuBar().addMenu("実行")
        self.run_menu = run_menu
        convert_action = QAction("変換", self)
        self.convert_action = convert_action
        convert_action.setShortcut(QKeySequence("Ctrl+Return"))
        convert_action.triggered.connect(self.start_conversion)
        run_menu.addAction(convert_action)

        search_action = QAction("自動検索", self)
        self.search_action = search_action
        search_action.setShortcut(QKeySequence.Find)
        search_action.triggered.connect(self.search_metadata)
        run_menu.addAction(search_action)

        edit_menu = self.menuBar().addMenu("編集")
        self.edit_menu = edit_menu
        apply_current_action = QAction("選択曲へ反映", self)
        self.apply_current_action = apply_current_action
        apply_current_action.triggered.connect(self.apply_candidate_to_current)
        edit_menu.addAction(apply_current_action)

        apply_all_action = QAction("全体へ反映", self)
        self.apply_all_action = apply_all_action
        apply_all_action.triggered.connect(self.apply_candidate_to_queue)
        edit_menu.addAction(apply_all_action)

        clear_metadata_action = QAction("曲情報を削除", self)
        self.clear_metadata_action = clear_metadata_action
        clear_metadata_action.triggered.connect(self.clear_current_metadata)
        edit_menu.addAction(clear_metadata_action)

        edit_menu.addSeparator()
        load_cover_action = QAction("アートワークを変更する", self)
        self.load_cover_action = load_cover_action
        load_cover_action.triggered.connect(self.load_cover_file)
        edit_menu.addAction(load_cover_action)

        choose_cover_action = QAction("アートワーク候補から選ぶ", self)
        self.choose_cover_action = choose_cover_action
        choose_cover_action.triggered.connect(self.show_cover_candidates)
        edit_menu.addAction(choose_cover_action)

        clear_cover_action = QAction("アートワーク削除", self)
        self.clear_cover_action = clear_cover_action
        clear_cover_action.triggered.connect(self.clear_cover)
        edit_menu.addAction(clear_cover_action)

        settings_menu = self.menuBar().addMenu("設定")
        self.settings_menu = settings_menu
        preferences_action = QAction("テーマと言語", self)
        self.preferences_action = preferences_action
        preferences_action.triggered.connect(self.open_preferences)
        settings_menu.addAction(preferences_action)
        self.retranslate_ui()

    def language_code(self) -> str:
        return LANGUAGES.get(self.language_name, DEFAULT_LANGUAGE_CODE)

    def ui_text(self, key: str):
        fallback = UI_TEXT[DEFAULT_LANGUAGE_CODE]
        lang = UI_TEXT.get(self.language_code(), fallback)
        return lang.get(key, fallback[key])

    def display_status(self, status: str) -> str:
        if self.language_code() == "ja":
            return status
        return {
            "待機": self.ui_text("status_wait"),
            "完了": self.ui_text("status_done"),
            "エラー": self.ui_text("status_error"),
            "変換中": self.ui_text("status_converting"),
        }.get(status, status)

    def retranslate_ui(self) -> None:
        if not hasattr(self, "status_label"):
            return
        self.setWindowTitle(APP_NAME)
        if self.status_label.text() in {"待機中", "Idle"}:
            self.status_label.setText(self.ui_text("idle"))
        self.output_label.setText(self.ui_text("output"))
        self.browse_out_button.setText(self.ui_text("change_output"))
        self.auto_lookup_check.setText(self.ui_text("auto_lookup"))
        self.action_hint.setText(self.ui_text("convert_hint"))
        self.table.setHorizontalHeaderLabels(self.ui_text("headers"))
        self.clear_queue_button.setText(self.ui_text("clear_queue"))
        self.search_title.setText(self.ui_text("auto_search"))
        self.search_edit.setPlaceholderText(self.ui_text("search_placeholder"))
        self.search_button.setText(self.ui_text("search"))
        self.apply_candidate_button.setText(self.ui_text("apply_current"))
        self.apply_album_button.setText(self.ui_text("apply_all"))
        self.clear_metadata_button.setText(self.ui_text("clear_metadata"))
        self.editor_title.setText(self.ui_text("track_info"))
        if hasattr(self, "cover_display"):
            self.cover_display.placeholder_text = self.ui_text("no_artwork")
            self.cover_display.refresh()
        for key, label in self.field_labels.items():
            label.setText(self.ui_text(key))
        self.cover_title.setText(self.ui_text("artwork"))
        self.load_cover_button.setText(self.ui_text("add"))
        self.cover_candidates_button.setText(self.ui_text("candidates"))
        self.crop_square_button.setText(self.ui_text("crop_square"))
        self.clear_cover_button.setText(self.ui_text("delete"))
        self.conversion_title.setText(self.ui_text("loudness"))
        self.preset_label.setText(self.ui_text("preset"))
        self.loudness_label.setText(self.ui_text("loudness_value"))
        self.true_peak_label.setText(self.ui_text("true_peak"))
        if hasattr(self, "file_menu"):
            self.file_menu.setTitle(self.ui_text("file"))
            self.run_menu.setTitle(self.ui_text("run"))
            self.edit_menu.setTitle(self.ui_text("edit"))
            self.settings_menu.setTitle(self.ui_text("settings"))
            self.add_action.setText(self.ui_text("add_song"))
            self.output_action.setText(self.ui_text("change_output"))
            self.clear_queue_action.setText(self.ui_text("clear_queue"))
            self.quit_action.setText(self.ui_text("quit"))
            self.convert_action.setText(self.ui_text("convert"))
            self.search_action.setText(self.ui_text("auto_search"))
            self.apply_current_action.setText(self.ui_text("apply_current"))
            self.apply_all_action.setText(self.ui_text("apply_all"))
            self.clear_metadata_action.setText(self.ui_text("clear_metadata"))
            self.load_cover_action.setText(self.ui_text("change_artwork"))
            self.choose_cover_action.setText(self.ui_text("choose_artwork"))
            self.clear_cover_action.setText(self.ui_text("delete_artwork"))
            self.preferences_action.setText(self.ui_text("theme_language"))
        self.update_status()

    def show_initial_preferences(self) -> None:
        self.open_preferences(first_run=True)

    def open_preferences(self, first_run: bool = False) -> None:
        dialog = PreferencesDialog(self, self.theme_name, self.language_name, first_run=first_run)
        dialog.setStyleSheet(self.styleSheet())
        if dialog.exec() != QDialog.Accepted:
            if first_run:
                self.settings.setValue("setup_complete", True)
            return
        self.theme_name, self.language_name = dialog.values()
        self.settings.setValue("theme", self.theme_name)
        self.settings.setValue("language", self.language_code())
        self.settings.setValue("setup_complete", True)
        self.apply_style()
        self.retranslate_ui()

    def apply_style(self) -> None:
        QApplication.instance().setFont(QFont("Helvetica Neue", 13))  
        t = THEMES.get(self.theme_name) or fallback_theme()
        if hasattr(self, "root_backdrop"):
            self.root_backdrop.set_theme(t)
        self.setStyleSheet(
            Template("""
            QWidget {
                color: $text;
                font-size: 13px;
            }
            #shell {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.68),
                    stop:0.36 $shell,
                    stop:1 rgba(218, 245, 255, 0.48));
                border: 1px solid rgba(255, 255, 255, 0.72);
                border-radius: 8px;
            }
            QFrame[card="true"], QFrame[section="true"], QGroupBox {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 0.62),
                    stop:1 $card);
                border: 1px solid rgba(255, 255, 255, 0.66);
                border-radius: 8px;
            }
            QGroupBox {
                margin-top: 12px;
                padding: 10px;
                font-weight: 700;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            #statusLabel {
                color: $text;
                font-size: 25px;
                font-weight: 800;
                padding: 0 2px;
            }
            #statusDetail {
                color: $muted;
                font-size: 13px;
                font-weight: 700;
                padding: 0 2px;
            }
            #latestLog {
                color: $muted;
                font-size: 11px;
                font-weight: 600;
                padding: 2px 2px 0 2px;
            }
            #sectionTitle {
                color: $text;
                font-size: 16px;
                font-weight: 800;
            }
            #actionHint {
                background: rgba(255, 255, 255, 0.50);
                border: 1px solid rgba(255, 255, 255, 0.72);
                border-radius: 8px;
                color: $text;
                font-weight: 700;
            }
            #dropLabel {
                background: rgba(255, 255, 255, 0.34);
                border: 1px dashed rgba(255, 255, 255, 0.82);
                border-radius: 8px;
                color: $muted;
                font-size: 16px;
                font-weight: 700;
            }
            QLineEdit, QTextEdit, QComboBox, QDoubleSpinBox {
                background: $field;
                border: 1px solid rgba(255, 255, 255, 0.78);
                border-radius: 8px;
                color: $text;
                padding: 7px 9px;
                min-height: 30px;
                selection-background-color: #8fd6ef;
            }
            QComboBox::drop-down, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                border: none;
                border-radius: 8px;
                width: 28px;
            }
            QTableWidget {
                background: $field;
                border: 1px solid rgba(255, 255, 255, 0.66);
                border-radius: 8px;
                color: $text;
                gridline-color: rgba(255, 255, 255, 0.22);
            }
            QHeaderView::section {
                background: $card;
                border: none;
                color: $muted;
                padding: 7px;
                font-weight: 700;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QTableWidget::item:selected {
                background: $accent;
                color: #ffffff;
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.42);
                border: 1px solid rgba(255, 255, 255, 0.72);
                border-radius: 7px;
                color: $text;
                padding: 8px 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.58);
            }
            QPushButton:pressed {
                background: rgba(186, 231, 246, 0.66);
            }
            QPushButton#convertButton {
                background: $accent;
                border-color: rgba(255, 255, 255, 0.82);
                border-radius: 31px;
                color: #f8feff;
                font-size: 27px;
                padding: 0 0 1px 4px;
            }
            QPushButton#convertButton:hover {
                background: $accent_hover;
            }
            QPushButton#undoButton, QPushButton#redoButton {
                background: rgba(255, 255, 255, 0.54);
                border-color: rgba(255, 255, 255, 0.84);
                border-radius: 22px;
                color: $text;
                font-size: 18px;
                padding: 0 0 2px 0;
            }
            QPushButton#undoButton:hover, QPushButton#redoButton:hover {
                background: rgba(255, 255, 255, 0.72);
            }
            QPushButton#addButton {
                background: rgba(255, 255, 255, 0.54);
                border-color: rgba(255, 255, 255, 0.84);
                border-radius: 31px;
                color: $text;
                font-size: 31px;
                padding: 0 0 4px 1px;
            }
            QPushButton#addButton:hover {
                background: rgba(255, 255, 255, 0.72);
            }
            QPushButton#rowRemoveButton {
                background: rgba(255, 255, 255, 0.38);
                border: none;
                border-radius: 14px;
                color: $text;
                font-size: 17px;
                padding: 0;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }
            QWidget#rowRemoveHolder {
                background: transparent;
            }
            QPushButton#artCandidateButton {
                text-align: center;
                padding: 10px;
            }
            QProgressBar {
                background: rgba(255, 255, 255, 0.42);
                border: 1px solid rgba(255, 255, 255, 0.70);
                border-radius: 6px;
                color: $text;
                min-width: 72px;
                max-width: 72px;
                height: 18px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: $chunk;
                border-radius: 5px;
            }
            QCheckBox {
                color: $text;
                spacing: 8px;
                font-weight: 700;
            }
            QLabel {
                background: transparent;
            }
            """).substitute(t)
        )

    def eventFilter(self, obj, event):  
        if obj is getattr(self, "convert_button", None):
            if event.type() == QEvent.Enter:
                self.show_action_hint(self.ui_text("convert_hint"))
            elif event.type() == QEvent.Leave:
                self.animate_action_hint(False)
        elif obj is getattr(self, "add_button", None):
            if event.type() == QEvent.Enter:
                self.show_action_hint(self.ui_text("add_hint"))
            elif event.type() == QEvent.Leave:
                self.animate_action_hint(False)
        return super().eventFilter(obj, event)

    def show_action_hint(self, text: str) -> None:
        self.action_hint.setText(text)
        self.animate_action_hint(True)

    def animate_action_hint(self, visible: bool) -> None:
        if not self.action_hint_effect or not self.action_hint_animation:
            return
        self.action_hint_animation.stop()
        self.action_hint_animation.setStartValue(self.action_hint_effect.opacity())
        self.action_hint_animation.setEndValue(1.0 if visible else 0.0)
        self.action_hint_animation.start()

    def integrate_macos_titlebar(self) -> None:
        app = QApplication.instance()
        if sys.platform != "darwin" or not app or app.platformName() != "cocoa":
            return
        try:
            import ctypes

            objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
            objc.sel_registerName.argtypes = [ctypes.c_char_p]
            objc.sel_registerName.restype = ctypes.c_void_p

            def selector(name: bytes) -> ctypes.c_void_p:
                return ctypes.c_void_p(objc.sel_registerName(name))

            def msg_void(receiver, sel, *args) -> None:
                objc.objc_msgSend.restype = None
                objc.objc_msgSend(receiver, sel, *args)

            def msg_ptr(receiver, sel):
                objc.objc_msgSend.restype = ctypes.c_void_p
                return ctypes.c_void_p(objc.objc_msgSend(receiver, sel))

            def msg_ulong(receiver, sel) -> int:
                objc.objc_msgSend.restype = ctypes.c_ulong
                return int(objc.objc_msgSend(receiver, sel))

            view = ctypes.c_void_p(int(self.winId()))
            window = msg_ptr(view, selector(b"window"))
            if not window.value:
                return

            style_mask = msg_ulong(window, selector(b"styleMask"))
            full_size_content_view = 1 << 15
            msg_void(window, selector(b"setStyleMask:"), ctypes.c_ulong(style_mask | full_size_content_view))
            msg_void(window, selector(b"setTitlebarAppearsTransparent:"), ctypes.c_bool(True))
            msg_void(window, selector(b"setMovableByWindowBackground:"), ctypes.c_bool(True))
            msg_void(window, selector(b"setTitleVisibility:"), ctypes.c_long(1))
            msg_void(window, selector(b"setToolbar:"), ctypes.c_void_p(0))
        except Exception:
            pass

    def apply_loudness_preset(self, name: str) -> None:
        preset = self.loudness_presets.get(name)
        enabled = preset is not None
        self.loudness_spin.blockSignals(True)
        self.true_peak_spin.blockSignals(True)
        if preset:
            loudness, true_peak = preset
            self.loudness_spin.setValue(loudness)
            self.true_peak_spin.setValue(true_peak)
        self.loudness_spin.setEnabled(enabled)
        self.true_peak_spin.setEnabled(enabled)
        self.loudness_spin.blockSignals(False)
        self.true_peak_spin.blockSignals(False)

    def mark_custom_loudness(self) -> None:
        if self.preset_combo.currentText() in {NO_OP_PRESET_KEY, "Custom"}:
            return
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText("Custom")
        self.preset_combo.blockSignals(False)

    def update_status(self, status: str = "") -> None:
        if status:
            self.status_label.setText(status)
        pending = sum(1 for track in self.tracks if track.status not in {"完了", "エラー"})
        done = sum(1 for track in self.tracks if track.status == "完了")
        self.status_detail_label.setText(self.ui_text("queue_count").format(total=len(self.tracks), pending=pending, done=done))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        self.add_paths(paths)

    def choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "曲を追加",
            str(Path.home()),
            "Audio Files (*.flac *.alac *.m4a *.wav *.aiff *.aif *.ape *.wv *.tta *.mka *.caf);;All Files (*)",
        )
        self.add_paths([Path(f) for f in files])

    def choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.ui_text("change_output"), self.output_dir_edit.text())
        if folder:
            self.output_dir_edit.setText(folder)

    def add_paths(self, paths: Iterable[Path]) -> None:
        files: List[Path] = []
        for path in paths:
            if path.is_dir():
                for child in path.rglob("*"):
                    if child.is_file():
                        files.append(child)
            elif path.is_file():
                files.append(path)

        start_index = len(self.tracks)
        new_tracks: List[TrackItemState] = []
        rejected_count = 0
        for path in files:
            if any(existing.path == path for existing in self.tracks) or any(t.path == path for t in new_tracks):
                continue
            try:
                info = probe_audio_file(path)
                tags, cover_data, cover_mime = read_tags_and_cover(path)
                if not tags.get("title"):
                    tags["title"] = path.stem
                track = TrackItemState(path=path, info=info, tags=tags, cover_data=cover_data, cover_mime=cover_mime)
                new_tracks.append(track)
                self.log(self.ui_text("log_add").format(name=path.name, codec=info.codec, quality=info.quality_label))
            except Exception as exc:
                rejected_count += 1
                simple = friendly_import_error(exc)
                self.log(self.ui_text("log_reject").format(name=path.name, error=exc), latest=self.ui_text("log_reject_simple").format(name=path.name, error=simple))

        if new_tracks:
            self.undo_stack.push(AddTracksCommand(self, new_tracks, start_index))
            if self.table.currentRow() < 0:
                self.table.selectRow(0)
            self.update_status(self.ui_text("status_analysis_done"))
        if rejected_count:
            self.update_status(self.ui_text("status_cannot_add_some"))
            self.latest_log_label.setText(self.ui_text("check_logs"))
        if self.auto_lookup_check.isChecked() and new_tracks:
            self.prepare_search_from_current()
            query = self.search_edit.text().strip()
            if query:
                self.search_metadata()

    def add_table_row(self, track: TrackItemState) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [
            track.path.name,
            track.info.codec.upper(),
            track.info.quality_label,
            format_duration(track.info.duration),
            "",
            "",
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(row, col, item)
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)
        self.table.setCellWidget(row, 4, progress)
        remove_button = QPushButton("×")
        remove_button.setObjectName("rowRemoveButton")
        remove_button.setFixedSize(28, 28)
        remove_button.clicked.connect(lambda _checked=False, button=remove_button: self.remove_row_for_button(button))
        remove_holder = QWidget()
        remove_holder.setObjectName("rowRemoveHolder")
        remove_layout = QHBoxLayout(remove_holder)
        remove_layout.setContentsMargins(0, 0, 0, 0)
        remove_layout.setSpacing(0)
        remove_layout.addStretch(1)
        remove_layout.addWidget(remove_button, 0, Qt.AlignCenter)
        remove_layout.addStretch(1)
        self.table.setCellWidget(row, 5, remove_holder)
        self.table.setRowHeight(row, 38)

    def remove_row_for_button(self, button: QPushButton) -> None:
        for row in range(self.table.rowCount()):
            holder = self.table.cellWidget(row, 5)
            if holder and button in holder.findChildren(QPushButton):
                self.remove_track_at(row)
                return

    def remove_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        self.remove_track_at(row)

    def remove_track_at(self, row: int) -> None:
        if not (0 <= row < len(self.tracks)):
            return
        self.undo_stack.push(RemoveTrackCommand(self, row, self.tracks[row]))

    def _do_remove_track_at(self, row: int) -> None:  
        if not (0 <= row < len(self.tracks)):
            return
        self.tracks.pop(row)
        self.table.removeRow(row)
        self.current_row = -1
        if self.tracks:
            self.table.selectRow(min(row, len(self.tracks) - 1))
        else:
            self.load_track_into_form(None)
        self.update_status()

    def clear_queue(self) -> None:
        if not self.tracks:
            return
        self.undo_stack.push(ClearQueueCommand(self, list(self.tracks)))

    def _do_clear_queue(self) -> None:  
        self.tracks.clear()
        self.table.setRowCount(0)
        self.current_row = -1
        self.load_track_into_form(None)
        self.update_status(self.ui_text("idle"))
        self.log(self.ui_text("log_queue_cleared"))

    def on_selection_changed(self) -> None:
        row = self.table.currentRow()
        if row == self.current_row:
            return
        self.current_row = row
        if 0 <= row < len(self.tracks):
            self.load_track_into_form(self.tracks[row])
            self.prepare_search_from_current()
        else:
            self.load_track_into_form(None)

    def load_track_into_form(self, track: Optional[TrackItemState]) -> None:
        self.loading_form = True
        try:
            for key, edit in self.fields.items():
                edit.setText(track.tags.get(key, "") if track else "")
            self.cover_label.set_cover(track.cover_data if track else None)
            self.update_cover_info(track.cover_data if track else None)
        finally:
            self.loading_form = False

    def sync_form_to_track(self) -> None:
        if self.loading_form or not (0 <= self.current_row < len(self.tracks)):
            return
        track = self.tracks[self.current_row]
        old_tags = track.tags.copy()
        new_tags = old_tags.copy()
        for key, edit in self.fields.items():
            new_tags[key] = edit.text().strip()
        if any(new_tags[k] != old_tags.get(k) for k in new_tags):
            self.undo_stack.push(EditTagsCommand(self, self.current_row, old_tags, new_tags))

    def prepare_search_from_current(self) -> None:
        if not (0 <= self.current_row < len(self.tracks)):
            return
        tags = self.tracks[self.current_row].tags
        pieces = [tags.get("albumartist") or tags.get("artist"), tags.get("album"), tags.get("title")]
        self.search_edit.setText(" ".join(piece for piece in pieces if piece).strip())

    def search_metadata(self) -> None:
        if self.metadata_worker and self.metadata_worker.isRunning():
            return
        self.sync_form_to_track()
        query = self.search_edit.text().strip()
        if not query:
            self.prepare_search_from_current()
            query = self.search_edit.text().strip()
        if not query:
            QMessageBox.information(self, APP_NAME, self.ui_text("msg_enter_query"))
            return
        self.log(self.ui_text("log_auto_search").format(query=query))
        self.update_status(self.ui_text("status_searching"))
        self.candidate_combo.clear()
        self.candidates = []
        self.release_detail = None
        self.release_cover_data = None
        self.release_cover_mime = ""
        self.metadata_worker = MetadataWorker("search", query=query)
        self.metadata_worker.results_ready.connect(self.on_metadata_results)
        self.metadata_worker.failed.connect(self.on_metadata_failed)
        self.metadata_worker.start()

    def on_metadata_results(self, candidates: list) -> None:
        self.candidates = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
        self.candidate_combo.clear()
        for candidate in self.candidates:
            self.candidate_combo.addItem(candidate.label(), candidate.release_id)
        self.log(self.ui_text("log_candidates").format(count=len(self.candidates)))
        if self.candidates:
            self.candidate_combo.setCurrentIndex(0)
            self.fetch_candidate_detail(0)

    def fetch_candidate_detail(self, index: int) -> None:
        if not (0 <= index < len(self.candidates)):
            return
        candidate = self.candidates[index]
        self.log(self.ui_text("log_getting_info").format(name=candidate.label()))
        self.metadata_worker = MetadataWorker(
            "detail",
            release_id=candidate.release_id,
            release_group_id=candidate.release_group_id,
        )
        self.metadata_worker.detail_ready.connect(self.on_release_detail)
        self.metadata_worker.failed.connect(self.on_metadata_failed)
        self.metadata_worker.start()

    def on_release_detail(self, release: dict, cover_data: bytes, cover_mime: str) -> None:
        self.release_detail = release
        self.release_cover_data = cover_data or None
        self.release_cover_mime = cover_mime or ""
        title = release.get("title", "")
        artist = artist_credit_phrase(release.get("artist-credit", []))
        self.log(self.ui_text("log_candidate_decided").format(artist=artist, title=title))
        if 0 <= self.current_row < len(self.tracks):
            self.undo_stack.push(ApplyReleaseCommand(self, self.current_row, release, cover_data or None, cover_mime or ""))
            self.log(self.ui_text("log_applied_to_current"))
            if cover_data:
                self.log(self.ui_text("log_artwork_fetched"))
        self.update_status(self.ui_text("status_ready"))

    def on_metadata_failed(self, message: str) -> None:
        self.log(self.ui_text("log_search_error").format(error=message), latest=self.ui_text("status_search_failed"))
        self.update_status(self.ui_text("status_search_failed"))

    def apply_candidate_to_current(self) -> None:
        index = self.candidate_combo.currentIndex()
        if index < 0:
            return
        if not self.release_detail or self.release_detail.get("id") != self.candidates[index].release_id:
            self.fetch_candidate_detail(index)
            return
        if not (0 <= self.current_row < len(self.tracks)):
            return
        self.undo_stack.push(ApplyReleaseCommand(self, self.current_row, self.release_detail, self.release_cover_data, self.release_cover_mime))
        self.log(self.ui_text("log_applied_to_current"))
        self.update_status(self.ui_text("status_ready"))

    def apply_candidate_to_queue(self) -> None:
        index = self.candidate_combo.currentIndex()
        if index < 0:
            return
        if not self.release_detail or self.release_detail.get("id") != self.candidates[index].release_id:
            self.fetch_candidate_detail(index)
            return
        self.apply_release_to_all_tracks(self.release_detail, self.release_cover_data, self.release_cover_mime)
        self.log(self.ui_text("log_applied_to_all"))
        self.update_status(self.ui_text("status_ready"))

    def clear_current_metadata(self) -> None:
        track = self.current_track()
        if not track:
            return
        for key in TAG_FIELDS:
            track.tags[key] = ""
        track.mb_release_id = None
        track.mb_release_group_id = None
        self.load_track_into_form(track)
        self.refresh_table_labels()
        self.log(self.ui_text("log_cleared_metadata"))
        self.update_status(self.ui_text("status_edited"))

    def apply_release_to_all_tracks(
        self,
        release: dict,
        cover_data: Optional[bytes] = None,
        cover_mime: str = "",
    ) -> None:
        for queue_index, track in enumerate(self.tracks):
            apply_release_to_track(release, track, queue_index=queue_index)
            if release.get("id"):
                track.mb_release_id = release["id"]
            release_group = release.get("release-group") or {}
            if release_group.get("id"):
                track.mb_release_group_id = release_group["id"]
            if cover_data:
                track.cover_data = cover_data
                track.cover_mime = cover_mime
        if 0 <= self.current_row < len(self.tracks):
            self.load_track_into_form(self.tracks[self.current_row])
        self.refresh_table_labels()
        self.update_status()

    def refresh_table_labels(self) -> None:
        for row, track in enumerate(self.tracks):
            self.table.item(row, 0).setText(track.tags.get("title") or track.path.name)

    def load_cover_file(self) -> None:
        if not (0 <= self.current_row < len(self.tracks)):
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "ジャケット画像",
            str(Path.home()),
            "Images (*.jpg *.jpeg *.png *.webp *.tif *.tiff);;All Files (*)",
        )
        if not filename:
            return
        data = Path(filename).read_bytes()
        data, mime = normalize_cover_image(data)
        track = self.tracks[self.current_row]
        track.cover_data = data
        track.cover_mime = mime
        self.cover_label.set_cover(data)
        self.update_cover_info(data)
        self.log(self.ui_text("log_loaded_jacket").format(name=Path(filename).name))

    def rotate_cover(self, degrees: int) -> None:
        track = self.current_track()
        if not track or not track.cover_data:
            return
        data, mime = transform_cover(track.cover_data, rotate_degrees=degrees)
        track.cover_data = data
        track.cover_mime = mime
        self.cover_label.set_cover(data)
        self.update_cover_info(data)

    def crop_cover_square(self) -> None:
        track = self.current_track()
        if not track or not track.cover_data:
            return
        data, mime = transform_cover(track.cover_data, crop_square=True)
        track.cover_data = data
        track.cover_mime = mime
        self.cover_label.set_cover(data)
        self.update_cover_info(data)

    def clear_cover(self) -> None:
        track = self.current_track()
        if not track:
            return
        track.cover_data = None
        track.cover_mime = None
        self.cover_label.set_cover(None)
        self.update_cover_info(None)

    def show_cover_candidates(self) -> None:
        if not self.release_detail:
            QMessageBox.information(self, APP_NAME, self.ui_text("msg_run_search_first"))
            return
        release_id = self.release_detail.get("id", "")
        release_group = self.release_detail.get("release-group") or {}
        candidates = fetch_cover_art_candidates(release_id, release_group.get("id", ""))
        if self.release_cover_data:
            candidates.insert(0, CoverArtCandidate(self.ui_text("lbl_current_candidate"), self.release_cover_data, self.release_cover_mime))
        if not candidates:
            QMessageBox.information(self, APP_NAME, self.ui_text("msg_no_artwork_candidates"))
            return
        dialog = CoverCandidateDialog(self, candidates)
        dialog.setStyleSheet(self.styleSheet())
        if dialog.exec() == QDialog.Accepted and dialog.selected:
            for track in self.tracks:
                track.cover_data = dialog.selected.data
                track.cover_mime = dialog.selected.mime
            self.release_cover_data = dialog.selected.data
            self.release_cover_mime = dialog.selected.mime
            if 0 <= self.current_row < len(self.tracks):
                self.load_track_into_form(self.tracks[self.current_row])
            self.log(self.ui_text("log_artwork_applied"))
            self.update_status(self.ui_text("status_ready"))

    def submit_cddb_metadata(self) -> None:
        if not self.tracks:
            QMessageBox.information(self, APP_NAME, self.ui_text("msg_no_metadata_to_send"))
            return
        self.sync_form_to_track()
        output_dir = Path(self.output_dir_edit.text()).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "app": APP_NAME,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "album": self.tracks[0].tags.get("album", ""),
            "albumartist": self.tracks[0].tags.get("albumartist", ""),
            "tracks": [
                {
                    "filename": track.path.name,
                    "codec": track.info.codec,
                    "sample_rate": track.info.sample_rate,
                    "bit_depth": track.info.bit_depth,
                    "duration": track.info.duration,
                    "tags": {key: value for key, value in track.tags.items() if value},
                    "release_id": track.mb_release_id,
                    "release_group_id": track.mb_release_group_id,
                    "has_artwork": bool(track.cover_data),
                }
                for track in self.tracks
            ],
        }
        target = unique_json_path(output_dir, "auralis-cddb-submission")
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log(self.ui_text("log_cddb_data_created").format(name=target.name))
        QMessageBox.information(
            self,
            APP_NAME,
            "公開データベースへの直接投稿は認証が必要です。送信用データを作成しました。",
        )

    def update_cover_info(self, data: Optional[bytes]) -> None:
        if not data:
            self.cover_info_label.setText("")
            return
        try:
            with Image.open(io.BytesIO(data)) as img:
                self.cover_info_label.setText(f"{img.format or 'IMAGE'} / {img.width} x {img.height}px")
        except Exception:
            self.cover_info_label.setText(self.ui_text("lbl_cannot_read_image"))

    def current_track(self) -> Optional[TrackItemState]:
        if 0 <= self.current_row < len(self.tracks):
            return self.tracks[self.current_row]
        return None

    def undo_action(self) -> None:
        self.undo_stack.undo()

    def redo_action(self) -> None:
        self.undo_stack.redo()

    def start_conversion(self) -> None:
        if self.conversion_worker and self.conversion_worker.isRunning():
            return
        if not self.tracks:
            QMessageBox.information(self, APP_NAME, self.ui_text("msg_no_tracks_to_convert"))
            return
        self.sync_form_to_track()
        output_dir = Path(self.output_dir_edit.text()).expanduser()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.log(self.ui_text("log_output_create_error").format(error=exc), latest=self.ui_text("msg_output_create_failed"))
            self.update_status(self.ui_text("status_check_output"))
            QMessageBox.warning(self, APP_NAME, self.ui_text("msg_output_create_failed"))
            return
        self.convert_button.setEnabled(False)
        self.update_status(self.ui_text("status_converting"))
        normalize_enabled = self.preset_combo.currentText() != NO_OP_PRESET_KEY
        settings = ConversionSettings(
            normalize=normalize_enabled,
            loudness_lufs=self.loudness_spin.value(),
            true_peak_db=self.true_peak_spin.value(),
        )
        self.conversion_worker = ConversionWorker(self.tracks, output_dir, settings)
        self.conversion_worker.track_progress.connect(self.on_track_progress)
        self.conversion_worker.track_done.connect(self.on_track_done)
        self.conversion_worker.log_line.connect(self.log)
        self.conversion_worker.done.connect(self.on_conversion_done)
        self.conversion_worker.start()
        self.log(self.ui_text("log_conversion_started"))

    def on_track_progress(self, row: int, percent: int, status: str) -> None:
        if 0 <= row < self.table.rowCount():
            progress = self.table.cellWidget(row, 4)
            if isinstance(progress, QProgressBar):
                progress.setValue(max(0, min(100, percent)))

    def on_track_done(self, row: int, success: bool, message: str) -> None:
        if success:
            self.log(self.ui_text("log_done").format(message=message))
            self.update_status()
        else:
            self.log(self.ui_text("log_convert_fail").format(message=message), latest=self.ui_text("status_convert_failed_some"))
            self.update_status(self.ui_text("status_convert_failed_some"))

    def on_conversion_done(self) -> None:
        self.convert_button.setEnabled(True)
        self.log(self.ui_text("log_conversion_finished"))
        rows_to_remove = [i for i, t in enumerate(self.tracks) if t.status == "完了"]
        for row in reversed(rows_to_remove):
            self._do_remove_track_at(row)
        self.update_status(self.ui_text("status_convert_done"))

    def log(self, text: str, latest: Optional[str] = None) -> None:
        self.log_view.append(text)
        if hasattr(self, "latest_log_label"):
            self.latest_log_label.setText(latest or text)


def probe_audio_file(path: Path) -> AudioInfo:
    cmd = [
        FFPROBE,
        "-v",
        "error",
        "-show_entries",
        "stream=index,codec_name,codec_type,sample_rate,bits_per_sample,bits_per_raw_sample,channels,duration:format=format_name,duration,bit_rate",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("ffprobe not found. Please install ffmpeg.") from exc
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Cannot read audio info")
    data = json.loads(result.stdout or "{}")
    audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not audio_stream:
        raise RuntimeError("No audio stream found")

    codec = str(audio_stream.get("codec_name") or "").lower()
    if not is_lossless_codec(codec):
        reason = "lossy codec" if codec in LOSSY_CODECS else "codec not verified as lossless"
        raise RuntimeError(f"{reason}: {codec or 'unknown'}")

    sample_rate = parse_int(audio_stream.get("sample_rate"))
    bit_depth = parse_int(audio_stream.get("bits_per_raw_sample")) or parse_int(audio_stream.get("bits_per_sample"))
    channels = parse_int(audio_stream.get("channels"))
    duration = parse_float(audio_stream.get("duration")) or parse_float((data.get("format") or {}).get("duration"))
    quality_label = "Hi-Res" if sample_rate > 48000 or bit_depth > 16 else "Lossless"
    if sample_rate and bit_depth:
        quality_label += f" {bit_depth}bit/{sample_rate // 1000 if sample_rate % 1000 == 0 else sample_rate / 1000:g}kHz"
    elif sample_rate:
        quality_label += f" {sample_rate // 1000 if sample_rate % 1000 == 0 else sample_rate / 1000:g}kHz"

    return AudioInfo(
        codec=codec,
        sample_rate=sample_rate,
        bit_depth=bit_depth,
        channels=channels,
        duration=duration,
        format_name=str((data.get("format") or {}).get("format_name") or ""),
        quality_label=quality_label,
    )


def friendly_import_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "非ロスレス" in str(exc) or "lossless と確認できない" in str(exc) or "codec" in message:
        return "ロスレス音源として確認できませんでした。"
    if "ffprobe" in message or "ffmpeg" in message:
        return "音源の解析に必要なツールが見つかりません。"
    if "音声ストリーム" in str(exc):
        return "音声ファイルとして読み込めませんでした。"
    return "このファイルを読み込めませんでした。"


def is_lossless_codec(codec: str) -> bool:
    return codec.startswith("pcm_") or codec in LOSSLESS_CODECS


def read_tags_and_cover(path: Path) -> Tuple[Dict[str, str], Optional[bytes], Optional[str]]:
    tags = {key: "" for key in TAG_FIELDS}
    try:
        easy = MutagenFile(path, easy=True)
        if easy and easy.tags:
            for key in TAG_FIELDS:
                value = first_value(easy.tags.get(key))
                if value:
                    tags[key] = value
    except Exception:
        pass

    cover_data: Optional[bytes] = None
    cover_mime: Optional[str] = None
    try:
        audio = MutagenFile(path)
        if audio is not None:
            cover_data, cover_mime = extract_cover(audio)
    except Exception:
        pass
    return tags, cover_data, cover_mime


def extract_cover(audio) -> Tuple[Optional[bytes], Optional[str]]:
    if hasattr(audio, "pictures") and audio.pictures:
        picture = audio.pictures[0]
        return picture.data, picture.mime
    tags = getattr(audio, "tags", None)
    if not tags:
        return None, None
    if "covr" in tags and tags["covr"]:
        cover = tags["covr"][0]
        mime = "image/png" if getattr(cover, "imageformat", None) == MP4Cover.FORMAT_PNG else "image/jpeg"
        return bytes(cover), mime
    for key in tags.keys():
        if str(key).startswith("APIC"):
            frame = tags[key]
            return frame.data, frame.mime
    return None, None


def convert_to_alac(track: TrackItemState, output_path: Path, settings: ConversionSettings, progress_cb) -> None:
    with tempfile.NamedTemporaryFile(prefix=output_path.stem + "-", suffix=".m4a", dir=str(output_path.parent), delete=False) as handle:
        temp_path = Path(handle.name)
    cmd = [
        FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(track.path),
        "-map",
        "0:a:0",
        "-vn",
        "-c:a",
        "alac",
        "-map_metadata",
        "0",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        str(temp_path),
    ]
    if settings.normalize:
        loudnorm_filter = f"loudnorm=I={settings.loudness_lufs:g}:TP={settings.true_peak_db:g}:LRA=11"
        cmd[cmd.index("-c:a"):cmd.index("-c:a")] = ["-af", loudnorm_filter]
    try:
        process = subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError as exc:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg not found.") from exc

    output_lines: List[str] = []
    if process.stdout:
        for line in process.stdout:
            stripped = line.strip()
            output_lines.append(stripped)
            if stripped.startswith("out_time_ms=") and track.info.duration > 0:
                micros = parse_float(stripped.split("=", 1)[1])
                progress_cb(int(min(99, (micros / 1_000_000) / track.info.duration * 100)))
            elif stripped == "progress=end":
                progress_cb(99)
    return_code = process.wait()
    if return_code != 0:
        temp_path.unlink(missing_ok=True)
        message = "\n".join(line for line in output_lines if line)
        raise RuntimeError(message or f"ffmpeg failed with exit code {return_code}")
    temp_path.replace(output_path)


def write_mp4_tags(
    path: Path,
    source_tags: Dict[str, str],
    cover_data: Optional[bytes],
    cover_mime: Optional[str],
    track: TrackItemState,
) -> None:
    audio = MP4(str(path))
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    tags.clear()

    def set_text(atom: str, value: str) -> None:
        if value:
            tags[atom] = [value]

    set_text("\xa9nam", source_tags.get("title", ""))
    set_text("\xa9ART", source_tags.get("artist", ""))
    set_text("\xa9alb", source_tags.get("album", ""))
    set_text("aART", source_tags.get("albumartist", ""))
    set_text("\xa9day", source_tags.get("date", ""))
    set_text("\xa9gen", source_tags.get("genre", ""))
    set_text("\xa9wrt", source_tags.get("composer", ""))
    set_text("\xa9cmt", source_tags.get("comment", ""))

    track_number, track_total = parse_number_pair(source_tags.get("tracknumber", ""))
    disc_number, disc_total = parse_number_pair(source_tags.get("discnumber", ""))
    if track_number:
        tags["trkn"] = [(track_number, track_total)]
    if disc_number:
        tags["disk"] = [(disc_number, disc_total)]

    if track.mb_release_id:
        tags["----:com.apple.iTunes:MusicBrainz Album Id"] = [track.mb_release_id.encode("utf-8")]
    if track.mb_release_group_id:
        tags["----:com.apple.iTunes:MusicBrainz Release Group Id"] = [track.mb_release_group_id.encode("utf-8")]

    if cover_data:
        cover_data, cover_mime = normalize_cover_image(cover_data)
        fmt = MP4Cover.FORMAT_PNG if cover_mime == "image/png" else MP4Cover.FORMAT_JPEG
        tags["covr"] = [MP4Cover(cover_data, imageformat=fmt)]
    audio.save()


def search_musicbrainz_releases(query: str) -> List[ReleaseCandidate]:
    response = requests.get(
        f"{MB_BASE}/release/",
        params={"query": query, "fmt": "json", "limit": 8},
        headers=HTTP_HEADERS,
        timeout=18,
    )
    response.raise_for_status()
    payload = response.json()
    candidates: List[ReleaseCandidate] = []
    for item in payload.get("releases", []):
        release_group = item.get("release-group") or {}
        candidates.append(
            ReleaseCandidate(
                release_id=item.get("id", ""),
                title=item.get("title", ""),
                artist=artist_credit_phrase(item.get("artist-credit", [])),
                date=item.get("date", ""),
                country=item.get("country", ""),
                score=parse_int(item.get("score")),
                release_group_id=release_group.get("id", ""),
            )
        )
    return [candidate for candidate in candidates if candidate.release_id]


def lookup_musicbrainz_release(release_id: str) -> dict:
    response = requests.get(
        f"{MB_BASE}/release/{release_id}",
        params={"inc": "artist-credits+recordings+release-groups+labels+media+tags", "fmt": "json"},
        headers=HTTP_HEADERS,
        timeout=18,
    )
    response.raise_for_status()
    return response.json()


def fetch_cover_art(release_id: str, release_group_id: str = "") -> Tuple[Optional[bytes], Optional[str]]:
    urls = [
        f"{CAA_BASE}/release/{release_id}/front-1200",
        f"{CAA_BASE}/release/{release_id}/front-500",
    ]
    if release_group_id:
        urls.extend(
            [
                f"{CAA_BASE}/release-group/{release_group_id}/front-1200",
                f"{CAA_BASE}/release-group/{release_group_id}/front-500",
            ]
        )
    for url in urls:
        try:
            response = requests.get(url, headers={"User-Agent": HTTP_HEADERS["User-Agent"]}, timeout=18)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            data = response.content
            data, mime = normalize_cover_image(data, preferred_mime="image/png" if "png" in content_type else "image/jpeg")
            return data, mime
        except Exception:
            continue
        finally:
            time.sleep(0.15)
    return None, None


def fetch_cover_art_candidates(release_id: str, release_group_id: str = "") -> List[CoverArtCandidate]:
    candidates: List[CoverArtCandidate] = []
    if release_id:
        try:
            response = requests.get(
                f"{CAA_BASE}/release/{release_id}",
                headers={"User-Agent": HTTP_HEADERS["User-Agent"], "Accept": "application/json"},
                timeout=18,
            )
            if response.status_code != 404:
                response.raise_for_status()
                for image_index, image in enumerate(response.json().get("images", [])[:12], start=1):
                    thumbs = image.get("thumbnails") or {}
                    image_url = thumbs.get("large") or thumbs.get("small") or image.get("image")
                    if not image_url:
                        continue
                    data, mime = download_cover_image(image_url)
                    if not data:
                        continue
                    types = ", ".join(image.get("types") or []) or "Artwork"
                    with Image.open(io.BytesIO(data)) as img:
                        width, height = img.size
                    candidates.append(CoverArtCandidate(f"{image_index}. {types} / {width}x{height}", data, mime, width, height))
                    time.sleep(0.12)
        except Exception:
            pass

    if not candidates and (release_id or release_group_id):
        data, mime = fetch_cover_art(release_id, release_group_id)
        if data and mime:
            with Image.open(io.BytesIO(data)) as img:
                width, height = img.size
            candidates.append(CoverArtCandidate(f"Front / {width}x{height}", data, mime, width, height))
    return candidates


def download_cover_image(url: str) -> Tuple[Optional[bytes], str]:
    try:
        response = requests.get(url, headers={"User-Agent": HTTP_HEADERS["User-Agent"]}, timeout=18)
        response.raise_for_status()
        preferred_mime = "image/png" if "png" in response.headers.get("content-type", "") else "image/jpeg"
        return normalize_cover_image(response.content, preferred_mime=preferred_mime)
    except Exception:
        return None, ""


def apply_release_to_track(release: dict, track: TrackItemState, queue_index: Optional[int]) -> None:
    album_artist = artist_credit_phrase(release.get("artist-credit", []))
    release_group = release.get("release-group") or {}
    track.tags["album"] = release.get("title", track.tags.get("album", ""))
    track.tags["albumartist"] = album_artist or track.tags.get("albumartist", "")
    track.tags["date"] = release.get("date", track.tags.get("date", ""))
    if release.get("tags"):
        top_tag = sorted(release["tags"], key=lambda t: t.get("count", 0), reverse=True)[0]
        track.tags["genre"] = top_tag.get("name", track.tags.get("genre", ""))

    flat_tracks = flatten_release_tracks(release)
    selected = pick_release_track(flat_tracks, track, queue_index)
    if selected:
        medium_pos, medium_count, track_pos, track_count, mb_track = selected
        track.tags["discnumber"] = f"{medium_pos}/{medium_count}" if medium_count > 1 else str(medium_pos)
        track.tags["tracknumber"] = f"{track_pos}/{track_count}"
        track.tags["title"] = mb_track.get("title", track.tags.get("title", ""))
        artist = artist_credit_phrase(mb_track.get("artist-credit", [])) or album_artist
        if artist:
            track.tags["artist"] = artist
    track.mb_release_id = release.get("id") or track.mb_release_id
    track.mb_release_group_id = release_group.get("id") or track.mb_release_group_id


def flatten_release_tracks(release: dict):
    media = release.get("media", []) or []
    flat = []
    medium_count = len(media) or 1
    for medium_index, medium in enumerate(media, start=1):
        tracks = medium.get("tracks", []) or []
        track_count = len(tracks) or parse_int(medium.get("track-count"))
        for track_index, item in enumerate(tracks, start=1):
            flat.append((medium_index, medium_count, track_index, track_count, item))
    return flat


def pick_release_track(flat_tracks: list, track: TrackItemState, queue_index: Optional[int]):
    if not flat_tracks:
        return None
    disc_number, _ = parse_number_pair(track.tags.get("discnumber", ""))
    track_number, _ = parse_number_pair(track.tags.get("tracknumber", ""))
    if track_number:
        for item in flat_tracks:
            medium_pos, _, track_pos, _, _track = item
            if track_pos == track_number and (not disc_number or disc_number == medium_pos):
                return item
    title = normalize_title(track.tags.get("title") or track.path.stem)
    if title:
        for item in flat_tracks:
            if normalize_title(item[4].get("title", "")) == title:
                return item
    if queue_index is not None and queue_index < len(flat_tracks):
        return flat_tracks[queue_index]
    return flat_tracks[0]


def artist_credit_phrase(credits: list) -> str:
    pieces = []
    for credit in credits or []:
        if isinstance(credit, dict):
            name = credit.get("name") or (credit.get("artist") or {}).get("name") or ""
            pieces.append(name + credit.get("joinphrase", ""))
        elif isinstance(credit, str):
            pieces.append(credit)
    return "".join(pieces).strip()


def normalize_cover_image(data: bytes, preferred_mime: str = "") -> Tuple[bytes, str]:
    with Image.open(io.BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if image.mode in ("P", "LA") else "RGB")
        output = io.BytesIO()
        if preferred_mime == "image/png" or image.mode == "RGBA":
            image.save(output, format="PNG", optimize=True)
            return output.getvalue(), "image/png"
        image.convert("RGB").save(output, format="JPEG", quality=94, optimize=True)
        return output.getvalue(), "image/jpeg"


def transform_cover(data: bytes, rotate_degrees: int = 0, crop_square: bool = False) -> Tuple[bytes, str]:
    with Image.open(io.BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image)
        if rotate_degrees:
            image = image.rotate(rotate_degrees, expand=True)
        if crop_square:
            side = min(image.width, image.height)
            image = ImageOps.fit(image, (side, side), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=94, optimize=True)
        return output.getvalue(), "image/jpeg"


def unique_output_path(output_dir: Path, stem: str) -> Path:
    safe_stem = re.sub(r"[\\/:*?\"<>|]+", "_", stem).strip() or "track"
    candidate = output_dir / f"{safe_stem}.m4a"
    counter = 2
    while candidate.exists():
        candidate = output_dir / f"{safe_stem}-{counter}.m4a"
        counter += 1
    return candidate


def unique_json_path(output_dir: Path, stem: str) -> Path:
    safe_stem = re.sub(r"[\\/:*?\"<>|]+", "_", stem).strip() or "submission"
    candidate = output_dir / f"{safe_stem}.json"
    counter = 2
    while candidate.exists():
        candidate = output_dir / f"{safe_stem}-{counter}.json"
        counter += 1
    return candidate


def app_asset_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "assets" / name
    return ASSET_DIR / name


def first_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return str(value)


def parse_int(value) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(str(value).split("/", 1)[0]))
    except Exception:
        return 0


def parse_float(value) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def parse_number_pair(value: str) -> Tuple[int, int]:
    if not value:
        return 0, 0
    pieces = str(value).strip().split("/", 1)
    first = parse_int(pieces[0])
    second = parse_int(pieces[1]) if len(pieces) > 1 else 0
    return first, second


def format_duration(seconds: float) -> str:
    if not seconds:
        return "--:--"
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def normalize_title(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^a-z0-9\u3040-\u30ff\u3400-\u9fff ]+", "", value)
    return value.strip()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
