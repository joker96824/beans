import sys
import json
import warnings
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QFileDialog,
                           QVBoxLayout, QHBoxLayout, QWidget, QLabel, QLineEdit,
                           QScrollArea, QDesktopWidget, QComboBox, QRadioButton,
                           QButtonGroup)
from PyQt5.QtGui import QPixmap, QImage, QPainter, QFont, QWheelEvent, QMouseEvent
from PyQt5.QtCore import Qt, QSize
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# 忽略 PyQt5 的废弃警告
warnings.filterwarnings("ignore", category=DeprecationWarning)

class ColorBlock:
    """单个色块类"""
    def __init__(self, x, y, color_code, original_color_code):
        self.x = x  # 色块在网格中的X坐标
        self.y = y  # 色块在网格中的Y坐标
        self.color_code = color_code  # 当前颜色代码
        self.original_color_code = original_color_code  # 原始颜色代码
        self.pixmap = None  # 缓存的色块图像
        self.modified = False  # 是否被修改过
        
    def update_color(self, new_color_code):
        """更新色块颜色"""
        self.color_code = new_color_code
        self.modified = True
        self.pixmap = None  # 清除缓存，需要重新生成

class ImageGrid:
    """图片网格管理类"""
    def __init__(self, width, height, block_size=20, axis_size=30):
        self.width = width  # 网格宽度
        self.height = height  # 网格高度
        self.block_size = block_size  # 色块大小
        self.axis_size = axis_size  # 坐标轴区域大小
        self.blocks = {}  # 存储所有色块 {(x,y): ColorBlock}
        self.background_pixmap = None  # 背景图像（坐标轴、统计等）
        self.composite_pixmap = None  # 合成后的显示图像
        self.show_color_codes = True  # 是否显示色号
        
    def add_block(self, x, y, color_code, original_color_code):
        """添加色块"""
        self.blocks[(x, y)] = ColorBlock(x, y, color_code, original_color_code)
        
    def update_block_color(self, x, y, new_color_code):
        """更新色块颜色"""
        if (x, y) in self.blocks:
            self.blocks[(x, y)].update_color(new_color_code)
            return True
        return False
        
    def get_block_color(self, x, y):
        """获取色块颜色"""
        if (x, y) in self.blocks:
            return self.blocks[(x, y)].color_code
        return None
        
    def get_modified_blocks(self):
        """获取所有修改过的色块"""
        return [(x, y) for (x, y), block in self.blocks.items() if block.modified]
        
    def reset_modifications(self):
        """重置所有修改标记"""
        for block in self.blocks.values():
            block.modified = False

class ZoomableLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.zoom_factor = 1.0
        self.original_pixmap = None
        self.parent_window = None  # 存储父窗口引用
        
    def setPixmap(self, pixmap):
        self.original_pixmap = pixmap
        self._update_pixmap()
        
    def setParentWindow(self, parent):
        """设置父窗口引用"""
        self.parent_window = parent
        
    def wheelEvent(self, event: QWheelEvent):
        if self.original_pixmap:
            # 获取鼠标滚轮的delta
            delta = event.angleDelta().y()
            
            # 根据滚轮方向调整缩放因子
            if delta > 0:
                self.zoom_factor *= 1.1  # 放大10%
            else:
                self.zoom_factor *= 0.9  # 缩小10%
                
            # 限制缩放范围
            self.zoom_factor = max(0.1, min(5.0, self.zoom_factor))
            
            self._update_pixmap()
            
    def mousePressEvent(self, event: QMouseEvent):
        """处理鼠标点击事件"""
        if self.parent_window and self.parent_window.brush_mode:
            # 计算点击位置对应的图片坐标
            self.parent_window.handle_brush_click(event.pos())
        else:
            super().mousePressEvent(event)
            
    def _update_pixmap(self):
        if self.original_pixmap:
            # 计算新的尺寸
            new_size = self.original_pixmap.size() * self.zoom_factor
            # 保持纵横比缩放
            scaled_pixmap = self.original_pixmap.scaled(
                new_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            super().setPixmap(scaled_pixmap)

class ColorMatcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Color Matcher')
        
        # 获取屏幕尺寸并设置窗口全屏
        screen = QDesktopWidget().screenGeometry()
        self.setGeometry(0, 0, screen.width(), screen.height())
        
        # 初始化颜色匹配方法
        self.matching_methods = {
            'RGB欧氏距离': self.find_closest_color_rgb,
            'LAB色彩空间': self.find_closest_color_lab,
            'HSV加权': self.find_closest_color_hsv_weighted
        }
        self.current_method = 'LAB色彩空间'
        
        # 初始化颜色数据
        self.color_sources = {'自选颜色': 'sample.json'}
        self.load_color_sources()
        self.current_source = '自选颜色'
        
        # 色号显示控制
        self.show_color_codes = True
        
        # 颜色替换功能
        self.color_replacement = {}  # 存储颜色替换映射
        self.replacement_history = []  # 存储替换历史，用于撤销
        
        # 图片处理控制
        self.processed_image = None  # 存储处理后的图片
        
        # 画笔功能
        self.brush_mode = False  # 画笔模式开关
        self.selected_brush_color = None  # 选中的画笔颜色
        self.brush_changes = []  # 存储画笔修改历史，用于撤销
        
        # 图片网格管理
        self.image_grid = None  # 图片网格管理器
        self.block_size = 20  # 色块大小
        self.axis_size = 30  # 坐标轴区域大小
        
        self.init_ui()
        
    def load_color_sources(self):
        """加载color目录下的所有颜色源"""
        if os.path.exists('color'):
            for file in os.listdir('color'):
                if file.endswith('.json'):
                    name = file.split('.')[0]
                    self.color_sources[name] = os.path.join('color', file)
    
    def load_color_data(self, source_name):
        """根据选择的源加载颜色数据"""
        file_path = self.color_sources[source_name]
        with open(file_path, 'r') as f:
            data = json.load(f)
            
        # 保存原始数据
        self.color_data = data
            
        if source_name == '自选颜色':
            # 原有格式处理
            self.color_lookup = {k: np.array(v['rgb']) for k, v in data.items() 
                               if not v.get('is_placeholder', False)}
        else:
            # 新格式处理（十六进制颜色代码）
            self.color_lookup = {}
            for item in data['data']:
                hex_color = item['color'].lstrip('#')
                rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
                self.color_lookup[item['colorCode']] = np.array(rgb)
    
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 顶部控制区域
        control_layout = QHBoxLayout()
        
        # 左侧按钮和控制区域
        left_control = QVBoxLayout()
        
        # 颜色源选择
        source_group = QButtonGroup(self)
        source_layout = QHBoxLayout()
        source_label = QLabel('颜色数据源：')
        source_layout.addWidget(source_label)
        
        for i, source_name in enumerate(self.color_sources.keys()):
            radio = QRadioButton(source_name)
            if source_name == self.current_source:
                radio.setChecked(True)
            radio.toggled.connect(lambda checked, name=source_name: 
                                self.on_source_changed(name) if checked else None)
            source_group.addButton(radio)
            source_layout.addWidget(radio)
        
        left_control.addLayout(source_layout)
        
        # 加载和处理按钮
        btn_layout = QHBoxLayout()
        self.load_btn = QPushButton('加载图片', self)
        self.load_btn.clicked.connect(self.load_image)
        btn_layout.addWidget(self.load_btn)
        
        self.process_btn = QPushButton('处理图片', self)
        self.process_btn.clicked.connect(self.process_image)
        self.process_btn.setEnabled(False)
        btn_layout.addWidget(self.process_btn)
        
        # 保存按钮
        self.save_btn = QPushButton('保存图片', self)
        self.save_btn.clicked.connect(self.save_image)
        self.save_btn.setEnabled(False)
        btn_layout.addWidget(self.save_btn)
        
        # 色号显示控制按钮
        self.show_codes_btn = QPushButton('隐藏色号', self)
        self.show_codes_btn.setCheckable(True)
        self.show_codes_btn.clicked.connect(self.toggle_color_codes)
        btn_layout.addWidget(self.show_codes_btn)
        
        # 颜色替换控制按钮
        self.replace_colors_btn = QPushButton('颜色替换', self)
        self.replace_colors_btn.clicked.connect(self.show_color_replacement_dialog)
        btn_layout.addWidget(self.replace_colors_btn)
        
        # 撤销替换按钮
        self.undo_replacement_btn = QPushButton('撤销替换', self)
        self.undo_replacement_btn.clicked.connect(self.undo_last_replacement)
        self.undo_replacement_btn.setEnabled(False)
        btn_layout.addWidget(self.undo_replacement_btn)
        
        # 画笔功能按钮
        self.brush_btn = QPushButton('画笔模式', self)
        self.brush_btn.setCheckable(True)
        self.brush_btn.clicked.connect(self.toggle_brush_mode)
        btn_layout.addWidget(self.brush_btn)
        
        # 撤销画笔按钮
        self.undo_brush_btn = QPushButton('撤销画笔', self)
        self.undo_brush_btn.clicked.connect(self.undo_last_brush_change)
        self.undo_brush_btn.setEnabled(False)
        btn_layout.addWidget(self.undo_brush_btn)
        
        left_control.addLayout(btn_layout)
        
        # 匹配方法选择
        method_layout = QHBoxLayout()
        method_label = QLabel('颜色匹配方法：')
        self.method_combo = QComboBox()
        self.method_combo.addItems(list(self.matching_methods.keys()))
        self.method_combo.setCurrentText(self.current_method)
        method_layout.addWidget(method_label)
        method_layout.addWidget(self.method_combo)
        left_control.addLayout(method_layout)
        
        # 新颜色输入控件（仅在自选颜色模式下显示）
        self.color_input_widget = QWidget()
        color_input_layout = QHBoxLayout(self.color_input_widget)
        self.color_code = QLineEdit(self)
        self.color_code.setPlaceholderText('颜色代码 (例: A1)')
        color_input_layout.addWidget(self.color_code)
        
        self.r_value = QLineEdit(self)
        self.r_value.setPlaceholderText('R (0-255)')
        color_input_layout.addWidget(self.r_value)
        
        self.g_value = QLineEdit(self)
        self.g_value.setPlaceholderText('G (0-255)')
        color_input_layout.addWidget(self.g_value)
        
        self.b_value = QLineEdit(self)
        self.b_value.setPlaceholderText('B (0-255)')
        color_input_layout.addWidget(self.b_value)
        
        self.add_color_btn = QPushButton('添加新颜色', self)
        self.add_color_btn.clicked.connect(self.add_new_color)
        color_input_layout.addWidget(self.add_color_btn)
        
        left_control.addWidget(self.color_input_widget)
        control_layout.addLayout(left_control)
        
        main_layout.addLayout(control_layout)
        
        # 图片显示区域 (3:7分割)
        image_container = QWidget()
        image_layout = QHBoxLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        
        # 左侧原始图片区域 (3)
        left_container = QWidget()
        left_container.setFixedWidth(int(self.width() * 0.3))
        left_layout = QVBoxLayout(left_container)
        self.original_image_label = QLabel('原始图片')
        self.original_image_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.original_image_label)
        image_layout.addWidget(left_container)
        
        # 右侧处理后图片区域 (7)
        right_container = QWidget()
        right_container.setFixedWidth(int(self.width() * 0.7))
        right_layout = QVBoxLayout(right_container)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.processed_image_label = ZoomableLabel('处理后图片')
        self.processed_image_label.setAlignment(Qt.AlignCenter)
        self.processed_image_label.setParentWindow(self)  # 设置父窗口引用
        scroll_area.setWidget(self.processed_image_label)
        
        right_layout.addWidget(scroll_area)
        image_layout.addWidget(right_container)
        
        main_layout.addWidget(image_container)
        
        # 状态标签
        self.status_label = QLabel('')
        main_layout.addWidget(self.status_label)
        
        # 加载初始颜色数据
        self.load_color_data(self.current_source)

    def on_source_changed(self, source_name):
        """处理颜色源改变事件"""
        self.current_source = source_name
        self.load_color_data(source_name)
        
        # 控制新颜色输入控件的显示/隐藏
        self.color_input_widget.setVisible(source_name == '自选颜色')
        
        # 更新状态
        self.status_label.setText(f'已切换到颜色源: {source_name}')
        
        # 清空颜色替换历史
        self.color_replacement.clear()
        self.replacement_history.clear()
        self.undo_replacement_btn.setEnabled(False)
        
        # 清空画笔修改历史
        self.brush_changes.clear()
        self.undo_brush_btn.setEnabled(False)
        self.brush_mode = False
        self.brush_btn.setChecked(False)
        self.brush_btn.setText('画笔模式')
        self.brush_btn.setStyleSheet("")
        
        # 清空图片网格
        self.image_grid = None

    def toggle_color_codes(self):
        """切换色号显示状态"""
        self.show_color_codes = not self.show_color_codes
        if self.show_color_codes:
            self.show_codes_btn.setText('隐藏色号')
        else:
            self.show_codes_btn.setText('显示色号')
        
        # 如果有图片网格，则更新所有色块显示
        if self.image_grid:
            self.image_grid.show_color_codes = self.show_color_codes
            self.update_all_blocks_display()
            # 更新统计区域
            self.update_statistics_display()

    def show_color_replacement_dialog(self):
        """显示颜色替换对话框"""
        if not hasattr(self, 'image_path') or not self.image_path:
            self.status_label.setText('请先加载并处理图片！')
            return
            
        # 创建对话框
        dialog = QWidget()
        dialog.setWindowTitle('颜色替换')
        dialog.setFixedSize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        # 说明文字
        info_label = QLabel('选择要替换的颜色和目标颜色：')
        layout.addWidget(info_label)
        
        # 源颜色选择
        source_layout = QHBoxLayout()
        source_label = QLabel('源颜色：')
        source_combo = QComboBox()
        source_combo.setEditable(True)  # 允许编辑
        source_combo.addItems(list(self.color_lookup.keys()))
        source_layout.addWidget(source_label)
        source_layout.addWidget(source_combo)
        layout.addLayout(source_layout)
        
        # 目标颜色选择（支持手动输入）
        target_layout = QHBoxLayout()
        target_label = QLabel('目标颜色：')
        target_combo = QComboBox()
        target_combo.setEditable(True)  # 允许编辑
        target_combo.addItems(list(self.color_lookup.keys()))
        target_layout.addWidget(target_label)
        target_layout.addWidget(target_combo)
        layout.addLayout(target_layout)
        
        # 预览区域
        preview_label = QLabel('预览：')
        layout.addWidget(preview_label)
        
        preview_widget = QWidget()
        preview_widget.setFixedHeight(60)
        preview_widget.setStyleSheet("background-color: white; border: 1px solid black;")
        preview_layout = QHBoxLayout(preview_widget)
        
        # 源颜色预览
        source_preview = QLabel()
        source_preview.setFixedSize(40, 40)
        source_preview.setStyleSheet(f"background-color: rgb({self.color_lookup[source_combo.currentText()][0]}, {self.color_lookup[source_combo.currentText()][1]}, {self.color_lookup[source_combo.currentText()][2]}); border: 1px solid black;")
        source_preview.setText(source_combo.currentText())
        source_preview.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(source_preview)
        
        # 箭头
        arrow_label = QLabel('→')
        arrow_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(arrow_label)
        
        # 目标颜色预览
        target_preview = QLabel()
        target_preview.setFixedSize(40, 40)
        target_preview.setStyleSheet("background-color: white; border: 1px solid black;")
        target_preview.setText('?')
        target_preview.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(target_preview)
        
        layout.addWidget(preview_widget)
        
        # 更新预览的函数
        def update_preview():
            source_text = source_combo.currentText()
            target_text = target_combo.currentText()
            
            # 检查源颜色是否存在
            if source_text in self.color_lookup:
                source_color = self.color_lookup[source_text]
                source_preview.setStyleSheet(f"background-color: rgb({source_color[0]}, {source_color[1]}, {source_color[2]}); border: 1px solid black;")
                source_preview.setText(source_text)
            else:
                source_preview.setStyleSheet("background-color: white; border: 1px solid red;")
                source_preview.setText('无效')
            
            # 检查目标颜色是否存在
            if target_text in self.color_lookup:
                target_color = self.color_lookup[target_text]
                target_preview.setStyleSheet(f"background-color: rgb({target_color[0]}, {target_color[1]}, {target_color[2]}); border: 1px solid black;")
                target_preview.setText(target_text)
            else:
                target_preview.setStyleSheet("background-color: white; border: 1px solid red;")
                target_preview.setText('无效')
        
        source_combo.currentTextChanged.connect(update_preview)
        target_combo.currentTextChanged.connect(update_preview)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        apply_btn = QPushButton('应用替换')
        apply_btn.clicked.connect(lambda: self.apply_color_replacement(source_combo.currentText(), target_combo.currentText(), dialog))
        button_layout.addWidget(apply_btn)
        
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(dialog.close)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # 显示对话框
        dialog.show()

    def apply_color_replacement(self, source_color, target_color, dialog):
        """应用颜色替换（优化版本）"""
        if source_color == target_color:
            self.status_label.setText('源颜色和目标颜色不能相同！')
            return
            
        # 验证源颜色是否存在
        if source_color not in self.color_lookup:
            self.status_label.setText(f'源颜色 {source_color} 不存在！')
            return
            
        # 验证目标颜色是否存在
        if target_color not in self.color_lookup:
            self.status_label.setText(f'目标颜色 {target_color} 不存在！')
            return
            
        # 保存当前状态到历史记录
        current_state = self.color_replacement.copy()
        self.replacement_history.append(current_state)
        
        # 添加替换映射
        self.color_replacement[source_color] = target_color
        
        # 关闭对话框
        dialog.close()
        
        # 使用优化的替换方法
        self.apply_color_replacement_optimized(source_color, target_color)
        
        # 启用撤销按钮
        self.undo_replacement_btn.setEnabled(True)
        
        self.status_label.setText(f'已将颜色 {source_color} 替换为 {target_color}')

    def apply_color_replacement_optimized(self, source_color, target_color):
        """优化的颜色替换方法"""
        if not self.image_grid:
            return
            
        # 找到所有需要替换的色块
        blocks_to_update = []
        for (x, y), block in self.image_grid.blocks.items():
            if block.color_code == source_color:
                blocks_to_update.append((x, y))
        
        # 批量更新色块
        for x, y in blocks_to_update:
            self.image_grid.update_block_color(x, y, target_color)
        
        # 批量更新显示
        self.batch_update_blocks_display(blocks_to_update)
        
        # 更新统计区域
        self.update_statistics_display()

    def batch_update_blocks_display(self, blocks_to_update):
        """批量更新色块显示"""
        if not self.image_grid or not blocks_to_update:
            return
            
        # 重新生成需要更新的色块图像
        for x, y in blocks_to_update:
            if (x, y) in self.image_grid.blocks:
                block = self.image_grid.blocks[(x, y)]
                block.pixmap = self.generate_block_pixmap(block, self.color_lookup, self.show_color_codes)
        
        # 更新合成图像
        if self.image_grid.composite_pixmap:
            painter = QPainter(self.image_grid.composite_pixmap)
            
            # 绘制所有更新的色块
            for x, y in blocks_to_update:
                if (x, y) in self.image_grid.blocks:
                    block = self.image_grid.blocks[(x, y)]
                    if block.pixmap:
                        display_x = x * self.block_size + self.axis_size
                        display_y = y * self.block_size + self.axis_size
                        painter.drawPixmap(display_x, display_y, block.pixmap)
            
            painter.end()
            
            # 更新显示
            self.processed_image_label.setPixmap(self.image_grid.composite_pixmap)

    def update_statistics_display(self):
        """更新统计区域显示"""
        if not self.image_grid:
            return
            
        # 计算当前的颜色统计
        color_statistics = {}
        for block in self.image_grid.blocks.values():
            color_code = block.color_code
            if color_code:
                color_statistics[color_code] = color_statistics.get(color_code, 0) + 1
        
        # 重新生成背景图像（包含更新的统计）
        base_width = self.image_grid.width * self.block_size + self.axis_size
        base_height = self.image_grid.height * self.block_size + self.axis_size
        
        self.image_grid.background_pixmap = self.generate_background_pixmap(
            self.image_grid.width, self.image_grid.height, color_statistics)
        
        # 重新合成显示图像
        self.composite_display_image()

    def get_replaced_color(self, original_color):
        """获取替换后的颜色"""
        return self.color_replacement.get(original_color, original_color)

    def undo_last_replacement(self):
        """撤销上一次颜色替换（优化版本）"""
        if not self.replacement_history:
            self.status_label.setText('没有可撤销的操作！')
            return
            
        # 恢复上一次的状态
        self.color_replacement = self.replacement_history.pop()
        
        # 使用优化的撤销方法
        self.undo_replacement_optimized()
        
        # 如果没有更多历史记录，禁用撤销按钮
        if not self.replacement_history:
            self.undo_replacement_btn.setEnabled(False)
        
        self.status_label.setText('已撤销上一次颜色替换！')

    def undo_replacement_optimized(self):
        """优化的撤销替换方法"""
        if not self.image_grid:
            return
            
        # 重新应用所有当前的颜色替换映射
        blocks_to_update = []
        for (x, y), block in self.image_grid.blocks.items():
            original_color = block.original_color_code
            current_color = self.get_replaced_color(original_color)
            
            # 如果当前颜色与原始颜色不同，需要更新
            if current_color != block.color_code:
                self.image_grid.update_block_color(x, y, current_color)
                blocks_to_update.append((x, y))
        
        # 批量更新显示
        if blocks_to_update:
            self.batch_update_blocks_display(blocks_to_update)
        
        # 更新统计区域
        self.update_statistics_display()

    def toggle_brush_mode(self):
        """切换画笔模式"""
        self.brush_mode = not self.brush_mode
        
        if self.brush_mode:
            self.brush_btn.setText('退出画笔')
            self.brush_btn.setStyleSheet("background-color: lightblue;")
            # 显示颜色选择对话框
            self.show_brush_color_dialog()
        else:
            self.brush_btn.setText('画笔模式')
            self.brush_btn.setStyleSheet("")
            self.selected_brush_color = None

    def show_brush_color_dialog(self):
        """显示画笔颜色选择对话框"""
        if not self.image_grid:
            self.status_label.setText('请先处理图片！')
            self.brush_mode = False
            self.brush_btn.setChecked(False)
            self.brush_btn.setText('画笔模式')
            self.brush_btn.setStyleSheet("")
            return
            
        # 创建对话框
        dialog = QWidget()
        dialog.setWindowTitle('选择画笔颜色')
        dialog.setFixedSize(300, 200)
        
        layout = QVBoxLayout(dialog)
        
        # 说明文字
        info_label = QLabel('请选择画笔颜色：')
        layout.addWidget(info_label)
        
        # 颜色选择下拉框
        color_layout = QHBoxLayout()
        color_label = QLabel('颜色：')
        color_combo = QComboBox()
        color_combo.setEditable(True)  # 允许编辑
        color_combo.addItems(list(self.color_lookup.keys()))
        color_layout.addWidget(color_label)
        color_layout.addWidget(color_combo)
        layout.addLayout(color_layout)
        
        # 颜色预览
        preview_label = QLabel('预览：')
        layout.addWidget(preview_label)
        
        preview_widget = QLabel()
        preview_widget.setFixedSize(60, 60)
        preview_widget.setStyleSheet(f"background-color: rgb({self.color_lookup[color_combo.currentText()][0]}, {self.color_lookup[color_combo.currentText()][1]}, {self.color_lookup[color_combo.currentText()][2]}); border: 2px solid black;")
        preview_widget.setAlignment(Qt.AlignCenter)
        preview_widget.setText(color_combo.currentText())
        layout.addWidget(preview_widget)
        
        # 更新预览的函数
        def update_preview():
            color_text = color_combo.currentText()
            
            # 检查颜色是否存在
            if color_text in self.color_lookup:
                color = self.color_lookup[color_text]
                preview_widget.setStyleSheet(f"background-color: rgb({color[0]}, {color[1]}, {color[2]}); border: 2px solid black;")
                preview_widget.setText(color_text)
            else:
                preview_widget.setStyleSheet("background-color: white; border: 2px solid red;")
                preview_widget.setText('无效')
        
        color_combo.currentTextChanged.connect(update_preview)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        ok_btn = QPushButton('确定')
        ok_btn.clicked.connect(lambda: self.select_brush_color(color_combo.currentText(), dialog))
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(lambda: self.cancel_brush_selection(dialog))
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # 显示对话框
        dialog.show()

    def select_brush_color(self, color_code, dialog):
        """选择画笔颜色"""
        # 验证颜色是否存在
        if color_code not in self.color_lookup:
            self.status_label.setText(f'颜色 {color_code} 不存在！')
            return
            
        self.selected_brush_color = color_code
        dialog.close()
        self.status_label.setText(f'画笔颜色已设置为: {color_code}')

    def cancel_brush_selection(self, dialog):
        """取消画笔颜色选择"""
        dialog.close()
        self.brush_mode = False
        self.brush_btn.setChecked(False)
        self.brush_btn.setText('画笔模式')
        self.brush_btn.setStyleSheet("")
        self.status_label.setText('画笔模式已取消')

    def handle_brush_click(self, pos):
        """处理画笔点击事件"""
        if not self.brush_mode or not self.selected_brush_color or not self.image_grid:
            return
            
        # 获取当前显示的图片尺寸
        current_pixmap = self.processed_image_label.pixmap()
        if not current_pixmap:
            return
            
        # 计算图片在标签中的实际显示区域
        label_size = self.processed_image_label.size()
        pixmap_size = current_pixmap.size()
        
        # 计算图片在标签中的偏移量（居中显示）
        x_offset = (label_size.width() - pixmap_size.width()) // 2
        y_offset = (label_size.height() - pixmap_size.height()) // 2
        
        # 计算点击位置相对于图片的坐标
        img_x = pos.x() - x_offset
        img_y = pos.y() - y_offset
        
        # 检查点击是否在图片范围内
        if (img_x < 0 or img_x >= pixmap_size.width() or 
            img_y < 0 or img_y >= pixmap_size.height()):
            return
            
        # 计算缩放比例
        base_width = self.image_grid.width * self.block_size + self.axis_size
        base_height = self.image_grid.height * self.block_size + self.axis_size
        
        # 计算统计区域所需高度
        color_statistics = {}
        for block in self.image_grid.blocks.values():
            color_code = block.color_code
            if color_code:
                color_statistics[color_code] = color_statistics.get(color_code, 0) + 1
        
        stats_height = self.calculate_stats_height(color_statistics, base_width)
        total_width = base_width
        total_height = base_height + stats_height
        
        scale_x = total_width / pixmap_size.width()
        scale_y = total_height / pixmap_size.height()
        
        # 计算原始图片中的坐标
        original_x = int(img_x * scale_x)
        original_y = int(img_y * scale_y)
        
        # 检查是否在色块区域内
        if (original_x < self.axis_size or original_y < self.axis_size or
            original_x >= total_width - self.axis_size or
            original_y >= total_height - self.axis_size):
            return
            
        # 计算色块索引
        block_x = (original_x - self.axis_size) // self.block_size
        block_y = (original_y - self.axis_size) // self.block_size
        
        # 检查色块索引是否有效
        if (0 <= block_x < self.image_grid.width and 
            0 <= block_y < self.image_grid.height):
            # 应用画笔修改
            self.apply_brush_change(block_x, block_y)

    def apply_brush_change(self, block_x, block_y):
        """应用画笔修改（优化版本）"""
        if not self.image_grid:
            return
            
        # 检查色块是否存在
        if (block_x, block_y) not in self.image_grid.blocks:
            return
            
        # 保存当前状态到历史记录
        current_state = {
            'x': block_x,
            'y': block_y,
            'old_color': self.image_grid.get_block_color(block_x, block_y),
            'new_color': self.selected_brush_color
        }
        self.brush_changes.append(current_state)
        
        # 更新色块颜色
        self.image_grid.update_block_color(block_x, block_y, self.selected_brush_color)
        
        # 只更新这个色块的显示
        self.update_single_block_display(block_x, block_y)
        
        # 更新统计区域
        self.update_statistics_display()
        
        # 启用撤销按钮
        self.undo_brush_btn.setEnabled(True)
        
        self.status_label.setText(f'已将位置 ({block_x + 1}, {block_y + 1}) 的颜色改为 {self.selected_brush_color}')

    def undo_last_brush_change(self):
        """撤销上一次画笔修改（优化版本）"""
        if not self.brush_changes:
            self.status_label.setText('没有可撤销的画笔操作！')
            return
            
        # 获取最后一次修改
        last_change = self.brush_changes.pop()
        x, y = last_change['x'], last_change['y']
        old_color = last_change['old_color']
        
        # 恢复色块颜色
        if old_color and self.image_grid:
            self.image_grid.update_block_color(x, y, old_color)
            # 只更新这个色块的显示
            self.update_single_block_display(x, y)
            
            # 更新统计区域
            self.update_statistics_display()
        
        # 如果没有更多修改，禁用撤销按钮
        if not self.brush_changes:
            self.undo_brush_btn.setEnabled(False)
        
        self.status_label.setText('已撤销上一次画笔修改！')

    def apply_brush_changes_to_image(self):
        """将画笔修改应用到图片上"""
        if not self.processed_image or not self.brush_changes:
            return
            
        # 创建新的图片副本
        new_image = self.processed_image.copy()
        draw = ImageDraw.Draw(new_image)
        
        # 尝试加载字体
        try:
            font = ImageFont.truetype("arial.ttf", 8)
        except:
            font = ImageFont.load_default()
        
        # 应用每个画笔修改
        for change in self.brush_changes:
            block_x = change['x']
            block_y = change['y']
            new_color_code = change['new_color']
            
            # 计算色块在图片中的位置
            block_size = 20
            axis_size = 30
            
            start_x = block_x * block_size + axis_size
            start_y = block_y * block_size + axis_size
            end_x = start_x + block_size
            end_y = start_y + block_size
            
            # 获取目标颜色
            target_color = tuple(self.color_lookup[new_color_code])
            
            # 填充色块
            draw.rectangle([start_x, start_y, end_x - 1, end_y - 1], fill=target_color)
            
            # 绘制灰色分隔线
            # 右边分隔线
            if block_x < (self.processed_image.size[0] - axis_size) // block_size - 1:
                draw.line([(end_x, start_y), (end_x, end_y)], fill=(200, 200, 200), width=1)
            
            # 下边分隔线
            if block_y < (self.processed_image.size[1] - axis_size) // block_size - 1:
                draw.line([(start_x, end_y), (end_x, end_y)], fill=(200, 200, 200), width=1)
            
            # 如果显示色号，绘制色号
            if self.show_color_codes:
                # 计算文字颜色
                brightness = sum(target_color) / 3
                text_color = (255, 255, 255) if brightness < 128 else (0, 0, 0)
                
                # 获取文字大小
                text_bbox = draw.textbbox((0, 0), new_color_code, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                # 计算文字位置（居中）
                text_x = start_x + (block_size - text_width) // 2
                text_y = start_y + (block_size - text_height) // 2
                
                # 绘制文字
                draw.text((text_x, text_y), new_color_code, fill=text_color, font=font)
        
        # 更新图片
        self.processed_image = new_image

    def generate_block_pixmap(self, block, color_lookup, show_color_codes=True):
        """生成单个色块的QPixmap"""
        # 创建色块图像
        block_img = Image.new('RGB', (self.block_size, self.block_size), 'white')
        draw = ImageDraw.Draw(block_img)
        
        # 获取颜色
        color_code = block.color_code
        if color_code in color_lookup:
            color = tuple(color_lookup[color_code])
        else:
            color = (255, 255, 255)  # 默认白色
            
        # 填充色块（不绘制边框，因为背景层已有辅助线）
        draw.rectangle([0, 0, self.block_size-1, self.block_size-1], fill=color)
        
        # 绘制色号
        if show_color_codes and color_code:
            try:
                font = ImageFont.truetype("arial.ttf", 8)
            except:
                font = ImageFont.load_default()
            
            # 计算文字颜色
            brightness = sum(color) / 3
            text_color = (255, 255, 255) if brightness < 128 else (0, 0, 0)
            
            # 获取文字大小
            text_bbox = draw.textbbox((0, 0), color_code, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            # 计算文字位置（居中）
            text_x = (self.block_size - text_width) // 2
            text_y = (self.block_size - text_height) // 2
            
            # 绘制文字
            draw.text((text_x, text_y), color_code, fill=text_color, font=font)
        
        # 转换为QPixmap
        img_data = block_img.convert("RGBA").tobytes("raw", "RGBA")
        qimg = QImage(img_data, block_img.width, block_img.height, QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimg)

    def generate_background_pixmap(self, width, height, color_statistics=None):
        """生成背景图像（坐标轴、统计等）"""
        # 计算基础尺寸（不包含统计区域）
        base_width = width * self.block_size + self.axis_size
        base_height = height * self.block_size + self.axis_size
        
        # 计算统计区域所需高度
        if color_statistics:
            stats_height = self.calculate_stats_height(color_statistics, base_width)
        else:
            stats_height = 60  # 最小高度，包含额外间距
            
        # 计算总尺寸
        total_width = base_width
        total_height = base_height + stats_height
        
        # 创建背景图像
        bg_img = Image.new('RGB', (total_width, total_height), 'white')
        draw = ImageDraw.Draw(bg_img)
        
        # 绘制浅灰色辅助线网格
        for x in range(width + 1):
            line_x = x * self.block_size + self.axis_size
            draw.line([(line_x, self.axis_size), (line_x, height * self.block_size + self.axis_size)], 
                     fill=(240, 240, 240), width=1)
        
        for y in range(height + 1):
            line_y = y * self.block_size + self.axis_size
            draw.line([(self.axis_size, line_y), (width * self.block_size + self.axis_size, line_y)], 
                     fill=(240, 240, 240), width=1)
        
        # 尝试加载字体
        try:
            font = ImageFont.truetype("arial.ttf", 10)
        except:
            font = ImageFont.load_default()
        
        # 绘制坐标轴
        self.draw_coordinate_axes(draw, width, height, self.block_size, self.axis_size, font)
        
        # 绘制色号统计
        if color_statistics:
            self.draw_color_statistics(draw, color_statistics, total_width, total_height, font)
        
        # 转换为QPixmap
        img_data = bg_img.convert("RGBA").tobytes("raw", "RGBA")
        qimg = QImage(img_data, bg_img.width, bg_img.height, QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimg)

    def update_single_block_display(self, x, y):
        """更新单个色块的显示"""
        if not self.image_grid or (x, y) not in self.image_grid.blocks:
            return
            
        block = self.image_grid.blocks[(x, y)]
        
        # 生成新的色块图像
        block.pixmap = self.generate_block_pixmap(block, self.color_lookup, self.show_color_codes)
        
        # 计算色块在显示区域的位置
        display_x = x * self.block_size + self.axis_size
        display_y = y * self.block_size + self.axis_size
        
        # 更新合成图像
        if self.image_grid.composite_pixmap:
            painter = QPainter(self.image_grid.composite_pixmap)
            painter.drawPixmap(display_x, display_y, block.pixmap)
            painter.end()
            
            # 更新显示
            self.processed_image_label.setPixmap(self.image_grid.composite_pixmap)

    def update_all_blocks_display(self):
        """更新所有色块的显示"""
        if not self.image_grid:
            return
            
        # 重新生成所有色块的图像
        for (x, y), block in self.image_grid.blocks.items():
            block.pixmap = self.generate_block_pixmap(block, self.color_lookup, self.show_color_codes)
        
        # 重新合成图像
        self.composite_display_image()

    def composite_display_image(self):
        """合成显示图像"""
        if not self.image_grid:
            return
            
        # 计算基础尺寸（不包含统计区域）
        base_width = self.image_grid.width * self.block_size + self.axis_size
        base_height = self.image_grid.height * self.block_size + self.axis_size
        
        # 计算统计区域所需高度
        color_statistics = {}
        for block in self.image_grid.blocks.values():
            color_code = block.color_code
            if color_code:
                color_statistics[color_code] = color_statistics.get(color_code, 0) + 1
        
        stats_height = self.calculate_stats_height(color_statistics, base_width)
        
        # 计算总尺寸
        total_width = base_width
        total_height = base_height + stats_height
        
        # 重新生成背景图像（包含更新的统计）
        self.image_grid.background_pixmap = self.generate_background_pixmap(
            self.image_grid.width, self.image_grid.height, color_statistics)
        
        composite_pixmap = QPixmap(total_width, total_height)
        composite_pixmap.fill(Qt.white)
        
        painter = QPainter(composite_pixmap)
        
        # 绘制背景
        if self.image_grid.background_pixmap:
            painter.drawPixmap(0, 0, self.image_grid.background_pixmap)
        
        # 绘制所有色块
        for (x, y), block in self.image_grid.blocks.items():
            if block.pixmap:
                display_x = x * self.block_size + self.axis_size
                display_y = y * self.block_size + self.axis_size
                painter.drawPixmap(display_x, display_y, block.pixmap)
        
        painter.end()
        
        # 更新网格和显示
        self.image_grid.composite_pixmap = composite_pixmap
        self.processed_image_label.setPixmap(composite_pixmap)

    def save_image(self):
        """保存处理后的图片"""
        if not self.image_grid:
            self.status_label.setText('没有可保存的图片！')
            return
            
        # 获取原始文件名和扩展名
        base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        output_path = f"{base_name}_processed.png"
        
        # 从网格数据合成完整图片
        self.composite_full_image()
        
        # 保存图片
        self.processed_image.save(output_path)
        self.status_label.setText(f'图片已保存为: {output_path}')

    def composite_full_image(self):
        """从网格数据合成完整图片"""
        if not self.image_grid:
            return
            
        # 计算基础尺寸（不包含统计区域）
        base_width = self.image_grid.width * self.block_size + self.axis_size
        base_height = self.image_grid.height * self.block_size + self.axis_size
        
        # 生成色号统计
        color_statistics = {}
        for block in self.image_grid.blocks.values():
            color_code = block.color_code
            if color_code:
                color_statistics[color_code] = color_statistics.get(color_code, 0) + 1
        
        # 计算统计区域所需高度
        stats_height = self.calculate_stats_height(color_statistics, base_width)
        
        # 计算总尺寸
        total_width = base_width
        total_height = base_height + stats_height
        
        # 创建完整图片
        full_image = Image.new('RGB', (total_width, total_height), 'white')
        draw = ImageDraw.Draw(full_image)
        
        # 尝试加载字体
        try:
            font = ImageFont.truetype("arial.ttf", 8)
            axis_font = ImageFont.truetype("arial.ttf", 10)
        except:
            font = ImageFont.load_default()
            axis_font = ImageFont.load_default()
        
        # 绘制坐标轴
        self.draw_coordinate_axes(draw, self.image_grid.width, self.image_grid.height, 
                                self.block_size, self.axis_size, axis_font)
        
        # 绘制所有色块
        for (x, y), block in self.image_grid.blocks.items():
            # 计算色块位置
            start_x = x * self.block_size + self.axis_size
            start_y = y * self.block_size + self.axis_size
            end_x = start_x + self.block_size
            end_y = start_y + self.block_size
            
            # 获取颜色
            color_code = block.color_code
            if color_code in self.color_lookup:
                color = tuple(self.color_lookup[color_code])
            else:
                color = (255, 255, 255)
            
            # 填充色块
            draw.rectangle([start_x, start_y, end_x - 1, end_y - 1], fill=color)
            
            # 绘制色号
            if self.show_color_codes and color_code:
                brightness = sum(color) / 3
                text_color = (255, 255, 255) if brightness < 128 else (0, 0, 0)
                
                text_bbox = draw.textbbox((0, 0), color_code, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                text_x = start_x + (self.block_size - text_width) // 2
                text_y = start_y + (self.block_size - text_height) // 2
                
                draw.text((text_x, text_y), color_code, fill=text_color, font=font)
        
        # 绘制色号统计
        self.draw_color_statistics(draw, color_statistics, total_width, total_height, axis_font)
        
        # 更新处理后的图片
        self.processed_image = full_image

    def update_display(self):
        """更新显示（不重新处理图片）"""
        if not self.processed_image:
            return
            
        # 计算显示尺寸（保持比例，但不超过屏幕大小的70%）
        screen = QDesktopWidget().screenGeometry()
        max_display_width = int(screen.width() * 0.7)
        max_display_height = int(screen.height() * 0.7)
        
        output_width, output_height = self.processed_image.size
        display_scale = min(max_display_width / output_width, 
                          max_display_height / output_height)
        display_width = int(output_width * display_scale)
        display_height = int(output_height * display_scale)
        
        # 调整原始图片和处理后图片的显示大小
        original_pixmap = QPixmap(self.image_path)
        scaled_original = original_pixmap.scaled(display_width, display_height, 
                                               Qt.KeepAspectRatio, 
                                               Qt.SmoothTransformation)
        self.original_image_label.setPixmap(scaled_original)
        
        # 将PIL图片转换为QPixmap用于显示
        img_data = self.processed_image.convert("RGBA").tobytes("raw", "RGBA")
        qimg = QImage(img_data, self.processed_image.width, self.processed_image.height, QImage.Format_RGBA8888)
        processed_pixmap = QPixmap.fromImage(qimg)
        
        scaled_processed = processed_pixmap.scaled(display_width, display_height, 
                                                 Qt.KeepAspectRatio,
                                                 Qt.SmoothTransformation)
        self.processed_image_label.setPixmap(scaled_processed)

    def load_image(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "选择图片", "", 
                                                 "Image Files (*.png *.jpg *.bmp)")
        if file_name:
            self.image_path = file_name
            pixmap = QPixmap(file_name)
            
            # 计算适合左侧区域的缩放尺寸
            label_width = int(self.width() * 0.3)
            scaled_pixmap = pixmap.scaled(label_width, self.height() * 0.8, 
                                        Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.original_image_label.setPixmap(scaled_pixmap)
            self.process_btn.setEnabled(True)

    def rgb_to_lab(self, rgb):
        """将RGB颜色转换为LAB色彩空间"""
        # 首先转换到XYZ空间
        r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
        
        # sRGB到XYZ的转换
        def to_linear(c):
            if c <= 0.04045:
                return c / 12.92
            return ((c + 0.055) / 1.055) ** 2.4
        
        r, g, b = to_linear(r), to_linear(g), to_linear(b)
        
        x = r * 0.4124 + g * 0.3576 + b * 0.1805
        y = r * 0.2126 + g * 0.7152 + b * 0.0722
        z = r * 0.0193 + g * 0.1192 + b * 0.9505
        
        # XYZ到LAB的转换
        def f(t):
            if t > (6.0/29.0)**3:
                return t**(1.0/3.0)
            return (1.0/3.0) * ((29.0/6.0)**2) * t + 4.0/29.0
        
        xn, yn, zn = 0.95047, 1.0, 1.08883
        
        l = 116.0 * f(y/yn) - 16.0
        a = 500.0 * (f(x/xn) - f(y/yn))
        b = 200.0 * (f(y/yn) - f(z/zn))
        
        return np.array([l, a, b])

    def rgb_to_hsv(self, rgb):
        """将RGB颜色转换为HSV色彩空间"""
        r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        diff = max_val - min_val
        
        # 计算色相 H
        if diff == 0:
            h = 0
        elif max_val == r:
            h = 60 * ((g - b) / diff % 6)
        elif max_val == g:
            h = 60 * ((b - r) / diff + 2)
        else:
            h = 60 * ((r - g) / diff + 4)
        
        # 计算饱和度 S
        s = 0 if max_val == 0 else diff / max_val
        
        # 计算明度 V
        v = max_val
        
        return np.array([h, s, v])

    def find_closest_color_rgb(self, target_rgb):
        """使用简单的RGB欧氏距离"""
        min_distance = float('inf')
        closest_code = None
        target_rgb = np.array(target_rgb)
        
        for code, rgb in self.color_lookup.items():
            distance = np.sum((target_rgb - rgb) ** 2)
            if distance < min_distance:
                min_distance = distance
                closest_code = code
                
        return closest_code

    def find_closest_color_lab(self, target_rgb):
        """使用LAB色彩空间的颜色匹配"""
        min_distance = float('inf')
        closest_code = None
        target_lab = self.rgb_to_lab(target_rgb)
        
        for code, rgb in self.color_lookup.items():
            lab = self.rgb_to_lab(rgb)
            # LAB空间中的欧氏距离
            distance = np.sum((target_lab - lab) ** 2)
            if distance < min_distance:
                min_distance = distance
                closest_code = code
        
        return closest_code

    def find_closest_color_hsv_weighted(self, target_rgb):
        """使用HSV色彩空间的加权颜色匹配"""
        min_distance = float('inf')
        closest_code = None
        target_hsv = self.rgb_to_hsv(target_rgb)
        
        # 权重设置：色相的权重更大，以更好地保持颜色的基本特征
        weights = np.array([2.0, 1.0, 0.8])  # H权重大，S次之，V最小
        
        for code, rgb in self.color_lookup.items():
            hsv = self.rgb_to_hsv(rgb)
            
            # 色相差异需要特殊处理（因为是环形的）
            h_diff = min(abs(target_hsv[0] - hsv[0]), 360 - abs(target_hsv[0] - hsv[0])) / 180.0
            sv_diff = target_hsv[1:] - hsv[1:]
            
            # 计算加权距离
            distance = weights[0] * h_diff**2 + np.sum(weights[1:] * sv_diff**2)
            
            if distance < min_distance:
                min_distance = distance
                closest_code = code
        
        return closest_code

    def process_image(self):
        try:
            # 打开图片并保持原始模式（可能是RGBA）
            img = Image.open(self.image_path)
            
            # 获取原始文件名和扩展名
            base_name = os.path.splitext(os.path.basename(self.image_path))[0]
            output_path = f"{base_name}_processed.png"
            
            # 获取原始图片尺寸
            width, height = img.size
            
            # 转换为numpy数组以便处理
            img_array = np.array(img)
            
            # 分析透明区域，找出需要删除的行和列
            transparent_rows = []
            transparent_cols = []
            
            # 检查每一行是否全透明
            for y in range(height):
                row_transparent = True
                for x in range(width):
                    pixel_color = img_array[y][x]
                    if len(pixel_color) == 4:  # RGBA模式
                        if pixel_color[3] > 0:  # 不是完全透明
                            row_transparent = False
                            break
                    elif len(pixel_color) == 3:  # RGB模式
                        if not all(c >= 250 for c in pixel_color):  # 不是接近白色
                            row_transparent = False
                            break
                if row_transparent:
                    transparent_rows.append(y)
            
            # 检查每一列是否全透明
            for x in range(width):
                col_transparent = True
                for y in range(height):
                    pixel_color = img_array[y][x]
                    if len(pixel_color) == 4:  # RGBA模式
                        if pixel_color[3] > 0:  # 不是完全透明
                            col_transparent = False
                            break
                    elif len(pixel_color) == 3:  # RGB模式
                        if not all(c >= 250 for c in pixel_color):  # 不是接近白色
                            col_transparent = False
                            break
                if col_transparent:
                    transparent_cols.append(x)
            
            # 创建新的图片数组，删除透明行列
            new_height = height - len(transparent_rows)
            new_width = width - len(transparent_cols)
            
            if new_height <= 0 or new_width <= 0:
                self.status_label.setText('图片完全透明，无法处理！')
                return
            
            # 计算实际输出图片的大小
            block_size = 20  # 每个像素扩大成20x20的方格
            cell_size = block_size  # 每个单元格的大小（去掉边框）
            
            # 坐标轴区域大小
            axis_size = 30  # 坐标轴区域的高度和宽度
            
            # 色号统计区域大小
            stats_height = 80  # 统计区域高度
            stats_margin = 20  # 统计区域与横坐标的间距
            
            # 创建新图片（考虑坐标轴和统计区域）
            output_width = new_width * cell_size + axis_size  # 加上坐标轴区域
            output_height = new_height * cell_size + axis_size + stats_margin + stats_height  # 加上坐标轴区域、间距和统计区域
            new_img = Image.new('RGB', (output_width, output_height), 'white')  # 改为白色背景
            draw = ImageDraw.Draw(new_img)
            
            # 尝试加载字体，如果失败则使用默认字体
            try:
                font = ImageFont.truetype("arial.ttf", 8)  # 减小字体大小以适应20x20的方格
                axis_font = ImageFont.truetype("arial.ttf", 10)  # 坐标轴字体稍大
            except:
                font = ImageFont.load_default()
                axis_font = ImageFont.load_default()
            
            result_codes = []
            color_statistics = {}  # 用于统计色号数量
            
            # 获取当前选择的匹配方法
            current_method = self.method_combo.currentText()
            matching_function = self.matching_methods[current_method]
            
            # 处理每个非透明像素点
            new_y = 0
            for y in range(height):
                if y in transparent_rows:
                    continue
                    
                row_codes = []
                new_x = 0
                for x in range(width):
                    if x in transparent_cols:
                        continue
                        
                    # 获取当前像素的颜色
                    pixel_color = img_array[y][x]
                    
                    # 检查是否为透明色（RGBA模式下的A通道为0，或RGB模式下为白色/透明）
                    is_transparent = False
                    if len(pixel_color) == 4:  # RGBA模式
                        if pixel_color[3] == 0:  # 完全透明
                            is_transparent = True
                    elif len(pixel_color) == 3:  # RGB模式
                        # 检查是否为白色或接近白色（可能是透明背景）
                        if all(c >= 250 for c in pixel_color):
                            is_transparent = True
                    
                    if is_transparent:
                        # 透明像素，跳过绘制色块，但绘制灰色分隔线
                        row_codes.append(None)
                        
                        # 计算新图片中的位置（考虑坐标轴）
                        block_x = new_x * cell_size + axis_size
                        block_y = new_y * cell_size + axis_size
                        
                        # 绘制灰色分隔线（只在右边和下边绘制，避免重复）
                        # 右边分隔线
                        if new_x < new_width - 1:  # 不是最后一列
                            draw.line([(block_x + block_size, block_y), 
                                     (block_x + block_size, block_y + block_size)], 
                                    fill=(200, 200, 200), width=1)
                        
                        # 下边分隔线
                        if new_y < new_height - 1:  # 不是最后一行
                            draw.line([(block_x, block_y + block_size), 
                                     (block_x + block_size, block_y + block_size)], 
                                    fill=(200, 200, 200), width=1)
                        
                        new_x += 1
                        continue
                    
                    # 使用选定的方法找到最接近的颜色
                    color_code = matching_function(pixel_color[:3])  # 只取RGB部分
                    
                    # 应用颜色替换
                    color_code = self.get_replaced_color(color_code)
                    
                    row_codes.append(color_code)
                    
                    # 统计色号数量（使用替换后的颜色）
                    if color_code not in color_statistics:
                        color_statistics[color_code] = 0
                    color_statistics[color_code] += 1
                    
                    # 计算新图片中的位置（考虑坐标轴）
                    block_x = new_x * cell_size + axis_size
                    block_y = new_y * cell_size + axis_size  # 恢复原始排列
                    
                    # 在新图片中填充色块
                    matched_color = tuple(self.color_lookup[color_code])
                    draw.rectangle([block_x, block_y, 
                                  block_x + block_size - 1, 
                                  block_y + block_size - 1], 
                                 fill=matched_color)  # 去掉边框
                    
                    # 绘制灰色分隔线（只在右边和下边绘制，避免重复）
                    # 右边分隔线
                    if new_x < new_width - 1:  # 不是最后一列
                        draw.line([(block_x + block_size, block_y), 
                                 (block_x + block_size, block_y + block_size)], 
                                fill=(200, 200, 200), width=1)
                    
                    # 下边分隔线
                    if new_y < new_height - 1:  # 不是最后一行
                        draw.line([(block_x, block_y + block_size), 
                                 (block_x + block_size, block_y + block_size)], 
                                fill=(200, 200, 200), width=1)
                    
                    # 只在启用色号显示时绘制文字
                    if self.show_color_codes:
                        # 计算文字颜色（深色背景用白色文字，浅色背景用黑色文字）
                        brightness = sum(matched_color) / 3
                        text_color = (255, 255, 255) if brightness < 128 else (0, 0, 0)
                        
                        # 获取文字大小
                        text_bbox = draw.textbbox((0, 0), color_code, font=font)
                        text_width = text_bbox[2] - text_bbox[0]
                        text_height = text_bbox[3] - text_bbox[1]
                        
                        # 计算文字位置（居中）
                        text_x = block_x + (block_size - text_width) // 2
                        text_y = block_y + (block_size - text_height) // 2
                        
                        # 绘制文字
                        draw.text((text_x, text_y), color_code, 
                                fill=text_color, font=font)
                        
                        new_x += 1
                            
                result_codes.append(row_codes)
                new_y += 1
            
            # 绘制坐标轴
            self.draw_coordinate_axes(draw, new_width, new_height, cell_size, axis_size, axis_font)
            
            # 绘制色号统计
            self.draw_color_statistics(draw, color_statistics, output_width, output_height, axis_font)
            
            # 创建图片网格管理器
            self.image_grid = ImageGrid(new_width, new_height, self.block_size, self.axis_size)
            self.image_grid.show_color_codes = self.show_color_codes
            
            # 添加所有色块到网格
            for new_y in range(new_height):
                for new_x in range(new_width):
                    if result_codes[new_y][new_x] is not None:  # 非透明色块
                        color_code = result_codes[new_y][new_x]
                        self.image_grid.add_block(new_x, new_y, color_code, color_code)
            
            # 生成背景图像
            self.image_grid.background_pixmap = self.generate_background_pixmap(new_width, new_height, color_statistics)
            
            # 生成所有色块图像并合成显示
            self.update_all_blocks_display()
            
            # 存储处理后的图片（用于保存）
            self.processed_image = new_img
            
            # 启用保存按钮
            self.save_btn.setEnabled(True)
            
            # 更新状态信息
            removed_rows = len(transparent_rows)
            removed_cols = len(transparent_cols)
            self.status_label.setText(
                f'图片处理完成！原始大小: {width}x{height}, 处理后大小: {new_width}x{new_height}, '
                f'删除透明行: {removed_rows}, 删除透明列: {removed_cols}, '
                f'输出大小: {output_width}x{output_height}')
            
        except Exception as e:
            self.status_label.setText(f'处理出错: {str(e)}')

    def draw_coordinate_axes(self, draw, width, height, cell_size, axis_size, font):
        """绘制坐标轴"""
        # 绘制X轴刻度（列号）- 显示全部数字，横坐标在图片下面
        for x in range(width):
            tick_x = x * cell_size + axis_size + cell_size // 2
            tick_y = height * cell_size + axis_size + 10  # X轴标签位置在图片下面
            
            # 绘制刻度标签
            label = str(x + 1)  # 从1开始编号
            text_bbox = draw.textbbox((0, 0), label, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_x = tick_x - text_width // 2
            text_y = tick_y
            draw.text((text_x, text_y), label, fill='black', font=font)
        
        # 绘制Y轴刻度（行号）- 显示全部数字，原点在左下角
        for y in range(height):
            tick_x = axis_size - 10  # Y轴标签位置
            tick_y = y * cell_size + axis_size + cell_size // 2  # 保持原始排列，但原点在左下角
            
            # 绘制刻度标签（从下往上编号）
            label = str(height - y)  # 从下往上编号
            text_bbox = draw.textbbox((0, 0), label, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_x = tick_x - text_width - 5
            text_y = tick_y - 5
            draw.text((text_x, text_y), label, fill='black', font=font)

    def draw_color_statistics(self, draw, color_statistics, output_width, output_height, font):
        """绘制色号统计"""
        if not color_statistics:
            return
            
        # 计算统计区域所需的高度
        stats_height = self.calculate_stats_height(color_statistics, output_width)
        
        # 统计区域位置（图片底部，增加间距避免覆盖横坐标）
        # 增加额外的顶部间距，避免与坐标轴重叠
        stats_start_y = output_height - stats_height + 20  # 额外增加20像素间距
        
        # 计算每个统计项的显示
        sorted_colors = sorted(color_statistics.items(), key=lambda x: x[1], reverse=True)
        
        x_offset = 10
        y_offset = stats_start_y + 10
        
        for color_code, count in sorted_colors:
            # 绘制色块
            color_rect_x = x_offset
            color_rect_y = y_offset
            color_rect_size = 20  # 与图片中的色块大小一致
            
            matched_color = tuple(self.color_lookup[color_code])
            draw.rectangle([(color_rect_x, color_rect_y), 
                          (color_rect_x + color_rect_size, color_rect_y + color_rect_size)], 
                         fill=matched_color, outline='black')  # 黑色边框
            
            # 在色块上绘制色号
            # 计算文字颜色（深色背景用白色文字，浅色背景用黑色文字）
            brightness = sum(matched_color) / 3
            text_color = (255, 255, 255) if brightness < 128 else (0, 0, 0)
            
            # 获取文字大小
            text_bbox = draw.textbbox((0, 0), color_code, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            # 计算文字位置（居中）
            text_x = color_rect_x + (color_rect_size - text_width) // 2
            text_y = color_rect_y + (color_rect_size - text_height) // 2
            
            # 绘制色号
            draw.text((text_x, text_y), color_code, fill=text_color, font=font)
            
            # 绘制数量
            count_text = f" x {count}"
            count_x = color_rect_x + color_rect_size + 5
            count_y = color_rect_y + 5
            draw.text((count_x, count_y), count_text, fill='black', font=font)
            
            # 更新位置
            x_offset += 80  # 每个统计项占80像素宽度
            
            # 如果超出宽度，换行
            if x_offset + 80 > output_width:
                x_offset = 10
                y_offset += 30
                
                # 如果超出高度，停止绘制
                if y_offset + 30 > stats_start_y + stats_height:
                    break

    def calculate_stats_height(self, color_statistics, output_width):
        """计算色号统计区域所需的高度"""
        if not color_statistics:
            return 60  # 最小高度，包含间距和额外顶部间距
            
        # 每个统计项的布局：
        # - 色块：20x20像素
        # - 色号文字：在色块上居中
        # - 数量文字：在色块右侧
        # - 每个统计项总宽度：约80像素（色块20 + 间距5 + 数量文字约55）
        # - 每个统计项高度：30像素（色块20 + 上下间距10）
        
        # 计算每行能容纳多少个统计项
        items_per_row = max(1, (output_width - 20) // 80)  # 减去左右边距20像素
        
        # 计算需要多少行
        num_items = len(color_statistics)
        num_rows = (num_items + items_per_row - 1) // items_per_row  # 向上取整
        
        # 计算总高度：行数 * 每行高度 + 上下边距 + 额外顶部间距
        total_height = num_rows * 30 + 20 + 20  # 20像素的上下边距 + 20像素的额外顶部间距
        
        # 设置最小高度和最大高度
        min_height = 60  # 增加最小高度，包含额外间距
        max_height = 320  # 增加最大高度限制，避免统计区域过大
        
        return max(min_height, min(total_height, max_height))

    def add_new_color(self):
        try:
            code = self.color_code.text().strip()
            r = int(self.r_value.text())
            g = int(self.g_value.text())
            b = int(self.b_value.text())
            
            if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
                raise ValueError("RGB值必须在0-255之间")
                
            if not code:
                raise ValueError("请输入颜色代码")
                
            # 添加新颜色到查找表
            self.color_lookup[code] = np.array([r, g, b])
            
            # 更新JSON数据
            self.color_data[code] = {
                "rgb": [r, g, b],
                "is_placeholder": False
            }
            
            # 保存到文件
            with open('sample.json', 'w') as f:
                json.dump(self.color_data, f, indent=4)
            
            self.status_label.setText(f'新颜色 {code} 添加成功！')
            
            # 清空输入框
            self.color_code.clear()
            self.r_value.clear()
            self.g_value.clear()
            self.b_value.clear()
            
        except ValueError as e:
            self.status_label.setText(f'输入错误: {str(e)}')
        except Exception as e:
            self.status_label.setText(f'添加颜色失败: {str(e)}')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ColorMatcher()
    window.showMaximized()  # 使用showMaximized而不是show来全屏显示
    sys.exit(app.exec_()) 