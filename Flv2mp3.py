import sys
import os
import re
import subprocess
from collections import defaultdict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QProgressBar, QLabel,
    QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QMutex, QMutexLocker

# ====================== 固定配置（焊死）======================
FIXED_PREFIX = "MVPDJ Trance Only Original Sound_"
FFMPEG_PATH = "ffmpeg.exe"
TIME_PATTERN = re.compile(r'\[(\d{4}-\d{2}-\d{2}) (\d{2}-\d{2}-\d{2})\]')

PROGRESS_COLORS = ["#3498db", "#9b59b6", "#e67e22", "#e74c3c", "#1abc9c", "#f1c40f"]
FINISH_COLOR = "#2ecc71"

# ====================== 转换线程 ======================
class ConvertThread(QThread):
    progress_update = pyqtSignal(int)
    finished_all = pyqtSignal()
    error_occur = pyqtSignal(str)

    def __init__(self, day_groups, parent=None):
        super().__init__(parent)
        self.day_groups = day_groups
        self.is_terminated = False
        self.mutex = QMutex()

    def run(self):
        total_files = sum(len(files) for files in self.day_groups.values())
        total_steps = total_files + len(self.day_groups)
        current_step = 0

        # ====================== 按日期一组一组顺序处理 ======================
        for date_str, files in self.day_groups.items():
            if self.is_terminated:
                return

            part_paths = []

            # --------------- 1. 先把当天所有 FLV 转成 MP3 分段 ---------------
            for idx, flv_path in enumerate(files, 1):
                if self.is_terminated:
                    return

                folder = os.path.dirname(flv_path)
                part_name = f"{FIXED_PREFIX}{date_str}_{idx:02d}.mp3"
                part_path = os.path.join(folder, part_name)

                cmd = [
                    FFMPEG_PATH, "-i", flv_path,
                    "-vn", "-b:a", "320k", "-ac", "2", "-ar", "48k", "-c:a", "mp3", "-y", part_path
                ]

                try:
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
                except:
                    self.error_occur.emit(f"转换失败：{os.path.basename(flv_path)}")

                part_paths.append(part_path)
                current_step += 1
                self.progress_update.emit(int(current_step / total_steps * 100))

            # --------------- 2. 当天分段转完，立刻合并 ---------------
            if len(part_paths) >= 2:
                if self.is_terminated:
                    return

                folder = os.path.dirname(part_paths[0])
                concat_str = "|".join(part_paths)
                final_output = os.path.join(folder, f"{FIXED_PREFIX}{date_str}.mp3")

                cmd = [
                    FFMPEG_PATH, "-i", f"concat:{concat_str}",
                    "-c", "copy", "-y", final_output
                ]

                try:
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
                except:
                    self.error_occur.emit(f"合并失败：{date_str}")

            current_step += 1
            self.progress_update.emit(int(current_step / total_steps * 100))

        self.progress_update.emit(100)
        self.finished_all.emit()

    def terminate_task(self):
        locker = QMutexLocker(self.mutex)
        self.is_terminated = True

