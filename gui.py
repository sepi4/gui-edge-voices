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

async def synthesize(text, voice, rate, output_path):
    rate_str = f"{rate:+d}%"
    communicate = edge_tts.Communicate(text, voice, rate=rate_str)
    await communicate.save(output_path)

# --- Voice Picker Modal ---

class VoicePickerModal(tk.Toplevel):
    def __init__(self, parent, voices, current_voice_name, on_select):
        super().__init__(parent)
        self.title("Select Voice")
        self.geometry("420x380")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.voices = voices
        self.filtered_voices = voices
        self.on_select = on_select

        self._build_ui(current_voice_name)

        # Center over parent
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

        self.voice_entry.focus_set()

    def _build_ui(self, current_voice_name):
        pad = {"padx": 12, "pady": 6}

        tk.Label(self, text="Search voice:").pack(anchor="w", padx=12, pady=(12, 2))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        self.voice_entry = tk.Entry(self, textvariable=self.search_var)
        self.voice_entry.pack(fill="x", padx=12)

        list_frame = tk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=12, pady=8)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        self.voice_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            selectmode="single",
            activestyle="dotbox"
        )
        scrollbar.config(command=self.voice_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.voice_listbox.pack(side="left", fill="both", expand=True)

        self.voice_listbox.bind("<Double-Button-1>", self._confirm)
        self.voice_listbox.bind("<Return>", self._confirm)
        self.voice_entry.bind("<Return>", self._confirm)
        self.voice_entry.bind("<Down>", self._focus_listbox)

        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(btn_frame, text="Select", width=12, command=self._confirm).pack(side="right", padx=(4, 0))
        tk.Button(btn_frame, text="Cancel", width=12, command=self.destroy).pack(side="right")

        # Populate listbox
        self._update_listbox()

        # Pre-select current voice
        if current_voice_name:
            for i, v in enumerate(self.filtered_voices):
                if v["ShortName"] == current_voice_name:
                    self.voice_listbox.selection_set(i)
                    self.voice_listbox.see(i)
                    break

    def _on_search(self, *args):
        query = self.search_var.get().lower()
        self.filtered_voices = [
            v for v in self.voices
            if query in v["ShortName"].lower() or query in v["Locale"].lower()
        ]
        self._update_listbox()

    def _update_listbox(self):
        self.voice_listbox.delete(0, "end")
        for v in self.filtered_voices:
            self.voice_listbox.insert("end", f"{v['ShortName']} ({v['Locale']})")

    def _focus_listbox(self, event=None):
        if self.filtered_voices:
            self.voice_listbox.focus_set()
            self.voice_listbox.selection_set(0)
            self.voice_listbox.activate(0)

    def _confirm(self, event=None):
        selection = self.voice_listbox.curselection()
        if not selection:
            # If nothing selected but there are results, pick first
            if self.filtered_voices:
                voice = self.filtered_voices[0]
            else:
                messagebox.showwarning("No selection", "Please select a voice.", parent=self)
                return
        else:
            voice = self.filtered_voices[selection[0]]
        self.on_select(voice)
        self.destroy()

# --- GUI Application ---

class EdgeTTSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Edge TTS GUI")
        self.root.geometry("900x500")
        self.voices = []
        self.selected_voice_name = None

        pygame.mixer.init()
        self._build_ui()
        self._load_voices()

    def _build_ui(self):
        # --- Main two-column frame ---
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        main_frame.columnconfigure(0, weight=3)
        main_frame.columnconfigure(1, weight=2)
        main_frame.rowconfigure(0, weight=1)

        # === LEFT: Text input ===
        left_frame = tk.Frame(main_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)

        tk.Label(left_frame, text="Text:").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.text_box = tk.Text(left_frame, wrap="word")
        self.text_box.grid(row=1, column=0, sticky="nsew")

        # === RIGHT: Options ===
        right_frame = tk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)

        pad = {"pady": 5}

        # Voice selector row
        tk.Label(right_frame, text="Voice:").pack(anchor="w", **pad)

        voice_row = tk.Frame(right_frame)
        voice_row.pack(fill="x", pady=(0, 4))

        tk.Button(voice_row, text="Choose Voice…", command=self._open_voice_picker).pack(side="left")

        self.selected_voice_var = tk.StringVar(value="No voice selected")
        tk.Label(voice_row, textvariable=self.selected_voice_var, fg="blue",
                 wraplength=160, justify="left").pack(side="left", padx=(8, 0))

        # Rate slider
        tk.Label(right_frame, text="Rate (speed):").pack(anchor="w", **pad)
        self.rate_var = tk.IntVar(value=0)
        tk.Scale(right_frame, from_=-50, to=50, orient="horizontal",
                 variable=self.rate_var, label="% (0 = normal)").pack(fill="x", **pad)

        # Buttons
        btn_frame = tk.Frame(right_frame)
        btn_frame.pack(pady=15)
        tk.Button(btn_frame, text="▶ Preview", width=13, command=self._preview).pack(side="left", padx=4)
        tk.Button(btn_frame, text="💾 Save MP3", width=13, command=self._save).pack(side="left", padx=4)

        # Status bar
        self.status_var = tk.StringVar(value="Loading voices...")
        tk.Label(self.root, textvariable=self.status_var, fg="gray").pack(side="bottom", pady=5)

    # --- Voice picker modal ---

    def _open_voice_picker(self):
        if not self.voices:
            messagebox.showinfo("Please wait", "Voices are still loading, please try again shortly.")
            return
        VoicePickerModal(
            self.root,
            self.voices,
            self.selected_voice_name,
            self._on_voice_selected
        )

    def _on_voice_selected(self, voice):
        self.selected_voice_name = voice["ShortName"]
        self.selected_voice_var.set(f"{voice['ShortName']} ({voice['Locale']})")

    # --- Voice loading ---

    def _load_voices(self):
        def task():
            voices = asyncio.run(get_voices())
            self.voices = sorted(voices, key=lambda v: v["ShortName"])
            # Default voice
            for v in self.voices:
                if v["ShortName"] == "en-US-AriaNeural":
                    self.root.after(0, lambda: self._on_voice_selected(v))
                    break
            self.root.after(0, lambda: self.status_var.set("Ready."))
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
            asyncio.run(synthesize(text, voice, self.rate_var.get(), output_path))
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