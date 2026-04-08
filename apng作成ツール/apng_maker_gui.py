import json
import shutil
import sys
import tempfile
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image, ImageOps
    from apng import APNG
    from PyQt5.QtCore import QMimeData, QPoint, QSize, Qt, QTimer
    from PyQt5.QtGui import QColor, QDrag, QDragEnterEvent, QDropEvent, QFont, QIcon, QImage, QPainter, QPixmap
    from PyQt5.QtWidgets import (
        QApplication,
        QAbstractItemView,
        QCheckBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QListView,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QSplitter,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError as exc:
    missing_name = exc.name or "required package"
    print(
        "必要なライブラリが見つかりませんでした: "
        f"{missing_name}\n"
        "次のコマンドでインストールしてください:\n"
        f'"{sys.executable}" -m pip install PyQt5 Pillow apng'
    )
    sys.exit(1)


APP_NAME = "APNG作成ツール"
SETTINGS_PATH = Path(__file__).with_name("apng_maker_settings.json")
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg"}
RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS
THUMBNAIL_SIZE = QSize(120, 120)
SOURCE_FOLDER_ROLE = Qt.UserRole + 1
INTERNAL_DRAG_MIME = "application/x-apng-maker-row"


class ImageListWidget(QListWidget):
    """外部ファイルの追加と内部並び替えを両立する画像リスト。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start_pos = QPoint()
        self._drag_row = -1
        self._live_drag_row = -1
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionRectVisible(False)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Snap)
        self.setSpacing(4)
        self.setIconSize(THUMBNAIL_SIZE)
        self.setGridSize(QSize(128, 128))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            self._drag_start_pos = event.pos()
            self._drag_row = self.row(item) if item is not None else -1
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        if self._drag_row < 0:
            super().mouseMoveEvent(event)
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return
        self._start_internal_drag(self._drag_row)
        self._drag_row = -1

    def _start_internal_drag(self, row: int) -> None:
        item = self.item(row)
        if item is None:
            return
        self._live_drag_row = row
        mime_data = QMimeData()
        mime_data.setData(INTERNAL_DRAG_MIME, str(row).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.setHotSpot(QPoint(self.iconSize().width() // 2, self.iconSize().height() // 2))
        pixmap = item.icon().pixmap(self.iconSize())
        if not pixmap.isNull():
            drag.setPixmap(pixmap)
        drag.exec_(Qt.MoveAction)
        self._live_drag_row = -1

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        if event.mimeData().hasFormat(INTERNAL_DRAG_MIME):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        if event.mimeData().hasFormat(INTERNAL_DRAG_MIME):
            self._live_reorder_item(event.pos())
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            self._add_files_from_mime(event.mimeData(), event.pos())
            event.acceptProposedAction()
            return
        if event.mimeData().hasFormat(INTERNAL_DRAG_MIME):
            self._reorder_item(event)
            event.acceptProposedAction()
            return
        super().dropEvent(event)
        window = self.window()
        if hasattr(window, "refresh_item_previews"):
            window.refresh_item_previews()

    def _reorder_item(self, event: QDropEvent) -> None:
        window = self.window()
        self._live_reorder_item(event.pos())
        current_item = self.item(self._live_drag_row) if 0 <= self._live_drag_row < self.count() else None
        if current_item is not None:
            self.setCurrentItem(current_item)
        if hasattr(window, "refresh_item_previews"):
            window.refresh_item_previews()
        if hasattr(window, "preview_selected_image") and current_item is not None:
            window.preview_selected_image(current_item)

    def _live_reorder_item(self, position: QPoint) -> None:
        if self._live_drag_row < 0 or self._live_drag_row >= self.count():
            return

        target_row = self.indexAt(position).row()
        if target_row < 0:
            target_row = self.count() - 1

        target_row = self._normalize_target_row(target_row, position)
        if target_row == self._live_drag_row:
            return

        item = self.takeItem(self._live_drag_row)
        if item is None:
            return
        self.insertItem(target_row, item)
        self._live_drag_row = target_row
        self.setCurrentItem(item)

        window = self.window()
        if hasattr(window, "refresh_item_previews"):
            window.refresh_item_previews()

    def _normalize_target_row(self, target_row: int, position: QPoint) -> int:
        target_item = self.item(target_row)
        if target_item is None:
            return max(0, min(target_row, self.count() - 1))

        rect = self.visualItemRect(target_item)
        if rect.isValid():
            moving_forward = self._live_drag_row < target_row
            midpoint_x = rect.left() + rect.width() // 2
            midpoint_y = rect.top() + rect.height() // 2

            if self.flow() == QListView.LeftToRight:
                passed_midpoint = position.x() > midpoint_x
            else:
                passed_midpoint = position.y() > midpoint_y

            if passed_midpoint and moving_forward:
                return target_row
            if passed_midpoint and not moving_forward:
                return min(target_row + 1, self.count() - 1)
            if not passed_midpoint and moving_forward:
                return max(target_row - 1, 0)
            return target_row

        return max(0, min(target_row, self.count() - 1))

    def _add_files_from_mime(self, mime_data: QMimeData, position: QPoint) -> None:
        window = self.window()
        paths = []
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            file_path = Path(url.toLocalFile())
            if file_path.suffix.lower() in SUPPORTED_EXTENSIONS and file_path.is_file():
                paths.append(file_path)
        if not paths:
            return

        insert_row = self.indexAt(position).row()
        if insert_row < 0:
            insert_row = self.count()
        for offset, path in enumerate(paths):
            if hasattr(window, "insert_image_path"):
                window.insert_image_path(path, insert_row + offset)
        if hasattr(window, "refresh_item_previews"):
            window.refresh_item_previews()


class PreviewLabel(QLabel):
    """APNGをQLabel上で安定して再生するプレビュー。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames = []
        self._durations = []
        self._current_index = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setStyleSheet(
            "QLabel { background: #f4f4f4; border: 1px solid #c8c8c8; }"
        )
        self.setText("プレビュー未作成")
        self._static_pixmap = None
        self._showing_static_override = False
        self._is_paused = False

    def load_preview_file(self, path: Path) -> bool:
        self.clear_preview()
        try:
            with Image.open(path) as image:
                while True:
                    frame = image.convert("RGBA")
                    self._frames.append(self._pixmap_from_pil_image(frame))
                    duration = int(image.info.get("duration", 100))
                    self._durations.append(max(20, duration))
                    image.seek(image.tell() + 1)
        except EOFError:
            pass
        except Exception:
            self.clear_preview()
            return False

        if not self._frames:
            self.clear_preview()
            return False

        self._current_index = 0
        self._is_paused = False
        self._show_current_frame()
        if len(self._frames) > 1:
            self._timer.start(self._durations[0])
        return True

    def show_static_image(self, path: Path, frame_index: int | None = None) -> bool:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return False
        if frame_index is not None and self._frames:
            self._current_index = max(0, min(frame_index, len(self._frames) - 1))
        self._timer.stop()
        self._static_pixmap = pixmap
        self._showing_static_override = True
        self._is_paused = True
        self._show_pixmap(pixmap)
        return True

    def clear_preview(self) -> None:
        self._timer.stop()
        self._frames = []
        self._durations = []
        self._current_index = 0
        self._static_pixmap = None
        self._showing_static_override = False
        self._is_paused = False
        self.clear()
        self.setText("プレビュー未作成")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._static_pixmap is not None:
            self._show_pixmap(self._static_pixmap)
        else:
            self._show_current_frame()

    def _advance_frame(self) -> None:
        if len(self._frames) <= 1 or self._is_paused:
            return
        self._current_index = (self._current_index + 1) % len(self._frames)
        self._show_current_frame()
        self._timer.start(self._durations[self._current_index])

    def _show_current_frame(self) -> None:
        if not self._frames:
            return
        self._show_pixmap(self._frames[self._current_index])

    def _show_pixmap(self, pixmap: QPixmap) -> None:
        self.setPixmap(
            pixmap.scaled(
                self.size() - QSize(8, 8),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def _pixmap_from_pil_image(self, image: Image.Image) -> QPixmap:
        data = image.tobytes("raw", "RGBA")
        qimage = QImage(
            data,
            image.width,
            image.height,
            image.width * 4,
            QImage.Format_RGBA8888,
        )
        return QPixmap.fromImage(qimage.copy())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.toggle_playback()
        super().mousePressEvent(event)

    def toggle_playback(self) -> None:
        if self._frames:
            if self._is_paused:
                self._static_pixmap = None
                self._showing_static_override = False
                self._is_paused = False
                self._show_current_frame()
                if len(self._frames) > 1:
                    self._timer.start(self._durations[self._current_index])
            else:
                self._is_paused = True
                self._timer.stop()
                self._static_pixmap = self._frames[self._current_index]
                self._showing_static_override = False
                self._show_pixmap(self._static_pixmap)
            return

        if self._static_pixmap is not None:
            self._show_pixmap(self._static_pixmap)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(960, 560)
        self.import_temp_dirs = []

        self.image_list = ImageListWidget(self)
        self.add_button = QPushButton("画像追加")
        self.remove_button = QPushButton("削除")

        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.01, 999.99)
        self.duration_spin.setSingleStep(0.1)
        self.duration_spin.setDecimals(2)
        self.duration_spin.setValue(0.5)
        self.duration_spin.setSuffix(" 秒")

        self.infinite_loop_checkbox = QCheckBox("無限ループ")
        self.infinite_loop_checkbox.setChecked(True)

        self.loop_count_spin = QSpinBox()
        self.loop_count_spin.setRange(1, 9999)
        self.loop_count_spin.setValue(1)
        self.loop_count_spin.setEnabled(False)

        self.resize_checkbox = QCheckBox("最初の画像サイズにリサイズ")
        self.resize_checkbox.setChecked(True)

        self.output_folder_edit = QLineEdit()
        self.output_folder_button = QPushButton("選択")
        self.use_first_image_folder_button = QPushButton("1枚目のフォルダ")

        self.preview_label = PreviewLabel()
        self.load_preview_button = QPushButton("プレビュー読込")
        self.create_button = QPushButton("APNG作成")

        self._build_ui()
        self._connect_signals()
        self.load_settings()

    def _build_ui(self) -> None:
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(self.image_list)

        left_buttons = QHBoxLayout()
        left_buttons.addWidget(self.add_button)
        left_buttons.addWidget(self.remove_button)
        left_layout.addLayout(left_buttons)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        form_layout = QFormLayout()
        form_layout.addRow("フレーム時間", self.duration_spin)
        form_layout.addRow("", self.infinite_loop_checkbox)
        form_layout.addRow("ループ回数", self.loop_count_spin)
        form_layout.addRow("", self.resize_checkbox)

        output_layout = QHBoxLayout()
        output_layout.addWidget(self.output_folder_edit)
        output_layout.addWidget(self.output_folder_button)
        output_layout.addWidget(self.use_first_image_folder_button)
        form_layout.addRow("出力フォルダ", output_layout)
        right_layout.addLayout(form_layout)

        right_layout.addWidget(self.preview_label, stretch=1)
        right_layout.addWidget(self.load_preview_button)
        right_layout.addWidget(self.create_button)

        splitter = QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        container = QWidget()
        root_layout = QHBoxLayout(container)
        root_layout.addWidget(splitter)
        self.setCentralWidget(container)

    def _connect_signals(self) -> None:
        self.add_button.clicked.connect(self.add_images)
        self.remove_button.clicked.connect(self.remove_selected_images)
        self.output_folder_button.clicked.connect(self.select_output_folder)
        self.use_first_image_folder_button.clicked.connect(self.set_output_folder_to_first_image_folder)
        self.load_preview_button.clicked.connect(self.load_preview_file)
        self.create_button.clicked.connect(self.create_apng)
        self.infinite_loop_checkbox.toggled.connect(self.loop_count_spin.setDisabled)
        self.image_list.itemClicked.connect(self.preview_selected_image)

    def add_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "画像を選択",
            "",
            "画像ファイル (*.png *.jpg *.jpeg)",
        )
        for file_path in files:
            self.insert_image_path(Path(file_path))
        self.refresh_item_previews()

    def insert_image_path(
        self,
        path: Path,
        row: int | None = None,
        source_folder: Path | None = None,
    ) -> None:
        display_path = str(path)
        item = QListWidgetItem()
        item.setData(Qt.UserRole, display_path)
        item.setData(SOURCE_FOLDER_ROLE, str(source_folder or path.parent))
        item.setIcon(self.create_thumbnail_icon(path))
        item.setToolTip(display_path)
        item.setSizeHint(QSize(128, 128))
        if row is None or row < 0 or row > self.image_list.count():
            self.image_list.addItem(item)
        else:
            self.image_list.insertItem(row, item)

    def create_thumbnail_icon(self, path: Path, number: int | None = None) -> QIcon:
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGBA")
                image.thumbnail((THUMBNAIL_SIZE.width(), THUMBNAIL_SIZE.height()), RESAMPLE)
                buffer = BytesIO()
                image.save(buffer, format="PNG")
        except Exception:
            return QIcon()

        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")
        if number is not None and not pixmap.isNull():
            pixmap = self.add_number_overlay(pixmap, number)
        return QIcon(pixmap)

    def add_number_overlay(self, pixmap: QPixmap, number: int) -> QPixmap:
        numbered = QPixmap(pixmap)
        painter = QPainter(numbered)
        painter.setRenderHint(QPainter.Antialiasing)

        badge_rect = numbered.rect().adjusted(6, 6, -numbered.width() + 42, -numbered.height() + 30)
        painter.setBrush(QColor(0, 0, 0, 180))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(badge_rect, 8, 8)

        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(Qt.white)
        painter.drawText(badge_rect, Qt.AlignCenter, str(number))
        painter.end()
        return numbered

    def refresh_item_previews(self) -> None:
        for index in range(self.image_list.count()):
            item = self.image_list.item(index)
            path = Path(item.data(Qt.UserRole))
            item.setIcon(self.create_thumbnail_icon(path, index + 1))

    def remove_selected_images(self) -> None:
        selected_items = self.image_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            row = self.image_list.row(item)
            self.image_list.takeItem(row)
        self.refresh_item_previews()

    def select_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "出力フォルダを選択",
            self.output_folder_edit.text() or "",
        )
        if folder:
            self.output_folder_edit.setText(folder)

    def set_output_folder_to_first_image_folder(self) -> None:
        source_folder = self.get_first_item_source_folder()
        if source_folder is None:
            QMessageBox.information(
                self,
                APP_NAME,
                "先に画像を追加してください。",
            )
            return
        self.output_folder_edit.setText(str(source_folder))

    def get_image_paths(self) -> list[Path]:
        paths = []
        for index in range(self.image_list.count()):
            item = self.image_list.item(index)
            paths.append(Path(item.data(Qt.UserRole)))
        return paths

    def get_first_item_source_folder(self) -> Path | None:
        if self.image_list.count() == 0:
            return None
        item = self.image_list.item(0)
        source_folder = item.data(SOURCE_FOLDER_ROLE)
        if source_folder:
            return Path(source_folder)
        return Path(item.data(Qt.UserRole)).parent

    def clear_image_list(self) -> None:
        self.image_list.clear()

    def preview_selected_image(self, item: QListWidgetItem) -> None:
        path = Path(item.data(Qt.UserRole))
        frame_index = self.image_list.row(item)
        if not self.preview_label.show_static_image(path, frame_index):
            QMessageBox.warning(
                self,
                APP_NAME,
                f"画像プレビューの読込に失敗しました。\n{path}",
            )

    def create_apng(self) -> None:
        image_paths = self.get_image_paths()
        if len(image_paths) < 2:
            QMessageBox.warning(self, APP_NAME, "画像は2枚以上必要です。")
            return

        for path in image_paths:
            if not path.exists():
                QMessageBox.warning(self, APP_NAME, f"画像が見つかりません:\n{path}")
                return

        try:
            output_path = self.build_output_path(image_paths)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            delay_ms = max(1, int(round(self.duration_spin.value() * 1000)))
            num_plays = 0 if self.infinite_loop_checkbox.isChecked() else self.loop_count_spin.value()

            with tempfile.TemporaryDirectory(prefix="apng_maker_") as temp_dir:
                temp_files = self.prepare_temp_images(image_paths, Path(temp_dir))
                animation = APNG(num_plays=num_plays)
                for temp_file in temp_files:
                    animation.append_file(str(temp_file), delay=delay_ms)
                animation.save(str(output_path))

            self.show_preview(output_path)
            self.save_settings()
            QMessageBox.information(self, APP_NAME, f"APNGを作成しました。\n{output_path}")
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"APNG作成中にエラーが発生しました。\n{exc}")

    def build_output_path(self, image_paths: list[Path]) -> Path:
        first_image = image_paths[0]
        folder_text = self.output_folder_edit.text().strip()
        if folder_text:
            output_dir = Path(folder_text)
        else:
            output_dir = self.get_first_item_source_folder() or first_image.parent
        return output_dir / f"{first_image.stem}.png"

    def prepare_temp_images(self, image_paths: list[Path], temp_dir: Path) -> list[Path]:
        temp_files = []
        target_size = None

        if self.resize_checkbox.isChecked():
            with Image.open(image_paths[0]) as base_image:
                target_size = ImageOps.exif_transpose(base_image).size

        for index, image_path in enumerate(image_paths):
            with Image.open(image_path) as image:
                image = ImageOps.exif_transpose(image).convert("RGBA")
                if target_size is not None and image.size != target_size:
                    image = image.resize(target_size, RESAMPLE)

                temp_file = temp_dir / f"frame_{index:04d}.png"
                image.save(temp_file, format="PNG")
                temp_files.append(temp_file)

        return temp_files

    def show_preview(self, output_path: Path) -> None:
        if not self.preview_label.load_preview_file(output_path):
            self.preview_label.clear_preview()
            QMessageBox.warning(
                self,
                APP_NAME,
                "APNGは作成されましたが、プレビューの読み込みに失敗しました。",
            )
            return

    def load_preview_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "プレビューするAPNGを選択",
            self.output_folder_edit.text().strip() or "",
            "PNG / APNG (*.png)",
        )
        if not file_path:
            return
        apng_path = Path(file_path)
        try:
            self.import_apng_for_edit(apng_path)
            self.show_preview(apng_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                APP_NAME,
                f"APNGの読込に失敗しました。\n{exc}",
            )

    def import_apng_for_edit(self, apng_path: Path) -> None:
        animation = APNG.open(str(apng_path))
        if not animation.frames:
            raise ValueError("フレームが見つかりませんでした。")

        temp_dir = Path(tempfile.mkdtemp(prefix="apng_import_"))
        extracted_paths = []
        for index, (png, control) in enumerate(animation.frames):
            frame_path = temp_dir / f"frame_{index:04d}.png"
            png.save(frame_path)
            extracted_paths.append(frame_path)

        self.import_temp_dirs.append(temp_dir)
        self.clear_image_list()
        for frame_path in extracted_paths:
            self.insert_image_path(frame_path, source_folder=apng_path.parent)
        self.refresh_item_previews()

        first_control = animation.frames[0][1]
        if first_control is not None and first_control.delay_den:
            duration_seconds = first_control.delay / first_control.delay_den
            self.duration_spin.setValue(max(0.01, round(duration_seconds, 3)))

        self.infinite_loop_checkbox.setChecked(animation.num_plays == 0)
        if animation.num_plays > 0:
            self.loop_count_spin.setValue(animation.num_plays)

        self.output_folder_edit.setText(str(apng_path.parent))
        self.save_settings()

    def cleanup_import_temp_dirs(self) -> None:
        for temp_dir in self.import_temp_dirs:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
        self.import_temp_dirs.clear()

    def load_settings(self) -> None:
        if not SETTINGS_PATH.exists():
            return

        try:
            with SETTINGS_PATH.open("r", encoding="utf-8") as file:
                settings = json.load(file)
        except Exception:
            return

        self.duration_spin.setValue(float(settings.get("frame_duration", 0.5)))
        self.infinite_loop_checkbox.setChecked(bool(settings.get("infinite_loop", True)))
        self.loop_count_spin.setValue(int(settings.get("loop_count", 1)))
        self.resize_checkbox.setChecked(bool(settings.get("resize_to_first", True)))
        self.output_folder_edit.setText(str(settings.get("output_folder", "")))

    def save_settings(self) -> None:
        settings = {
            "frame_duration": self.duration_spin.value(),
            "infinite_loop": self.infinite_loop_checkbox.isChecked(),
            "loop_count": self.loop_count_spin.value(),
            "resize_to_first": self.resize_checkbox.isChecked(),
            "output_folder": self.output_folder_edit.text().strip(),
        }

        try:
            with SETTINGS_PATH.open("w", encoding="utf-8") as file:
                json.dump(settings, file, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        self.save_settings()
        self.cleanup_import_temp_dirs()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    try:
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        window.close()
        sys.exit(0)


if __name__ == "__main__":
    main()
