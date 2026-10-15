#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
久坐提醒 · 今日任务面板（Windows 桌面小程序）
============================================

一个常驻桌面的侧边小程序（.pyw，双击即可在 Windows 上运行）：

* 屏幕右缘（默认）常驻一个半透明卡通小人（戴「加油」头巾、举着拳头）；
  **鼠标长时间停在小人上**（约 0.6 秒）自动拉出提醒框；
  **双击面板顶栏**（或点右上角 ✕ / 按 Esc）即可收起。
* 每 1 小时自动滑出一次，面板最下方是大字提醒「不要久坐！起来活动 5 分钟」，
  下面深色底板上是轮换的寄语（做一个健康的人 / 做一个不断学习的人 ……），
  点那条深色寄语条即可随时加入自己的话。
* 任务按 P1 / P2 / P3 / P4 …… 优先级上下排列（数量可增删）；
  每一行都可以直接点击编辑、勾选完成、删除、新增；
  按住行首的 ⋮⋮ 手柄可把任务拖到其他优先级下；
  每个优先级的标题文字也可以直接点击修改。
* 点击面板空白处即可退出编辑状态（光标消失）。
* 按住顶部标题栏可以把面板拖到屏幕任意位置；拖到屏幕中间后不会自动消失，
  双击顶栏 / 点 ✕ / Esc 即可收回。
* 任务自动保存在脚本同目录的 tasks.json，按日期归档，跨天顺延未完成任务；
  优先级结构保存在 settings.json。

用法：
    python3 sit_reminder.py                 # 正常启动（小人常驻待命，每小时弹出）
    python3 sit_reminder.py --now           # 启动后立即弹出（测试用）
    python3 sit_reminder.py --left          # 改为屏幕左侧
    python3 sit_reminder.py --interval 5    # 每 5 分钟弹出一次（调试用）
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import random
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, simpledialog

# --------------------------------------------------------------------------
# 常量与配置
# --------------------------------------------------------------------------

# 数据目录：%APPDATA%/久坐提醒/（Windows 标准做法，无需特殊权限）
# 回退到脚本同目录，保证任何环境都能跑起来。
_appdata = os.environ.get("APPDATA")
if _appdata:
    DATA_DIR = Path(_appdata) / "久坐提醒"
else:
    DATA_DIR = Path.home() / "久坐提醒"
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    DATA_DIR = Path(__file__).resolve().parent
    DATA_DIR.mkdir(parents=True, exist_ok=True)

TASKS_FILE = DATA_DIR / "tasks.json"
SETTINGS_FILE = DATA_DIR / "settings.json"     # 优先级结构（数量/编号/标题）
WELCOME_FILE = DATA_DIR / ".welcome_shown"     # 首次启动欢迎标记
LOCK_FILE = DATA_DIR / ".sit_reminder.pid"     # 单实例锁
LOG_FILE = DATA_DIR / "运行日志.txt"

SLIDE_STEP = 100     # 滑出动画每步移动的像素（大步快走，文字不滞后）
SLIDE_MS = 10        # 滑出动画每步间隔（ms）
Y0 = 30              # 面板距屏幕顶部的距离（避开菜单栏）
PANEL_W = 330        # 面板宽度
KEEP_DAYS = 14       # tasks.json 中保留多少天的历史
VIEW_CAP = 260       # 滚动视口封顶高度（px）：面板保持「短」，超出部分靠滚轮下拉
                     # （含 P1 在内的所有优先级都在同一滚动区，超长则滚动而非撑长面板）

# 卡通小人（常驻屏幕右缘，半透明；悬停拉出 / 双击面板顶栏收起，可拖动）
MASCOT_W = 56        # 小人窗口宽度
MASCOT_H = 76        # 小人窗口高度
MASCOT_MARGIN = 8    # 小人距屏幕边缘的距离
MASCOT_SPAN = MASCOT_W + MASCOT_MARGIN + 4   # 小人占据的水平空间（含缝）
MASCOT_ALPHA = 0.5   # 小人常态半透明度（够淡、不抢眼）
MASCOT_ALPHA_HI = 0.75   # 鼠标悬停时
MASCOT_ALPHA_REACT = 0.9  # 点击反馈时
MASCOT_HOVER_MS = 600     # 鼠标在小人上停留多久（ms）才拉出面板（防误触）
MAGIC = "#FF00FF"          # 透明魔法色：Windows 上该颜色被视为完全透明（画面上绝不出现）

C = {
    "bg":     "#F7F8FA",
    "header_bg": "#E7EBF1",  # 顶栏抓握/双击收起区（略深于 bg，便于一眼辨认有效区域）
    "card":   "#FFFFFF",
    "line":   "#E5E7EB",
    "text":   "#1F2937",
    "sub":    "#6B7280",
    "accent": "#2563EB",
    "drag_bg": "#DBEAFE",   # 拖拽中的行高亮底色
    "banner_bg": "#FFF7ED", # 提醒横幅底色（浅）
    "banner_fg": "#C2410C", # 大字提醒文字颜色
    "plate_bg": "#1F2937",  # 寄语深色底板
    "plate_fg": "#FBBF24",  # 寄语文字颜色（金黄）
}

# 优先级配色（超过 8 个循环使用）
PALETTE_FG = ["#DC2626", "#D97706", "#2563EB", "#6B7280",
              "#7C3AED", "#0D9488", "#DB2777", "#4D7C0F"]
PALETTE_BG = ["#FEF2F2", "#FFFBEB", "#EFF6FF", "#F3F4F6",
              "#F5F3FF", "#F0FDFA", "#FDF2F8", "#F7FEE7"]

# 每次弹出时轮换展示的寄语（不会连续重复）
SLOGANS = [
    "做一个健康的人。",
    "做一个积极向上的人。",
    "做一个有思考深度的人。",
    "做一个不浪费时间的人。",
    "做一个不断学习的人。",
    "做一个不慌乱的人。",
]

DEFAULT_PRIORITIES = [
    {"id": "p1", "tag": "P1", "desc": "重要且紧急"},
    {"id": "p2", "tag": "P2", "desc": "重要不紧急"},
    {"id": "p3", "tag": "P3", "desc": "紧急不重要"},
    {"id": "p4", "tag": "P4", "desc": "日常琐事"},
]

# 首次运行时的示例任务
SEED = {
    "p1": ["完成今天最重要的一件事"],
    "p2": ["深度学习 30 分钟"],
    "p3": ["回复待处理的邮件"],
    "p4": ["取快递 / 买菜"],
}

FONT = "Microsoft YaHei"      # Windows 自带中文字体（微软雅黑）


# --------------------------------------------------------------------------
# 设置层：优先级结构（数量 / 编号 / 标题）
# --------------------------------------------------------------------------

def load_settings() -> dict:
    """读取优先级结构与寄语列表；文件缺失或损坏时用默认值。"""
    pris = [dict(p) for p in DEFAULT_PRIORITIES]
    slogans = list(SLOGANS)
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            sp = saved.get("priorities")
            if isinstance(sp, list) and sp:
                pris = []
                for p in sp:
                    if isinstance(p, dict) and p.get("id") and p.get("tag"):
                        pris.append({"id": str(p["id"]), "tag": str(p["tag"]),
                                     "desc": str(p.get("desc", ""))})
            s = saved.get("slogans")
            if isinstance(s, list) and all(isinstance(x, str) for x in s):
                s = [x for x in s if x.strip()]
                if s:
                    slogans = s
        except Exception:
            pass
    return {"priorities": pris, "slogans": slogans or list(SLOGANS)}


def save_settings(s: dict) -> None:
    SETTINGS_FILE.write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --------------------------------------------------------------------------
# 数据层：tasks.json 读写、按天归档、跨天顺延
# --------------------------------------------------------------------------

def today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _empty_day(priorities) -> dict:
    return {p["id"]: [] for p in priorities}


def load_tasks(priorities) -> dict:
    """读取任务数据；新的一天自动建档，昨天没做完的顺延到今天。"""
    data = {}
    if TASKS_FILE.exists():
        try:
            data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    key = today_key()
    if key not in data:
        day = _empty_day(priorities)
        prev_days = sorted(k for k in data.keys() if k < key)
        if prev_days:
            prev = data[prev_days[-1]]
            for p in priorities:
                for item in prev.get(p["id"], []):
                    if not item.get("done"):
                        day[p["id"]].append({"t": item.get("t", ""), "done": False})
        if not any(day.values()):
            for p in priorities:
                day[p["id"]] = [{"t": t, "done": False}
                                for t in SEED.get(p["id"], [])]
        data[key] = day
        for old in [k for k in data if k < key][:-KEEP_DAYS] if KEEP_DAYS > 0 else []:
            data.pop(old, None)
        save_tasks(data)
    else:
        # 新增过优先级：给今天补齐空分组
        changed = False
        for p in priorities:
            if p["id"] not in data[key]:
                data[key][p["id"]] = []
                changed = True
        if changed:
            save_tasks(data)
    return data


def save_tasks(data: dict) -> None:
    TASKS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --------------------------------------------------------------------------
# 平台相关原生窗口控制（Windows 版：tkinter 原生能力已足够，无需原生 API）
# --------------------------------------------------------------------------

def _mac_focus():
    """Windows 上 tkinter 的输入框点击即可正常接收键盘，无需额外处理。"""
    pass


def _mac_make_keyable():
    """占位（macOS 专属，Windows 无对应需求）。"""
    pass


def _mac_make_key():
    """占位（macOS 专属，Windows 无对应需求）。"""
    pass


def _mac_pin_windows():
    """占位（macOS 专属；Windows 用 -topmost 即可常驻最上层）。"""
    pass


# --------------------------------------------------------------------------
# 卡通小人（常驻屏幕一侧，悬停拉出 / 双击面板顶栏收起，可拖动）
# --------------------------------------------------------------------------

