"""Compact Windows floating dashboard; UI and storage stay on the Tk main thread."""
from __future__ import annotations

import queue
import sys
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from .config import DB_FILE, load_config, save_config, validate_controller
from .core import TrafficAccumulator, bytes_label, parse_keywords
from .monitor import LocalController, PollWorker
from .storage import SessionStore

W, FULL_H, SMALL_H = 456, 321, 77
BG = '#101827'
BORDER = '#344456'
TEXT = '#f4f7ff'
MUTED = '#a6b4c8'
CYAN = '#57e3cf'
BLUE = '#78adff'
AMBER = '#f5bc75'
RED = '#ff7782'
TRANSPARENT = '#010203'
FONT = 'Microsoft YaHei UI' if sys.platform == 'win32' else 'DejaVu Sans'


def round_rect(canvas: tk.Canvas, x: int, y: int, w: int, h: int, r: int,
               color: str, outline: str | None = None, tag: str | None = None) -> None:
    pts = [x+r, y, x+w-r, y, x+w, y, x+w, y+r, x+w, y+h-r,
           x+w-r, y+h, x+r, y+h, x, y+h-r, x, y+r]
    canvas.create_polygon(pts, smooth=True, splinesteps=12,
                          fill=color, outline=outline or color, width=1,
                          tags=(tag,) if tag else ())


def set_geometry(root: tk.Tk, x: int, y: int, h: int) -> None:
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    x = max(0, min(x, max(0, sw - W)))
    y = max(0, min(y, max(0, sh - h)))
    root.geometry(f'{W}x{h}+{x}+{y}')


