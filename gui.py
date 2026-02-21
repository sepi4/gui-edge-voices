import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import edge_tts
import asyncio
import threading
import pygame
import os
import tempfile

# --- Core TTS functions ---

async def get_voices():
    voices = await edge_tts.list_voices()
    return voices

async def synthesize(text, voice, rate, pitch, output_path):
    rate_str = f"{rate:+d}%"
    pitch_str = f"{pitch:+d}Hz"
    communicate = edge_tts.Communicate(text, voice, rate=rate_str, pitch=pitch_str)
    await communicate.save(output_path)

# --- GUI Application ---

class EdgeTTSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Edge TTS GUI")
        self.root.geometry("800x600")
        self.voices = []
        self.temp_file = None

        pygame.mixer.init()
        self._build_ui()
        self._load_voices()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 5}

        # Text input
        tk.Label(self.root, text="Text:").pack(anchor="w", **pad)
        self.text_box = tk.Text(self.root, height=8, wrap="word")
        self.text_box.pack(fill="x", **pad)

        # Voice selector
        tk.Label(self.root, text="Voice:").pack(anchor="w", **pad)
        self.voice_var = tk.StringVar()
        self.voice_combo = ttk.Combobox(self.root, textvariable=self.voice_var, state="readonly", width=60)
        self.voice_combo.pack(fill="x", **pad)

        # Rate slider
        tk.Label(self.root, text="Rate (speed):").pack(anchor="w", **pad)
        self.rate_var = tk.IntVar(value=0)
        tk.Scale(self.root, from_=-50, to=50, orient="horizontal",
                 variable=self.rate_var, label="% (0 = normal)").pack(fill="x", **pad)

        # Pitch slider
        tk.Label(self.root, text="Pitch:").pack(anchor="w", **pad)
        self.pitch_var = tk.IntVar(value=0)
        tk.Scale(self.root, from_=-20, to=20, orient="horizontal",
                 variable=self.pitch_var, label="Hz (0 = normal)").pack(fill="x", **pad)

        # Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="▶ Preview", width=15, command=self._preview).pack(side="left", padx=5)
        tk.Button(btn_frame, text="💾 Save MP3", width=15, command=self._save).pack(side="left", padx=5)

        # Status bar
        self.status_var = tk.StringVar(value="Loading voices...")
        tk.Label(self.root, textvariable=self.status_var, fg="gray").pack(side="bottom", pady=5)

    def _load_voices(self):
        def task():
            voices = asyncio.run(get_voices())
            self.voices = voices
            names = [f"{v['ShortName']} ({v['Locale']})" for v in voices]
            self.voice_combo["values"] = names
            # Default to en-US-AriaNeural
            for i, v in enumerate(voices):
                if v["ShortName"] == "en-US-AriaNeural":
                    self.voice_combo.current(i)
                    break
            self.status_var.set("Ready.")
        threading.Thread(target=task, daemon=True).start()

    def _get_selected_voice(self):
        idx = self.voice_combo.current()
        if idx < 0:
            messagebox.showerror("Error", "Please select a voice.")
            return None
        return self.voices[idx]["ShortName"]

    def _run_synthesis(self, output_path, callback):
        text = self.text_box.get("1.0", "end").strip()
        if not text:
            messagebox.showerror("Error", "Please enter some text.")
            return
        voice = self._get_selected_voice()
        if not voice:
            return
        self.status_var.set("Generating audio...")

        def task():
            asyncio.run(synthesize(text, voice, self.rate_var.get(), self.pitch_var.get(), output_path))
            self.root.after(0, callback)
        threading.Thread(target=task, daemon=True).start()

    def _preview(self):
        self.temp_file = os.path.join(tempfile.gettempdir(), "edge_tts_preview.mp3")
        def on_done():
            pygame.mixer.music.load(self.temp_file)
            pygame.mixer.music.play()
            self.status_var.set("Playing preview...")
        self._run_synthesis(self.temp_file, on_done)

    def _save(self):
        path = filedialog.asksaveasfilename(defaultextension=".mp3",
                                            filetypes=[("MP3 files", "*.mp3")])
        if not path:
            return
        def on_done():
            self.status_var.set(f"Saved to {path}")
            messagebox.showinfo("Done", f"File saved to:\n{path}")
        self._run_synthesis(path, on_done)



# --- Entry point ---

if __name__ == "__main__":
    root = tk.Tk()
    app = EdgeTTSApp(root)
    root.mainloop()