import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from PIL import Image, ImageTk, ImageFilter, ImageDraw, ImageFont
import numpy as np
from scipy.spatial import KDTree
import json
import os

class BeadImageGenerator:
    def __init__(self, root):
        self.root = root
        self.root.title("拼豆图片生成工具")
        self.root.geometry("1200x800")
        
        # 配置网格布局
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=3)
        self.root.rowconfigure(1, weight=1)
        
        # 初始化变量
        self.image_path = ""
        self.original_image = None
        self.processed_image = None
        self.tk_original = None
        self.tk_processed = None
        self.color_map = self.load_color_map()
        self.zoom_level = 1.0
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0
        self.processed_canvas = None
        self.last_drag_x = None
        self.last_drag_y = None
        self.top_left_x = 0
        self.top_left_y = 0
        self.is_brush_mode = False  # 画笔模式状态
        
        # 初始化原始颜色映射文件
        self.initialize_original_color_map()
        
        # 初始化图片处理器
        self.image_processor = ImageProcessor(self)
        
        # 绑定撤销快捷键
        self.bind_undo_shortcut()
        
        # 顶部控制面板
        self.control_frame = ttk.Frame(self.root, padding="10")
        self.control_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        
        # 初始化控件
        self.setup_controls()
        
        # 图片预览区域
        self.setup_preview_frames()
        
        # 颜色信息面板
        self.setup_color_info_frames()
        
        # 窗口设置
        self.root.minsize(1000, 700)
        self.root.bind("<Configure>", self.on_window_resize)
    
    def setup_controls(self):
        """初始化所有控制控件"""
        # 文件操作按钮
        self.browse_btn = ttk.Button(
            self.control_frame, 
            text="选择图片", 
            command=self.image_processor.load_image
        )
        self.browse_btn.pack(side="left", padx=5)
        
        # 目标宽度设置
        self.width_label = ttk.Label(self.control_frame, text="目标宽度:")
        self.width_label.pack(side="left", padx=5)
        
        self.width_entry = ttk.Entry(self.control_frame, width=6)
        self.width_entry.pack(side="left", padx=5)
        self.width_entry.insert(0, "64")
        
        # 处理选项
        self.pixelate_var = tk.IntVar(value=1)
        self.pixelate_cb = ttk.Checkbutton(
            self.control_frame, 
            text="生成拼豆图", 
            variable=self.pixelate_var,
            command=self.toggle_options
        )
        self.pixelate_cb.pack(side="left", padx=5)
        
        # 像素块大小
        self.block_size_frame = ttk.Frame(self.control_frame)
        self.block_size_label = ttk.Label(self.block_size_frame, text="豆子大小:")
        self.block_size_label.pack(side="left")
        
        self.block_size_entry = ttk.Entry(self.block_size_frame, width=4)
        self.block_size_entry.pack(side="left", padx=5)
        self.block_size_entry.insert(0, "20")
        self.block_size_frame.pack(side="left", padx=5)
        
        # 颜色分级
        self.level_frame = ttk.Frame(self.control_frame)
        self.level_label = ttk.Label(self.level_frame, text="颜色等级:")
        self.level_label.pack(side="left")
        
        self.color_level = tk.StringVar(value="144")
        self.level_menu = ttk.OptionMenu(
            self.level_frame,
            self.color_level, 
            "144", "72", "96", "144"
        )
        self.level_menu.pack(side="left", padx=5)
        self.level_frame.pack(side="left", padx=5)
        
        # 缩放显示标签
        self.zoom_label = ttk.Label(self.control_frame, text="缩放: 1.0x")
        self.zoom_label.pack(side="left", padx=10)
        
        # 操作按钮
        self.generate_btn = ttk.Button(
            self.control_frame, 
            text="生成",
            command=self.generate_image
        )
        self.generate_btn.pack(side="left", padx=10)
        
        self.save_btn = ttk.Button(
            self.control_frame, 
            text="保存",
            command=self.save_image,
            state="disabled"
        )
        self.save_btn.pack(side="left", padx=5)
        
        # 添加配置按钮
        ttk.Button(
            self.control_frame, 
            text="颜色配置", 
            command=self.open_color_config
        ).pack(side="left", padx=5)
        
        # 画笔工具按钮和颜色选择器
        self.setup_brush_tools()
        
        # 状态栏
        self.status_label = ttk.Label(
            self.root, 
            text="请选择一张图片", 
            relief="sunken",
            padding="5"
        )
        self.status_label.grid(row=2, column=0, columnspan=2, sticky="ew")
    
    def setup_brush_tools(self):
        """设置画笔颜色选择器"""
        # 创建颜色选择器框架
        color_picker_frame = ttk.Frame(self.control_frame)
        color_picker_frame.pack(side="left", padx=5)
        # 创建颜色网格和更多颜色按钮
        self.color_grid_and_menu_frame = ttk.Frame(color_picker_frame)
        self.color_grid_and_menu_frame.pack(side="left")
        self.setup_color_grid(self.color_grid_and_menu_frame)
        # 颜色选择下拉菜单
        self.brush_color_var = tk.StringVar()
        self.brush_color_menu = tk.Menubutton(
            self.color_grid_and_menu_frame,
            text="更多颜色",
            relief="raised",
            direction="below"
        )
        self.brush_color_menu.grid(row=0, column=3, rowspan=2, padx=5, pady=2, sticky="ns")
        self.color_menu = tk.Menu(self.brush_color_menu, tearoff=0)
        self.brush_color_menu.config(menu=self.color_menu)
        
        # 创建子菜单字典，用于存储每个字母的子菜单
        self.letter_menus = {}
        
        self.update_color_menu()
    
    def update_color_menu(self):
        """更新颜色下拉菜单，按字母分组"""
        # 清空主菜单
        self.color_menu.delete(0, "end")
        
        # 清空子菜单字典
        self.letter_menus.clear()
        
        def sort_color_code(code):
            """自定义排序函数：先按字母排序，字母相同时按数字大小排序"""
            letter = code[0]  # 第一个字母
            number = ''.join(filter(str.isdigit, code))  # 提取数字部分
            number = int(number) if number else 0  # 转换为数字，如果没有数字则为0
            return (letter, number)
        
        # 对颜色代码进行排序
        sorted_codes = sorted(self.color_map.keys(), key=sort_color_code)
        
        # 按首字母分组
        letter_groups = {}
        for code in sorted_codes:
            letter = code[0]
            if letter not in letter_groups:
                letter_groups[letter] = []
            letter_groups[letter].append(code)
        
        # 创建每个字母的子菜单
        for letter in sorted(letter_groups.keys()):
            # 为每个字母创建一个新的子菜单
            letter_menu = tk.Menu(self.color_menu, tearoff=0)
            self.letter_menus[letter] = letter_menu
            
            # 将子菜单添加到主菜单
            self.color_menu.add_cascade(
                label=f"{letter}系列",
                menu=letter_menu
            )
            
            # 在子菜单中添加该字母的所有颜色
            for code in letter_groups[letter]:
                rgb = self.color_map[code]['rgb']
                hex_color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
                letter_menu.add_command(
                    label=code,
                    background=hex_color,
                    command=lambda c=code: self.set_brush_color_from_menu(c)
                )
    
    def set_brush_color_from_menu(self, code):
        self.brush_color_var.set(code)
    
    def on_brush_color_select(self, *args):
        selected = self.brush_color_var.get()
        if selected and selected in self.color_map:
            color_data = self.color_map[selected]
            self.selected_brush_color = color_data['rgb']
            # 激活画笔模式
            self.is_brush_mode = True
            self.processed_canvas.configure(cursor="pencil")
            self.root.bind("<Button-3>", self.cancel_brush_mode)
    
    def select_brush_color(self, color):
        if isinstance(color, list):
            self.selected_brush_color = color
        else:
            self.selected_brush_color = self.hex_to_rgb(color)
        self.is_brush_mode = True
        self.processed_canvas.configure(cursor="pencil")
        self.root.bind("<Button-3>", self.cancel_brush_mode)
    
    def bind_undo_shortcut(self):
        """绑定撤销快捷键"""
        self.root.bind('<Control-z>', self.undo_brush_action)
    
    def undo_brush_action(self, event=None):
        """撤销画笔操作"""
        if not hasattr(self.image_processor, 'undo_stack') or not self.image_processor.undo_stack:
            return
            
        # 从撤销栈中恢复上一个状态
        self.image_processor.pixel_matrix = self.image_processor.undo_stack.pop()
        
        # 重新生成图片
        block_size = int(self.block_size_entry.get())
        self.processed_image = self.create_image_from_matrix(
            self.image_processor.pixel_matrix,
            block_size,
            with_code=True
        )
        self.update_preview()
    
    def create_image_from_matrix(self, pixel_matrix, block_size, with_code=False):
        """根据像素矩阵生成图片，with_code=True时标注色号"""
        height = len(pixel_matrix)
        width = len(pixel_matrix[0]) if height > 0 else 0
        new_image = Image.new("RGB", (width * block_size, height * block_size))
        draw = ImageDraw.Draw(new_image)
        font = None
        if with_code and block_size >= 10:
            try:
                font = ImageFont.truetype("arial.ttf", max(6, block_size//2))
            except:
                font = ImageFont.load_default()
        for y in range(height):
            for x in range(width):
                color = tuple(pixel_matrix[y][x])
                x1 = x * block_size
                y1 = y * block_size
                x2 = x1 + block_size
                y2 = y1 + block_size
                draw.rectangle([x1, y1, x2, y2], fill=color)
                if with_code and font:
                    # 查找色号
                    code = None
                    for k, v in self.color_map.items():
                        if v['rgb'] == list(color):
                            code = k
                            break
                    if code:
                        text = str(code)
                        if hasattr(draw, 'textbbox'):
                            bbox = draw.textbbox((0, 0), text, font=font)
                            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
                        else:
                            w, h = draw.textsize(text, font=font)
                        x_pos = x1 + (block_size - w) // 2
                        y_pos = y1 + (block_size - h) // 2
                        draw.text((x_pos, y_pos), text, fill="black", font=font)
        return new_image
    
    def on_brush_click(self, event, color):
        """处理画笔点击事件，支持撤销"""
        if not self.is_brush_mode or not self.image_processor.pixel_matrix:
            return
            
        # 记录撤销栈
        import copy
        self.image_processor.undo_stack.append(copy.deepcopy(self.image_processor.pixel_matrix))
        
        # 获取点击位置并计算矩阵坐标
        canvas_x = event.x
        canvas_y = event.y
        
        # 使用主类的图片左上角位置和缩放级别
        img_x = int((canvas_x - self.top_left_x) / self.zoom_level)
        img_y = int((canvas_y - self.top_left_y) / self.zoom_level)
        
        # 计算矩阵位置
        matrix_x = img_x // int(self.block_size_entry.get())
        matrix_y = img_y // int(self.block_size_entry.get())
        
        # 添加调试信息
        # print("\n=== 画笔点击位置信息 ===")
        # print(f"画布点击位置: ({canvas_x}, {canvas_y})")
        # print(f"图片左上角: ({self.top_left_x}, {self.top_left_y})")
        # print(f"缩放比例: {self.zoom_level}")
        # print(f"图片坐标: ({img_x}, {img_y})")
        # print(f"矩阵坐标: ({matrix_x}, {matrix_y})")
        # print("======================\n")
        
        # 检查并更新矩阵
        if 0 <= matrix_x < len(self.image_processor.pixel_matrix[0]) and 0 <= matrix_y < len(self.image_processor.pixel_matrix):
            self.image_processor.pixel_matrix[matrix_y][matrix_x] = color
            # 重新生成图片并标注色号
            block_size = int(self.block_size_entry.get())
            self.processed_image = self.create_image_from_matrix(self.image_processor.pixel_matrix, block_size, with_code=True)
            self.update_preview()
    
    def toggle_options(self):
        """切换选项显示"""
        if self.pixelate_var.get():
            self.block_size_frame.pack(side="left", padx=5)
            self.level_frame.pack(side="left", padx=5)
        else:
            self.block_size_frame.pack_forget()
            self.level_frame.pack_forget()
    
    def toggle_brush_mode(self):
        """切换画笔模式"""
        self.is_brush_mode = not self.is_brush_mode
        if self.is_brush_mode:
            self.processed_canvas.configure(cursor="pencil")
            self.root.bind("<Button-3>", self.cancel_brush_mode)
        else:
            self.processed_canvas.configure(cursor="")
            self.root.unbind("<Button-3>")
    
    def cancel_brush_mode(self, event):
        """取消画笔模式"""
        self.is_brush_mode = False
        self.processed_canvas.configure(cursor="")
        self.root.unbind("<Button-3>")
    
    def setup_preview_frames(self):
        """设置预览区域"""
        # 原图区域（较小）
        self.original_frame = ttk.LabelFrame(
            self.root, 
            text="原始图片", 
            padding="10",
            width=300
        )
        self.original_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.original_frame.grid_propagate(False)
        
        # 创建一个容器框架来居中图片
        self.original_container = ttk.Frame(self.original_frame)
        self.original_container.pack(expand=True, fill="both")
        
        # 原图显示标签
        self.original_label = ttk.Label(self.original_container)
        self.original_label.pack(expand=True)
        
        # 绑定原图点击事件
        self.original_label.bind("<Button-1>", self.on_original_click)
        
        # 处理结果区域（较大）
        self.processed_frame = ttk.LabelFrame(
            self.root, 
            text="拼豆效果",
            padding="10"
        )
        self.processed_frame.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)
        
        # 创建画布和滚动条
        self.processed_canvas = tk.Canvas(self.processed_frame, bg="white")
        self.h_scroll = ttk.Scrollbar(self.processed_frame, orient="horizontal", command=self.processed_canvas.xview)
        self.v_scroll = ttk.Scrollbar(self.processed_frame, orient="vertical", command=self.processed_canvas.yview)
        self.processed_canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)
        
        # 布局
        self.processed_canvas.grid(row=0, column=0, sticky="nsew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll.grid(row=1, column=0, sticky="ew")
        
        # 使处理结果区域可以扩展
        self.processed_frame.columnconfigure(0, weight=1)
        self.processed_frame.rowconfigure(0, weight=1)
        
        # 绑定鼠标事件
        self.processed_canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.processed_canvas.bind("<Button-4>", self.on_mouse_wheel)
        self.processed_canvas.bind("<Button-5>", self.on_mouse_wheel)
        self.processed_canvas.bind("<Button-1>", self.on_processed_click)
        self.processed_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.processed_canvas.bind("<ButtonRelease-1>", self.on_canvas_drag_end)
        
        # 让画布获取焦点
        self.processed_canvas.bind("<Enter>", lambda e: self.processed_canvas.focus_set())
    
    def setup_color_info_frames(self):
        """设置颜色信息面板"""
        # 原图颜色信息面板
        self.original_color_frame = ttk.LabelFrame(
            self.root, 
            text="原图颜色信息",
            padding="10"
        )
        self.original_color_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        
        # 原图颜色预览
        self.original_color_preview = tk.Canvas(self.original_color_frame, width=50, height=50, bg="white")
        self.original_color_preview.pack(side="left", padx=10)
        
        # 原图颜色信息标签
        self.original_color_info_label = ttk.Label(
            self.original_color_frame,
            text="点击原图查看颜色信息",
            font=("Arial", 10)
        )
        self.original_color_info_label.pack(side="left", padx=10)
        
        # 处理后图片颜色信息面板
        self.processed_color_frame = ttk.LabelFrame(
            self.root,
            text="处理后图片颜色信息",
            padding="10"
        )
        self.processed_color_frame.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        
        # 处理后图片颜色预览
        self.processed_color_preview = tk.Canvas(self.processed_color_frame, width=50, height=50, bg="white")
        self.processed_color_preview.pack(side="left", padx=10)
        
        # 处理后图片颜色信息标签
        self.processed_color_info_label = ttk.Label(
            self.processed_color_frame,
            text="点击处理后图片查看颜色信息",
            font=("Arial", 10)
        )
        self.processed_color_info_label.pack(side="left", padx=10)
    
    def load_color_map(self):
        """从JSON文件加载颜色映射"""
        try:
            # 获取当前脚本所在目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            color_map_path = os.path.join(current_dir, "color_map.json")
            
            # 读取JSON文件
            with open(color_map_path, 'r', encoding='utf-8') as f:
                color_map = json.load(f)
            
            # 预计算颜色向量和级别
            self.color_vectors = np.array([v['rgb'] for v in color_map.values()])
            self.color_codes = list(color_map.keys())
            self.color_levels = np.array([v['level'] for v in color_map.values()])
            
            return color_map
        except Exception as e:
            # 如果加载失败，返回一个空字典
            return {}
    
    def generate_color_map(self):
        """生成颜色映射（已弃用，现在从文件加载）"""
        return self.load_color_map()
    
    def get_filtered_colors(self, level):
        """优化颜色过滤逻辑，使高级别包含低级别的颜色"""
        level = int(level)
        # 首先过滤掉占位颜色
        non_placeholder_colors = {
            code: rgb for code, rgb in zip(
                self.color_codes,
                self.color_vectors
            ) if not self.color_map[code]['is_placeholder']
        }
        
        # 根据级别过滤，高级别包含低级别
        filtered_colors = {}
        for code, rgb in non_placeholder_colors.items():
            color_level = self.color_map[code]['level']
            # 如果当前颜色级别小于等于所选级别，则包含该颜色
            if color_level <= level:
                filtered_colors[code] = rgb
                
        return filtered_colors
    
    def generate_image(self):
        """生成处理后的图片"""
        if not self.image_path or not self.original_image:
            return
        try:
            target_width = int(self.width_entry.get())
            ratio = target_width / float(self.original_image.width)
            target_height = int(self.original_image.height * ratio)
            self.processed_image = self.original_image.resize(
                (target_width, target_height),
                Image.LANCZOS
            )
            if self.pixelate_var.get():
                block_size = int(self.block_size_entry.get())
                level = self.color_level.get()
                if self.image_processor.pixel_matrix:
                    self.processed_image = self.create_image_from_matrix(self.image_processor.pixel_matrix, block_size, with_code=True)
                else:
                    self.processed_image = self.create_bead_image(self.processed_image, block_size, level)
            self.zoom_level = 1.0
            self.canvas_offset_x = 0
            self.canvas_offset_y = 0
            self.zoom_label.config(text=f"缩放: {self.zoom_level:.1f}x")
            self.update_preview()
            self.status_label["text"] = f"生成完成: {target_width}x{target_height}"
            self.refresh_brush_color_grid()
        except Exception as e:
            self.status_label["text"] = f"生成错误: {str(e)}"
    
    def create_bead_image(self, image, block_size, level):
        """创建拼豆效果图片，并生成像素矩阵"""
        filtered_colors = self.get_filtered_colors(level)
        colors = np.array(list(filtered_colors.values()))
        color_codes = list(filtered_colors.keys())
        tree = KDTree(colors)
        width, height = image.size
        new_image = Image.new("RGB", (width * block_size, height * block_size))
        img_array = np.array(image)
        pixels = img_array.reshape(-1, 3)
        _, indices = tree.query(pixels)
        try:
            font = ImageFont.truetype("arial.ttf", max(6, block_size//2))
        except:
            font = ImageFont.load_default()
        draw = ImageDraw.Draw(new_image)
        pixel_matrix = []
        for y in range(height):
            row = []
            for x in range(width):
                idx = y * width + x
                color_idx = indices[idx]
                color = colors[color_idx]
                code = color_codes[color_idx]
                x1 = x * block_size
                y1 = y * block_size
                x2 = x1 + block_size
                y2 = y1 + block_size
                draw.rectangle([x1, y1, x2, y2], fill=tuple(color))
                if block_size >= 10:
                    text = str(code)
                    if hasattr(draw, 'textbbox'):
                        bbox = draw.textbbox((0, 0), text, font=font)
                        w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
                    else:
                        w, h = draw.textsize(text, font=font)
                    x_pos = x1 + (block_size - w) // 2
                    y_pos = y1 + (block_size - h) // 2
                    draw.text((x_pos, y_pos), text, fill="black", font=font)
                row.append(list(color))
            pixel_matrix.append(row)
        self.image_processor.pixel_matrix = pixel_matrix
        return new_image
    
    def update_preview(self):
        """更新预览"""
        if self.original_image:
            # 保存原始图片的引用
            self.original_display = self.original_image.copy()
            # 创建缩略图
            self.original_display.thumbnail((300, 300), Image.LANCZOS)
            self.tk_original = ImageTk.PhotoImage(self.original_display)
            self.original_label.config(image=self.tk_original)
        
        if self.processed_image:
            self.update_processed_preview()
    
    def update_processed_preview(self):
        """更新处理后的图片预览"""
        if not self.processed_image:
            return
        
        # 计算缩放后的尺寸
        zoomed_width = int(self.processed_image.width * self.zoom_level)
        zoomed_height = int(self.processed_image.height * self.zoom_level)
        
        # 计算画布尺寸
        canvas_width = self.processed_canvas.winfo_width() - 20
        canvas_height = self.processed_canvas.winfo_height() - 20
        
        # 创建缩放后的图片
        zoomed_image = self.processed_image.resize(
            (zoomed_width, zoomed_height),
            Image.NEAREST
        )
        self.tk_processed = ImageTk.PhotoImage(zoomed_image)
        
        # 更新画布
        self.processed_canvas.delete("all")
        self.processed_canvas.create_image(
            -self.canvas_offset_x,
            -self.canvas_offset_y,
            anchor="nw",
            image=self.tk_processed
        )
        
        # 配置画布
        self.processed_canvas.config(
            scrollregion=(0, 0, zoomed_width, zoomed_height),
            width=canvas_width,
            height=canvas_height
        )
    
    def on_mouse_wheel(self, event):
        """鼠标滚轮缩放"""
        if not self.processed_image:
            return
        
        if event.num == 4 or event.num == 5:
            delta = 1 if event.num == 4 else -1
            img_x = self.processed_canvas.canvasx(event.x)
            img_y = self.processed_canvas.canvasy(event.y)
        else:
            delta = event.delta
            img_x = event.x
            img_y = event.y
        
        old_zoom = self.zoom_level
        rel_x = (img_x + self.canvas_offset_x) / old_zoom
        rel_y = (img_y + self.canvas_offset_y) / old_zoom
        
        zoom_factor = 1.1 if delta > 0 else 0.9
        new_zoom = self.zoom_level * zoom_factor
        new_zoom = max(0.1, min(new_zoom, 10.0))
        
        if abs(new_zoom - self.zoom_level) < 0.01:
            return
        
        self.zoom_level = new_zoom
        
        self.canvas_offset_x = rel_x * self.zoom_level - img_x
        self.canvas_offset_y = rel_y * self.zoom_level - img_y
        
        # 更新左上角坐标
        self.top_left_x = -self.canvas_offset_x
        self.top_left_y = -self.canvas_offset_y
        
        self.update_processed_preview()
        self.zoom_label.config(text=f"缩放: {self.zoom_level:.1f}x")
        
        return "break"
    
    def save_image(self):
        """保存图片"""
        if not self.processed_image:
            return
        
        output_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("所有文件", "*.*")]
        )
        
        if output_path:
            try:
                if output_path.lower().endswith(".png"):
                    self.processed_image.save(output_path, format="PNG")
                else:
                    self.processed_image.save(output_path, format="JPEG", quality=95)
                self.status_label["text"] = f"图片已保存: {output_path}"
            except Exception as e:
                self.status_label["text"] = f"保存失败: {str(e)}"
    
    def on_window_resize(self, event):
        """窗口大小改变时更新预览"""
        if hasattr(self, 'processed_image') and self.processed_image:
            self.update_processed_preview()
    
    def get_click_coordinates(self, event):
        """获取点击位置在原始图片中的坐标
        
        Args:
            event: 鼠标点击事件
            
        Returns:
            tuple: (img_x, img_y) 原始图片中的坐标
        """
        if not self.original_image or not self.original_display:
            print("\n=== 坐标信息 ===")
            print("未加载图片")
            print("===============\n")
            return None
            
        # 获取容器框架的大小
        container_width = self.original_container.winfo_width()
        container_height = self.original_container.winfo_height()
        
        # 获取显示图片的实际大小
        display_width = self.original_display.width
        display_height = self.original_display.height
        
        # 计算图片在容器中的实际显示位置（居中）
        x_offset = (container_width - display_width) // 2
        y_offset = (container_height - display_height) // 2
        
        # 计算图片四个角在窗口中的坐标
        top_left = (x_offset, y_offset)
        top_right = (x_offset + display_width, y_offset)
        bottom_left = (x_offset, y_offset + display_height)
        bottom_right = (x_offset + display_width, y_offset + display_height)
        
        # 计算图片显示长度和宽度
        display_length = top_right[0] - top_left[0]  # 图片显示长度
        display_height = bottom_left[1] - top_left[1]  # 图片显示高度
        
        # 打印调试信息
        print(f"\n点击位置:")
        print(f"窗口坐标: ({event.x}, {event.y})")
        
        # 计算原始图片坐标
        # 使用窗口坐标与显示长度的比例计算
        img_x = int(event.x / display_length * self.original_image.width)
        img_y = int(event.y / display_height * self.original_image.height)
        
        print(f"原始图片坐标: ({img_x}, {img_y})")
        print("===============\n")
        
        return (img_x, img_y)
    
    def on_original_click(self, event):
        """处理原图点击事件"""
        # 获取点击位置在原始图片中的坐标
        coords = self.get_click_coordinates(event)
        
        if coords is not None:
            img_x, img_y = coords
            
            # 确保坐标在原始图片范围内
            if 0 <= img_x < self.original_image.width and 0 <= img_y < self.original_image.height:
                # 获取点击位置的颜色
                color = self.original_image.getpixel((img_x, img_y))
                
                # 找到最相近的颜色
                closest_color = self.find_closest_color(color)
                
                # 更新颜色信息显示
                self.update_color_info(color, closest_color, (img_x, img_y))
            else:
                self.clear_color_info()
        else:
            self.clear_color_info()
    
    def find_closest_color(self, target_color):
        """找到最相近的颜色"""
        target_array = np.array(target_color)
        distances = np.sum((self.color_vectors - target_array) ** 2, axis=1)
        closest_idx = np.argmin(distances)
        return self.color_codes[closest_idx]
    
    def update_color_info(self, color, code, position):
        """更新颜色信息显示"""
        # 更新颜色预览
        self.original_color_preview.delete("all")
        self.original_color_preview.create_rectangle(0, 0, 50, 50, fill=f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}")
        
        # 更新信息标签
        info_text = (
            f"位置: ({position[0]}, {position[1]})\n"
            f"原图颜色: RGB{color}\n"
            f"最相近颜色: {code}"
        )
        self.original_color_info_label.config(text=info_text)
    
    def clear_color_info(self):
        """清空颜色信息显示"""
        self.original_color_preview.delete("all")
        self.original_color_info_label.config(text="请点击图片区域")
    
    def on_processed_click(self, event):
        """处理处理后图片的点击事件"""
        if not self.processed_image:
            return
            
        # 保存拖拽起始位置
        self.last_drag_x = event.x
        self.last_drag_y = event.y
        
        # 计算原始图片坐标
        img_x = int((event.x - self.top_left_x) / self.zoom_level)
        img_y = int((event.y - self.top_left_y) / self.zoom_level)
        
        # 添加调试信息
        print("\n=== 点击位置信息 ===")
        print(f"点击位置: ({event.x}, {event.y})")
        print(f"图片左上角: ({self.top_left_x}, {self.top_left_y})")
        print(f"缩放比例: {self.zoom_level}")
        print(f"转换后坐标: ({img_x}, {img_y})")
        print("===================\n")
        
        # 确保坐标在图片范围内
        if 0 <= img_x < self.processed_image.width and 0 <= img_y < self.processed_image.height:
            # 获取点击位置的颜色
            color = self.processed_image.getpixel((img_x, img_y))
            
            # 找到最相近的颜色
            closest_color = self.find_closest_color(color)
            
            # 更新颜色信息显示
            self.update_processed_color_info(color, closest_color, (img_x, img_y))
            
            # 如果是画笔模式，则处理画笔点击
            if self.is_brush_mode and hasattr(self, 'selected_brush_color'):
                self.image_processor.on_brush_click(event, self.selected_brush_color)
        else:
            self.clear_processed_color_info()
    
    def update_processed_color_info(self, color, code, position):
        """更新处理后图片的颜色信息显示"""
        # 更新颜色预览
        self.processed_color_preview.delete("all")
        self.processed_color_preview.create_rectangle(0, 0, 50, 50, fill=f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}")
        
        # 更新信息标签
        info_text = (
            f"位置: ({position[0]}, {position[1]})\n"
            f"颜色: RGB{color}\n"
            f"最相近颜色: {code}"
        )
        self.processed_color_info_label.config(text=info_text)
    
    def clear_processed_color_info(self):
        """清空处理后图片的颜色信息显示"""
        self.processed_color_preview.delete("all")
        self.processed_color_info_label.config(text="点击处理后图片查看颜色信息")
    
    def on_canvas_drag(self, event):
        """处理画布拖拽事件"""
        if not self.processed_image:
            return
            
        # 计算拖拽距离
        dx = event.x - self.last_drag_x
        dy = event.y - self.last_drag_y
        
        # 更新偏移量
        self.canvas_offset_x -= dx
        self.canvas_offset_y -= dy
        
        # 更新显示
        self.update_processed_preview()
        
        # 保存当前位置
        self.last_drag_x = event.x
        self.last_drag_y = event.y
    
    def on_canvas_drag_end(self, event):
        """处理画布拖拽结束事件"""
        # 更新左上角坐标
        self.top_left_x = -self.canvas_offset_x
        self.top_left_y = -self.canvas_offset_y
        
        self.last_drag_x = None
        self.last_drag_y = None

    def open_color_config(self):
        """打开颜色配置窗口"""
        ColorConfigWindow(self.root, self.color_map, self)

    def initialize_original_color_map(self):
        """初始化原始颜色映射文件"""
        try:
            # 如果原始文件不存在，创建它
            if not os.path.exists("color_map_original.json"):
                with open("color_map_original.json", "w", encoding="utf-8") as f:
                    json.dump(self.color_map, f, indent=4)
        except Exception as e:
            print(f"初始化原始颜色映射文件失败: {str(e)}")

    def refresh_brush_color_grid(self):
        """刷新画笔颜色选择区（颜色网格）"""
        # 清空原有颜色网格
        for child in self.color_grid_and_menu_frame.winfo_children():
            if isinstance(child, ttk.Frame):
                child.destroy()
        # 重新绘制颜色网格
        self.setup_color_grid(self.color_grid_and_menu_frame)
        # 重新放置更多颜色按钮
        self.brush_color_menu.grid(row=0, column=3, rowspan=2, padx=5, pady=2, sticky="ns")

    def setup_color_grid(self, parent):
        """设置颜色网格，两排三列，色块20x20"""
        # 获取最常用的颜色
        frequent_colors = self.get_most_frequent_colors()
        if not frequent_colors:
            frequent_colors = [
                [0, 0, 0],      # 黑色
                [255, 0, 0],    # 红色
                [0, 255, 0],    # 绿色
                [0, 0, 255],    # 蓝色
                [255, 255, 0],  # 黄色
                [255, 255, 255] # 白色
            ]
        color_size = 20
        for i, rgb in enumerate(frequent_colors):
            row = i // 3
            col = i % 3
            color_frame = ttk.Frame(parent)
            color_frame.grid(row=row, column=col, padx=2, pady=2)
            hex_color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            color_canvas = tk.Canvas(
                color_frame,
                width=color_size,
                height=color_size,
                bg=hex_color,
                highlightthickness=1,
                highlightbackground="black"
            )
            color_canvas.pack()
            color_code = None
            for code, data in self.color_map.items():
                if data['rgb'] == rgb:
                    color_code = code
                    break
            if color_code:
                color_canvas.create_text(
                    color_size/2,
                    color_size/2,
                    text=color_code,
                    fill="white" if sum(rgb) < 380 else "black",
                    font=("Arial", 7, "bold")
                )
            color_canvas.bind("<Button-1>", lambda e, c=rgb: self.select_brush_color(c))
            color_canvas.bind("<Enter>", lambda e, cv=color_canvas: cv.configure(highlightbackground="red"))
            color_canvas.bind("<Leave>", lambda e, cv=color_canvas: cv.configure(highlightbackground="black"))

    def get_most_frequent_colors(self):
        """获取图片中出现频率最高的颜色"""
        if not hasattr(self.image_processor, 'pixel_matrix') or not self.image_processor.pixel_matrix:
            # 默认色号
            default_codes = ["H7", "H2", "F4", "A4", "C4", "B4"]
            result = []
            for code in default_codes:
                if code in self.color_map:
                    result.append(self.color_map[code]['rgb'])
            return result
        # 统计颜色频率
        color_count = {}
        for row in self.image_processor.pixel_matrix:
            for color in row:
                color_tuple = tuple(color)
                color_count[color_tuple] = color_count.get(color_tuple, 0) + 1
        # 获取前6个最常用的颜色
        most_common = sorted(color_count.items(), key=lambda x: x[1], reverse=True)[:6]
        return [list(color) for color, _ in most_common]

class ColorConfigWindow:
    def __init__(self, parent, color_map, main_app):
        self.parent = parent
        self.color_map = color_map
        self.original_color_map = color_map.copy()
        self.main_app = main_app
        self.modified_colors = set()  # 记录修改过的颜色
        self.selected_color = None  # 当前选中的颜色
        
        # 创建新窗口
        self.window = tk.Toplevel(parent)
        self.window.title("颜色配置")
        self.window.geometry("800x600")
        
        # 设置窗口属性，使其保持在最前
        self.window.transient(parent)
        self.window.grab_set()
        
        # 创建主框架
        self.main_frame = ttk.Frame(self.window, padding="10")
        self.main_frame.pack(fill="both", expand=True)
        
        # 创建工具栏
        self.setup_toolbar()
        
        # 创建颜色列表
        self.setup_color_list()
        
        # 创建编辑区域
        self.setup_edit_area()
        
        # 绑定窗口关闭事件
        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)
    
    def sort_color_codes(self, codes):
        """自定义排序颜色代码"""
        def get_sort_key(code):
            # 分离主要分类和后续内容
            main_category = code[0]
            suffix = code[1:]
            
            # 检查后续内容是否全为数字
            is_numeric = suffix.isdigit()
            
            # 返回排序键：(主要分类, 是否为数字, 数字值或字符串)
            if is_numeric:
                return (main_category, 0, int(suffix))
            else:
                return (main_category, 1, suffix)
        
        return sorted(codes, key=get_sort_key)
    
    def setup_toolbar(self):
        """设置工具栏"""
        toolbar = ttk.Frame(self.main_frame)
        toolbar.pack(fill="x", pady=5)
        
        # 添加按钮
        ttk.Button(toolbar, text="添加颜色", command=self.add_color).pack(side="left", padx=5)
        ttk.Button(toolbar, text="保存更改", command=self.save_changes).pack(side="left", padx=5)
        ttk.Button(toolbar, text="重置所有颜色", command=lambda: self.reset_changes(True)).pack(side="left", padx=5)
        ttk.Button(toolbar, text="恢复所有初始颜色", command=lambda: self.restore_original(True)).pack(side="left", padx=5)
    
    def setup_color_list(self):
        """设置颜色列表"""
        # 创建列表框架
        list_frame = ttk.LabelFrame(self.main_frame, text="颜色列表", padding="5")
        list_frame.pack(fill="both", expand=True, side="left", padx=5)
        
        # 创建操作按钮框架
        button_frame = ttk.Frame(list_frame)
        button_frame.pack(fill="x", pady=5)
        
        # 创建滚动区域
        canvas = tk.Canvas(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        # 配置滚动区域
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 保存滚动区域引用
        self.scrollable_frame = scrollable_frame
        
        # 创建选中样式
        style = ttk.Style()
        style.configure("Selected.TFrame", background="#e0e0e0")
        
        # 填充列表
        self.update_color_list()
    
    def update_color_list(self):
        """更新颜色列表"""
        # 清除现有内容
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # 获取并排序颜色代码
        sorted_codes = self.sort_color_codes(self.color_map.keys())
        
        # 颜色块大小
        color_block_size = 16
        
        # 添加颜色到列表
        for code in sorted_codes:
            color_data = self.color_map[code]
            is_modified = code in self.modified_colors
            
            # 创建颜色项框架
            item_frame = ttk.Frame(self.scrollable_frame)
            item_frame.pack(fill="x", pady=2)
            
            # 添加颜色代码标签
            ttk.Label(item_frame, text=code, width=10).pack(side="left", padx=5)
            
            # 创建颜色块画布
            canvas = tk.Canvas(item_frame, width=color_block_size * 2, height=color_block_size, bg="white")
            canvas.pack(side="left", padx=5)
            
            # 绘制颜色块
            if is_modified and code in self.original_color_map:
                # 修改过的颜色显示两个不同的色块
                canvas.create_rectangle(0, 0, color_block_size, color_block_size, 
                                     fill=f"#{color_data['rgb'][0]:02x}{color_data['rgb'][1]:02x}{color_data['rgb'][2]:02x}")
                canvas.create_rectangle(color_block_size, 0, color_block_size * 2, color_block_size, 
                                     fill=f"#{self.original_color_map[code]['rgb'][0]:02x}{self.original_color_map[code]['rgb'][1]:02x}{self.original_color_map[code]['rgb'][2]:02x}")
            else:
                # 未修改的颜色显示两个相同的色块
                color = f"#{color_data['rgb'][0]:02x}{color_data['rgb'][1]:02x}{color_data['rgb'][2]:02x}"
                canvas.create_rectangle(0, 0, color_block_size, color_block_size, fill=color)
                canvas.create_rectangle(color_block_size, 0, color_block_size * 2, color_block_size, fill=color)
            
            # 绑定点击事件
            item_frame.bind("<Button-1>", lambda e, c=code: self.on_color_click(c))
            canvas.bind("<Button-1>", lambda e, c=code: self.on_color_click(c))
            
            # 如果是选中的颜色，设置高亮
            if code == self.selected_color:
                item_frame.configure(style="Selected.TFrame")
    
    def on_color_click(self, code):
        """处理颜色点击事件"""
        # 更新选择状态
        self.selected_color = code
        self.update_selection_highlight()
        self.on_color_select(None)
    
    def update_selection_highlight(self):
        """更新选择高亮"""
        for widget in self.scrollable_frame.winfo_children():
            if isinstance(widget, ttk.Frame):
                # 移除所有框架的背景色
                widget.configure(style="TFrame")
                # 如果是选中的颜色，设置高亮背景
                if widget.winfo_children()[0].cget("text") == self.selected_color:
                    widget.configure(style="Selected.TFrame")
    
    def on_color_select(self, event):
        """处理颜色选择事件"""
        if not self.selected_color:
            return
            
        color_data = self.color_map[self.selected_color]
        
        # 更新编辑区域
        self.code_entry.delete(0, tk.END)
        self.code_entry.insert(0, self.selected_color)
        
        self.r_entry.delete(0, tk.END)
        self.g_entry.delete(0, tk.END)
        self.b_entry.delete(0, tk.END)
        self.r_entry.insert(0, str(color_data['rgb'][0]))
        self.g_entry.insert(0, str(color_data['rgb'][1]))
        self.b_entry.insert(0, str(color_data['rgb'][2]))
        
        self.level_entry.delete(0, tk.END)
        self.level_entry.insert(0, str(color_data['level']))
        
        self.is_placeholder_var.set(color_data['is_placeholder'])
        
        # 更新颜色预览
        self.update_color_preview(color_data['rgb'])
    
    def setup_edit_area(self):
        """设置编辑区域"""
        edit_frame = ttk.LabelFrame(self.main_frame, text="编辑颜色", padding="5")
        edit_frame.pack(fill="both", expand=True, side="left", padx=5)
        
        # 颜色代码
        ttk.Label(edit_frame, text="颜色代码:").grid(row=0, column=0, sticky="w", pady=5)
        self.code_entry = ttk.Entry(edit_frame)
        self.code_entry.grid(row=0, column=1, sticky="ew", pady=5)
        
        # RGB值
        ttk.Label(edit_frame, text="RGB值:").grid(row=1, column=0, sticky="w", pady=5)
        rgb_frame = ttk.Frame(edit_frame)
        rgb_frame.grid(row=1, column=1, sticky="ew", pady=5)
        
        self.r_entry = ttk.Entry(rgb_frame, width=5)
        self.g_entry = ttk.Entry(rgb_frame, width=5)
        self.b_entry = ttk.Entry(rgb_frame, width=5)
        self.r_entry.pack(side="left", padx=2)
        self.g_entry.pack(side="left", padx=2)
        self.b_entry.pack(side="left", padx=2)
        
        # 级别
        ttk.Label(edit_frame, text="级别:").grid(row=2, column=0, sticky="w", pady=5)
        self.level_entry = ttk.Entry(edit_frame)
        self.level_entry.grid(row=2, column=1, sticky="ew", pady=5)
        
        # 占位符标记
        self.is_placeholder_var = tk.BooleanVar()
        ttk.Checkbutton(edit_frame, text="尚未配置颜色（新增颜色请取消勾选）", variable=self.is_placeholder_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=5)
        
        # 颜色预览
        self.color_preview = tk.Canvas(edit_frame, width=100, height=100, bg="white")
        self.color_preview.grid(row=4, column=0, columnspan=2, pady=10)
        
        # 操作按钮
        button_frame = ttk.Frame(edit_frame)
        button_frame.grid(row=5, column=0, columnspan=2, pady=5)
        
        ttk.Button(button_frame, text="删除", command=self.delete_color).pack(side="left", padx=5)
        ttk.Button(button_frame, text="重置当前颜色", command=lambda: self.reset_changes(False)).pack(side="left", padx=5)
        ttk.Button(button_frame, text="恢复当前初始颜色", command=lambda: self.restore_original(False)).pack(side="left", padx=5)
        
        # 绑定输入事件
        self.code_entry.bind("<KeyRelease>", self.on_entry_change)
        self.r_entry.bind("<KeyRelease>", self.on_entry_change)
        self.g_entry.bind("<KeyRelease>", self.on_entry_change)
        self.b_entry.bind("<KeyRelease>", self.on_entry_change)
        self.level_entry.bind("<KeyRelease>", self.on_entry_change)
        self.is_placeholder_var.trace_add("write", lambda *args: self.on_entry_change(None))
    
    def on_entry_change(self, event):
        """处理输入变化事件"""
        if not self.selected_color:
            return
            
        try:
            # 获取新的颜色数据
            new_code = self.code_entry.get()
            r = int(self.r_entry.get())
            g = int(self.g_entry.get())
            b = int(self.b_entry.get())
            level = int(self.level_entry.get())
            is_placeholder = self.is_placeholder_var.get()
            
            # 验证RGB值
            if not all(0 <= x <= 255 for x in [r, g, b]):
                return
            
            # 创建新的颜色数据
            color_data = {
                'rgb': [r, g, b],
                'level': level,
                'is_placeholder': is_placeholder
            }
            
            # 如果代码改变了，需要删除旧的并添加新的
            if new_code != self.selected_color:
                del self.color_map[self.selected_color]
                self.color_map[new_code] = color_data
                self.modified_colors.add(new_code)
                self.selected_color = new_code
            else:
                self.color_map[self.selected_color] = color_data
                self.modified_colors.add(self.selected_color)
            
            # 更新列表和预览
            self.update_color_list()
            self.update_color_preview([r, g, b])
            
        except ValueError:
            pass
    
    def update_color_preview(self, rgb):
        """更新颜色预览"""
        self.color_preview.delete("all")
        self.color_preview.create_rectangle(0, 0, 100, 100, fill=f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}")
    
    def add_color(self):
        """添加新颜色"""
        # 创建新窗口
        add_window = tk.Toplevel(self.window)
        add_window.title("添加新颜色")
        add_window.geometry("400x300")
        
        # 设置窗口属性，使其保持在最前
        add_window.transient(self.window)
        add_window.grab_set()
        
        # 创建主框架
        main_frame = ttk.Frame(add_window, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # 颜色代码
        ttk.Label(main_frame, text="颜色代码:").grid(row=0, column=0, sticky="w", pady=5)
        code_entry = ttk.Entry(main_frame)
        code_entry.grid(row=0, column=1, sticky="ew", pady=5)
        
        # RGB值
        ttk.Label(main_frame, text="RGB值:").grid(row=1, column=0, sticky="w", pady=5)
        rgb_frame = ttk.Frame(main_frame)
        rgb_frame.grid(row=1, column=1, sticky="ew", pady=5)
        
        r_entry = ttk.Entry(rgb_frame, width=5)
        g_entry = ttk.Entry(rgb_frame, width=5)
        b_entry = ttk.Entry(rgb_frame, width=5)
        r_entry.pack(side="left", padx=2)
        g_entry.pack(side="left", padx=2)
        b_entry.pack(side="left", padx=2)
        
        # 级别
        ttk.Label(main_frame, text="级别:").grid(row=2, column=0, sticky="w", pady=5)
        level_entry = ttk.Entry(main_frame)
        level_entry.grid(row=2, column=1, sticky="ew", pady=5)
        
        # 占位符标记
        # 添加颜色时默认取消勾选
        is_placeholder_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(main_frame, text="尚未配置颜色（新增颜色请取消勾选）", variable=is_placeholder_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=5)
        
        # 颜色预览
        color_preview = tk.Canvas(main_frame, width=100, height=100, bg="white")
        color_preview.grid(row=4, column=0, columnspan=2, pady=10)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=2, pady=5)
        
        def update_preview():
            try:
                r = int(r_entry.get())
                g = int(g_entry.get())
                b = int(b_entry.get())
                if all(0 <= x <= 255 for x in [r, g, b]):
                    color_preview.delete("all")
                    color_preview.create_rectangle(0, 0, 100, 100, fill=f"#{r:02x}{g:02x}{b:02x}")
            except ValueError:
                pass
        
        def save_color():
            try:
                code = code_entry.get()
                r = int(r_entry.get())
                g = int(g_entry.get())
                b = int(b_entry.get())
                level = int(level_entry.get())
                is_placeholder = is_placeholder_var.get()
                
                if not all(0 <= x <= 255 for x in [r, g, b]):
                    messagebox.showerror("错误", "RGB值必须在0-255之间")
                    return
                
                if code in self.color_map:
                    messagebox.showerror("错误", "颜色代码已存在")
                    return
                
                # 添加到颜色映射
                self.color_map[code] = {
                    'rgb': [r, g, b],
                    'level': level,
                    'is_placeholder': is_placeholder
                }
                # 同时更新原始颜色映射
                self.original_color_map[code] = {
                    'rgb': [r, g, b],
                    'level': level,
                    'is_placeholder': is_placeholder
                }
                self.modified_colors.add(code)
                self.update_color_list()
                add_window.destroy()
                
                # 选择新添加的颜色
                self.selected_color = code
                self.update_selection_highlight()
                self.on_color_select(None)
                
            except ValueError as e:
                messagebox.showerror("错误", str(e))
        
        # 绑定输入事件
        r_entry.bind("<KeyRelease>", lambda e: update_preview())
        g_entry.bind("<KeyRelease>", lambda e: update_preview())
        b_entry.bind("<KeyRelease>", lambda e: update_preview())
        
        # 添加按钮
        ttk.Button(button_frame, text="保存", command=save_color).pack(side="left", padx=5)
        ttk.Button(button_frame, text="取消", command=add_window.destroy).pack(side="left", padx=5)
        
        # 设置默认值
        code_entry.insert(0, self.generate_new_code())
        r_entry.insert(0, "255")
        g_entry.insert(0, "255")
        b_entry.insert(0, "255")
        level_entry.insert(0, "144")
        update_preview()
    
    def generate_new_code(self):
        """生成新的颜色代码"""
        # 获取所有现有的代码
        existing_codes = set(self.color_map.keys())
        
        # 尝试生成新的代码
        for letter in 'ABCDEFGH':
            for number in range(1, 100):
                new_code = f"{letter}{number}"
                if new_code not in existing_codes:
                    return new_code
        
        return "Z1"  # 如果所有组合都用完了，返回一个默认值
    
    def save_changes(self):
        """保存更改"""
        try:
            # 保存到文件
            with open("color_map.json", "w", encoding="utf-8") as f:
                json.dump(self.color_map, f, indent=4)
            
            # 更新原始颜色映射
            self.original_color_map = self.color_map.copy()
            
            # 更新主应用的颜色数据
            self.main_app.color_map = self.color_map.copy()
            self.main_app.load_color_map()  # 重新加载颜色映射
            
            messagebox.showinfo("成功", "颜色配置已保存")
            
            # 关闭窗口
            self.window.destroy()
            
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")
    
    def reset_changes(self, reset_all=False):
        """重置更改"""
        if reset_all:
            if messagebox.askyesno("确认", "确定要重置所有颜色吗？"):
                self.color_map = self.original_color_map.copy()
                self.modified_colors.clear()
        else:
            if self.selected_color:
                if messagebox.askyesno("确认", f"确定要重置颜色 {self.selected_color} 吗？"):
                    self.color_map[self.selected_color] = self.original_color_map[self.selected_color].copy()
                    self.modified_colors.discard(self.selected_color)
        
        self.update_color_list()
        # 更新主应用的颜色数据
        self.main_app.color_map = self.color_map.copy()
        self.main_app.load_color_map()
    
    def restore_original(self, restore_all=False):
        """恢复到初始状态"""
        try:
            # 从原始文件加载
            with open("color_map_original.json", "r", encoding="utf-8") as f:
                original_data = json.load(f)
            
            if restore_all:
                if messagebox.askyesno("确认", "确定要恢复所有颜色到初始状态吗？"):
                    self.color_map = original_data.copy()
                    self.original_color_map = original_data.copy()
                    self.modified_colors.clear()
            else:
                if self.selected_color:
                    if messagebox.askyesno("确认", f"确定要恢复颜色 {self.selected_color} 到初始状态吗？"):
                        if self.selected_color in original_data:
                            self.color_map[self.selected_color] = original_data[self.selected_color].copy()
                            self.modified_colors.discard(self.selected_color)
            
            # 保存到当前配置文件
            with open("color_map.json", "w", encoding="utf-8") as f:
                json.dump(self.color_map, f, indent=4)
            
            # 更新显示
            self.update_color_list()
            
            # 更新主应用的颜色数据
            self.main_app.color_map = self.color_map.copy()
            self.main_app.load_color_map()
            
            messagebox.showinfo("成功", "已恢复到初始状态")
            
        except Exception as e:
            messagebox.showerror("错误", f"恢复失败: {str(e)}")
    
    def on_window_close(self):
        """处理窗口关闭事件"""
        # 检查是否有未保存的更改
        has_unsaved_changes = False
        for code in self.color_map:
            if code not in self.original_color_map:
                has_unsaved_changes = True
                break
            if self.color_map[code] != self.original_color_map[code]:
                has_unsaved_changes = True
                break
        
        if has_unsaved_changes:
            if messagebox.askyesno("确认", "有未保存的更改，确定要关闭吗？"):
                # 重新加载color_map
                try:
                    with open("color_map.json", "r", encoding="utf-8") as f:
                        self.main_app.color_map = json.load(f)
                    self.main_app.load_color_map()
                except Exception as e:
                    print(f"重新加载color_map失败: {str(e)}")
                self.window.destroy()
        else:
            self.window.destroy()

    def delete_color(self):
        """删除颜色"""
        if not self.selected_color:
            return
        
        # 确认删除
        if messagebox.askyesno("确认删除", f"确定要删除颜色 {self.selected_color} 吗？\n此操作不可恢复！"):
            del self.color_map[self.selected_color]
            self.selected_color = None
            self.update_color_list()

class ImageProcessor:
    def __init__(self, main_app):
        self.main_app = main_app
        self.original_image = None
        self.processed_image = None
        self.tk_original = None
        self.tk_processed = None
        self.zoom_level = 1.0
        self.block_size = 20
        self.target_width = 64
        self.color_level = 144
        self.pixel_matrix = None  # 存储像素矩阵
        self.undo_stack = []  # 初始化撤销栈
    
    def load_image(self):
        """加载图片"""
        filetypes = [("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif")]
        self.main_app.image_path = filedialog.askopenfilename(filetypes=filetypes)
        
        if self.main_app.image_path:
            try:
                self.main_app.original_image = Image.open(self.main_app.image_path).convert("RGB")
                self.main_app.update_preview()
                self.main_app.save_btn["state"] = "normal"
                self.main_app.status_label["text"] = f"已加载: {self.main_app.image_path}"
            except Exception as e:
                self.main_app.status_label["text"] = f"错误: {str(e)}"
                self.main_app.save_btn["state"] = "disabled"
    
    def on_brush_click(self, event, color):
        """处理画笔点击事件，支持撤销"""
        if not self.main_app.is_brush_mode or not self.pixel_matrix:
            return
            
        # 记录撤销栈
        import copy
        self.undo_stack.append(copy.deepcopy(self.pixel_matrix))
        
        # 获取点击位置并计算矩阵坐标
        canvas_x = event.x
        canvas_y = event.y
        
        # 使用主类的图片左上角位置和缩放级别
        img_x = int((canvas_x - self.main_app.top_left_x) / self.main_app.zoom_level)
        img_y = int((canvas_y - self.main_app.top_left_y) / self.main_app.zoom_level)
        
        # 计算矩阵位置
        matrix_x = img_x // int(self.main_app.block_size_entry.get())
        matrix_y = img_y // int(self.main_app.block_size_entry.get())
        
        # 添加调试信息
        print("\n=== 画笔点击位置信息 ===")
        print(f"画布点击位置: ({canvas_x}, {canvas_y})")
        print(f"图片左上角: ({self.main_app.top_left_x}, {self.main_app.top_left_y})")
        print(f"缩放比例: {self.main_app.zoom_level}")
        print(f"图片坐标: ({img_x}, {img_y})")
        print(f"矩阵坐标: ({matrix_x}, {matrix_y})")
        print("======================\n")
        
        # 检查并更新矩阵
        if 0 <= matrix_x < len(self.pixel_matrix[0]) and 0 <= matrix_y < len(self.pixel_matrix):
            self.pixel_matrix[matrix_y][matrix_x] = color
            # 重新生成图片并标注色号
            block_size = int(self.main_app.block_size_entry.get())
            self.main_app.processed_image = self.main_app.create_image_from_matrix(self.pixel_matrix, block_size, with_code=True)
            self.main_app.update_preview()

if __name__ == "__main__":
    root = tk.Tk()
    app = BeadImageGenerator(root)
    root.mainloop()