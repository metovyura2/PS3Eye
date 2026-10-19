"""Главное окно приложения PSEyes: превью, настройки, запись таймлапса."""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sys
import threading
import time

import cv2
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import device
from . import dshow
from . import encoder as enc_mod
from .camera import CaptureThread, show_properties
from .config import AppConfig, project_root
from .recorder import TimelapseRecorder

ROTATE_VALUES = [0, 90, 180, 270]
# Запасной список режимов PS Eye — используется, если драйвер не ответил
FALLBACK_RESOLUTIONS = [
    (160, 120),
    (176, 144),
    (320, 240),
    (352, 288),
    (640, 480),
    (800, 600),
    (1024, 576),
    (1280, 720),
    (1600, 896),
    (1920, 1080),
    (2304, 1296),
    (2304, 1536),
]
# Частота обновления превью (кадры камеры приходят чаще, GUI не должен захлёбываться)
PREVIEW_FPS = 25
# Журнал приложения дублируется в файл: после закрытия окна иначе ничего не проверить
LOG_FILE = os.path.join(project_root(), "temp", "pseyes.log")
LOG_MAX_BYTES = 1_000_000
# Стартовый размер окна: фиксированный, не зависит от ширины монитора
START_WIDTH = 1220
START_HEIGHT = 780
# Ниже этого окно не сжимается, иначе панель настроек и превью ломаются
MIN_WIDTH = 900
MIN_HEIGHT = 620
# Меньше этого панель не сжимается: иначе обрезаются подписи и поля ввода
PANEL_MIN_WIDTH = 520
# Верхняя граница ширины панели: остальное отдаём превью
PANEL_MAX_WIDTH = 760
# Минимум, который оставляем превью в широком окне
MIN_PREVIEW_WIDTH = 320
# Минимальная ширина раскрытого списка устройств: длинные имена камер видны целиком
DEVICE_POPUP_WIDTH = 560


