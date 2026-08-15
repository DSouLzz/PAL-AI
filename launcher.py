import tkinter as tk

import pal_ai
from voice_fix import reliable_speak

# Apply the reliable Windows voice implementation before the app starts.
pal_ai.Voice.speak = reliable_speak

if __name__ == "__main__":
    root = tk.Tk()
    app = pal_ai.App(root)
    root.mainloop()
