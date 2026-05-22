import tkinter as tk

from app.ui_main import MainApp


def main() -> None:
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