def window_icon() -> QIcon | None:
    """Иконка окна: assets/pseyes.ico, рядом с EXE или в распакованном бандле PyInstaller."""
    candidates = [
        os.path.join(getattr(sys, "_MEIPASS", ""), "assets", "pseyes.ico"),
        os.path.join(project_root(), "assets", "pseyes.ico"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return QIcon(path)
    return None


class MainWindow(QMainWindow):
    """Окно приложения."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.capture: CaptureThread | None = None
        self.recorder: TimelapseRecorder | None = None
        self.encoder: enc_mod.TimelapseEncoder | None = None
        self.session_dir: str | None = None
        self._last_frame = None
        self._capture_lost = False
        self._cam_fps = 0.0
        self._last_device_name = ""
        # Устройство и разрешение, для которых сейчас идёт фоновый опрос режимов
        self._modes_pending = ("", "")
        # Камеры в списке: текст пункта -> реальное имя устройства
        self._device_entries: dict[str, str] = {}
        # Имена и статусы камер, найденных в системе (PowerShell/Get-PnpDevice)
        self._camera_entries: list[tuple[str, str]] = []
        self._system_camera_names: list[str] = []
        self._shutting_down = False
        # Ширина окна при первом показе (без рамки): от неё считаются доли превью/панели
        self._initial_width = max(self.config.window_size()[0], START_WIDTH)

        self.setWindowTitle("PSEyes — таймлапс с камеры Sony PS Eye")
        icon = window_icon()
        if icon is not None:
            self.setWindowIcon(icon)

        # Стартовая геометрия фиксирована и подогнана под экран: окно никогда не
        # открывается шире рабочего стола и остаётся пригодным для масштабирования
        self._apply_initial_geometry()

        self._initializing = True
        self._build_ui()
        self._load_config_into_ui()
        self._refresh_devices()
        self._initializing = False
        self._repair_camera_on_start()
        self._start_capture()

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(1000)

        self._preview_timer = QTimer(self)
        self._preview_timer.timeout.connect(self._update_preview)
        self._preview_timer.start(max(int(1000 / PREVIEW_FPS), 1))

    # ------------------------------------------------------------------ UI

    def _apply_initial_geometry(self) -> None:
        """Задаёт стартовый размер окна и центрирует его.

        Ширина окна — не меньше START_WIDTH, чтобы панель настроек получила
        ширину из config.json (panel_width), и не больше рабочего стола (на большом
        экране окно открывается шире, чтобы названия камер были видны целиком).
        """
        # Минимум окна растёт вместе с панелью: на узком экране окно не должно
        # быть шире рабочего стола из-за PANEL_MIN_WIDTH
        screen = QApplication.primaryScreen()
        min_width = MIN_WIDTH
        if screen is not None:
            min_width = min(max(min_width, PANEL_MIN_WIDTH + MIN_PREVIEW_WIDTH), screen.availableGeometry().width())
        self.setMinimumSize(min_width, MIN_HEIGHT)

        if screen is None:
            base_width, base_height = self.config.window_size()
            self.resize(max(base_width, START_WIDTH), base_height)
            return

        area = screen.availableGeometry()
        base_width, base_height = self.config.window_size()
        width = min(max(base_width, START_WIDTH), area.width())
        height = min(base_height, area.height())
        # Окно не шире рабочего стола, но и не уже минимума
        width = max(width, min(MIN_WIDTH, area.width()))
        height = max(height, min(MIN_HEIGHT, area.height()))
        self.resize(width, height)

        # Центрирование по рабочему столу (без панели задач)
        left = area.x() + max((area.width() - width) // 2, 0)
        top = area.y() + max((area.height() - height) // 2, 0)
        self.move(left, top)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_preview())
        splitter.addWidget(self._build_panel())
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        # Жёсткие стартовые доли: раскладка не «прыгает» от подсказок размера.
        # Ширина главного окна на этом этапе ещё не равна заданной в _apply_initial_geometry
        # (включает рамки), поэтому доли считаются от центрального виджета
        splitter.setSizes(list(self._split_sizes(self._initial_width)))
        self.splitter = splitter
        root.addWidget(splitter, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFormat("Сборка: %p%")
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.stats_label = QLabel("—")
        self.stats_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.stats_label)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setFixedHeight(150)
        root.addWidget(self.log_view)

    def _build_preview(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)

        self.video_label = QLabel("Ожидание кадра...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; color: #888888;")
        # Без минимума: превью должно занимать всё место, которое даёт окно,
        # и масштабироваться вместе с ним (свои границы задаёт только окно)
        self.video_label.setMinimumSize(0, 0)
        self.video_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        layout.addWidget(self.video_label, 1)

        self.state_label = QLabel("Камера не подключена")
        layout.addWidget(self.state_label)

        # Подпись «что видно на превью»: fps камеры и частота отрисовки
        self.preview_info = QLabel("—")
        self.preview_info.setStyleSheet("color: #666666;")
        layout.addWidget(self.preview_info)
        return box

    def _split_sizes(self, width: int) -> tuple[int, int]:
        """Ширины превью и панели настроек для окна заданной ширины.

        Панель получает сохранённую ширину (по умолчанию 640 px): длинные
        названия камер и пути видны целиком, а лишнее место забирает превью.
        """
        panel = max(
            min(width - MIN_PREVIEW_WIDTH, self.config.panel_width, PANEL_MAX_WIDTH),
            PANEL_MIN_WIDTH,
        )
        return width - panel, panel

    def _build_panel(self) -> QWidget:
        panel = QWidget()
        # Стартовая ширина задаётся жёстко (как preferred size сплиттера):
        # при первом показе QSplitter иначе делит место по sizeHint, не читая setSizes
        panel.setMinimumWidth(self.config.panel_width)
        layout = QVBoxLayout(panel)
        layout.addWidget(self._build_camera_group())
        layout.addWidget(self._build_timelapse_group())
        layout.addWidget(self._build_actions_group())
        layout.addStretch(1)
        return panel

    def _build_camera_group(self) -> QGroupBox:
        group = QGroupBox("Камера")
        form = QFormLayout(group)

        self.device_combo = QComboBox()
        self.device_combo.setEditable(True)
        self.device_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.device_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.device_combo.setToolTip(
            "Список всех камер, подключённых к ПК: системные (PnP) и доступные\n"
            "DirectShow. Занятая другой программой камера помечается как недоступная."
        )
        # Смена устройства: перезапуск захвата и новый список разрешений камеры
        self.device_combo.currentTextChanged.connect(self._on_device_changed)
        # Подсказка со статусом выбранной камеры (работает / ошибка / не подключено)
        self.device_combo.currentTextChanged.connect(self._update_device_tooltip)
        self.btn_refresh = QPushButton("Обновить")
        self.btn_refresh.setToolTip("Перечитать все камеры, подключённые к ПК")
        self.btn_refresh.clicked.connect(self._refresh_devices)
        self.btn_repair = QPushButton("Починить")
        self.btn_repair.setToolTip(
            "Перезапустить USB-устройство камеры, если оно в ошибке (код 10)"
        )
        self.btn_repair.clicked.connect(self._on_repair_camera)
        device_row = QWidget()
        device_layout = QHBoxLayout(device_row)
        device_layout.setContentsMargins(0, 0, 0, 0)
        device_layout.addWidget(self.device_combo, 1)
        device_layout.addWidget(self.btn_refresh)
        device_layout.addWidget(self.btn_repair)
        form.addRow("Устройство:", device_row)
        # Названия камер длинные («… — ошибка (код 10)»): список раскрывается
        # по самой длинной строке и шире поля ввода
        view = self.device_combo.view()
        view.setMinimumWidth(DEVICE_POPUP_WIDTH)
        view.setSizeAdjustPolicy(QAbstractItemView.SizeAdjustPolicy.AdjustToContents)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.res_combo = QComboBox()
        self.res_combo.setEditable(True)
        # Список заполняется из драйвера в _refresh_resolutions(),
        # редактируемое поле позволяет ввести своё разрешение вручную
        self.res_combo.addItems([f"{w}x{h}" for w, h in FALLBACK_RESOLUTIONS])
        self.res_combo.currentTextChanged.connect(self._restart_capture)
        form.addRow("Разрешение:", self.res_combo)

        # Подсказка: на какое максимальное разрешение способна камера
        self.res_info = QLabel("—")
        self.res_info.setStyleSheet("color: #666666;")
        self.res_info.setWordWrap(True)
        self.res_info.setToolTip(
            "Максимальный режим, который поддерживает камера.\n"
            "Большие разрешения дают меньший fps и выше нагрузку на USB."
        )
        form.addRow("", self.res_info)

        self.cam_fps_combo = QComboBox()
        self.cam_fps_combo.setEditable(True)
        self.cam_fps_combo.addItems(["30", "60", "15"])
        self.cam_fps_combo.currentTextChanged.connect(self._restart_capture)
        form.addRow("FPS камеры:", self.cam_fps_combo)

        self.btn_props = QPushButton("Свойства камеры")
        self.btn_props.setToolTip("Экспозиция, усиление, баланс белого (драйвер камеры)")
        self.btn_props.clicked.connect(self._open_properties)
        form.addRow(self.btn_props)

        # «Рябь» PS Eye при слабом свете: сглаживание только в превью,
        # сохраняемые кадры таймлапса остаются без обработки
        self.smooth_check = QCheckBox("Сглаживать превью (убирает рябь)")
        self.smooth_check.setToolTip(
            "Лёгкое размытие только на экране. В файлы таймлапса не попадает"
        )
        self.smooth_check.toggled.connect(self._on_smooth_toggled)
        form.addRow(self.smooth_check)
        return group

    def _build_timelapse_group(self) -> QGroupBox:
        group = QGroupBox("Таймлапс")
        form = QFormLayout(group)

        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.5, 7200.0)
        self.interval_spin.setDecimals(1)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setSuffix(" с")
        form.addRow("Интервал съёмки:", self.interval_spin)

        self.out_fps_combo = QComboBox()
        self.out_fps_combo.addItems(["24", "25", "30", "60"])
        form.addRow("FPS видео:", self.out_fps_combo)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(50, 100)
        form.addRow("Качество JPEG:", self.quality_spin)

        self.rotate_combo = QComboBox()
        self.rotate_combo.addItems([f"{value}°" for value in ROTATE_VALUES])
        form.addRow("Поворот кадра:", self.rotate_combo)

        self.codec_combo = QComboBox()
        self.codec_combo.addItems(enc_mod.AVAILABLE_CODECS)
        form.addRow("Кодек видео:", self.codec_combo)

        self.sessions_edit = QLineEdit()
        self.btn_browse = QPushButton("...")
        self.btn_browse.setFixedWidth(34)
        self.btn_browse.clicked.connect(self._choose_sessions_dir)
        dir_row = QWidget()
        dir_layout = QHBoxLayout(dir_row)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.addWidget(self.sessions_edit, 1)
        dir_layout.addWidget(self.btn_browse)
        form.addRow("Папка сессий:", dir_row)

        self.auto_build_check = QCheckBox("Собирать MP4 сразу после остановки")
        self.keep_frames_check = QCheckBox("Оставлять кадры после сборки")
        form.addRow(self.auto_build_check)
        form.addRow(self.keep_frames_check)
        return group

    def _build_actions_group(self) -> QGroupBox:
        group = QGroupBox("Управление")
        layout = QVBoxLayout(group)

        top_row = QHBoxLayout()
        self.btn_start = QPushButton("Старт")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_pause = QPushButton("Пауза")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_stop = QPushButton("Стоп")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        top_row.addWidget(self.btn_start)
        top_row.addWidget(self.btn_pause)
        top_row.addWidget(self.btn_stop)
        layout.addLayout(top_row)

        bottom_row = QHBoxLayout()
        self.btn_build = QPushButton("Собрать MP4")
        self.btn_build.setEnabled(False)
        self.btn_build.clicked.connect(self._on_build)
        self.btn_folder = QPushButton("Открыть папку")
        self.btn_folder.clicked.connect(self._open_folder)
        bottom_row.addWidget(self.btn_build)
        bottom_row.addWidget(self.btn_folder)
        layout.addLayout(bottom_row)
        return group

    # --------------------------------------------------------- настройки

    def _read_resolution(self) -> tuple[int, int]:
        """Разбирает поле «Разрешение» (можно ввести своё, например 1024x576)."""
        text = self.res_combo.currentText().strip().lower().replace(" ", "")
        for sep in ("x", "х", "*", ","):
            if sep in text:
                left, _, right = text.partition(sep)
                try:
                    width, height = int(left), int(right)
                except ValueError:
                    break
                if width > 0 and height > 0:
                    return width, height
                break
        self.log(
            f"Разрешение «{self.res_combo.currentText()}» не распознано, "
            f"остаётся {self.config.width}x{self.config.height}"
        )
        return self.config.width, self.config.height

    def _load_config_into_ui(self) -> None:
        cfg = self.config
        self.res_combo.setCurrentText(f"{cfg.width}x{cfg.height}")
        self.cam_fps_combo.setCurrentText(str(cfg.cam_fps))
        self.interval_spin.setValue(max(float(cfg.interval_sec), 0.5))
        self.out_fps_combo.setCurrentText(str(cfg.out_fps))
        self.quality_spin.setValue(cfg.jpeg_quality)
        if cfg.rotate in ROTATE_VALUES:
            self.rotate_combo.setCurrentIndex(ROTATE_VALUES.index(cfg.rotate))
        if cfg.codec in enc_mod.AVAILABLE_CODECS:
            self.codec_combo.setCurrentText(cfg.codec)
        self.sessions_edit.setText(cfg.sessions_dir)
        self.auto_build_check.setChecked(cfg.auto_build)
        self.keep_frames_check.setChecked(cfg.keep_frames)
        self.smooth_check.setChecked(cfg.preview_smooth)

    def _collect_config(self) -> AppConfig:
        """Переносит значения из интерфейса в config и сохраняет его."""
        cfg = self.config
        cfg.device_name = self._selected_device()
        cfg.width, cfg.height = self._read_resolution()
        cfg.cam_fps = int(self.cam_fps_combo.currentText())
        cfg.interval_sec = self.interval_spin.value()
        cfg.out_fps = int(self.out_fps_combo.currentText())
        cfg.jpeg_quality = self.quality_spin.value()
        cfg.rotate = ROTATE_VALUES[self.rotate_combo.currentIndex()]
        cfg.codec = self.codec_combo.currentText()
        cfg.sessions_dir = self.sessions_edit.text().strip() or "sessions"
        cfg.auto_build = self.auto_build_check.isChecked()
        cfg.keep_frames = self.keep_frames_check.isChecked()
        cfg.preview_smooth = self.smooth_check.isChecked()
        cfg.ffmpeg_path = dshow.find_ffmpeg(cfg.ffmpeg_path)
        # Размер окна не привязан к полям интерфейса — его хранит _remember_geometry
        try:
            cfg.save()
        except OSError as exc:
            self.log(f"Не удалось сохранить настройки: {exc}")
        return cfg

    def _set_settings_enabled(self, enabled: bool) -> None:
        """Блокирует параметры камеры и таймлапса во время съёмки."""
        for widget in (
            self.device_combo,
            self.btn_refresh,
            self.btn_repair,
            self.res_combo,
            self.cam_fps_combo,
            self.btn_props,
            self.interval_spin,
            self.quality_spin,
            self.rotate_combo,
        ):
            widget.setEnabled(enabled)

    # ------------------------------------------------------------- камера

    def _on_device_changed(self) -> None:
        """Смена устройства в списке: обновляет разрешения и перезапускает захват.

        Сигнал приходит на каждое изменение текста, в том числе на каждую
        нажатую клавишу и на программный setCurrentText. Поэтому работаем
        только когда выбран существующий девайс и это действительно новое имя.
        """
        device_name = self._selected_device()
        if not device_name or device_name == self._last_device_name:
            return
        self._last_device_name = device_name
        # Разрешения обновляем в фоне: ffmpeg -list_options грузит камеру на
        # 0.4-2 с, и синхронный вызов подвешивал окно при смене устройства
        self._refresh_resolutions_async()
        self._restart_capture()

    def _refresh_resolutions_async(self) -> None:
        """Обновляет список разрешений в фоне, не блокируя интерфейс.

        ffmpeg -list_options загружает камеру и отвечает за 0.4-2 с. Пока он
        работает, окно должно оставаться живым (перетаскивание, кнопки), иначе
        смена устройства выглядит как зависание.
        """
        device_name = self._selected_device()
        if not device_name:
            return
        # Недоступные (занятые/в ошибке) камеры не опрашиваем: это лишний
        # захват USB и лишние 2 секунды ожидания впустую
        known = dshow.list_devices(self.config.ffmpeg_path)
        if device_name not in known and device_name not in self._system_camera_names:
            return
        if device_name not in known:
            self.res_info.setText(
                "Максимум камеры: недоступно (камера занята или в ошибке)"
            )
            self.log(f"Камера «{device_name}» недоступна для опроса режимов")
            return
        key = (device_name, self.res_combo.currentText().strip())
        self._modes_pending = key
        self.res_info.setText("Максимум камеры: определение...")
        self.log(f"Опрос режимов камеры «{device_name}»...")

        def _probe() -> None:
            try:
                modes = dshow.list_modes(self.config.ffmpeg_path, device_name)
            except Exception as exc:  # noqa: BLE001 - сбой ffmpeg не должен ронять окно
                modes = []
                message = f"Не удалось получить список режимов камеры: {exc}"
            else:
                message = ""
            # Возврат в GUI-поток: виджеты нельзя трогать из рабочего потока
            QTimer.singleShot(0, lambda: self._apply_modes(key, modes, message))

        threading.Thread(target=_probe, name="list-modes", daemon=True).start()

    def _apply_modes(
        self, key: tuple[str, str], modes: list[tuple[str, int, int, float]], message: str
    ) -> None:
        """Применяет режимы, полученные в фоне, к списку разрешений.

        Опрос камеры идёт асинхронно: пока он шёл, пользователь мог выбрать
        другое устройство, поэтому устаревший результат игнорируется.
        """
        if message:
            self.log(message)
        # Устройство сменилось за время опроса: результат больше не актуален
        if key != self._modes_pending:
            return
        # Режимы могли прийти, когда камера уже сменилась на недоступную
        if self._selected_device() != key[0]:
            return

        if not modes:
            self.res_info.setText(
                "Максимум камеры: не удалось определить (нет устройства или драйвер не ответил)"
            )
            self.log("Режимы камеры не получены, список разрешений оставлен без изменений")
            return

        # Режим = разрешение + максимальный fps; уникальные разрешения для списка,
        # сортировка по возрастанию площади кадра
        unique: dict[tuple[int, int], float] = {}
        for _pixel_format, width, height, fps in modes:
            res_key = (width, height)
            if res_key not in unique or fps > unique[res_key]:
                unique[res_key] = fps
        ordered = sorted(unique.items(), key=lambda item: (item[0][0] * item[0][1], item[0][0]))

        # Выбранное разрешение: до перезаполнения списка и после него
        previous = self.res_combo.currentText().strip()
        _, previous_selected = key
        items = [f"{width}x{height}" for (width, height) in unique]
        self.res_combo.blockSignals(True)
        self.res_combo.clear()
        self.res_combo.addItems(items)
        if previous and previous in items:
            self.res_combo.setCurrentText(previous)
        elif previous_selected and previous_selected in items:
            self.res_combo.setCurrentText(previous_selected)
        self.res_combo.blockSignals(False)

        # Самое большое разрешение — обычно оно и есть максимум камеры
        (max_w, max_h), max_fps = ordered[-1]
        mode_list = ", ".join(f"{w}x{h}@{fps:g}" for (w, h), fps in ordered)
        self.res_info.setText(f"Максимум камеры: {max_w}x{max_h} @ {max_fps:g} fps")
        self.res_info.setToolTip(
            "Все режимы, которые отдаёт камера (разрешение@максимальный fps):\n"
            f"{mode_list}\n\n"
            "Большие разрешения дают меньший fps и выше нагрузку на USB."
        )
        device_name, _selected = key
        self.log(f"Камера «{device_name}» поддерживает разрешения: {', '.join(items)}")

    def _selected_device(self) -> str:
        """Выбранное устройство без служебной пометки в списке."""
        return self._device_entries.get(self.device_combo.currentText().strip(), "").strip()

    def _update_device_tooltip(self) -> None:
        """Подсказка со статусом выбранной камеры: что именно нашлось в системе."""
        name = self._selected_device()
        if not name:
            return
        statuses = [status for cam, status in self._camera_entries if cam == name]
        if statuses:
            note = ", ".join(dshow.device_status_label(status) for status in statuses)
        else:
            note = "нет в системе"
        self.device_combo.setToolTip(
            "Список всех камер, подключённых к ПК: системные (PnP) и доступные\n"
            "DirectShow. Занятая другой программой камера помечается как недоступная.\n\n"
            f"Выбрано: «{name}» — {note}"
        )

    def _refresh_devices(self) -> None:
        """Перечитывает список камер, подключённых к ПК.

        Источники дополняют друг друга: ffmpeg (DirectShow) видит только
        свободные устройства, PowerShell (Get-PnpDevice) — вообще все камеры,
        включая занятые другой программой.
        """
        directshow = dshow.list_devices(self.config.ffmpeg_path)
        system_cameras = dshow.list_system_cameras()
        self._camera_entries = list(system_cameras)
        self._system_camera_names = [name for name, _status in system_cameras]

        entries: list[tuple[str, str]] = []
        used: set[str] = set()
        for name in directshow:
            used.add(name)
            entries.append((name, "доступна"))
        for name, status in system_cameras:
            if name in used:
                continue
            used.add(name)
            entries.append((name, dshow.device_status_label(status)))
        # Камера могла быть введена вручную или сохранена в настройках — не теряем её
        current = self._selected_device() or self.config.device_name.strip()
        if current and current not in used:
            entries.append((current, "нет в системе"))

        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self._device_entries.clear()
        for name, note in entries:
            label = f"{name} — {note}"
            self.device_combo.addItem(label)
            self._device_entries[label] = name
        self.device_combo.blockSignals(False)

        # Возвращаем прежний выбор или берём первую доступную камеру
        if current and current in used:
            self._set_device_combo(current)
        else:
            preferred = next(
                (name for name in directshow),
                next((name for name in self._system_camera_names), ""),
            )
            if preferred:
                self._set_device_combo(preferred)
                if current:
                    self.log(f"Камера «{current}» не найдена, выбрана «{preferred}»")
        self._last_device_name = self._selected_device()
        self._update_device_tooltip()

        available = ", ".join(directshow) if directshow else "не найдены"
        self.log("Видеоустройства DirectShow: " + available)
        if system_cameras:
            self.log(
                "Камеры в системе: "
                + ", ".join(f"{name} ({dshow.device_status_label(status)})" for name, status in system_cameras)
            )
        elif sys.platform == "win32":
            self.log("Камеры в системе: не найдены")
        # Список разрешений берётся из выбранного устройства (в фоне)
        self._refresh_resolutions_async()

    def _set_device_combo(self, name: str) -> None:
        """Выбирает камеру в списке по её имени (без пометки)."""
        for label, value in self._device_entries.items():
            if value == name:
                self.device_combo.setCurrentText(label)
                return
        self.device_combo.setCurrentText(name)

    def _repair_camera_on_start(self) -> None:
        """Лечит устройство камеры при старте: при ошибке (код 10) перезапускает его."""
        if device.ensure_camera_ready(self.log):
            self._refresh_devices()

    def _on_repair_camera(self) -> None:
        """Ручное восстановление камеры: перезапуск USB-устройства (лечит код 10)."""
        if self.recorder is not None:
            self.log("Сначала остановите съёмку")
            return
        if not device.repair_needed():
            self.log("Устройство камеры в порядке, перезапуск не требуется")
            self._refresh_devices()
            return
        self._stop_capture()
        self.state_label.setText("Восстановление камеры...")
        QApplication.processEvents()
        _ok, message = device.restart_camera()
        self.log(message)
        self._refresh_devices()
        self._start_capture()

    def _restart_capture(self) -> None:
        """Перезапуск захвата после смены устройства, разрешения или FPS."""
        if self._initializing or self.recorder is not None:
            return
        self._start_capture()

    def _start_capture(self) -> None:
        self._stop_capture()
        cfg = self._collect_config()
        self.capture = CaptureThread(
            cfg.device_name,
            cfg.device_index,
            cfg.width,
            cfg.height,
            cfg.cam_fps,
            cfg.ffmpeg_path,
        )
        self.capture.frame_ready.connect(self._on_frame)
        self.capture.state_changed.connect(self._on_state)
        self.capture.error_occurred.connect(self.log)
        self.capture.capture_lost.connect(self._on_capture_lost)
        self.capture.capture_restored.connect(self._on_capture_restored)
        self.capture.fps_updated.connect(self._on_fps)
        self.capture.start()

    def _stop_capture(self) -> None:
        if self.capture is not None:
            self.capture.stop()
            self.capture = None
        # Замороженный кадр на превью вводит в заблуждение — показываем ожидание
        if hasattr(self, "video_label"):
            self._show_waiting("Ожидание кадра...")
        self._cam_fps = 0.0

    def _on_frame(self, frame) -> None:
        """Запоминает кадр; отрисовку делает отдельный таймер (не чаще PREVIEW_FPS)."""
        self._last_frame = frame

    def _show_waiting(self, text: str) -> None:
        """Убирает с превью устаревший кадр и показывает ожидание."""
        self._last_frame = None
        self.video_label.setPixmap(QPixmap())
        self.video_label.setText(text)

    def _update_preview(self) -> None:
        if self._last_frame is None:
            return
        label_size = self.video_label.size()
        if label_size.width() < 10 or label_size.height() < 10:
            return
        frame = self._last_frame
        if self.smooth_check.isChecked():
            # Рябь PS Eye при слабом свете: гасим только на экране
            frame = cv2.GaussianBlur(frame, (3, 3), 0)
        height, width, _channels = frame.shape
        # Кадр уже BGR — конвертация не нужна, QImage понимает этот формат
        image = QImage(frame.data, width, height, width * 3, QImage.Format.Format_BGR888)
        pixmap = QPixmap.fromImage(image.copy())
        self.video_label.setPixmap(
            pixmap.scaled(
                label_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _on_capture_lost(self, reason: str) -> None:
        """Камера пропала: превью не должно показывать старый (шумный) кадр."""
        self._show_waiting("Ожидание кадра...")
        if not self._capture_lost:
            self._capture_lost = True
            self.log(f"Камера потеряна: {reason}")
        self._update_preview_info()

    def _on_capture_restored(self, width: int, height: int) -> None:
        if self._capture_lost:
            self.log("Камера снова отдаёт кадры")
        self._capture_lost = False
        self._update_preview_info()

    def _on_fps(self, value: float) -> None:
        self._cam_fps = value
        self._update_preview_info()

    def _on_smooth_toggled(self, enabled: bool) -> None:
        """Сглаживание превью применяется сразу, без перезапуска захвата."""
        if self._initializing:
            return
        self._collect_config()
        self.log(f"Сглаживание превью: {'включено' if enabled else 'выключено'}")

    def _update_preview_info(self) -> None:
        """Подпись под превью: что реально приходит с камеры."""
        if self._last_frame is None:
            self.preview_info.setText("превью: нет кадров")
            return
        height, width, _channels = self._last_frame.shape
        self.preview_info.setText(
            f"превью: {width}x{height}, fps камеры: {self._cam_fps:.1f}, "
            f"обновление {PREVIEW_FPS} к/с"
        )

    def _on_state(self, text: str) -> None:
        self.state_label.setText(text)
        self.log(text)

    # -------------------------------------------------------------- запись

    def _on_start(self) -> None:
        if self.recorder is not None:
            return
        cfg = self._collect_config()
        stamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.session_dir = os.path.join(cfg.sessions_path(), stamp)
        try:
            os.makedirs(os.path.join(self.session_dir, "frames"), exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать папку сессии:\n{exc}")
            return

        if self.capture is None:
            self._start_capture()

        self.recorder = TimelapseRecorder(
            self.capture, self.session_dir, cfg.interval_sec, cfg.jpeg_quality, cfg.rotate
        )
        self.recorder.status_message.connect(self.log)
        self.recorder.recording_finished.connect(self._on_recording_finished)
        self.recorder.start()

        self.log(f"Сессия: {self.session_dir}")
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("Пауза")
        self.btn_stop.setEnabled(True)
        self.btn_build.setEnabled(False)
        self._set_settings_enabled(False)

    def _on_pause(self) -> None:
        if self.recorder is None:
            return
        if self.recorder.is_paused():
            self.recorder.resume()
            self.btn_pause.setText("Пауза")
            self.log("Съёмка продолжена")
        else:
            self.recorder.pause()
            self.btn_pause.setText("Продолжить")
            self.log("Съёмка приостановлена")

    def _on_stop(self) -> None:
        if self.recorder is None:
            return
        recorder = self.recorder
        self.recorder = None
        recorder.stop()

        cfg = self._collect_config()
        recorder.save_session_info(
            {
                "width": cfg.width,
                "height": cfg.height,
                "out_fps": cfg.out_fps,
                "codec": cfg.codec,
                "device": cfg.device_name,
            }
        )
        self.log(f"Сессия сохранена: {recorder.session_dir}, кадров: {recorder.frames_saved}")

        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Пауза")
        self.btn_stop.setEnabled(False)
        self.btn_build.setEnabled(True)
        self._set_settings_enabled(True)

        if cfg.auto_build and recorder.frames_saved > 0:
            self._run_encoder()

    def _on_recording_finished(self, info: dict) -> None:
        self.log(f"Итог съёмки: кадров {info['frames']}, пропусков {info['skipped']}")

    # -------------------------------------------------------------- сборка

    def _on_build(self) -> None:
        if self.encoder is not None:
            self.log("Отмена сборки...")
            self.encoder.cancel()
            return
        self._run_encoder()

    def _run_encoder(self) -> None:
        if self.encoder is not None or not self.session_dir:
            return
        cfg = self._collect_config()
        frames_dir = os.path.join(self.session_dir, "frames")
        total = enc_mod.count_frames(frames_dir)
        if total == 0:
            QMessageBox.information(self, "Нет кадров", "В сессии нет кадров для сборки")
            return

        out_path = os.path.join(self.session_dir, "timelapse.mp4")
        ffmpeg = dshow.find_ffmpeg(cfg.ffmpeg_path)
        self.encoder = enc_mod.TimelapseEncoder(ffmpeg, frames_dir, out_path, cfg.out_fps, cfg.codec)
        self.encoder.progress.connect(self._on_encode_progress)
        self.encoder.log_line.connect(self.log)
        self.encoder.finished_ok.connect(self._on_encode_done)
        self.encoder.failed.connect(self._on_encode_failed)
        self.encoder.cancelled.connect(self._on_encode_cancelled)

        self.progress.setVisible(True)
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(0)
        self.btn_build.setText("Отменить сборку")
        self.log(f"Сборка видео: {total} кадров, {cfg.out_fps} fps, кодек {cfg.codec}")
        self.encoder.start()

    def _on_encode_progress(self, done: int, total: int) -> None:
        self.progress.setValue(min(done, total))

    def _finish_encode_ui(self) -> None:
        self.encoder = None
        self.progress.setVisible(False)
        self.btn_build.setText("Собрать MP4")
        self.btn_build.setEnabled(True)

    def _on_encode_done(self, path: str) -> None:
        self._finish_encode_ui()
        self.log(f"Видео готово: {path}")
        cfg = self._collect_config()
        if not cfg.keep_frames and self.session_dir:
            frames_dir = os.path.join(self.session_dir, "frames")
            try:
                shutil.rmtree(frames_dir)
                self.log(f"Кадры удалены: {frames_dir}")
            except OSError as exc:
                self.log(f"Не удалось удалить кадры: {exc}")
        QMessageBox.information(self, "Готово", f"Видео сохранено:\n{path}")

    def _on_encode_failed(self, message: str) -> None:
        self._finish_encode_ui()
        self.log(f"Ошибка сборки: {message}")
        QMessageBox.warning(self, "Ошибка сборки", message)

    def _on_encode_cancelled(self) -> None:
        self._finish_encode_ui()
        self.log("Сборка отменена")

    # ---------------------------------------------------------------- прочее

    def _open_properties(self) -> None:
        if self.recorder is not None:
            QMessageBox.information(self, "Идёт съёмка", "Остановите съёмку перед настройкой камеры")
            return
        cfg = self._collect_config()
        self._stop_capture()
        self.state_label.setText("Настройка камеры...")
        QApplication.processEvents()
        result = show_properties(
            cfg.device_name, cfg.device_index, cfg.ffmpeg_path, cfg.width, cfg.height, cfg.cam_fps
        )
        self.log(result)
        self._start_capture()

    def _choose_sessions_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Папка для сессий", self.config.sessions_path()
        )
        if chosen:
            self.sessions_edit.setText(chosen)

    def _open_folder(self) -> None:
        path = self.session_dir or self.config.sessions_path()
        if not os.path.isdir(path):
            self.log(f"Папка ещё не создана: {path}")
            return
        try:
            os.startfile(path)  # Windows
        except (AttributeError, OSError) as exc:
            self.log(f"Не удалось открыть папку: {exc}")

    def _update_stats(self) -> None:
        cfg = self.config
        parts: list[str] = []
        frames = 0

        if self.capture is not None:
            parts.append(f"fps камеры: {self.capture.actual_fps:.1f}")
        if self.recorder is not None:
            frames = self.recorder.frames_saved
            parts.append(f"кадров снято: {frames}")
            if self.recorder.started_at:
                parts.append(f"время съёмки: {self._fmt_duration(time.time() - self.recorder.started_at)}")
            if self.recorder.is_paused():
                parts.append("ПАУЗА")
        elif self.session_dir:
            frames = enc_mod.count_frames(os.path.join(self.session_dir, "frames"))
            parts.append(f"кадров в сессии: {frames}")

        if frames:
            parts.append(f"длина видео: {self._fmt_duration(frames / max(cfg.out_fps, 1))}")
        if self.session_dir:
            parts.append(f"размер сессии: {self._fmt_size(self._dir_size(self.session_dir))}")
        try:
            free = shutil.disk_usage(cfg.sessions_path()).free
            parts.append(f"свободно: {self._fmt_size(free)}")
        except OSError:
            pass

        self.stats_label.setText(" | ".join(parts) if parts else "—")

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        seconds = int(max(seconds, 0))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours} ч {minutes:02d} мин {secs:02d} с"
        return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def _fmt_size(size: float) -> str:
        for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
            if size < 1024 or unit == "ТБ":
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} ТБ"

    @staticmethod
    def _dir_size(path: str) -> int:
        total = 0
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
        return total

    def log(self, text: str) -> None:
        """Добавляет строку в журнал приложения и дублирует её в temp/pseyes.log."""
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {text}"
        self.log_view.appendPlainText(line)
        self._log_to_file(f"{dt.datetime.now():%Y-%m-%d} {line}")

    @staticmethod
    def _log_to_file(line: str) -> None:
        """Пишет строку в файл журнала (с ротацией), ошибки записи не критичны."""
        try:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
            if os.path.isfile(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
                os.replace(LOG_FILE, LOG_FILE + ".old")
            with open(LOG_FILE, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass

    def shutdown(self) -> None:
        """Аварийно-безопасное завершение: останавливает потоки и освобождает камеру.

        Вызывается из closeEvent, при необработанном исключении и по сигналу:
        незакрытый WinUSB «залипает» и даёт код 10 при следующем запуске.
        """
        if self._shutting_down:
            return
        self._shutting_down = True
        if self.recorder is not None:
            self.recorder.stop()
            self.recorder = None
        if self.encoder is not None:
            self.encoder.cancel()
            self.encoder.wait(5000)
            self.encoder = None
        self._stop_capture()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.log("Закрытие приложения")
        self._remember_geometry()
        self.shutdown()
        try:
            self._collect_config()
        except (OSError, ValueError):
            pass
        event.accept()

    def _remember_geometry(self) -> None:
        """Запоминает текущий размер окна и ширину панели настроек."""
        size = self.size()
        width, height = size.width(), size.height()
        if width <= 0 or height <= 0 or self.isMaximized() or self.isFullScreen():
            return
        self.config.window_width = width
        self.config.window_height = height
        sizes = self.splitter.sizes()
        # 0 — превью, 1 — панель; после старта/preview_width=0 сплиттера ещё не раскладывался
        if len(sizes) == 2 and sizes[1] > 0:
            self.config.panel_width = sizes[1]