class ClashMeterApp:
    def __init__(self) -> None:
        self.config = load_config()
        self.store = SessionStore(DB_FILE)
        self.meter = TrafficAccumulator()
        self.meter.mode = self.config['mode']
        self.meter.keywords = parse_keywords(self.config['keywords'])
        self.current_session: int | None = None
        self.last_error = '正在连接 Clash…'
        self.connected = False
        self.outbox: queue.Queue = queue.Queue()
        self.worker: PollWorker | None = None
        self.settings_window: tk.Toplevel | None = None
        self.history_window: tk.Toplevel | None = None
        self.drag_origin: tuple[int, int, int, int] | None = None
        self.collapsed = bool(self.config.get('collapsed'))

        self.root = tk.Tk()
        self.root.title('Clash Art Meter · Dual Browser')
        self.root.overrideredirect(True)
        self.root.configure(bg=TRANSPARENT)
        try:
            self.root.wm_attributes('-transparentcolor', TRANSPARENT)
        except tk.TclError:
            self.root.configure(bg=BG)
        self.root.wm_attributes('-topmost', bool(self.config['always_on_top']))
        self.root.resizable(False, False)
        self.root.protocol('WM_DELETE_WINDOW', self.quit)
        try:
            from pathlib import Path
            icon = Path(__file__).resolve().parent.parent / 'resources' / 'app.png'
            if icon.exists():
                self.root.iconphoto(False, tk.PhotoImage(file=str(icon)))
        except (OSError, tk.TclError):
            pass

        position = self.config.get('position')
        if (isinstance(position, list) and len(position) == 2
                and all(isinstance(n, int) for n in position)):
            x, y = position
        else:
            x, y = self.root.winfo_screenwidth() - W - 35, 120
        set_geometry(self.root, x, y, SMALL_H if self.collapsed else FULL_H)

        self.canvas = tk.Canvas(self.root, width=W, height=SMALL_H if self.collapsed else FULL_H,
                                bg=TRANSPARENT if sys.platform == 'win32' else BG,
                                bd=0, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<ButtonPress-1>', self._drag_start)
        self.canvas.bind('<B1-Motion>', self._drag_motion)
        self.canvas.bind('<ButtonRelease-1>', self._drag_end)
        self.canvas.bind('<Button-3>', self._context_menu)
        self._menu = tk.Menu(self.root, tearoff=False)
        self._menu.add_command(label='开始 / 结束作图统计', command=self.toggle_session)
        self._menu.add_command(label='历史记录', command=self.open_history)
        self._menu.add_command(label='连接设置', command=self.open_settings)
        self._menu.add_separator()
        self._menu.add_command(label='退出', command=self.quit)

        self._connect_worker()
        self._render()
        self.root.after(160, self._tick)

    def run(self) -> None:
        self.root.mainloop()

    def _connect_worker(self) -> None:
        if self.worker is not None:
            self.worker.stop()
        self.outbox = queue.Queue()
        self.connected = False
        self.last_error = '正在连接 Clash…'
        self.meter.reset_baseline()
        self.worker = PollWorker(LocalController(self.config['controller'], self.config['secret']), self.outbox)
        self.worker.start()

    def _tick(self) -> None:
        changed = False
        try:
            while True:
                kind, data, wall, mono = self.outbox.get_nowait()
                changed = True
                if kind == 'sample':
                    try:
                        payload, port_map = data
                        up, down = self.meter.ingest(payload, wall, mono, port_map)
                    except ValueError as error:
                        self.connected, self.last_error = False, str(error)
                        self.meter.reset_baseline()
                    else:
                        self.connected, self.last_error = True, ''
                        if self.current_session is not None:
                            breakdown = (self.meter.last_breakdown
                                         if self.meter.mode == 'dual_gpt' else None)
                            self.store.add(self.current_session, up, down, breakdown)
                else:
                    self.connected, self.last_error = False, str(data)
                    self.meter.reset_baseline()
        except queue.Empty:
            pass
        if changed:
            self._render()
        self.root.after(160, self._tick)

    def _add_text(self, x, y, content, size=11, color=TEXT, bold=False, anchor='nw', tag=None):
        self.canvas.create_text(x, y, text=content, anchor=anchor,
                                fill=color, font=(FONT, size, 'bold' if bold else 'normal'),
                                tags=(tag,) if tag else ())

    def _clickable(self, tag: str, handler) -> None:
        self.canvas.tag_bind(tag, '<Button-1>', lambda _evt: handler())
        self.canvas.tag_bind(tag, '<Enter>', lambda _evt: self.canvas.configure(cursor='hand2'))
        self.canvas.tag_bind(tag, '<Leave>', lambda _evt: self.canvas.configure(cursor='arrow'))

    def _render(self) -> None:
        c = self.canvas
        c.delete('all')
        h = SMALL_H if self.collapsed else FULL_H
        round_rect(c, 1, 1, W-2, h-2, 16, BG, BORDER)
        c.create_oval(19, 19, 28, 28, fill=CYAN if self.connected else RED, outline='')
        self._add_text(34, 12, 'CLASH ART METER', 12, TEXT, True)
        self._add_text(283, 15, '统计中' if self.meter.active else '待机', 9,
                       CYAN if self.meter.active else MUTED)
        self._add_text(367, 12, '⚙', 17, MUTED, tag='settings_btn')
        self._add_text(406, 12, '▭' if not self.collapsed else '▣', 17, MUTED, tag='collapse_btn')
        self._add_text(437, 12, '×', 16, MUTED, tag='quit_btn')
        for tag, callback in [('settings_btn', self.open_settings),
                              ('collapse_btn', self.toggle_collapsed), ('quit_btn', self.quit)]:
            self._clickable(tag, callback)

        total = self.meter.session_up + self.meter.session_down
        if self.collapsed:
            self._add_text(20, 45, bytes_label(total), 13, TEXT, True)
            self._add_text(170, 46, f'↓ {bytes_label(self.meter.down_speed)}/s', 10, CYAN)
            self._add_text(313, 46, f'↑ {bytes_label(self.meter.up_speed)}/s', 10, BLUE)
            return

        mode = self.meter.mode if self.meter.active else self.config['mode']
        dual = mode == 'dual_gpt'
        self._add_text(20, 43, 'Edge + Chrome / ChatGPT 估算' if dual else '本次作图流量', 10, MUTED)
        self._add_text(20, 63, bytes_label(total), 29, TEXT, True)
        self._add_text(20, 108, f'↓ 下载 {bytes_label(self.meter.session_down)}', 10, CYAN)
        self._add_text(243, 108, f'↑ 上传 {bytes_label(self.meter.session_up)}', 10, BLUE)
        c.create_line(20, 134, W-20, 134, fill='#2c3a4b', width=1)

        if dual:
            for y, key, name, color in [(145, 'edge', 'Edge · ChatGPT', '#a4c9ff'),
                                        (173, 'chrome', 'Chrome · ChatGPT', '#a4c9ff'),
                                        (201, 'unknown', '未识别浏览器', AMBER)]:
                up, down = self.meter.session_by_bucket[key]
                speed_up, speed_down = self.meter.speed_by_bucket[key]
                self._add_text(20, y, name, 10, color)
                self._add_text(245, y, bytes_label(up + down), 10, TEXT, True, anchor='ne')
                self._add_text(429, y, f'↓{bytes_label(speed_down)}/s  ↑{bytes_label(speed_up)}/s',
                               9, MUTED, anchor='ne')
        else:
            self._add_text(20, 149, '当前使用其他统计模式', 11, TEXT, True)
            self._add_text(20, 175, '选择 Edge + Chrome 模式可查看分浏览器数据', 10, MUTED)
            self._add_text(20, 201, '所有网速均按当前筛选范围计算', 10, MUTED)

        c.create_line(20, 231, W-20, 231, fill='#2c3a4b', width=1)
        self._add_text(20, 240, f'总速 ↓ {bytes_label(self.meter.down_speed)}/s', 10, CYAN)
        self._add_text(238, 240, f'↑ {bytes_label(self.meter.up_speed)}/s', 10, BLUE)
        round_rect(c, 292, 277, 144, 31, 9, CYAN if not self.meter.active else '#273a51', tag='start_btn')
        self._add_text(364, 293, '● 开始作图' if not self.meter.active else '结束并保存',
                       10, BG if not self.meter.active else TEXT, True,
                       anchor='center', tag='start_btn')
        self._clickable('start_btn', self.toggle_session)
        self._add_text(20, 269, '双浏览器·域名过滤·估算' if dual else
                       {'global': '全部 Clash 流量', 'domains': '域名·估算', 'process': '程序·估算'}.get(mode, mode),
                       9, MUTED)
        status = '已连接' if self.connected else self.last_error[:37]
        self._add_text(20, 289, status, 9, CYAN if self.connected else RED)

    def _drag_start(self, event) -> None:
        ids = self.canvas.find_withtag('current')
        tags = self.canvas.gettags(ids[0]) if ids else ()
        if any(t in {'settings_btn', 'collapse_btn', 'quit_btn', 'start_btn'} for t in tags):
            return
        self.drag_origin = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())

    def _drag_motion(self, event) -> None:
        if self.drag_origin is None:
            return
        px, py, x, y = self.drag_origin
        set_geometry(self.root, x + event.x_root - px, y + event.y_root - py,
                     SMALL_H if self.collapsed else FULL_H)

    def _drag_end(self, _event) -> None:
        if self.drag_origin is not None:
            self.drag_origin = None
            self._persist_position()

    def _persist_position(self) -> None:
        self.config['position'] = [self.root.winfo_x(), self.root.winfo_y()]
        self.config['collapsed'] = self.collapsed
        save_config(self.config)

    def _context_menu(self, event) -> None:
        self._menu.tk_popup(event.x_root, event.y_root)
        self._menu.grab_release()

    def toggle_collapsed(self) -> None:
        self.collapsed = not self.collapsed
        h = SMALL_H if self.collapsed else FULL_H
        self.canvas.configure(width=W, height=h)
        set_geometry(self.root, self.root.winfo_x(), self.root.winfo_y(), h)
        self._persist_position()
        self._render()

    def toggle_session(self) -> None:
        if self.meter.active:
            if self.current_session is not None:
                self.store.finish(self.current_session)
            self.current_session = None
            self.meter.stop()
            self.meter.mode = self.config['mode']
            self.meter.keywords = parse_keywords(self.config['keywords'])
        else:
            if self.config['mode'] != 'global' and not self.config['keywords'].strip():
                messagebox.showwarning('请设置筛选词', '筛选模式需要填写域名或进程名。', parent=self.root)
                return
            self.meter.start(self.config['mode'], self.config['keywords'], time.time())
            self.current_session = self.store.begin(self.meter.mode, self.config['keywords'])
        self._render()

    def _dialog(self, title: str, width: int = 520, height: int = 490) -> tk.Toplevel:
        top = tk.Toplevel(self.root)
        top.title(title)
        top.configure(bg=BG)
        top.geometry(f'{width}x{height}')
        top.resizable(False, False)
        top.attributes('-topmost', bool(self.config['always_on_top']))
        return top

    def open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        top = self._dialog('Clash Art Meter · 设置', 535, 545)
        self.settings_window = top
        tk.Label(top, text='连接 Clash / Mihomo 控制器', bg=BG, fg=TEXT,
                 font=(FONT, 14, 'bold')).pack(anchor='w', padx=22, pady=(16, 12))
        frame = tk.Frame(top, bg=BG)
        frame.pack(fill='x', padx=22)
        tk.Label(frame, text='控制器 API 地址（不是代理端口）', bg=BG, fg=MUTED,
                 font=(FONT, 10)).pack(anchor='w')
        url_var = tk.StringVar(value=self.config['controller'])
        tk.Entry(frame, textvariable=url_var, bg='#202c40', fg=TEXT,
                 insertbackground=TEXT, relief='flat', font=(FONT, 11)).pack(fill='x', ipady=6, pady=(4, 9))
        tk.Label(frame, text='API Secret（没有设置可留空；不要向他人透露）', bg=BG, fg=MUTED,
                 font=(FONT, 10)).pack(anchor='w')
        secret_var = tk.StringVar(value=self.config['secret'])
        tk.Entry(frame, textvariable=secret_var, show='●', bg='#202c40', fg=TEXT,
                 insertbackground=TEXT, relief='flat', font=(FONT, 11)).pack(fill='x', ipady=6, pady=(4, 9))
        tk.Label(frame, text='统计范围', bg=BG, fg=MUTED, font=(FONT, 10)).pack(anchor='w')
        mode_var = tk.StringVar(value=self.config['mode'])
        for value, label in [
            ('dual_gpt', 'Edge + Chrome 的 ChatGPT（推荐，分别统计，估算）'),
            ('domains', '指定域名（合计，估算）'),
            ('global', '全部 Clash 流量（包含其他网站）'),
            ('process', '指定程序（估算）')]:
            tk.Radiobutton(frame, text=label, value=value, variable=mode_var,
                           bg=BG, fg=TEXT, activebackground=BG, activeforeground=TEXT,
                           selectcolor='#202c40', font=(FONT, 10)).pack(anchor='w')
        tk.Label(frame, text='匹配域名（用英文逗号分隔；程序模式填写程序名）',
                 bg=BG, fg=MUTED, font=(FONT, 10)).pack(anchor='w', pady=(8, 0))
        keywords_var = tk.StringVar(value=self.config['keywords'])
        tk.Entry(frame, textvariable=keywords_var, bg='#202c40', fg=TEXT,
                 insertbackground=TEXT, relief='flat', font=(FONT, 10)).pack(fill='x', ipady=6, pady=(4, 6))
        tk.Label(frame, text='分浏览器识别依赖 Clash 提供进程名；无法识别会计入“未识别”。',
                 bg=BG, fg=AMBER, font=(FONT, 9)).pack(anchor='w')
        tk.Label(frame, text='不能识别 ChatGPT 标签页或只区分图片生成与聊天。',
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor='w', pady=(2, 6))
        top_var = tk.BooleanVar(value=self.config['always_on_top'])
        tk.Checkbutton(frame, text='悬浮窗始终置顶', variable=top_var, bg=BG, fg=TEXT,
                       activebackground=BG, activeforeground=TEXT, selectcolor='#202c40',
                       font=(FONT, 10)).pack(anchor='w')

        def save() -> None:
            try:
                addr = validate_controller(url_var.get())
                if mode_var.get() != 'global' and not keywords_var.get().strip():
                    raise ValueError('筛选模式至少需要一个匹配词')
                old_addr = (self.config['controller'], self.config['secret'])
                self.config.update(controller=addr, secret=secret_var.get().strip(),
                                   mode=mode_var.get(), keywords=keywords_var.get().strip(),
                                   always_on_top=top_var.get(), schema_version=2)
                save_config(self.config)
                if not self.meter.active:
                    self.meter.mode = self.config['mode']
                    self.meter.keywords = parse_keywords(self.config['keywords'])
                self.root.attributes('-topmost', top_var.get())
                if old_addr != (addr, secret_var.get().strip()):
                    self._connect_worker()
                top.destroy()
                self.settings_window = None
                self._render()
                if self.meter.active and (self.meter.mode != mode_var.get() or
                                         self.meter.keywords !=
                                         [k.strip().lower() for k in keywords_var.get().split(',') if k.strip()]):
                    messagebox.showinfo('设置已保存', '新统计范围会从下一次“开始作图”生效。', parent=self.root)
            except ValueError as error:
                messagebox.showerror('设置有误', str(error), parent=top)

        tk.Button(top, text='保存并连接', command=save, bg=CYAN, fg=BG,
                  activebackground=CYAN, relief='flat', font=(FONT, 11, 'bold'),
                  cursor='hand2').pack(pady=(12, 0), ipadx=28, ipady=6)

    def open_history(self) -> None:
        if self.history_window is not None and self.history_window.winfo_exists():
            self.history_window.lift()
            return
        top = self._dialog('Clash Art Meter · 统计历史', 965, 485)
        self.history_window = top
        count, up, down = self.store.totals()
        tk.Label(top, text='双浏览器作图流量历史', bg=BG, fg=TEXT,
                 font=(FONT, 16, 'bold')).pack(anchor='w', padx=22, pady=(17, 4))
        tk.Label(top, text=f'共 {count} 次    累计 ↓ {bytes_label(down)}    ↑ {bytes_label(up)}'
                 f'    合计 {bytes_label(up + down)}', bg=BG, fg=CYAN,
                 font=(FONT, 10)).pack(anchor='w', padx=22, pady=(0, 8))
        tk.Label(top, text='Edge / Chrome 分项仅适用于双浏览器模式。旧版记录仍保留。',
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor='w', padx=22, pady=(0, 12))
        style = ttk.Style(top)
        style.theme_use('clam')
        style.configure('Meter.Treeview', background='#192439', foreground=TEXT,
                        fieldbackground='#192439', rowheight=29, borderwidth=0,
                        font=(FONT, 10))
        style.configure('Meter.Treeview.Heading', background='#2c3b50',
                        foreground=TEXT, relief='flat', font=(FONT, 10, 'bold'))
        cols = ('time', 'mode', 'edge', 'chrome', 'unknown', 'down', 'up', 'total')
        tree = ttk.Treeview(top, columns=cols, show='headings', style='Meter.Treeview')
        for col, title, width in zip(cols,
                                     ['开始时间', '模式', 'Edge', 'Chrome', '未识别', '下载', '上传', '合计'],
                                     [180, 108, 100, 100, 110, 100, 100, 110]):
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor='center')
        tree.pack(fill='both', expand=True, padx=22, pady=(0, 22))
        names = {'dual_gpt': '双浏览器·估算', 'global': '全部流量',
                 'domains': '域名·估算', 'process': '程序·估算'}
        for (started, _ended, mode, up, down, eu, ed, cu, cd, uu, ud) in self.store.recent():
            try:
                local = datetime.fromisoformat(started).astimezone().strftime('%m-%d %H:%M:%S')
            except ValueError:
                local = started[:19]
            dual = mode == 'dual_gpt'
            tree.insert('', 'end', values=(local, names.get(mode, mode),
                                           bytes_label(eu + ed) if dual else '—',
                                           bytes_label(cu + cd) if dual else '—',
                                           bytes_label(uu + ud) if dual else '—',
                                           bytes_label(down), bytes_label(up), bytes_label(up + down)))

    def quit(self) -> None:
        if self.worker:
            self.worker.stop()
        if self.current_session is not None:
            self.store.finish(self.current_session)
            self.current_session = None
        self._persist_position()
        self.store.close()
        self.root.destroy()
