import sys
import os
import shutil
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QFileDialog, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QMessageBox, QSplitter, QTabWidget,
                             QListWidget, QListWidgetItem, QSpinBox, QProgressBar, QAbstractItemView)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QFont
import dataset_parser
import augmenter

class ModernUI:
    STYLESHEET = """
    QMainWindow, QWidget {
        background-color: #ffffff;
        font-family: 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
        color: #333333;
    }
    QPushButton {
        background-color: #f0f0f0;
        border: 1px solid #dcdcdc;
        border-radius: 6px;
        padding: 8px 16px;
        font-weight: 600;
    }
    QPushButton:hover {
        background-color: #e8e8e8;
    }
    QPushButton:pressed {
        background-color: #dcdcdc;
    }
    QPushButton:disabled {
        background-color: #fafafa;
        color: #a0a0a0;
        border-color: #e0e0e0;
    }
    QLabel {
        font-size: 14px;
    }
    QLabel#titleLabel {
        font-size: 24px;
        font-weight: bold;
        color: #111111;
        margin-bottom: 10px;
    }
    QTableWidget {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        gridline-color: #f0f0f0;
    }
    QHeaderView::section {
        background-color: #f9f9f9;
        padding: 6px;
        border: none;
        border-right: 1px solid #e0e0e0;
        border-bottom: 1px solid #e0e0e0;
        font-weight: 600;
    }
    QSplitter::handle {
        background-color: #e0e0e0;
        width: 2px;
    }
    QTabWidget::pane {
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        background-color: #ffffff;
    }
    QTabBar::tab {
        background-color: #f0f0f0;
        border: 1px solid #e0e0e0;
        border-bottom: none;
        padding: 8px 16px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        margin-right: 2px;
    }
    QTabBar::tab:selected {
        background-color: #ffffff;
        border-bottom: 1px solid #ffffff;
        font-weight: bold;
    }
    """

