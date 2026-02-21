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
        self.filtered_voices = []
        self.temp_file = None
        self._listbox_visible = False

        pygame.mixer.init()
        self._build_ui()
        self._load_voices()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 5}

        # Text input
        tk.Label(self.root, text="Text:").pack(anchor="w", **pad)
        self.text_box = tk.Text(self.root, height=8, wrap="word")
        self.text_box.pack(fill="x", **pad)

        # Voice search
        tk.Label(self.root, text="Voice (type to search):").pack(anchor="w", **pad)

        self.voice_search_var = tk.StringVar()
        self.voice_search_var.trace_add("write", self._on_search)

        voice_frame = tk.Frame(self.root)
        voice_frame.pack(fill="x", padx=10)

        self.voice_entry = tk.Entry(voice_frame, textvariable=self.voice_search_var, width=70)
        self.voice_entry.pack(fill="x")
        self.voice_entry.bind("<Down>", self._focus_listbox)
        self.voice_entry.bind("<Escape>", self._hide_listbox)

        # Dropdown listbox (hidden by default)
        self.listbox_frame = tk.Frame(self.root, relief="solid", borderwidth=1)
        self.listbox_scrollbar = tk.Scrollbar(self.listbox_frame, orient="vertical")
        self.voice_listbox = tk.Listbox(
            self.listbox_frame,
            height=6,
            yscrollcommand=self.listbox_scrollbar.set,
            selectmode="single",
            activestyle="dotbox"
        )
        self.listbox_scrollbar.config(command=self.voice_listbox.yview)
        self.listbox_scrollbar.pack(side="right", fill="y")
        self.voice_listbox.pack(side="left", fill="both", expand=True)

        self.voice_listbox.bind("<Return>", self._select_voice)
        self.voice_listbox.bind("<Double-Button-1>", self._select_voice)
        self.voice_listbox.bind("<Escape>", self._hide_listbox)
        self.voice_listbox.bind("<Up>", self._on_listbox_up)

        # Selected voice label
        self.selected_voice_var = tk.StringVar(value="No voice selected")
        tk.Label(self.root, textvariable=self.selected_voice_var, fg="blue").pack(anchor="w", padx=10)

        self.selected_voice_name = None  # stores the ShortName

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

        # Clicking elsewhere hides the listbox
        self.root.bind("<Button-1>", self._on_click_outside)

    # --- Voice search logic ---

    def _on_search(self, *args):
        query = self.voice_search_var.get().lower()
        self.filtered_voices = [
            v for v in self.voices
            if query in v["ShortName"].lower() or query in v["Locale"].lower()
        ]
        self._update_listbox()
        self._show_listbox()

    def _update_listbox(self):
        self.voice_listbox.delete(0, "end")
        for v in self.filtered_voices:
            self.voice_listbox.insert("end", f"{v['ShortName']} ({v['Locale']})")

    def _show_listbox(self):
        if not self._listbox_visible and self.filtered_voices:
            self.listbox_frame.place(
                in_=self.voice_entry,
                x=0,
                rely=1.0,
                relwidth=1.0,
                anchor="nw"
            )
            self.listbox_frame.lift()
            self._listbox_visible = True

    def _hide_listbox(self, event=None):
        if self._listbox_visible:
            self.listbox_frame.place_forget()
            self._listbox_visible = False

    def _select_voice(self, event=None):
        selection = self.voice_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        voice = self.filtered_voices[idx]
        self.selected_voice_name = voice["ShortName"]
        self.selected_voice_var.set(f"Selected: {voice['ShortName']} ({v['Locale']})" if False else f"Selected: {voice['ShortName']} ({voice['Locale']})")
        self.voice_search_var.set(f"{voice['ShortName']} ({voice['Locale']})")
        self._hide_listbox()
        self.voice_entry.icursor("end")

    def _focus_listbox(self, event=None):
        if self.filtered_voices:
            self._show_listbox()
            self.voice_listbox.focus_set()
            self.voice_listbox.selection_set(0)
            self.voice_listbox.activate(0)

    def _on_listbox_up(self, event=None):
        if self.voice_listbox.curselection() == (0,):
            self.voice_entry.focus_set()

    def _on_click_outside(self, event):
        widget = event.widget
        if widget not in (self.voice_entry, self.voice_listbox, self.listbox_frame):
            self._hide_listbox()

    # --- Voice loading ---

    def _load_voices(self):
        def task():
            voices = asyncio.run(get_voices())
            self.voices = sorted(voices, key=lambda v: v["ShortName"])
            self.filtered_voices = self.voices
            self._update_listbox()
            # Default to en-US-AriaNeural
            for v in self.voices:
                if v["ShortName"] == "en-US-AriaNeural":
                    self.selected_voice_name = v["ShortName"]
                    self.selected_voice_var.set(f"Selected: {v['ShortName']} ({v['Locale']})")
                    self.voice_search_var.set(f"{v['ShortName']} ({v['Locale']})")
                    break
            self.status_var.set("Ready.")
        threading.Thread(target=task, daemon=True).start()

    # --- Synthesis ---

    def _get_selected_voice(self):
        if not self.selected_voice_name:
            messagebox.showerror("Error", "Please select a voice.")
            return None
        return self.selected_voice_name

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