class Mascot(tk.Toplevel):
    """半透明卡通小人：戴「加油」头巾、举着拳头。

    设计要点：
    * 鼠标**长时间停留**（约 0.6 秒）才拉出面板（防误触）；
      鼠标滑过本身不触发；单击小人不再收起面板。
      悬停是**切换式**的：第一次停留拉出面板，移开后再放回小
      人上停留则收回面板（与「双击面板顶栏 / 点 ✕ / Esc」并列的收回方式）。
    * 悬停时提高不透明度作为反馈；**未悬停时只显示头部，悬停才出现身体并做一个
      举拳泵动的简单动作**；点击时眨眼 + 变亮；
    * 可拖动到屏幕任意位置（位置记入 settings.json，重启后保留）；
    * 画布背景用透明魔法色——没有黑底，只有小人本身；
    * 与面板左右并排、互不遮挡（面板让出 MASCOT_SPAN 宽度）。
    """

    def __init__(self, panel, side):
        super().__init__(panel)
        self.panel = panel
        self.side = side
        self.title("久坐提醒小人")           # 与面板标题区分，便于定位面板窗口
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", MASCOT_ALPHA)
        # Windows：用「透明色」实现只有小人、无背景方块（魔法洋红 MAGIC 被视为完全透明）
        # 该属性在部分 Tk/macOS 组合上不被支持，失败则忽略（退回普通半透明窗口）。
        try:
            self.attributes("-transparentcolor", MAGIC)
        except Exception:
            pass
        self.configure(bg=MAGIC)

        # 画布背景也用魔法色，未绘制区域全部透明
        self.cv = tk.Canvas(self, width=MASCOT_W, height=MASCOT_H,
                            bg=MAGIC, highlightthickness=0, bd=0)
        self.cv.pack()
        self._draw()
        self._set_body(False)            # 默认只显示头部，悬停才出现身体

        sw = panel.SW
        sh = panel.SH
        # 位置：优先用上次拖动保存的位置，其次默认（右缘 55% 高度处）
        saved = panel.settings.get("mascot", {})
        try:
            x = int(saved.get("x"))
            y = int(saved.get("y"))
            x = max(0, min(x, sw - MASCOT_W))
            y = max(0, min(y, sh - MASCOT_H - 90))
        except Exception:
            y = int(sh * 0.5)
            if side == "right":
                x = sw - MASCOT_W - MASCOT_MARGIN
            else:
                x = MASCOT_MARGIN
        self.geometry(f"{MASCOT_W}x{MASCOT_H}+{x}+{y}")

        self.cv.bind("<Button-1>", self._drag_start)
        # Windows 无 Dock：右键小人弹出菜单，可退出程序
        self.cv.bind("<Button-3>", self._popup_menu)
        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="退出久坐提醒", command=self.panel.on_quit)
        self._react_job = None
        self._drag = None
        self._hover_job = None
        # 当前指针是否真正停在小人上（由轮询判定，而非 <Enter>/<Leave> 事件——
        # macOS 面板显隐产生的合成事件会让「离开却没收回身体」漏触发）。
        self._hovering = False
        self._just_dragged = False      # 刚结束拖动：需先离开再悬停才触发面板切换
        self._poll_ms = 120             # 悬停判定轮询间隔（ms）
        self._anim_on = False
        self._anim_off = 0
        self._anim_job = None
        # 用轮询判定指针是否停在小人上：比 <Enter>/<Leave> 可靠，
        # 离开即收身体、回来即显身体，杜绝「鼠标已离开身体却没消失」。
        self.after(200, self._poll_hover)

    # ---------------- 绘制 ----------------

    def _draw(self):
        cv = self.cv
        skin, skin_d = "#FFD9B3", "#E8A87C"
        band, band_d = "#EF4444", "#B91C1C"
        shirt, shirt_d = "#3B82F6", "#2563EB"
        ink = "#374151"

        # 身体与手臂等描边全部改成与填充同色（去掉「边框」感，只留小人形状）。
        # 分组标签：body=躯干+左臂（不悬停时隐藏），arm=右臂+拳头（悬停时泵动），
        # head=头+头巾+脸（始终可见）。
        # 左手（自然下垂）
        cv.create_line(18, 54, 13, 63, fill=shirt, width=7, capstyle=tk.ROUND,
                       tags="body")
        cv.create_oval(9, 61, 17, 69, fill=skin, outline=skin, width=1,
                       tags="body")
        # 身体
        cv.create_oval(13, 44, 43, 72, fill=shirt, outline=shirt, width=1,
                       tags="body")
        # 右手举拳：手臂 + 拳头 + 四指节（悬停泵动）
        cv.create_line(34, 56, 44, 37, fill=shirt, width=7, capstyle=tk.ROUND,
                       tags="arm")
        cv.create_oval(36, 18, 52, 32, fill=skin, outline=skin, width=1,
                       tags="arm")
        for dx in (0, 5, 10):
            cv.create_oval(36 + dx, 13, 41 + dx, 20, fill=skin, outline=skin,
                           width=1, tags="arm")
        # 头（始终可见）
        cv.create_oval(14, 7, 42, 35, fill=skin, outline=skin, width=1,
                       tags="head")
        # 头巾带（横绕额头）+ 「加油」二字
        cv.create_rectangle(12, 10, 44, 19, fill=band, outline=band, width=1,
                            tags="head")
        cv.create_text(28, 14, text="加油", fill="#FFFFFF",
                       font=(FONT, 7, "bold"), tags="head")
        # 头巾结与飘带（左侧）
        cv.create_oval(5, 8, 15, 16, fill=band, outline=band, width=1,
                       tags="head")
        cv.create_polygon(6, 15, 2, 22, 11, 18, fill=band, outline=band,
                          width=1, tags="head")
        cv.create_polygon(9, 14, 8, 23, 15, 17, fill=band, outline=band,
                          width=1, tags="head")
        # 眼睛（常态圆点）
        cv.create_oval(20, 26, 23, 29, fill=ink, tags=("eyes", "head"))
        cv.create_oval(32, 26, 35, 29, fill=ink, tags=("eyes", "head"))
        # 笑眼（点击反馈时显示）
        cv.create_arc(19, 24, 24, 30, start=200, extent=140, style=tk.ARC,
                      outline=ink, width=1.5, tags=("smile", "head"),
                      state=tk.HIDDEN)
        cv.create_arc(31, 24, 36, 30, start=200, extent=140, style=tk.ARC,
                      outline=ink, width=1.5, tags=("smile", "head"),
                      state=tk.HIDDEN)
        # 微笑的嘴
        cv.create_arc(24, 26, 33, 36, start=20, extent=140, style=tk.ARC,
                      outline=ink, width=1.5, tags="head")

    # ---------------- 交互 ----------------

    def _alpha(self, a):
        try:
            self.attributes("-alpha", a)
        except Exception:
            pass

    def _on_click(self, e=None):
        """单击小人：不再收起面板（收回改由双击面板顶栏完成，见 Panel）。

        这里只保留一点点点击反馈，避免「点了没反应」的错觉。
        """
        self._react()

    def _popup_menu(self, e):
        """右键弹出菜单（Windows 无 Dock，用它来退出程序）。"""
        try:
            self._menu.tk_popup(e.x_root, e.y_root)
        except Exception:
            pass

    def _poll_hover(self):
        """每 _poll_ms 轮询一次指针位置，判定是否真正停在小人上。

        比依赖 <Enter>/<Leave> 事件可靠得多：macOS 上面板显隐、拖动等会
        产生合成事件，导致「鼠标离开后身体却没收回」。这里改用「指针是否
        落在小人窗口矩形内」这一权威判定——离开即收身体、回来即显身体，
        不会再出现「离开小人身体不消失」的漏触发。
        """
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        try:
            px, py = self.winfo_pointerx(), self.winfo_pointery()
            mx, my = self.winfo_x(), self.winfo_y()
            # 指针落在小人窗口矩形内（含 2px 容差，避免边缘抖动）
            over = (mx - 2 <= px <= mx + MASCOT_W + 2) and \
                   (my - 2 <= py <= my + MASCOT_H + 2)
        except Exception:
            over = False
        if over and not self._hovering:
            self._hover_begin()
        elif not over and self._hovering:
            self._hover_end()
        self.after(self._poll_ms, self._poll_hover)

    def _hover_begin(self):
        """指针进入小人：提高不透明度、显现身体并做泵动；停留够久才切换面板。"""
        self._hovering = True
        self._alpha(MASCOT_ALPHA_HI)
        self._set_body(True)              # 悬停：身体出现（不悬停时只留头部）
        self._anim_start()
        # 拖动中或刚结束拖动（指针还没真正离开过）：不自动切换面板
        if self._drag or self._just_dragged:
            return
        if self._hover_job:
            try:
                self.after_cancel(self._hover_job)
            except Exception:
                pass
        self._hover_job = self.after(MASCOT_HOVER_MS, self._hover_fire)

    def _hover_end(self):
        """指针离开小人：身体消失、只留头部、恢复半透明；取消面板切换计时。"""
        self._hovering = False
        self._just_dragged = False        # 真正离开过 → 下次再悬停可正常切换面板
        self._set_body(False)             # 离开：身体消失，只留头部
        self._anim_stop()
        self._alpha(MASCOT_ALPHA)
        if self._hover_job:
            try:
                self.after_cancel(self._hover_job)
            except Exception:
                pass
            self._hover_job = None

    def _hover_fire(self):
        """悬停计时到点：面板隐藏则拉出，已显示则收回（再次悬停切换）。

        第一次在小人上停留 → 出现面板；移开后再放回小人上停留
        → 面板收回。满足「悬停出现 / 重新悬停收回」的切换式交互。
        """
        self._hover_job = None
        if self._drag:
            return
        if self.panel.state == "hidden":
            self.panel.show()
        else:
            self.panel.hide()

    def _drag_start(self, e):
        """按住小人：几乎不动（位移<8px）算单击（收起面板），否则拖动小人。"""
        # 按下即取消悬停计时：避免「悬停拉出」与「按下」竞态
        if self._hover_job:
            try:
                self.after_cancel(self._hover_job)
            except Exception:
                pass
            self._hover_job = None
        self._drag = {"x": e.x_root, "y": e.y_root,
                      "wx": self.winfo_x(), "wy": self.winfo_y(),
                      "active": False, "nx": self.winfo_x(), "ny": self.winfo_y()}
        try:
            self.grab_set_global()     # 拖出小人窗口也不丢事件
        except Exception:
            pass
        self.bind_all("<B1-Motion>", self._drag_motion)
        self.bind_all("<ButtonRelease-1>", self._drag_end)

    def _drag_motion(self, e):
        d = self._drag
        if not d:
            return
        dx = e.x_root - d["x"]
        dy = e.y_root - d["y"]
        if not d["active"]:
            if abs(dx) < 8 and abs(dy) < 8:
                return
            d["active"] = True
            # 拖动开始：取消未完成的点击反馈，恢复常态眼睛
            if self._react_job:
                try:
                    self.after_cancel(self._react_job)
                except Exception:
                    pass
                self._react_job = None
            try:
                self.cv.itemconfigure("eyes", state=tk.NORMAL)
                self.cv.itemconfigure("smile", state=tk.HIDDEN)
            except Exception:
                pass
        nx = max(0, min(d["wx"] + dx, self.panel.SW - MASCOT_W))
        ny = max(0, min(d["wy"] + dy, self.panel.SH - MASCOT_H - 90))
        d["nx"], d["ny"] = nx, ny
        self.geometry(f"+{nx}+{ny}")

    def _drag_end(self, e):
        try:
            self.grab_release()
        except Exception:
            pass
        self.unbind_all("<B1-Motion>")
        self.unbind_all("<ButtonRelease-1>")
        d = self._drag
        self._drag = None
        self._just_dragged = True         # 拖动结束：需先离开小人再悬停，才切换面板
        if not d:
            return
        # 位移极小（含「按下即松开」或轻微抖动）→ 视作单击（收起面板）
        net = abs(d["nx"] - d["wx"]) + abs(d["ny"] - d["wy"])
        if (not d["active"]) or net < 8:
            self._on_click()
            return
        # 真正的拖动：把位置持久化，重启后小人还在原地
        try:
            self.panel.settings["mascot"] = {"x": d["nx"], "y": d["ny"]}
            save_settings(self.panel.settings)
        except Exception:
            pass

    def _react(self):
        """点击反馈：眨眼笑 + 短暂变亮，300ms 后恢复。"""
        try:
            self.cv.itemconfigure("eyes", state=tk.HIDDEN)
            self.cv.itemconfigure("smile", state=tk.NORMAL)
            self._alpha(MASCOT_ALPHA_REACT)
        except Exception:
            pass
        if self._react_job:
            try:
                self.after_cancel(self._react_job)
            except Exception:
                pass
        self._react_job = self.after(300, self._react_restore)

    def _react_restore(self):
        self._react_job = None
        try:
            self.cv.itemconfigure("eyes", state=tk.NORMAL)
            self.cv.itemconfigure("smile", state=tk.HIDDEN)
        except Exception:
            pass
        self._alpha(MASCOT_ALPHA)

    def _set_body(self, show):
        """显示/隐藏身体与手臂（不悬停时只留头部）。"""
        st = tk.NORMAL if show else tk.HIDDEN
        for tag in ("body", "arm"):
            try:
                self.cv.itemconfigure(tag, state=st)
            except Exception:
                pass

    def _anim_start(self):
        """开始悬停动作：举起的拳头小幅上下泵动（加油）。"""
        self._anim_on = True
        self._anim_t = 0
        self._anim_off = 0
        self._anim_job = None
        self._anim_body()

    def _anim_body(self):
        if not getattr(self, "_anim_on", False):
            return
        self._anim_t += 1
        off = int(round(3 * math.sin(self._anim_t * 0.4)))
        d = off - self._anim_off
        try:
            self.cv.move("arm", 0, d)
        except Exception:
            pass
        self._anim_off = off
        self._anim_job = self.after(70, self._anim_body)

    def _anim_stop(self):
        self._anim_on = False
        job = getattr(self, "_anim_job", None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._anim_job = None
        # 把拳头复位到原始位置（移动的是隐藏项也安全）
        try:
            self.cv.move("arm", 0, -self._anim_off)
            self._anim_off = 0
        except Exception:
            pass


# --------------------------------------------------------------------------
# 主面板
# --------------------------------------------------------------------------

class Panel(tk.Tk):
    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self.title("久坐提醒")
        _mac_make_keyable()                 # 占位（Windows 下无需特殊处理）
        self.args = args
        self.side = "left" if args.left else "right"
        self.interval_ms = int(args.interval * 60 * 1000)

        self.settings = load_settings()
        self.priorities = self.settings["priorities"]
        self.slogans = self.settings.get("slogans") or list(SLOGANS)
        self.data = load_tasks(self.priorities)
        self.day = today_key()

        self.state = "hidden"          # hidden / showing / shown / hiding
        self.free = False              # 是否被拖到屏幕中间（自由位置）
        self._slide_job = None
        self._slide_pos = None         # 动画内部位置（Tk 9/macOS 下 winfo_x()
                                       # 对完全离屏窗口会返回 clamp 值，不可靠）
        self._welcome_job = None
        self._drag = None              # 任务行拖拽状态
        self._ghost = None             # 拖拽浮动条
        self._drop_line = None         # 拖拽落点指示线
        self._win_drag = None          # 窗口拖动状态
        self._ensure_hidden_job = None # 隐藏兜底定时器：防动画卡住露一半
        self._last_slogan = None
        # 自带点击处理的控件（输入框/＋/✕/勾选/手柄/寄语条）在各自的
        # <Button-1> 里把它置真，使 Panel 级一键分发直接跳过（不抢焦点、不误拖动）。
        # 不依赖 winfo_containing 反查——macOS 的 overrideredirect 窗口里坐标反查
        # 只能精确到 Toplevel 本身，会误把输入框判成空白而抢走焦点。
        self._suppress_blur = False
        self.y_pos = Y0                # 面板当前的顶部 y 坐标
        self._header_h = 52            # 顶栏高度（_layout 内会重新测量）

        self.SW = self.winfo_screenwidth()
        self.SH = self.winfo_screenheight()
        self.max_h = self.SH - Y0 - 90  # 预留底部 Dock 空间

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=C["bg"])

        self.cards = {}                # pid -> 分组卡片 Frame
        self.rows = {}                 # pid -> 行容器 Frame
        self.items = {}                # pid -> [行状态 dict]
        self.desc_vars = {}            # pid -> 标题 StringVar

        self._build_ui()
        self._build_sections()
        self._layout()
        self.y_pos = self._center_y()   # 默认停在屏幕右侧中央

        if self.side == "right":
            self.x_hidden = self.SW                    # 完全移出屏幕
            self.x_shown = self.SW - MASCOT_SPAN - PANEL_W
        else:
            self.x_hidden = -PANEL_W                   # 完全移出屏幕
            self.x_shown = MASCOT_SPAN
        self.geometry(f"{PANEL_W}x{self.H}+{self.x_hidden}+{self.y_pos}")
        self._slide_pos = self.x_hidden
        # 初始即彻底隐藏（withdraw）：Tk 9/macOS 下"屏幕外位置"会被
        # 窗口服务器 clamp 成边缘可见的一条，必须 withdraw 才干净
        self.withdraw()

        # 常驻卡通小人（悬停拉出 / 双击面板顶栏收起 面板）
        self.mascot = Mascot(self, self.side)

        self.bind("<Escape>", lambda e: self.hide())
        # 点击 / 双击面板：顶栏区域单击拖动、双击收起；其余区域点空白退出编辑、
        # 点输入框进入编辑。双击用 Panel 级 <Double-1>，靠屏幕坐标判断是否在
        # 顶栏内，避免 Tk 把第二下 press 合成 Double-1 后漏判。
        self.bind("<Button-1>", self._on_button1)
        self.bind("<Double-1>", self._on_double1)
        self.bind_all("<MouseWheel>", self._on_wheel)
        # Windows 无 Dock：右键面板也可退出程序
        self.bind("<Button-3>", self._panel_popup)
        self._pmenu = tk.Menu(self, tearoff=0)
        self._pmenu.add_command(label="退出久坐提醒", command=self.on_quit)

        self._tick_time()
        self._schedule_hourly()
        self._keep_top()               # 定时重申置顶（当前桌面内始终最上）
        self.after(1000, _mac_pin_windows)   # 占位：Windows 下为空操作
        if not WELCOME_FILE.exists():
            self.after(800, self._first_run)   # 首次启动：亮明身份
        if args.now:
            self.after(400, self.show)

    # ---------------- UI 框架 ----------------

    def _build_ui(self):
        main = tk.Frame(self, bg=C["bg"])
        main.pack(fill=tk.BOTH, expand=True)
        self.main = main              # 供 _layout 测量内容高度（不受 Toplevel geometry 钳制）

        # 顶部标题栏（按住可拖动整个面板到屏幕任意位置；双击收起面板）。
        # 整条顶栏用略深的 header_bg，让用户一眼看清「有效双击/抓握区」在哪。
        header = tk.Frame(main, bg=C["header_bg"], cursor="fleur")
        header.pack(fill=tk.X, padx=14, pady=(12, 8))
        tk.Label(header, text="⏰ 久坐提醒", font=(FONT, 13, "bold"),
                 bg=C["header_bg"], fg=C["text"]).pack(side=tk.LEFT)
        self.clock = tk.Label(header, text="", font=(FONT, 10),
                              bg=C["header_bg"], fg=C["sub"])
        self.clock.pack(side=tk.LEFT, padx=(8, 0), pady=(3, 0))
        # 右上角圆形 ✕：整圆（含圆外方形热区）点击都收起面板，比裸 ✕ 更易点中
        self._mk_close_btn(header).pack(side=tk.RIGHT, padx=(0, 2))
        # 双击顶栏收起面板改由 Panel 级 <Button-1> 手动判定（见 _on_button1），
        # 这样「只有双击顶部边框才会收回，其余区域双击不会收回」，且不再受
        # 拖动抓取吞掉第二次点击的影响。
        self.header = header

        # 中间：所有优先级（含 P1）统一放进同一个可滚动区域。
        # 滚轮下拉时 P1 与其余优先级一起向上滚动（不再有「P1 固定不动」的分区）。
        wrap = tk.Frame(main, bg=C["bg"])
        wrap.pack(fill=tk.BOTH, expand=True, padx=8)

        # 全部优先级：可滚动区域（P1 也在这里，随内容一起滚动）
        self.canvas = tk.Canvas(wrap, bg=C["bg"], highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self._win = self.canvas.create_window((0, 0), window=None, anchor="nw")
        self.scroll_inner = tk.Frame(self.canvas, bg=C["bg"])
        self.canvas.itemconfigure(self._win, window=self.scroll_inner)
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(
                self._win, width=max(e.width, PANEL_W - 16)),
        )
        def _on_inner_configure(e=None):
            try:
                bbox = self.canvas.bbox("all")
                if bbox:
                    self.canvas.configure(scrollregion=bbox)
                else:
                    self._refresh_canvas()
            except Exception:
                pass
        self.scroll_inner.bind("<Configure>", _on_inner_configure)
        # 「＋ 新增优先级」放在列表最下方；仅文字区可点击，右侧空白点击不触发
        add_row = tk.Frame(wrap, bg=C["bg"])
        add_row.pack(side=tk.BOTTOM, fill=tk.X, pady=(2, 0))
        self.add_bar = tk.Label(add_row, text="＋ 新增优先级", font=(FONT, 10),
                                bg=C["bg"], fg=C["sub"], cursor="plus",
                                anchor="w", padx=6, pady=3)
        self.add_bar.pack(side=tk.LEFT, padx=(2, 0))
        self.add_bar.bind("<Button-1>",
                           lambda e: (setattr(self, "_suppress_blur", True),
                                      self.add_priority()))
        self.add_bar._interactive = True

        # 最下方：防久坐提醒（大字一行 + 深色底板上的寄语）。
        # 必须 side=BOTTOM：main 中间的 wrap 用了 expand=True 会吞噬剩余空间，
        # 若 banner 用默认 side=TOP 就会被推到 main 底边之外（溢出窗口、看不见）。
        # 用 side=BOTTOM 把它钉在 main 底部，独立于 P 内容，不进滚动区、不随 P 增删变长。
        banner = tk.Frame(main, bg=C["banner_bg"],
                          highlightbackground="#FED7AA", highlightthickness=1)
        banner.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(4, 12))
        tk.Label(banner, text="不要久坐！起来活动 5 分钟",
                 font=(FONT, 15, "bold"), bg=C["banner_bg"], fg=C["banner_fg"]
                 ).pack(anchor="w", padx=12, pady=(10, 6))
        plate = tk.Frame(banner, bg=C["plate_bg"], cursor="hand2")
        plate.pack(fill=tk.X, padx=12, pady=(0, 10))
        # 当前寄语直接可编辑：单击进入编辑当前这句（替换它），回车/点别处保存；
        # 点这条深色底板的其它空白区域则新增一句（保留「随时添加」能力）。
        self.tip_var = tk.StringVar()
        self.tip = tk.Entry(plate, textvariable=self.tip_var, font=(FONT, 12),
                            bg=C["plate_bg"], fg=C["plate_fg"], relief=tk.FLAT,
                            bd=0, highlightthickness=0,
                            insertbackground=C["plate_fg"], cursor="xterm", width=24)
        self.tip.pack(anchor="w", padx=10, pady=7)
        self._cur_slogan = ""
        # 单击寄语 → 进入编辑（标记抑制 Panel 级失焦，聚焦 + 变 key window）
        self.tip.bind("<Button-1>",
                      lambda e: (setattr(self, "_suppress_blur", True),
                                 self.tip.focus_set(), _mac_focus()))
        # 编辑结束（回车 / 失焦）→ 保存到 slogans 并持久化
        self.tip.bind("<FocusOut>", lambda e: self._tip_commit())
        self.tip.bind("<Return>",
                      lambda e: (self._tip_commit(),
                                 self.tk.call("focus", "none")))
        # 点深色底板（非寄语输入框）→ 弹框新增一句寄语
        plate.bind("<Button-1>",
                   lambda e: (setattr(self, "_suppress_blur", True),
                              None if e.widget is self.tip else self._add_slogan()))
        plate._interactive = True          # 视为自带点击控件，空白点击逻辑跳过它

    def _mk_btn(self, parent, text, color, cmd, cursor="hand2"):
        b = tk.Label(parent, text=text, bg=parent["bg"], fg=color,
                     font=(FONT, 14), cursor=cursor, padx=10, pady=4)
        def _h(e):
            self._suppress_blur = True
            cmd()
        b.bind("<Button-1>", _h)
        b._interactive = True          # 自带点击处理：空白点击/拖动时应跳过它
        return b

    def _mk_close_btn(self, parent):
        """右上角 X 收起按钮（无可见背景块）。

        不加圆角长方形底，X 直接落在顶栏灰底上；左侧保留一条浅浅的竖线与前面
        文字隔开。可点击区域尽量宽、尽量高，覆盖整条顶栏右侧，让用户在红色框
        标注的整个区域内任意位置单击都能收回面板。自身 <Button-1> 设
        ``_suppress_blur`` 并返回 "break"，避免事件继续冒泡到顶栏拖动逻辑。
        """
        W, H = 120, 30                # 更宽更高，覆盖顶栏右侧大部分区域
        cv = tk.Canvas(parent, width=W, height=H, bg=C["header_bg"],
                       highlightthickness=0, cursor="hand2")
        # 先铺一层与顶栏同色的透明填充，确保 Canvas 任意位置都能收到点击事件
        hit = cv.create_rectangle(0, 0, W, H, fill=C["header_bg"], outline="")
        pad = 2
        x1, y1, x2, y2 = pad, pad, W - pad, H - pad
        # 左侧一条浅浅的竖线，与前面文字隔开
        dvx = x1 + 10
        cv.create_line(dvx, y1 + 6, dvx, y2 - 6, fill="#C7CED8", width=1)
        # ✕ 居中于竖线右侧区域
        cx = (dvx + x2) / 2 + 1
        txt = cv.create_text(cx, H / 2 + 1, text="✕",
                             fill=C["sub"], font=(FONT, 18, "bold"))
        cv._interactive = True           # 自带点击处理：空白点击/拖动时应跳过它
        def _h(e):
            self._suppress_blur = True
            self.hide()
            return "break"
        cv.bind("<Button-1>", _h)          # Canvas 全局点击
        for item in (hit, txt):
            cv.tag_bind(item, "<Button-1>", _h)  # 各子图元也绑，防止漏接
        return cv

    # ---------------- 分组与行 ----------------

    def _fg_of(self, pid):
        for i, p in enumerate(self.priorities):
            if p["id"] == pid:
                return PALETTE_FG[i % len(PALETTE_FG)]
        return C["sub"]

    def _bg_of(self, pid):
        for i, p in enumerate(self.priorities):
            if p["id"] == pid:
                return PALETTE_BG[i % len(PALETTE_BG)]
        return C["card"]

    def _build_sections(self, commit=True):
        """按当前优先级结构重建全部分组。

        commit=True 时先把界面上未保存的编辑写回模型（增删优先级用）；
        跨天重建传 False（新一天的模型已由 load_tasks 准备好，不能拿旧行覆盖）。
        """
        if commit:
            self._commit_all()
        for card in list(self.cards.values()):
            try:
                card.destroy()
            except Exception:
                pass
        self.cards, self.rows, self.items, self.desc_vars = {}, {}, {}, {}
        for p in self.priorities:
            # 所有优先级（含 P1）都进入同一个滚动区，统一滚动
            parent = self.scroll_inner
            self._build_section(p, parent)
        self._resize()

    def _commit_all(self):
        for p in self.priorities:
            for st in list(self.items.get(p["id"], [])):
                self._commit(st)

    def _build_section(self, p, parent=None):
        pid = p["id"]
        if parent is None:
            parent = self.scroll_inner
        fg, bg = self._fg_of(pid), self._bg_of(pid)
        card = tk.Frame(parent, bg=C["card"],
                        highlightbackground=C["line"], highlightthickness=1)
        card.pack(fill=tk.X, padx=2, pady=4)
        self.cards[pid] = card

        head = tk.Frame(card, bg=bg)
        head.pack(fill=tk.X)
        tk.Label(head, text=p["tag"], font=(FONT, 10, "bold"),
                 bg=bg, fg=fg).pack(side=tk.LEFT, padx=(8, 2), pady=5)
        # 标题文字：可直接点击编辑
        var = tk.StringVar(value=p["desc"])
        self.desc_vars[pid] = var
        ent = tk.Entry(head, textvariable=var, font=(FONT, 9), relief=tk.FLAT,
                       bd=0, bg=bg, fg=fg, highlightthickness=0, insertbackground=fg)
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=3)
        ent.bind("<FocusOut>", lambda e, pr=p: self._desc_commit(pr))
        ent.bind("<Return>", lambda e, pr=p: (self._desc_commit(pr), self.focus_set()))
        ent.bind("<FocusIn>", lambda e: _mac_focus())
        # 点击标题输入框直接进入编辑：标记抑制 Panel 级空白失焦（macOS 坐标反查不可靠）
        ent.bind("<Button-1>", lambda e: self._entry_click())
        # 添加任务（plus 光标）/ 删除该优先级（X 光标，与删除任务区分）
        self._mk_btn(head, "＋", C["sub"], lambda: self.add_task(pid),
                     cursor="plus").pack(side=tk.RIGHT, padx=(0, 2))
        self._mk_btn(head, "✕", "#C9CDD3", lambda: self.remove_priority(pid),
                     cursor="X_cursor").pack(side=tk.RIGHT, padx=(0, 6))

        body = tk.Frame(card, bg=C["card"])
        body.pack(fill=tk.X, padx=6, pady=(2, 6))
        self.rows[pid] = body
        self.items[pid] = []
        for it in self.data[self.day].get(pid, []):
            self._add_row(pid, it["t"], it.get("done", False))

    def _add_row(self, pid, text="", done=False):
        fg = self._fg_of(pid)
        row = tk.Frame(self.rows[pid], bg=C["card"])
        row.pack(fill=tk.X, pady=1)
        # 拖拽手柄
        handle = tk.Label(row, text="⋮⋮", width=2, bg=C["card"], fg="#C0C4CC",
                          cursor="fleur", font=(FONT, 10))
        handle.pack(side=tk.LEFT)
        handle._interactive = True
        chk = tk.Label(row, text="✓" if done else "○", width=2, bg=C["card"],
                       fg=fg if done else "#C0C4CC", cursor="hand2",
                       font=(FONT, 11, "bold"))
        chk.pack(side=tk.LEFT)
        chk._interactive = True
        var = tk.StringVar(value=text)
        entry = tk.Entry(row, textvariable=var, font=(FONT, 11),
                         relief=tk.FLAT, bd=0, bg=C["card"],
                         fg=C["text"] if not done else "#9CA3AF",
                         insertbackground=C["accent"], highlightthickness=0)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        if done:
            entry.configure(font=(FONT, 11, "overstrike"))
        dele = tk.Label(row, text="✕", bg=C["card"], fg="#D1D5DB",
                        cursor="X_cursor", font=(FONT, 13), padx=8, pady=2)
        dele.pack(side=tk.RIGHT, padx=(6, 2))
        dele._interactive = True
        st = {"pid": pid, "row": row, "entry": entry, "var": var,
              "chk": chk, "done": done}
        chk.bind("<Button-1>",
                 lambda e, s=st: (setattr(self, "_suppress_blur", True),
                                  self.toggle_done(s)))
        dele.bind("<Button-1>",
                  lambda e, s=st: (setattr(self, "_suppress_blur", True),
                                   self.remove_row(s)))
        handle.bind("<Button-1>",
                    lambda e, s=st: (setattr(self, "_suppress_blur", True),
                                     self._row_drag_start(e, s)))
        entry.bind("<FocusOut>", lambda e, s=st: self._focus_out(s))
        entry.bind("<Return>", lambda e, s=st: (self._commit(s), self.focus_set()))
        entry.bind("<FocusIn>", lambda e: _mac_focus())
        # 点内容行直接编辑：标记抑制 Panel 级空白失焦，避免刚获焦点被抢走
        entry.bind("<Button-1>", lambda e, s=st: self._entry_click(s))
        self.items[pid].append(st)
        self._resize()
        return st

    # ---------------- 布局与尺寸 ----------------

    def _layout(self):
        """测量外壳高度，再按内容高度设置滚动区与窗口。"""
        self.update_idletasks()
        self._header_h = max(40, self.header.winfo_reqheight())
        # 把滚动区压到 1px，让 P1 + 标题栏 + 横幅等「固定外壳」测得真实高度
        self.canvas.configure(height=1)
        self.update_idletasks()
        # 外壳高度 = 标题栏 + 滚动区(1px) + 新增优先级 + 提醒横幅
        # （P1 已并入滚动区，不再单独占固定高度）
        # 用 main 的 reqheight（始终反映内容真实需要，不受 _resize 设过的 geometry 钳制），
        # 避免反复测量时把 banner 漏算进外壳高度。
        self.chrome_h = self.main.winfo_reqheight() - 1
        self._resize()

    def _rel_y(self, w):
        """返回 w 相对 scroll_inner 的纵向偏移（不依赖屏幕映射，withdraw 下也准）。"""
        y = 0
        cur = w
        while cur is not None and cur is not self.scroll_inner:
            try:
                y += cur.winfo_y()
            except Exception:
                break
            cur = cur.master
        return y

    def _resize(self):
        if not hasattr(self, "chrome_h"):
            return
        self.update_idletasks()
        # 全部优先级（含 P1）的总高度。视口封顶在 VIEW_CAP：内容少则面板随之变短，
        # 内容多则停在 VIEW_CAP 高度、改用滚轮下拉——绝不让面板随内容无限变长。
        full = self.scroll_inner.winfo_reqheight()
        canvas_h = max(80, min(full, VIEW_CAP))
        self.canvas.configure(height=canvas_h)
        self.H = self.chrome_h + canvas_h
        # 高度变化后重新夹紧纵向位置，避免面板底部超出屏幕
        self.y_pos = max(Y0, min(self.y_pos, self.SH - self.H - 90))
        self.geometry(f"{PANEL_W}x{self.H}+{self._cur_x()}+{self.y_pos}")
        # 每次重算都强制对齐滚动区，避免 withdraw/deiconify 后内容空白一会儿
        self._refresh_canvas()

    def _refresh_canvas(self, retries=3):
        """强制把滚动区窗口项与 scrollregion 对齐到当前真实几何。

        withdraw/deiconify 循环下，scroll_inner 的 ``<Configure>`` 可能未及时触发，
        导致 scrollregion 停在旧值（甚至 ``(0,0,0,0)``），面板出现时内容「空白一会儿
        才冒出来」。这里按当前真实几何显式重算，并在几何未稳时主动重试。
        """
        try:
            # 必须同时更新 canvas 与 inner，否则读到的尺寸可能是旧值
            self.canvas.update_idletasks()
            self.scroll_inner.update_idletasks()
            w = self.canvas.winfo_width()
            if w < 10:
                w = PANEL_W - 16
            h = self.scroll_inner.winfo_reqheight()
            if h < 10 and retries > 0:
                # inner 还没 layout 好，稍后再试一次
                self.after(50, lambda: self._refresh_canvas(retries - 1))
                return
            self.canvas.itemconfigure(self._win, width=w)
            self.canvas.configure(scrollregion=(0, 0, w, max(h, 1)))
            # 确保视图回到顶部，避免上次滚动残留导致新窗口内容被卷走
            self.canvas.yview_moveto(0.0)
        except Exception:
            pass

    def _schedule_refreshes(self):
        """show() 后分阶段再刷新几次滚动区，彻底杜绝间歇性空白。"""
        for ms in (50, 150, 300):
            self.after(ms, self._refresh_canvas)

    def _center_y(self):
        """面板在屏幕右侧的纵向中心位置（内容过高则贴顶，保证完整可见）。"""
        if not getattr(self, "H", 0):
            return Y0
        top = (self.SH - self.H) // 2
        top = max(Y0, top)
        limit = self.SH - self.H - 40
        if top > limit:
            top = Y0
        return top

    # ---------------- 任务编辑 ----------------

    def add_task(self, pid):
        st = self._add_row(pid)
        st["entry"].focus_set()
        # 新行可能加在滚动区外：滚入视野并短暂高亮
        self.after_idle(lambda: self._reveal_row(st))
        return st

    def _reveal_row(self, st):
        """把新行滚入可视区域，并高亮 400ms 作为反馈。"""
        try:
            row = st["row"]
            if not row.winfo_exists():
                return
            # 所有优先级（含 P1）都在同一滚动区，新行若超出视口则滚入视野
            self.canvas.update_idletasks()
            bottom = self._rel_y(row) + row.winfo_height()
            if bottom > self.canvas.winfo_height():
                self.canvas.yview_moveto(1.0)      # 新行在最后，滚到底即可
            for w in (row, st["entry"]):
                w.configure(bg=C["drag_bg"])
            self.after(400, self._restore_row_bg, st)
        except Exception:
            pass

    def _scroll_cancel(self):
        j = getattr(self, "_scroll_job", None)
        if j:
            try:
                self.after_cancel(j)
            except Exception:
                pass
            self._scroll_job = None

    def _scroll_animate(self, target):
        """平滑滚动到 target 比例位置（0=顶，1=底），约 260ms 滑到位。"""
        cur = self.canvas.yview()[0]
        if abs(target - cur) < 0.001:
            self.canvas.yview_moveto(target)
            return
        steps, step_ms = 12, 22

        def step(i):
            f = cur + (target - cur) * ((i + 1) / steps)
            self.canvas.yview_moveto(f)
            if i + 1 < steps:
                self._scroll_job = self.after(step_ms, step, i + 1)
            else:
                self._scroll_job = None

        self._scroll_job = self.after(step_ms, step, 0)

    def _rebuild_scroll(self, new_pid=None, was_at_bottom=False, old_frac=0.0):
        """重建优先级后决定滚动位置（不再盲目跳顶 / 向上滚）。

        - 全部内容已可见：停在顶部（此时本就该全部显示）。
        - 新增且「之前已在底部」：直接停在最底，露出新优先级，不向上滚一遍。
        - 新增且不在底部：平滑跳到新优先级卡片（底部对齐）。
        - 删除（无 new_pid）：保持删除前的浏览比例，位置不跳动。
        """
        self._scroll_cancel()
        self.canvas.update_idletasks()
        total = self.scroll_inner.winfo_reqheight()
        view = self.canvas.winfo_height()
        if total <= view:
            self.canvas.yview_moveto(0.0)
            return
        if new_pid is not None:
            if was_at_bottom:
                # 已在底部新增 → 直接停最底（新优先级恰好在末尾），不再向上滚一遍
                self.canvas.yview_moveto(1.0)
                return
            card = self.cards.get(new_pid)
            if card and card.winfo_exists():
                y = self._rel_y(card)
                h = card.winfo_height() or card.winfo_reqheight()
                frac = (y + h - view) / (total - view)
                frac = max(0.0, min(1.0, frac))
                self._scroll_animate(frac)
            return
        # 删除：保持删除前的浏览比例，避免突然回到顶部造成「向上滚动」
        self.canvas.yview_moveto(min(max(old_frac, 0.0), 1.0))

    def _restore_row_bg(self, st):
        try:
            if st["row"].winfo_exists():
                st["row"].configure(bg=C["card"])
                st["entry"].configure(bg=C["card"])
        except Exception:
            pass

    def remove_row(self, st):
        try:
            self.items[st["pid"]].remove(st)
        except ValueError:
            return
        st["row"].destroy()
        self._persist()
        self._resize()

    def toggle_done(self, st):
        st["done"] = not st["done"]
        st["chk"].configure(text="✓" if st["done"] else "○",
                            fg=self._fg_of(st["pid"]) if st["done"] else "#C0C4CC")
        st["entry"].configure(
            font=(FONT, 11, "overstrike") if st["done"] else (FONT, 11),
            fg="#9CA3AF" if st["done"] else C["text"])
        self._persist()

    def _commit(self, st):
        if not st["row"].winfo_exists():
            return
        if not st["var"].get().strip():
            self.remove_row(st)      # 空内容视为放弃新增
            return
        self._persist()

    def _focus_out(self, st):
        self._commit(st)

    # 输入说明：本程序是常规应用（出现在 Dock 栏），macOS 会把键盘交给
    # 被点击的窗口——点任务行/标题直接打字即可，回车或点别处保存。

    def _blur(self):
        """把键盘焦点从当前输入框移开，消除编辑光标（光标停止闪烁）。

        对 overrideredirect 窗口直接 ``self.focus_set()`` 常常是空操作
        （Tk 无法把焦点交给没有窗口管理装饰的顶层窗口），导致「点空白
        退出编辑」失效、光标一直闪。用 Tcl 的 ``focus none`` 让 Tk 显式
        丢掉焦点，是最可靠的「失焦」方式；失败再退回 focus_set。
        """
        try:
            self.tk.call("focus", "none")
        except Exception:
            try:
                self.focus_set()
            except Exception:
                pass

    def _on_click_blank(self, e):
        """点击面板非交互区域（空白/边框）→ 退出编辑状态（光标停止闪烁）。

        输入框/＋/✕/勾选/手柄/寄语条等自带点击处理的控件，在各自的
        ``<Button-1>`` 绑定里已把 ``_suppress_blur`` 置真，使 ``_on_button1``
        直接 return，本函数根本不会被调用，故不会抢它们的焦点。
        """
        self._blur()

    def _entry_click(self, st=None):
        """点输入框 → 直接进入编辑，并抑制 Panel 级空白失焦/拖动。

        关键：在控件自身的 <Button-1> 里先把 ``_suppress_blur`` 置真，
        等事件冒泡到 Panel 级 _on_button1 时读到即跳过，
        这样刚刚获得的焦点不会被 ``focus none`` 抢走（这是此前进不了编辑的根因）。
        """
        self._suppress_blur = True
        if st is not None:
            st["entry"].focus_set()
        _mac_focus()

    def _header_bounds(self):
        """顶栏「有效双击/拖动区」的下边界（含条带上方的细小间隙与下方 pady）。

        返回 ``(bot_rel, bot_root)``：相对面板顶部的像素、相对屏幕顶部的像素。
        上边界取面板顶端，下边界取到加深条带底部 + 其下 pady——让**整条顶部边框**
        （含条带上方的间隙）都能可靠触发，不必再精确找位置。
        事件若落在顶栏内子控件（标题/✕）上，``e.y`` 是相对子控件的，这里统一用
        面板/屏幕坐标，确保顶栏内任意位置的双击都被识别。
        """
        try:
            top_root = self.header.winfo_rooty()
            h = self.header.winfo_height()
            gap = 8                       # 条带下方 pady，一并纳入有效区
            bot_rel = (top_root - self.winfo_rooty()) + h + gap
            return bot_rel, top_root + h + gap
        except Exception:
            hh = getattr(self, "_header_h", 52)
            return hh, self.winfo_rooty() + hh

    def _on_button1(self, e):
        """统一一键分发：

        * 顶栏区域（含边框及其上的 ✕/＋/标题）：单击 → 退出编辑并准备拖动；
          真正的双击由 Panel 级 ``<Double-1>`` 处理，不再依赖两次
          ``<Button-1>`` 的人工计时（Tk 的第二下 press 会被合成为
          ``<Double-1>``，导致人工判定频频漏掉）。
        * 其余空白区域：点击 → 退出编辑。
        * 自带点击处理的控件（输入框/＋/✕/勾选/手柄/寄语条）在各自 <Button-1>
          里把 ``_suppress_blur`` 置真，本函数读到就跳过拖动/失焦，交给它们自己。
        """
        # 顶栏区域（整条顶部边框，含加深条带上方的细小间隙）：单击退出编辑并准备拖动；
        # 双击收起交给 _on_double1。用 _header_bounds 精确匹配实际加深条带的下边界。
        bot_rel, _ = self._header_bounds()
        if e.y <= bot_rel:
            # 点到 ✕/＋ 等自带处理控件 → 交给它自己（不抢焦点、不拖动）
            if getattr(self, "_suppress_blur", False):
                self._suppress_blur = False
                return
            self._blur()                # 点顶部边框也退出编辑状态
            self._win_drag_start(e)     # 顶栏空白处：拖动面板
            return
        # 非顶栏：自带点击控件已通过 suppress 提前跳过；其余空白退出编辑
        if getattr(self, "_suppress_blur", False):
            self._suppress_blur = False
            return
        self._on_click_blank(e)

    def _on_double1(self, e):
        """双击面板顶栏 → 收起面板。

        事件可能来自顶栏内的任意子控件（标题、✕ 等），此时 ``e.y`` 是相对
        于该子控件的，不能直接用 ``e.y < _header_h``。这里用顶栏**实际可见条带**
        的下边界（屏幕坐标）比较，精确匹配用户看到的加深区域，不再用
        「窗口顶 + _header_h」的近似（会因 pady 偏移而错位，导致要找多处才生效）。
        """
        _, bot_root = self._header_bounds()
        if e.y_root > bot_root:
            return                      # 只有顶部边框条带内双击才收起
        self._win_drag_cancel()         # 清理单击时可能残留的拖动状态
        self.hide()

    def _persist(self):
        for p in self.priorities:
            pid = p["id"]
            self.data[self.day][pid] = [
                {"t": s["var"].get().strip() or "未命名任务", "done": s["done"]}
                for s in self.items.get(pid, [])
            ]
        save_tasks(self.data)

    # ---------------- 优先级标题编辑 / 增删 ----------------

    def _desc_commit(self, p):
        pid = p["id"]
        txt = self.desc_vars[pid].get().strip()
        if not txt:
            self.desc_vars[pid].set(p["desc"])   # 清空则还原
            return
        if txt != p["desc"]:
            p["desc"] = txt
            self.settings["priorities"] = self.priorities
            save_settings(self.settings)

    def add_priority(self):
        ids = {p["id"] for p in self.priorities}
        tags = {p["tag"] for p in self.priorities}
        i = len(self.priorities) + 1
        while f"p{i}" in ids:
            i += 1
        j = len(self.priorities) + 1
        while f"P{j}" in tags:
            j += 1
        new = {"id": f"p{i}", "tag": f"P{j}", "desc": "新优先级"}
        self.priorities.append(new)
        self.data[self.day][new["id"]] = []
        self.settings["priorities"] = self.priorities
        save_settings(self.settings)
        # 新增前先在旧几何上判断「是否已滚动到底部」：用 yview()[1]（视口底部分数，
        # 到底时为 ~1.0）；注意不能用 yview()[0]（视口顶部，到底时也远小于 1，会误判）。
        was_at_bottom = (self.canvas.yview()[1] >= 0.999) \
            if self.canvas.winfo_exists() else True
        self._build_sections()
        self._persist()
        # 新增后：已在底部则停在最底（直接露出新优先级，不向上滚一遍）；
        # 否则页面平滑跳到新增加的优先级部分。
        self.after_idle(lambda: self._rebuild_scroll(
            new_pid=new["id"], was_at_bottom=was_at_bottom))

    def remove_priority(self, pid):
        if len(self.priorities) <= 1:
            messagebox.showinfo("久坐提醒", "至少需要保留一个优先级。")
            return
        tasks = self.data[self.day].get(pid, [])
        if tasks and not messagebox.askyesno(
                "久坐提醒",
                f"该优先级下还有 {len(tasks)} 条任务，删除后会一并删除，确定吗？"):
            return
        self.priorities = [p for p in self.priorities if p["id"] != pid]
        self.data[self.day].pop(pid, None)
        self.settings["priorities"] = self.priorities
        save_settings(self.settings)
        # 删除前记录当前浏览比例，删除后保持同一位置（不向上滚动）
        old_frac = self.canvas.yview()[0] if self.canvas.winfo_exists() else 0.0
        self._build_sections()
        self._persist()
        self.after_idle(lambda: self._rebuild_scroll(old_frac=old_frac))

    # ---------------- 拖拽：把任务拖到其他优先级下 ----------------

    def _row_drag_start(self, e, st):
        self._cancel_slide()
        self._drag = {"st": st, "x": e.x_root, "y": e.y_root,
                      "off": e.y_root - st["row"].winfo_rooty(), "active": False}
        try:
            self.grab_set_global()     # 拖出窗口也不丢事件
        except Exception:
            pass
        self.bind_all("<B1-Motion>", self._row_drag_motion)
        self.bind_all("<ButtonRelease-1>", self._row_drag_end)

    def _row_drag_motion(self, e):
        d = self._drag
        if not d:
            return
        if not d["active"]:
            if abs(e.x_root - d["x"]) < 6 and abs(e.y_root - d["y"]) < 6:
                return
            d["active"] = True
            # 原行留位高亮，提示“正在拖这一行”
            row = d["st"]["row"]
            for w in (row, *row.winfo_children()):
                try:
                    w.configure(bg=C["drag_bg"])
                except Exception:
                    pass
            # 浮动幽灵条：必须是 self 的直接子节点才能 place（Tk 不允许
            # 把深层子控件 place 到祖先窗口上），跟随指针移动
            self._ghost = tk.Frame(self, bg=C["drag_bg"], height=26,
                                   highlightbackground=C["accent"], highlightthickness=1)
            tk.Label(self._ghost, text="  " + d["st"]["var"].get(),
                     font=(FONT, 11), bg=C["drag_bg"], fg=C["text"],
                     anchor="w").pack(fill="both", expand=True)
            self._ghost.place(x=10, width=PANEL_W - 20)
            self._drop_line = tk.Frame(self, bg=C["accent"], height=2)
        # 幽灵条跟随指针（垂直居中）
        self._ghost.place_configure(y=e.y_root - 13 - self.winfo_rooty())
        self._update_drop_target(e)

    def _update_drop_target(self, e):
        pid, idx, y_line = self._hit_test(e, self._drag["st"])
        if pid is None or self._drop_line is None:
            if self._drop_line:
                self._drop_line.place_forget()
            return
        card = self.cards[pid]
        self._drop_line.place(in_=card, x=10, y=y_line - card.winfo_rooty(),
                              width=card.winfo_width() - 20)
        self._drop_line.lift()

    def _hit_test(self, e, dragged):
        """返回 (目标pid, 插入序号, 指示线绝对y)；不在任何分组上返回 (None, 0, 0)。"""
        for p in self.priorities:
            card = self.cards[p["id"]]
            top = card.winfo_rooty()
            if not (top - 2 <= e.y_root <= top + card.winfo_height() + 2):
                continue
            pid = p["id"]
            idx = 0
            y_line = self.rows[pid].winfo_rooty()
            for st in self.items[pid]:
                if st is dragged:
                    continue
                rtop = st["row"].winfo_rooty()
                rh = st["row"].winfo_height()
                if e.y_root > rtop + rh // 2:
                    idx += 1
                    y_line = rtop + rh
                else:
                    break
            return pid, idx, y_line
        return None, 0, 0

    def _row_drag_end(self, e):
        try:
            self.grab_release()
        except Exception:
            pass
        self.unbind_all("<B1-Motion>")
        self.unbind_all("<ButtonRelease-1>")
        d = self._drag
        self._drag = None
        if self._ghost:
            try:
                self._ghost.destroy()
            except Exception:
                pass
            self._ghost = None
        if self._drop_line:
            try:
                self._drop_line.destroy()
            except Exception:
                pass
            self._drop_line = None
        if not d or not d["active"]:
            return                          # 只是单击，没有拖动

        st = d["st"]
        src = st["pid"]
        pid, idx, _ = self._hit_test(e, st)
        if pid is None:
            pid = src                      # 拖到面板外：放回原分组

        # 先把源/目标两组未保存的编辑写回模型，再按行序号取出任务
        # （注意用 st2，避免遮蔽外层的 st）
        for gid in {src, pid}:
            for st2 in list(self.items.get(gid, [])):
                self._commit(st2)
        if st not in self.items.get(src, []):
            return
        k = self.items[src].index(st)
        task = self.data[self.day][src].pop(k)
        self.data[self.day].setdefault(pid, [])
        idx = max(0, min(idx, len(self.data[self.day][pid])))
        self.data[self.day][pid].insert(idx, task)

        self._rebuild_section(src)
        if pid != src:
            self._rebuild_section(pid)
        self._persist()

    def _rebuild_section(self, pid):
        """按数据模型重建该分组的所有行。

        约定：模型必须已经是最新的（调用方负责先 commit/修改），这里既不 commit
        也不 persist——部分重建时全量 persist 会拿其他分组的旧行覆盖模型。
        需要落盘时由调用方统一 _persist()。
        """
        for st in list(self.items.get(pid, [])):
            try:
                st["row"].destroy()
            except Exception:
                pass
        self.items[pid] = []
        for it in self.data[self.day].get(pid, []):
            self._add_row(pid, it["t"], it.get("done", False))
        self._resize()

    # ---------------- 拖动：把整个面板拖到屏幕任意位置 ----------------

    def _win_drag_cancel(self):
        """取消正在准备的窗口拖动（双击顶栏收起前清理，避免残留抓取）。"""
        d = self._win_drag
        self._win_drag = None
        if d:
            if d.get("job"):                # 取消可能尚未执行的 geometry flush
                try:
                    self.after_cancel(d["job"])
                except Exception:
                    pass
            if d.get("grabbed"):            # 双击第一下若有轻微移动已抓取，需释放
                try:
                    self.grab_release()
                except Exception:
                    pass
        self.unbind_all("<B1-Motion>")
        self.unbind_all("<ButtonRelease-1>")

    def _win_drag_start(self, e):
        """按住标题栏拖动面板。移动 <5px 视为点击（仍可退出编辑状态）。

        注意：全局指针抓取（grab）必须**延迟到真正开始拖动**时才设置，
        不能在按下瞬间就 grab。否则双击顶栏时第一次按下的 grab 会吞掉
        后续的第二次点击 / 合成出的 <Double-1>，导致「双击收不回 / 收一半」。
        """
        self._cancel_slide()
        self._win_drag = {"x": e.x_root, "y": e.y_root,
                          "wx": self.winfo_x(), "wy": self.winfo_y(),
                          "active": False, "job": None, "grabbed": False,
                          "tx": self.winfo_x(), "ty": self.winfo_y()}
        self.bind_all("<B1-Motion>", self._win_drag_motion)
        self.bind_all("<ButtonRelease-1>", self._win_drag_end)

    def _win_drag_grab(self):
        """真正拖动开始（位移超阈值）时才全局抓取指针，避免吞掉双击。"""
        d = self._win_drag
        if not d or d["grabbed"]:
            return
        try:
            self.grab_set_global()      # 拖出窗口后事件仍派发到本程序
            d["grabbed"] = True
        except Exception:
            pass

    def _win_drag_motion(self, e):
        """拖动中：只记录目标位置，用 after(0) 合并到每帧一次 geometry。

        直接在每个 Motion 事件里 geometry 会让窗口服务器来不及合成，
        表现为拖动卡顿；合并后一帧最多移动一次，跟手且流畅。
        """
        d = self._win_drag
        if not d:
            return
        dx = e.x_root - d["x"]
        dy = e.y_root - d["y"]
        if not d["active"]:
            if abs(dx) < 5 and abs(dy) < 5:
                return
            d["active"] = True
            self._win_drag_grab()      # 真正拖动才开始抓取（见 _win_drag_start 说明）
        d["tx"] = max(0, min(d["wx"] + dx, self.SW - 60))
        d["ty"] = max(Y0, min(d["wy"] + dy, self.SH - 80))
        if d["job"] is None:
            d["job"] = self.after(0, lambda: self._win_drag_flush(d))

    def _win_drag_flush(self, d=None):
        if d is None:
            d = self._win_drag
        if not d:
            return
        d["job"] = None
        self.geometry(f"+{d['tx']}+{d['ty']}")
        self.y_pos = d["ty"]
        self._slide_pos = d["tx"]        # 拖动后位置也由内部跟踪

    def _win_drag_end(self, e):
        d0 = self._win_drag
        if d0 and d0.get("grabbed"):
            try:
                self.grab_release()
            except Exception:
                pass
        self.unbind_all("<B1-Motion>")
        self.unbind_all("<ButtonRelease-1>")
        d = self._win_drag
        if d and d["job"]:
            try:
                self.after_cancel(d["job"])
            except Exception:
                pass
            self._win_drag_flush(d)      # 松手前最后一帧立刻应用
        self._win_drag = None
        if d and d["active"]:
            # 拖到屏幕中间：进入自由位置。此后不会自动消失，
            # 双击面板顶栏 / 点 ✕ / Esc 即可收回。
            self.free = True
            self._slide_job = None

    # ---------------- 滑出 / 收起 ----------------

    def toggle_mascot(self):
        """点击卡通小人：拉出 / 收回面板。"""
        if self.state == "hidden":
            self.show()
        else:
            self.hide()

    def show(self):
        self._cur_slogan = self._pick_slogan()
        self.tip_var.set(self._cur_slogan)
        self._cancel_slide()
        if self.state in ("showing", "shown"):
            return
        self.state = "showing"
        if not self.free:
            self.y_pos = self._center_y()  # 常规弹出：回到右侧中央
        if not self.winfo_ismapped():
            # 隐藏态是 withdraw（彻底不渲染）；重新出现时先恢复到隐藏位置
            self.deiconify()
            self.geometry(f"{PANEL_W}x{self.H}+{self.x_hidden}+{self.y_pos}")
            self._slide_pos = self.x_hidden
            # macOS 上 withdraw/deiconify 循环可能丢置顶属性，重新声明
            try:
                self.attributes("-topmost", True)
            except Exception:
                pass
        # 关键：窗口已映射，立刻按真实几何重算画布高度与滚动区，并强制绘制首帧，
        # 让 P1 等任务内容「及时出现」，不再等一会儿才冒出来。
        self.update()                    # 全量刷新：比 idletasks 更能稳住首帧几何
        self._resize()
        self.update()
        # deiconify 后首帧几何可能仍未稳定，多刷新几次滚动区，
        # 杜绝「内容空白一会儿才出现」的间歇现象。
        self._refresh_canvas()
        self._schedule_refreshes()
        _mac_make_key()                  # 把面板变成 key window，输入框才能打字
        self._slide(self.x_shown, self._on_shown)

    def _keep_top(self):
        """定时重申置顶：Windows 下用 -topmost 即可常驻最上层。

        每 3 秒重新设置一次 -topmost，避免被别的置顶程序抢走层级。
        """
        self.after(3000, self._keep_top)
        try:
            self.mascot.lift()
            self.attributes("-topmost", True)
            if self.state != "hidden":
                self.lift()
        except Exception:
            pass

    def _pick_slogan(self):
        pool = self.slogans if self.slogans else list(SLOGANS)
        s = random.choice(pool)
        while s == self._last_slogan and len(pool) > 1:
            s = random.choice(pool)
        self._last_slogan = s
        return s

    def _add_slogan(self):
        """弹出输入框，让用户随时新增一句自己的寄语（持久化、参与轮换）。"""
        text = simpledialog.askstring(
            "新增寄语", "输入一句你想看到的提醒：", parent=self)
        if not text or not text.strip():
            return
        text = text.strip()
        if text not in self.slogans:
            self.slogans.append(text)
            self.settings["slogans"] = self.slogans
            save_settings(self.settings)
        self._cur_slogan = text
        self.tip_var.set(text)             # 立即展示刚加的这句

    def _tip_commit(self):
        """编辑完当前寄语：把整句替换为新内容并持久化（参与轮换）。"""
        new = self.tip_var.get().strip()
        if not new:
            self.tip_var.set(self._cur_slogan)   # 空输入则恢复原句
            return
        old = self._cur_slogan
        if old and old in self.slogans:
            self.slogans[self.slogans.index(old)] = new
        elif new not in self.slogans:
            self.slogans.append(new)
        self.settings["slogans"] = self.slogans
        save_settings(self.settings)
        self._cur_slogan = new
        self._last_slogan = new

    def _on_shown(self):
        self.state = "shown"
        # 出现后清除遗留的编辑光标：不要停留在上次的编辑状态（问题 4）
        try:
            self._blur()
        except Exception:
            pass
        self.after(50, _mac_pin_windows)   # 显隐循环后重新固定

    def hide(self):
        """收起面板。自愈式设计：任何状态下调用都会完成收起动画。"""
        self._cancel_slide()
        if self.state == "hidden":
            return
        self.state = "hiding"
        self._slide(self.x_hidden, self._on_hidden)
        # 兜底：如果滑出动画因异常/事件冲突中途卡住，400ms 后强制完成隐藏。
        # 正常动画 <200ms，此兜底不会干扰正常流程。
        if self._ensure_hidden_job:
            try:
                self.after_cancel(self._ensure_hidden_job)
            except Exception:
                pass
        self._ensure_hidden_job = self.after(400, self._ensure_hidden)

    def _ensure_hidden(self):
        """隐藏动画兜底：仍未 hidden 则强制 withdraw。"""
        self._ensure_hidden_job = None
        if self.state != "hidden":
            self._cancel_slide()
            self._on_hidden()

    def _on_hidden(self):
        self.state = "hidden"
        self.free = False                  # 下次弹出回到右缘标准位置
        # 取消兜底定时器（如果它还没触发）
        if self._ensure_hidden_job:
            try:
                self.after_cancel(self._ensure_hidden_job)
            except Exception:
                pass
            self._ensure_hidden_job = None
        # 彻底隐藏：withdraw 后窗口不再渲染。Tk 9 + macOS 下即使把
        # geometry 设到屏幕外，窗口服务器也可能 clamp 回一条可见边缘，
        # withdraw 是从根本上杜绝"收了还在边缘露一线"。
        try:
            self.withdraw()
        except Exception:
            pass

    def _slide(self, target, done=None):
        # 位置由内部跟踪（self._slide_pos），不读 winfo_x()：
        # Tk 9/macOS 下完全离屏窗口的 winfo_x() 返回 clamp 值，
        # 用它做动画终点判断会永远差几步、甚至原地狂奔。
        cur = self._slide_pos
        if cur is None:
            cur = self.winfo_x()
        if abs(target - cur) <= SLIDE_STEP:
            self._slide_pos = target
            self.geometry(f"+{target}+{self.y_pos}")
            if done:
                done()
            return
        nxt = cur + SLIDE_STEP if target > cur else cur - SLIDE_STEP
        self._slide_pos = nxt
        self.geometry(f"+{nxt}+{self.y_pos}")
        self._slide_job = self.after(SLIDE_MS, lambda: self._slide(target, done))

    def _cur_x(self):
        """面板当前 x 坐标（动画中取内部跟踪值，避免 clamp 干扰）。"""
        return self._slide_pos if self._slide_pos is not None else self.winfo_x()

    def _cancel_slide(self):
        """取消正在进行的滑出/收起动画。"""
        if self._slide_job:
            try:
                self.after_cancel(self._slide_job)
            except Exception:
                pass
            self._slide_job = None

    # ---------------- 定时器 ----------------

    def _schedule_hourly(self):
        self.after(self.interval_ms, self._hourly)

    def _hourly(self):
        self.show()
        self._schedule_hourly()

    def _tick_time(self):
        now = datetime.now()
        self.clock.configure(text=now.strftime("%m月%d日 %H:%M"))
        if now.strftime("%Y-%m-%d") != self.day:
            self.data = load_tasks(self.priorities)
            self.day = today_key()
            self._build_sections(commit=False)
        self.after(20000, self._tick_time)

    # ---------------- 杂项 ----------------

    def _first_run(self):
        """首次启动时自动亮出面版并弹窗说明。

        这个程序会出现在 Dock 栏、小人常驻屏幕边缘且半透明，
        不提示的话用户会以为“双击没反应”。
        """
        try:
            WELCOME_FILE.write_text(datetime.now().isoformat(), encoding="utf-8")
        except Exception:
            pass
        self.show()
        self._welcome_job = self.after(25000, self.hide)   # 欢迎期间多留一会儿
        self.after(900, lambda: messagebox.showinfo(
            "久坐提醒 · 已在后台启动",
            "小程序正在运行（无任务栏图标，常驻桌面一侧）。\n\n"
            "· 屏幕右缘有一个半透明卡通小人（戴加油头巾、举着拳头）\n"
            "· 鼠标长时间停在小人上（约 0.6 秒）自动拉出面板；双击面板顶栏收起\n"
            "· 每 1 小时会自动亮出一次「不要久坐」提醒\n"
            "· 任务按 P1~P4 排列，可直接编辑；按住行首 ⋮⋮ 可拖到其他优先级下\n"
            "· 按住顶部标题栏可把面板拖到屏幕任意位置（拖走后不会自动消失）\n"
            "· 点底部深色「寄语条」可随时加入自己的提醒语，参与轮换\n\n"
            "✕ / 双击顶栏 / Esc 收起面板；\n"
            "右键小人 或 右键面板 可「退出久坐提醒」。"))


    def _on_wheel(self, e):
        if self.state == "hidden":
            return
        if isinstance(self.focus_get(), tk.Entry):
            return
        bbox = self.canvas.bbox("all")
        if bbox and bbox[3] > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")

    def on_quit(self):
        if messagebox.askyesno("久坐提醒", "确定退出吗？退出后将不再提醒。"):
            try:
                LOCK_FILE.unlink()
            except Exception:
                pass
            self.destroy()

    def _panel_popup(self, e):
        """右键面板弹出菜单（Windows 无 Dock，用它来退出程序）。"""
        try:
            self._pmenu.tk_popup(e.x_root, e.y_root)
        except Exception:
            pass


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="久坐提醒 · 今日任务面板")
    p.add_argument("--now", action="store_true", help="启动后立即弹出（测试用）")
    p.add_argument("--left", action="store_true", help="改为屏幕左侧")
    p.add_argument("--interval", type=float, default=60, help="弹出间隔（分钟，默认 60）")
    return p.parse_args()


