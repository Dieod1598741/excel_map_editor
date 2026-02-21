import tkinter as tk
from tkinter import ttk
import ttkbootstrap as tb

root = tk.Tk()
style = tb.Style(theme="litera")

e1 = tk.Entry(root)
e2 = ttk.Entry(root)
e3 = tb.Entry(root)

print(f"tk.Entry class: {e1.winfo_class()}")
print(f"ttk.Entry class: {e2.winfo_class()}")
print(f"tb.Entry class: {e3.winfo_class()}")

root.destroy()
