"""
BSC OPC Agent OS — Activation Dialog
=====================================
Shows on first run / trial expired. User can start trial or enter license key.
"""
# Reconstructed from activate_ui.pyc (Python 3.14).
# All user-facing strings (zh-CN) and colors preserved verbatim.

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox


class ActivateDialog:
    """Modal dialog for license activation."""

    def __init__(self, machine_id: str):
        self.machine_id = machine_id
        self.result: str | None = None

    def show(self) -> str | None:
        root = tk.Tk()
        root.title("BSC OPC Agent OS — 激活")
        root.geometry("480x400")
        root.resizable(False, False)
        root.configure(bg="#1a1d27")

        # Center on screen
        root.update_idletasks()
        x = (root.winfo_screenwidth() - 480) // 2
        y = (root.winfo_screenheight() - 400) // 2
        root.geometry(f"+{x}+{y}")

        # Color scheme
        bg = "#1a1d27"
        panel_bg = "#22263a"
        fg = "#e2e8f0"
        dim = "#8892a4"
        accent = "#1677ff"
        warn = "#f59e0b"
        ok_color = "#22c55e"
        err_color = "#ef4444"
        border = "#2d3348"
        btn_trial = "#16a34a"
        btn_activate = "#1d4ed8"

        # Header
        header = tk.Label(
            root, text="BSC OPC Agent OS", bg=bg, fg=fg,
            font=("Microsoft YaHei", 16, "bold"),
        )
        header.pack(pady=(20, 4))
        tk.Label(
            root, text="欢迎使用 — 请选择激活方式", bg=bg, fg=dim,
            font=("Microsoft YaHei", 10),
        ).pack()

        # Machine ID panel
        mid_panel = tk.Frame(root, bg=panel_bg, highlightbackground=border, highlightthickness=1)
        mid_panel.pack(fill="x", padx=24, pady=16)
        tk.Label(
            mid_panel, text="机器码 (提供给客服获取密钥)", bg=panel_bg, fg=dim,
            font=("Microsoft YaHei", 9),
        ).pack(anchor="w", padx=12, pady=(8, 0))

        mid_row = tk.Frame(mid_panel, bg=panel_bg)
        mid_row.pack(fill="x", padx=12, pady=(0, 10))
        mid_label = tk.Label(
            mid_row, text=self.machine_id, bg=panel_bg, fg=fg,
            font=("Consolas", 11, "bold"),
        )
        mid_label.pack(side="left")

        def _copy_mid():
            root.clipboard_clear()
            root.clipboard_append(self.machine_id)

        tk.Button(
            mid_row, text="📋 复制", bg=accent, fg="white",
            relief="flat", cursor="hand2",
            command=_copy_mid,
        ).pack(side="left", padx=8)

        # Trial button
        def _on_trial():
            self.result = "trial"
            root.destroy()

        tk.Button(
            root, text="免费试用 3 天", bg=btn_trial, fg="white",
            font=("Microsoft YaHei", 11, "bold"),
            relief="flat", cursor="hand2",
            command=_on_trial,
        ).pack(fill="x", padx=24, pady=(0, 8))

        # Divider label
        tk.Label(root, text="或输入激活密钥", bg=bg, fg=dim,
                 font=("Microsoft YaHei", 9)).pack(pady=(4, 4))

        # Key entry
        key_entry = tk.Entry(
            root, justify="center", bg="#2a2f45", fg=fg,
            insertbackground=fg, relief="flat",
            font=("Consolas", 11),
        )
        key_entry.pack(fill="x", padx=24, ipady=8)

        msg_label = tk.Label(root, text="", bg=bg, fg=err_color,
                             font=("Microsoft YaHei", 9))
        msg_label.pack(pady=(4, 0))

        def _on_activate():
            key = key_entry.get().strip()
            if not key:
                msg_label.config(text="请输入激活密钥", fg=err_color)
                return
            try:
                from license_crypto import verify_and_save_license
                res = verify_and_save_license(key)
                self.result = "active"
                messagebox.showinfo(
                    "激活成功",
                    f"✅ 激活成功！\n到期日期: {res.get('exp_date', '?')}\n"
                    f"剩余: {res.get('days_left', '?')} 天",
                )
                root.destroy()
            except Exception as e:
                msg_label.config(text=str(e), fg=err_color)

        btn_row = tk.Frame(root, bg=bg)
        btn_row.pack(fill="x", padx=24, pady=12)
        tk.Button(
            btn_row, text="激活", bg=btn_activate, fg="white",
            font=("Microsoft YaHei", 10, "bold"),
            relief="flat", cursor="hand2",
            command=_on_activate,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        def _on_quit():
            self.result = "quit"
            root.destroy()

        tk.Button(
            btn_row, text="退出", bg="#374151", fg="white",
            relief="flat", cursor="hand2",
            command=_on_quit,
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

        root.protocol("WM_DELETE_WINDOW", _on_quit)
        root.mainloop()
        return self.result


def show_activation_dialog(status: str) -> str:
    """Show appropriate dialog based on license status.

    status: 'none' | 'trial' | 'expired'
    Returns: 'active' | 'trial' | 'quit'
    """
    from license_crypto import get_machine_id, start_trial, trial_days_left

    mid = get_machine_id()

    if status == "none":
        dlg = ActivateDialog(mid)
        result = dlg.show()
        if result == "trial":
            start_trial()
        return result or "quit"

    if status == "trial":
        remaining = trial_days_left()
        # Just a reminder popup, not a blocker
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            "试用提示",
            f"当前为试用模式，剩余 {remaining} 天。\n"
            f"如需激活，请联系客服获取密钥。\n机器码: {mid}",
        )
        root.destroy()
        return "trial"

    # status == 'expired'
    root = tk.Tk()
    root.title("BSC OPC Agent OS — 试用已到期")
    root.geometry("480x360")
    root.configure(bg="#1a1d27")
    root.resizable(False, False)
    root.update_idletasks()
    x = (root.winfo_screenwidth() - 480) // 2
    y = (root.winfo_screenheight() - 360) // 2
    root.geometry(f"+{x}+{y}")

    tk.Label(
        root, text="试用已到期", bg="#1a1d27", fg="#ef4444",
        font=("Microsoft YaHei", 14, "bold"),
    ).pack(pady=(24, 6))
    tk.Label(
        root, text=f"机器码: {mid}", bg="#1a1d27", fg="#e2e8f0",
        font=("Consolas", 10),
    ).pack()

    key_entry = tk.Entry(root, justify="center", bg="#2a2f45", fg="#e2e8f0",
                         insertbackground="#e2e8f0", relief="flat",
                         font=("Consolas", 11))
    key_entry.pack(fill="x", padx=24, ipady=8, pady=(16, 4))
    msg = tk.Label(root, text="", bg="#1a1d27", fg="#ef4444",
                   font=("Microsoft YaHei", 9))
    msg.pack()

    result_state = {"value": "quit"}

    def _activate():
        key = key_entry.get().strip()
        if not key:
            msg.config(text="请输入激活密钥")
            return
        try:
            from license_crypto import verify_and_save_license
            res = verify_and_save_license(key)
            result_state["value"] = "active"
            messagebox.showinfo(
                "激活成功",
                f"✅ 激活成功！\n到期日期: {res.get('exp_date', '?')}",
            )
            root.destroy()
        except Exception as e:
            msg.config(text=str(e))

    def _quit():
        result_state["value"] = "quit"
        root.destroy()

    def _copy_mid2():
        root.clipboard_clear()
        root.clipboard_append(mid)

    btn_row = tk.Frame(root, bg="#1a1d27")
    btn_row.pack(fill="x", padx=24, pady=12)
    tk.Button(btn_row, text="📋 复制机器码", bg="#1677ff", fg="white",
              relief="flat", cursor="hand2", command=_copy_mid2).pack(side="left", padx=(0, 4))
    tk.Button(btn_row, text="激活", bg="#1d4ed8", fg="white",
              font=("Microsoft YaHei", 10, "bold"),
              relief="flat", cursor="hand2", command=_activate).pack(side="left", expand=True, fill="x", padx=4)
    tk.Button(btn_row, text="退出", bg="#374151", fg="white",
              relief="flat", cursor="hand2", command=_quit).pack(side="left", padx=(4, 0))

    root.protocol("WM_DELETE_WINDOW", _quit)
    root.mainloop()
    return result_state["value"]