def _already_running() -> bool:
    """单实例保护：已有实例在跑就返回 True（避免双开互相覆盖 tasks.json）。"""
    try:
        pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _kill_existing() -> bool:
    """结束正在运行的旧实例（双击 .app / .command 时替换旧实例）。

    用户常见困境：之前用 .command 启动过实例，之后双击 .app 却被
    单实例锁静默拦截，看起来"双击没反应"。这里在启动新实例前先
    确认旧实例仍是本程序（ps 确认是 python），礼貌杀掉再起新的。
    新旧版本的锁位置不同（数据目录 vs .app 旁边），两处都查。
    """
    candidates = [LOCK_FILE]
    legacy = os.environ.get("SIT_LEGACY_DIR")
    if legacy:
        candidates.append(Path(legacy) / ".sit_reminder.pid")
    for f in candidates:
        if _kill_by_lock(f):
            return True
    return False


def _kill_by_lock(lock_file) -> bool:
    try:
        pid = int(Path(lock_file).read_text(encoding="utf-8").strip())
    except Exception:
        return False
    try:
        os.kill(pid, 0)
    except Exception:
        return False                      # 陈旧锁：进程早没了
    # 确认是 Python 进程再杀（避免误杀 PID 复用）；Windows 用 tasklist，其余用 ps
    try:
        if sys.platform.startswith("win"):
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                capture_output=True, text=True, timeout=5).stdout
            if "python" not in out.lower():
                # pyw 在任务列表里也可能显示为 pythonw；放宽判定，仍尝试结束
                pass
        else:
            out = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True, text=True, timeout=5).stdout
            if "python" not in out.lower():
                return False              # PID 被别的程序复用，不动它
    except Exception:
        pass                              # ps/tasklist 不可用时按锁文件信息处理
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except Exception:
                break
        else:
            os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
    return True


