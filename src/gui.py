import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import sys
from .logic import FreightBatchProcessor
from .utils import logger

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
        self.root.title("孔夫子旧书网 - 批量修改运费模板工具")
        self.root.geometry("900x600")
        
        # 变量
        self.csv_path = tk.StringVar()
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.is_running = False
        self.processor = FreightBatchProcessor(self.log_to_ui)
        
        self.setup_ui()
        
        # 初始日志
        logger.info("程序启动。请选择模板文件并输入账号信息。")

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
        
        # 日志区
        frame_log = ttk.LabelFrame(self.root, text="运行日志", padding="10")
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.txt_log = scrolledtext.ScrolledText(frame_log, state='disabled')
        self.txt_log.pack(fill="both", expand=True)
        
        # 重定向 stdout/stderr 到日志窗口 (可选，但由于我们用了 logger，主要靠 log_callback)
        # sys.stdout = TextRedirector(self.txt_log, "stdout")
        # sys.stderr = TextRedirector(self.txt_log, "stderr")

    def log_to_ui(self, message):
        self.root.after(0, self._append_log, message)

    def _append_log(self, message):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", message + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def browse_file(self):
        filename = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if filename:
            self.csv_path.set(filename)

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
            self.log_to_ui("正在停止任务...")
            self.btn_stop.config(state="disabled")

    def run_thread(self, csv_file, user, pwd):
        try:
            self.processor.run(csv_file, user, pwd)
        except Exception as e:
            self.log_to_ui(f"发生未捕获异常: {e}")
            logger.exception("Run loop error")
        finally:
            self.is_running = False
            self.root.after(0, self.task_finished)

    def task_finished(self):
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        messagebox.showinfo("完成", "任务运行结束，请查看日志和结果文件。")