class ImageViewerWidget(QWidget):
    def __init__(self, parent_window, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # Important for keyboard events
        
        self.pairs = []
        self.class_map = {}
        self.current_idx = 0
        self.is_staged = False
        
        layout = QVBoxLayout(self)
        
        # Image Display
        self.image_label = QLabel("Load a dataset to view images.")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        self.image_label.setStyleSheet("background-color: #f5f5f5; border: 1px solid #e0e0e0; border-radius: 4px;")
        layout.addWidget(self.image_label, stretch=1)
        
        # Controls Layout
        controls_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("Previous")
        self.prev_btn.clicked.connect(self.show_prev)
        self.prev_btn.setEnabled(False)
        controls_layout.addWidget(self.prev_btn)
        
        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls_layout.addWidget(self.info_label)
        
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.show_next)
        self.next_btn.setEnabled(False)
        controls_layout.addWidget(self.next_btn)
        
        layout.addLayout(controls_layout)
        
        # Review Staged Controls Layout
        self.review_widget = QWidget()
        review_layout = QHBoxLayout(self.review_widget)
        review_layout.setContentsMargins(0, 0, 0, 0)
        
        self.accept_btn = QPushButton("Accept Image")
        self.accept_btn.setStyleSheet("""
            QPushButton { background-color: #e0ffe0; border-color: #ccffcc; color: #008800; font-weight: bold; }
            QPushButton:hover { background-color: #ccffcc; }
        """)
        self.accept_btn.clicked.connect(self.accept_current)
        review_layout.addWidget(self.accept_btn)
        
        self.redo_btn = QPushButton("Redo Image")
        self.redo_btn.setStyleSheet("""
            QPushButton { background-color: #ffe0e0; border-color: #ffcccc; color: #cc0000; font-weight: bold; }
            QPushButton:hover { background-color: #ffcccc; }
        """)
        self.redo_btn.clicked.connect(self.redo_current)
        review_layout.addWidget(self.redo_btn)
        
        layout.addWidget(self.review_widget)
        self.review_widget.hide() # Hidden by default

    def load_dataset(self, pairs, class_map, is_staged=False):
        self.pairs = pairs
        self.class_map = class_map
        self.is_staged = is_staged
        self.current_idx = 0
        
        if is_staged:
            self.review_widget.show()
        else:
            self.review_widget.hide()
            
        self.update_view()
        self.setFocus() # Grab focus for arrow keys

    def update_view(self):
        if not self.pairs:
            self.image_label.setText("No image-label pairs found in dataset.")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.info_label.setText("")
            return
            
        self.prev_btn.setEnabled(self.current_idx > 0)
        self.next_btn.setEnabled(self.current_idx < len(self.pairs) - 1)
        
        img_path, label_path = self.pairs[self.current_idx]
        self.info_label.setText(f"{self.current_idx + 1} / {len(self.pairs)}\n{os.path.basename(img_path)}")
        
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            self.image_label.setText(f"Failed to load image: {os.path.basename(img_path)}")
            return
            
        # Draw annotations
        boxes = dataset_parser.parse_yolo_boxes_raw(label_path)
        if boxes:
            painter = QPainter(pixmap)
            font = QFont("Arial", max(10, pixmap.width() // 80), QFont.Weight.Bold)
            painter.setFont(font)
            
            img_w, img_h = pixmap.width(), pixmap.height()
            
            # Generate some consistent colors based on class ID
            colors = [
                QColor(255, 0, 0), QColor(0, 255, 0), QColor(0, 0, 255),
                QColor(255, 255, 0), QColor(0, 255, 255), QColor(255, 0, 255),
                QColor(255, 128, 0), QColor(128, 0, 255), QColor(0, 255, 128)
            ]
            
            for class_id, xc, yc, w, h in boxes:
                color = colors[class_id % len(colors)]
                pen = QPen(color, max(2, img_w // 200)) # Scale line width
                painter.setPen(pen)
                
                # Convert YOLO to pixel coordinates
                # If width or height is > 1.1, assume coordinates are already absolute
                if w > 1.1 or h > 1.1 or xc > 1.1 or yc > 1.1:
                    x_min = int(xc - w / 2)
                    y_min = int(yc - h / 2)
                    box_w = int(w)
                    box_h = int(h)
                else:
                    x_min = int((xc - w / 2) * img_w)
                    y_min = int((yc - h / 2) * img_h)
                    box_w = int(w * img_w)
                    box_h = int(h * img_h)
                
                painter.drawRect(x_min, y_min, box_w, box_h)
                
                # Draw label background and text
                class_name = self.class_map.get(class_id, f"cls_{class_id}")
                
                # Simple text background
                text_rect = painter.fontMetrics().boundingRect(class_name)
                text_rect.moveTo(x_min, y_min - text_rect.height() - 2)
                
                if text_rect.y() < 0:
                    text_rect.moveTo(x_min, y_min + 2) # Push down if outside
                
                # Draw background rect
                painter.fillRect(text_rect.adjusted(-2, -2, 2, 2), color)
                
                # Draw text in contrasting color
                painter.setPen(QColor(0, 0, 0) if color.lightness() > 128 else QColor(255, 255, 255))
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, class_name)
                
            painter.end()
            
        # Scale pixmap to fit label while keeping aspect ratio
        scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.pairs:
            self.update_view() # Redraw scaled image on resize

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self.show_prev()
        elif event.key() == Qt.Key.Key_Right:
            self.show_next()
        else:
            super().keyPressEvent(event)

    def show_prev(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self.update_view()

    def show_next(self):
        if self.current_idx < len(self.pairs) - 1:
            self.current_idx += 1
            self.update_view()

    def accept_current(self):
        if not self.pairs or self.current_idx >= len(self.pairs):
            return
        img_path, label_path = self.pairs[self.current_idx]
        self.parent_window.accept_single(img_path, label_path)

    def redo_current(self):
        if not self.pairs or self.current_idx >= len(self.pairs):
            return
        img_path, label_path = self.pairs[self.current_idx]
        self.parent_window.redo_single(img_path, label_path)


class DatasetCounterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dataset Class Counter & Viewer")
        self.resize(1000, 600)
        self.setStyleSheet(ModernUI.STYLESHEET)
        
        self.dir_path = None
        self.yaml_path = None
        
        # Central Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.splitter)
        
        # Left: Viewer Tab Widget
        self.viewer_tabs = QTabWidget(self)
        self.splitter.addWidget(self.viewer_tabs)
        
        self.original_viewer = ImageViewerWidget(self, self)
        self.augmented_viewer = ImageViewerWidget(self, self)
        
        self.viewer_tabs.addTab(self.original_viewer, "Original Images")
        
        # Right: Tabbed Panel
        self.right_panel = QTabWidget(self)
        self.splitter.addWidget(self.right_panel)
        
        # Set initial sizes (e.g., 60% viewer, 40% panel)
        self.splitter.setSizes([600, 400])
        
        self.setup_controls_tab()
        self.setup_counts_tab()
        self.setup_augmentation_tab()

    def setup_controls_tab(self):
        controls_tab = QWidget()
        layout = QVBoxLayout(controls_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title Label
        title_label = QLabel("Dataset Setup")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title_label)
        
        # Path Label
        self.path_label = QLabel("No dataset selected")
        self.path_label.setStyleSheet("color: #777777;")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        # YAML Path Label
        self.yaml_label = QLabel("No YAML selected")
        self.yaml_label.setStyleSheet("color: #777777;")
        self.yaml_label.setWordWrap(True)
        layout.addWidget(self.yaml_label)
        
        # Select Button
        self.select_btn = QPushButton("Select Dataset Directory")
        self.select_btn.clicked.connect(self.select_directory)
        layout.addWidget(self.select_btn)

        # Select YAML Button
        self.yaml_btn = QPushButton("Select YAML File")
        self.yaml_btn.clicked.connect(self.select_yaml)
        layout.addWidget(self.yaml_btn)
        
        layout.addStretch() # Push everything up
        
        # Convert Button (Bottom)
        self.convert_btn = QPushButton("Convert to YOLOv8")
        self.convert_btn.clicked.connect(self.convert_labels)
        self.convert_btn.setEnabled(False)
        self.convert_btn.setStyleSheet("""
            QPushButton { background-color: #ffe0e0; border-color: #ffcccc; color: #cc0000; }
            QPushButton:hover { background-color: #ffcccc; }
            QPushButton:disabled { background-color: #fafafa; color: #a0a0a0; border-color: #dcdcdc; }
        """)
        layout.addWidget(self.convert_btn)
        
        self.right_panel.addTab(controls_tab, "Controls")

    def setup_counts_tab(self):
        counts_tab = QWidget()
        layout = QVBoxLayout(counts_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Class Name", "Count"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 100)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("alternate-background-color: #fafafa;")
        layout.addWidget(self.table)
        
        self.right_panel.addTab(counts_tab, "Class Counts")

    def setup_augmentation_tab(self):
        aug_tab = QWidget()
        layout = QVBoxLayout(aug_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title Label
        title_label = QLabel("Offline Dataset Balancing")
        title_label.setObjectName("titleLabel")
        layout.addWidget(title_label)
        
        # 1. Normal Controls Container Widget
        self.norm_controls_widget = QWidget()
        norm_layout = QVBoxLayout(self.norm_controls_widget)
        norm_layout.setContentsMargins(0, 0, 0, 0)
        norm_layout.setSpacing(15)
        
        info = QLabel("Select minority classes below and specify how many new instances you want to generate. "
                      "The tool will automatically copy and paste objects across images to balance your dataset safely.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #555555;")
        norm_layout.addWidget(info)
        
        norm_layout.addWidget(QLabel("Select Classes to Augment:"))
        self.class_list_widget = QListWidget()
        self.class_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.class_list_widget.setStyleSheet("background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 4px;")
        norm_layout.addWidget(self.class_list_widget)
        
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("Target count (per selected class):"))
        self.target_spinbox = QSpinBox()
        self.target_spinbox.setRange(1, 10000)
        self.target_spinbox.setValue(100)
        count_layout.addWidget(self.target_spinbox)
        
        self.autobalance_btn = QPushButton("Auto-Balance")
        self.autobalance_btn.setToolTip("Automatically sets target to the highest class count")
        self.autobalance_btn.clicked.connect(self.auto_balance)
        count_layout.addWidget(self.autobalance_btn)
        norm_layout.addLayout(count_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        norm_layout.addWidget(self.progress_bar)
        
        self.run_aug_btn = QPushButton("Run Copy-Paste Augmentation")
        self.run_aug_btn.clicked.connect(self.run_augmentation)
        self.run_aug_btn.setEnabled(False)
        self.run_aug_btn.setStyleSheet("""
            QPushButton { background-color: #e0ffe0; border-color: #ccffcc; color: #008800; }
            QPushButton:hover { background-color: #ccffcc; }
            QPushButton:disabled { background-color: #fafafa; color: #a0a0a0; border-color: #dcdcdc; }
        """)
        norm_layout.addWidget(self.run_aug_btn)
        
        layout.addWidget(self.norm_controls_widget)
        
        # 2. Review Controls Container Widget
        self.review_controls_widget = QWidget()
        review_layout = QVBoxLayout(self.review_controls_widget)
        review_layout.setContentsMargins(0, 0, 0, 0)
        review_layout.setSpacing(15)
        
        review_title = QLabel("Staged Augmentation Review")
        review_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #333333;")
        review_layout.addWidget(review_title)
        
        self.review_status_label = QLabel("Reviewing Staged Images...")
        self.review_status_label.setStyleSheet("color: #666666;")
        review_layout.addWidget(self.review_status_label)
        
        self.accept_all_btn = QPushButton("Accept All Staged")
        self.accept_all_btn.setStyleSheet("background-color: #e0ffe0; color: #008800; font-weight: bold; border-color: #ccffcc; padding: 10px;")
        self.accept_all_btn.clicked.connect(self.accept_all_staged)
        review_layout.addWidget(self.accept_all_btn)
        
        self.reject_all_btn = QPushButton("Reject All Staged")
        self.reject_all_btn.setStyleSheet("background-color: #ffe0e0; color: #cc0000; font-weight: bold; border-color: #ffcccc; padding: 10px;")
        self.reject_all_btn.clicked.connect(self.reject_all_staged)
        review_layout.addWidget(self.reject_all_btn)
        
        review_layout.addStretch()
        layout.addWidget(self.review_controls_widget)
        self.review_controls_widget.hide() # Hidden by default
        
        self.right_panel.addTab(aug_tab, "Augmentation")
        self.current_counts = {}

    def auto_balance(self):
        if self.current_counts:
            max_val = max(self.current_counts.values())
            self.target_spinbox.setValue(max_val)

    def select_directory(self):
        options = QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontUseNativeDialog
        dir_path = QFileDialog.getExistingDirectory(self, "Select Dataset Directory", "", options)
        if dir_path:
            self.dir_path = dir_path
            self.path_label.setText(f"Dataset: {dir_path}")
            self.process_dataset()

    def select_yaml(self):
        options = QFileDialog.Option.DontUseNativeDialog
        yaml_path, _ = QFileDialog.getOpenFileName(self, "Select YAML File", "", "YAML Files (*.yaml *.yml)", options=options)
        if yaml_path:
            self.yaml_path = yaml_path
            self.yaml_label.setText(f"YAML: {os.path.basename(yaml_path)}")
            self.process_dataset()
            
    def process_dataset(self):
        if not self.dir_path:
            return

        counts = dataset_parser.parse_dataset(self.dir_path, self.yaml_path)
        self.current_counts = counts
        
        self.table.setRowCount(0)
        self.class_list_widget.clear()
        
        for row, (class_name, count) in enumerate(sorted(counts.items())):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(class_name)))
            
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, count_item)
            
            # Find class_id from class_map
            class_id = None
            for cid, name in dataset_parser.load_classes(self.yaml_path).items():
                if name == class_name:
                    class_id = cid
                    break
            if class_id is None:
                class_id = class_name # Fallback
                
            item = QListWidgetItem(f"{class_name} (Current: {count})")
            item.setData(Qt.ItemDataRole.UserRole, class_id)
            self.class_list_widget.addItem(item)
            
        if not counts:
            self.path_label.setText(f"Dataset: {self.dir_path} (No valid labels found)")
            self.convert_btn.setEnabled(False)
            self.run_aug_btn.setEnabled(False)
        else:
            self.convert_btn.setEnabled(True)
            self.run_aug_btn.setEnabled(True)
            # Load images into viewer
            pairs = dataset_parser.get_image_label_pairs(self.dir_path)
            class_map = dataset_parser.load_classes(self.yaml_path)
            
            # Check staging folder
            staging_images_dir = os.path.join(self.dir_path, '.aug_staging', 'images')
            staging_labels_dir = os.path.join(self.dir_path, '.aug_staging', 'labels')
            
            augmented_pairs = []
            is_staged = False
            
            if os.path.exists(staging_images_dir):
                staged_files = [f for f in os.listdir(staging_images_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                if staged_files:
                    is_staged = True
                    for f in sorted(staged_files):
                        img_p = os.path.join(staging_images_dir, f)
                        lbl_p = os.path.join(staging_labels_dir, os.path.splitext(f)[0] + '.txt')
                        augmented_pairs.append((img_p, lbl_p))
            
            # If no staged files under review, look for finalized augmented files in the main dataset
            if not augmented_pairs:
                augmented_pairs = [p for p in pairs if "_aug_" in os.path.basename(p[0])]
                
            # Filter original pairs from the main dataset
            original_pairs = [p for p in pairs if "_aug_" not in os.path.basename(p[0])]
            
            # Load original
            self.original_viewer.load_dataset(original_pairs, class_map, is_staged=False)
            
            # Control right panel layouts based on staging status
            if is_staged:
                self.norm_controls_widget.hide()
                self.review_controls_widget.show()
                self.review_status_label.setText(f"Reviewing {len(augmented_pairs)} Staged Images")
            else:
                self.norm_controls_widget.show()
                self.review_controls_widget.hide()
            
            # Handle augmented tab dynamically
            has_augmented_tab = False
            augmented_tab_index = -1
            for idx in range(self.viewer_tabs.count()):
                if self.viewer_tabs.tabText(idx) == "Augmented Images":
                    has_augmented_tab = True
                    augmented_tab_index = idx
                    break
                    
            if augmented_pairs:
                self.augmented_viewer.load_dataset(augmented_pairs, class_map, is_staged=is_staged)
                if not has_augmented_tab:
                    self.viewer_tabs.addTab(self.augmented_viewer, "Augmented Images")
                    augmented_tab_index = self.viewer_tabs.count() - 1
                
                # Switch to "Augmented Images" tab automatically if review active or newly run
                if is_staged or self.right_panel.currentIndex() == 2:
                    self.viewer_tabs.setCurrentIndex(augmented_tab_index)
            else:
                if has_augmented_tab:
                    self.viewer_tabs.removeTab(augmented_tab_index)
            
    def convert_labels(self):
        if not self.dir_path:
            return
            
        reply = QMessageBox.question(self, 'Confirm Conversion',
                                     "This will OVERWRITE your existing .txt files to strictly enforce YOLOv8 format.\n\n"
                                     "Are you sure you want to proceed? Please ensure you have a backup.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
                                     
        if reply == QMessageBox.StandardButton.Yes:
            self.convert_btn.setEnabled(False)
            self.convert_btn.setText("Converting...")
            QApplication.processEvents() # Force UI update
            
            converted, errors = dataset_parser.convert_labels_to_yolov8(self.dir_path)
            
            self.convert_btn.setText("Convert to YOLOv8")
            self.convert_btn.setEnabled(True)
            
            QMessageBox.information(self, 'Conversion Complete',
                                    f"Successfully converted {converted} files.\n"
                                    f"Errors encountered: {errors}\n\n"
                                    "Your tables and image views will now use the normalized coordinates.")
            
            self.process_dataset()

    def run_augmentation(self):
        if not self.dir_path:
            return
            
        selected_items = self.class_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select at least one class to augment.")
            return
            
        target_counts = {}
        target_value = self.target_spinbox.value()
        for item in selected_items:
            class_id = item.data(Qt.ItemDataRole.UserRole)
            target_counts[class_id] = target_value
            
        reply = QMessageBox.question(self, 'Confirm Augmentation',
                                     f"This will safely generate {target_value * len(target_counts)} new images using Copy-Paste augmentation.\n\n"
                                     "Do you want to proceed?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
                                     
        if reply == QMessageBox.StandardButton.Yes:
            self.run_aug_btn.setEnabled(False)
            self.progress_bar.setValue(0)
            
            def update_progress(msg, val):
                self.progress_bar.setValue(val)
                self.progress_bar.setFormat(f"{msg} %p%")
                QApplication.processEvents()
                
            QApplication.processEvents()
            
            try:
                generated = augmenter.generate_augmented_images(self.dir_path, target_counts, update_progress)
                self.progress_bar.setValue(100)
                self.progress_bar.setFormat(f"Completed! %p%")
                
                QMessageBox.information(self, 'Augmentation Complete',
                                        f"Successfully generated {generated} new augmented images for review!\n\n"
                                        "Please inspect them in the 'Augmented Images' tab.")
                self.process_dataset() # Refresh counts
            except Exception as e:
                QMessageBox.critical(self, 'Error', f"Augmentation failed:\n{str(e)}")
            finally:
                self.run_aug_btn.setEnabled(True)

    def accept_single(self, img_path, label_path):
        if not self.dir_path:
            return
            
        # Ensure main directories exist
        dest_images_dir = os.path.join(self.dir_path, 'images')
        dest_labels_dir = os.path.join(self.dir_path, 'labels')
        os.makedirs(dest_images_dir, exist_ok=True)
        os.makedirs(dest_labels_dir, exist_ok=True)
        
        # Move files
        dest_img_path = os.path.join(dest_images_dir, os.path.basename(img_path))
        dest_label_path = os.path.join(dest_labels_dir, os.path.basename(label_path))
        
        try:
            shutil.move(img_path, dest_img_path)
            shutil.move(label_path, dest_label_path)
            
            # If staging is now empty, delete staging folder
            staging_dir = os.path.join(self.dir_path, '.aug_staging')
            staged_images_dir = os.path.join(staging_dir, 'images')
            staged_files = os.listdir(staged_images_dir) if os.path.exists(staged_images_dir) else []
            if not staged_files and os.path.exists(staging_dir):
                shutil.rmtree(staging_dir)
                
            self.process_dataset() # Reload dataset to update tables
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to commit file:\n{str(e)}")

    def redo_single(self, img_path, label_path):
        if not self.dir_path:
            return
            
        try:
            success = augmenter.generate_single_replacement(self.dir_path, img_path, label_path)
            if success:
                # Force reload of image viewer for augmented
                self.augmented_viewer.update_view()
            else:
                QMessageBox.warning(self, "Redo Failed", "Failed to generate a new replacement image. Try again.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Redo operation failed:\n{str(e)}")

    def accept_all_staged(self):
        if not self.dir_path:
            return
            
        staging_dir = os.path.join(self.dir_path, '.aug_staging')
        staged_images_dir = os.path.join(staging_dir, 'images')
        staged_labels_dir = os.path.join(staging_dir, 'labels')
        
        if not os.path.exists(staged_images_dir):
            return
            
        dest_images_dir = os.path.join(self.dir_path, 'images')
        dest_labels_dir = os.path.join(self.dir_path, 'labels')
        os.makedirs(dest_images_dir, exist_ok=True)
        os.makedirs(dest_labels_dir, exist_ok=True)
        
        staged_images = [f for f in os.listdir(staged_images_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        
        if not staged_images:
            return
            
        # Move all staged files to main dataset
        for f in staged_images:
            shutil.move(os.path.join(staged_images_dir, f), os.path.join(dest_images_dir, f))
            lbl_name = os.path.splitext(f)[0] + '.txt'
            staged_lbl = os.path.join(staged_labels_dir, lbl_name)
            if os.path.exists(staged_lbl):
                shutil.move(staged_lbl, os.path.join(dest_labels_dir, lbl_name))
                
        # Clean staging directory
        shutil.rmtree(staging_dir)
        
        QMessageBox.information(self, "Success", f"Successfully committed all {len(staged_images)} staged images!")
        self.process_dataset()

    def reject_all_staged(self):
        if not self.dir_path:
            return
            
        reply = QMessageBox.question(self, 'Confirm Reject All',
                                     "Are you sure you want to REJECT and DELETE all staged augmented images?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
                                     
        if reply == QMessageBox.StandardButton.Yes:
            staging_dir = os.path.join(self.dir_path, '.aug_staging')
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir)
            self.process_dataset()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = DatasetCounterApp()
    window.show()
    sys.exit(app.exec())