# ====================== 主窗口 ======================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FLV 转 MP3 工具")
        self.setFixedSize(780, 580)

        self.day_groups = {}
        self.convert_thread = None

        self.init_ui()
        self.apply_style()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(24, 20, 24, 12)

        self.list_widget = QListWidget()
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("添加文件")
        self.btn_start = QPushButton("开始转换")
        self.btn_clear = QPushButton("清空列表")
        self.btn_stop = QPushButton("强制终止")

        for btn in [self.btn_add, self.btn_start, self.btn_clear, self.btn_stop]:
            btn_layout.addWidget(btn)
            btn.setFixedHeight(34)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(False)

        self.progress_label = QLabel("进度：0%")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label_sign = QLabel("Designed by CarrolChen")
        self.label_sign.setAlignment(Qt.AlignmentFlag.AlignCenter)

        main_layout.addWidget(self.list_widget, stretch=12)
        main_layout.addLayout(btn_layout)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.progress_label)
        main_layout.addStretch(1)
        main_layout.addWidget(self.label_sign)

        self.setAcceptDrops(True)

        self.btn_add.clicked.connect(self.add_files)
        self.btn_start.clicked.connect(self.start_convert)
        self.btn_clear.clicked.connect(self.clear_list)
        self.btn_stop.clicked.connect(self.force_stop)

    def apply_style(self):
        self.btn_add.setStyleSheet("""
            QPushButton { background-color: #3498db; color: white; border-radius: 6px; }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.btn_start.setStyleSheet("""
            QPushButton { background-color: #2ecc71; color: white; border-radius: 6px; }
            QPushButton:hover { background-color: #27ae60; }
        """)
        self.btn_clear.setStyleSheet("""
            QPushButton { background-color: #f39c12; color: white; border-radius: 6px; }
            QPushButton:hover { background-color: #e67e22; }
        """)
        self.btn_stop.setStyleSheet("""
            QPushButton { background-color: #e74c3c; color: white; border-radius: 6px; }
            QPushButton:hover { background-color: #c0392b; }
        """)

        stops = ", ".join([f"stop:{i/len(PROGRESS_COLORS):.2f} {c}" for i, c in enumerate(PROGRESS_COLORS)])
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ border-radius: 10px; background-color: #f0f0f0; }}
            QProgressBar::chunk {{ border-radius: 10px; background: qlineargradient(x1:0,y1:0,x2:1,y1:0, {stops}); }}
        """)
        self.label_sign.setStyleSheet("color: purple; font-size: 11px;")

    def set_finish_style(self):
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ border-radius: 10px; background-color: #f0f0f0; }}
            QProgressBar::chunk {{ border-radius: 10px; background: {FINISH_COLOR}; }}
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.toLocalFile().lower().endswith(".flv")]
        self.add_paths_to_list(paths)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(filter="FLV Files (*.flv)")
        self.add_paths_to_list(paths)

    def add_paths_to_list(self, new_paths):
        existing = []
        for i in range(self.list_widget.count()):
            existing.append(self.list_widget.item(i).data(Qt.ItemDataRole.UserRole))

        all_paths = existing + new_paths
        file_dt = []

        for p in all_paths:
            fn = os.path.basename(p)
            match = TIME_PATTERN.search(fn)
            if match:
                date_part, time_part = match.groups()
                file_dt.append((f"{date_part} {time_part}", p))

        file_dt.sort(key=lambda x: x[0])
        sorted_paths = [p for dt, p in file_dt]

        self.list_widget.clear()
        for p in sorted_paths:
            item = QListWidgetItem(os.path.basename(p))
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.list_widget.addItem(item)

    def build_day_groups(self):
        path_list = []
        for i in range(self.list_widget.count()):
            path_list.append(self.list_widget.item(i).data(Qt.ItemDataRole.UserRole))

        day_groups = defaultdict(list)
        for p in path_list:
            match = TIME_PATTERN.search(os.path.basename(p))
            if match:
                date_str, _ = match.groups()
                day_groups[date_str].append(p)

        # 按日期先后排序
        sorted_days = sorted(day_groups.keys())
        sorted_groups = {d: day_groups[d] for d in sorted_days}
        return sorted_groups

    def start_convert(self):
        if self.list_widget.count() == 0:
            QMessageBox.warning(self, "提示", "请先添加文件")
            return

        self.btn_start.setEnabled(False)
        self.btn_add.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.day_groups = self.build_day_groups()

        self.convert_thread = ConvertThread(self.day_groups)
        self.convert_thread.progress_update.connect(self.on_progress)
        self.convert_thread.finished_all.connect(self.on_all_done)
        self.convert_thread.error_occur.connect(lambda msg: QMessageBox.critical(self,"错误",msg))
        self.convert_thread.start()

    def on_progress(self, percent):
        self.progress_bar.setValue(percent)
        self.progress_label.setText(f"进度：{percent}%")

    def on_all_done(self):
        self.set_finish_style()
        QMessageBox.information(self, "完成", "全部转换与合并完成！")
        self.reset_ui()

    def force_stop(self):
        if self.convert_thread and self.convert_thread.isRunning():
            self.convert_thread.terminate_task()
            self.reset_ui()
            QMessageBox.information(self, "已终止", "已停止")

    def clear_list(self):
        self.list_widget.clear()
        self.progress_bar.setValue(0)
        self.progress_label.setText("进度：0%")
        self.apply_style()

    def reset_ui(self):
        self.btn_start.setEnabled(True)
        self.btn_add.setEnabled(True)
        self.btn_clear.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())