def _migrate_old_data():
    """把旧版本放在脚本/.app 同目录的数据迁移到新数据目录（一次性）。

    旧版本把 tasks.json 等放在 .app 旁边；新版为绕开系统对「下载」
    文件夹的访问限制改放 ~/Library/Application Support/。
    launcher 会把 .app 所在目录通过 SIT_LEGACY_DIR 传进来；
    读不到（无权限/不存在）就静默跳过，不影响使用。
    """
    legacy = os.environ.get("SIT_LEGACY_DIR")
    if not legacy:
        return
    legacy = Path(legacy)
    for name in ("tasks.json", "settings.json", ".welcome_shown"):
        src = legacy / name
        dst = DATA_DIR / name
        if dst.exists() or not src.exists():
            continue
        try:
            dst.write_bytes(src.read_bytes())
        except Exception:
            pass


def main():
    # Windows 版：无需任何原生 API 调用，直接初始化即可。
    # 正确时机：Panel.__init__ 里 super().__init__() 之后（见那里），并由
    # _keep_top 每 3 秒兜底重试。
    _migrate_old_data()
    _kill_existing()                      # 替换掉正在运行的旧实例
    try:
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass
    app = Panel(parse_args())
    try:
        app.mainloop()
    finally:
        try:
            LOCK_FILE.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()
