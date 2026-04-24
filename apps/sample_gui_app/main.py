#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def main() -> None:
    root = tk.Tk()
    root.title("GUIサンプルアプリ")
    root.geometry("420x220")
    root.minsize(360, 180)

    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)

    title = ttk.Label(frame, text="GUIサンプルアプリ", font=("", 16, "bold"))
    title.pack(anchor="w")

    message = ttk.Label(frame, text="ToolHubからPython GUIアプリを起動できました。", wraplength=340)
    message.pack(anchor="w", pady=(12, 20))

    close_button = ttk.Button(frame, text="閉じる", command=root.destroy)
    close_button.pack(anchor="e")

    root.mainloop()


if __name__ == "__main__":
    main()

