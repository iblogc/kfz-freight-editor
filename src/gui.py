import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import sys
import os
from .logic import FreightBatchProcessor
from .utils import logger, open_directory

class TextRedirector(object):
    def __init__(self, widget, tag="stdout"):
        self.widget = widget
        self.tag = tag

    def write(self, str):
        self.widget.configure(state="normal")
        self.widget.insert("end", str, (self.tag,))
        self.widget.see("end")
        self.widget.configure(state="disabled")

    def flush(self):
        pass

class MainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("孔网 - 批量修改商品运费模板工具")
        self.root.geometry("900x600")
        
        # 强制固定界面颜色，防止随系统主题切换
        self.setup_fixed_theme()
        
        # 变量
        self.csv_path = tk.StringVar()
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.is_running = False
        self.processor = FreightBatchProcessor(self.log_to_ui)
        
        self.setup_ui()
        
        # 初始日志
        logger.info("程序启动。请选择模板文件并输入账号信息。")

    def setup_fixed_theme(self):
        """配置固定的 UI 主题颜色"""
        bg_color = "#f0f0f0"
        fg_color = "#333333"
        
        self.root.configure(bg=bg_color)
        style = ttk.Style()
        
        # 使用 'clam' 主题，因为它在跨平台时表现较为一致，不强制依赖系统原生主题色
        if "clam" in style.theme_names():
            style.theme_use("clam")
            
        style.configure(".", background=bg_color, foreground=fg_color)
        style.configure("TLabel", background=bg_color, foreground=fg_color)
        style.configure("TLabelframe", background=bg_color, foreground=fg_color)
        style.configure("TLabelframe.Label", background=bg_color, foreground=fg_color)
        style.configure("TEntry", fieldbackground="white", foreground="black")
        style.configure("TButton", background="#e1e1e1", foreground="black", padding=5)
        style.map("TButton", background=[("active", "#cccccc")])
        style.configure("TSeparator", background="#cccccc")

    def setup_ui(self):
        # 顶部操作区
        frame_top = ttk.LabelFrame(self.root, text="操作设置", padding="10")
        frame_top.pack(fill="x", padx=10, pady=5)
        
        # 模板文件选择
        frame_file = ttk.Frame(frame_top)
        frame_file.pack(fill="x", pady=5)
        ttk.Label(frame_file, text="运费修改模板(CSV):").pack(side="left")
        ttk.Entry(frame_file, textvariable=self.csv_path, width=50).pack(side="left", padx=5)
        ttk.Button(frame_file, text="浏览...", command=self.browse_file).pack(side="left")
        
        # 账号信息
        frame_account = ttk.Frame(frame_top)
        frame_account.pack(fill="x", pady=5)
        ttk.Label(frame_account, text="孔网账号:").pack(side="left")
        ttk.Entry(frame_account, textvariable=self.username, width=20).pack(side="left", padx=5)
        ttk.Label(frame_account, text="密码:").pack(side="left")
        ttk.Entry(frame_account, textvariable=self.password, show="*", width=20).pack(side="left", padx=5)
        
        # 按钮区
        frame_btn = ttk.Frame(frame_top)
        frame_btn.pack(fill="x", pady=10)
        self.btn_start = ttk.Button(frame_btn, text="开始执行", command=self.start_task)
        self.btn_start.pack(side="left", padx=5)
        self.btn_stop = ttk.Button(frame_btn, text="停止", command=self.stop_task, state="disabled")
        self.btn_stop.pack(side="left", padx=5)
        
        ttk.Separator(frame_btn, orient="vertical").pack(side="left", fill="y", padx=10)
        
        self.btn_open_output = ttk.Button(frame_btn, text="打开输出目录", command=self.open_output_dir)
        self.btn_open_output.pack(side="left", padx=5)
        self.btn_open_logs = ttk.Button(frame_btn, text="打开日志目录", command=self.open_logs_dir)
        self.btn_open_logs.pack(side="left", padx=5)
        
        # 日志区
        frame_log = ttk.LabelFrame(self.root, text="运行日志", padding="10")
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.txt_log = scrolledtext.ScrolledText(frame_log, state='disabled', bg="white", fg="black", insertbackground="black")
        self.txt_log.pack(fill="both", expand=True)
        
        # 配置日志颜色标签
        self.txt_log.tag_config("INFO", foreground="black")
        self.txt_log.tag_config("WARNING", foreground="orange")
        self.txt_log.tag_config("ERROR", foreground="red")

    def log_to_ui(self, message, level="INFO"):
        self.root.after(0, self._append_log, message, level)

    def _append_log(self, message, level="INFO"):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", message + "\n", (level,))
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def browse_file(self):
        filename = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if filename:
            self.csv_path.set(filename)

    def open_output_dir(self):
        success, msg = open_directory("output")
        if not success:
            messagebox.showerror("错误", f"无法打开目录: {msg}")

    def open_logs_dir(self):
        success, msg = open_directory("logs")
        if not success:
            messagebox.showerror("错误", f"无法打开目录: {msg}")

    def start_task(self):
        csv_file = self.csv_path.get()
        user = self.username.get()
        pwd = self.password.get()
        
        if not csv_file:
            messagebox.showwarning("提示", "请选择模板文件")
            return
        if not user or not pwd:
            messagebox.showwarning("提示", "请输入账号和密码")
            return
            
        self.is_running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.txt_log.delete(1.0, "end") # 清空日志
        
        # 在新线程运行
        thread = threading.Thread(target=self.run_thread, args=(csv_file, user, pwd))
        thread.daemon = True
        thread.start()

    def stop_task(self):
        if self.is_running:
            self.processor.stop()
            self.log_to_ui("正在停止任务...", "WARNING")
            self.btn_stop.config(state="disabled")

    def run_thread(self, csv_file, user, pwd):
        try:
            self.processor.run(csv_file, user, pwd)
        except Exception as e:
            self.log_to_ui(f"发生未捕获异常: {e}", "ERROR")
            logger.exception("Run loop error")
        finally:
            self.is_running = False
            self.root.after(0, self.task_finished)

    def task_finished(self):
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        messagebox.showinfo("完成", "任务运行完成，请查看界面运行日志，注意红色错误信息。")
