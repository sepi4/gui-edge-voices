import tkinter as tk
from tkinter import filedialog, messagebox
import edge_tts
import asyncio
import threading
import pygame
import os
import tempfile

# --- Core TTS functions ---

async def get_voices():
    return await edge_tts.list_voices()

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

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")
        self.voice_entry.focus_set()

    def _build_ui(self, current_voice_name):
        tk.Label(self, text="Search voice:").pack(anchor="w", padx=12, pady=(12, 2))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        self.voice_entry = tk.Entry(self, textvariable=self.search_var)
        self.voice_entry.pack(fill="x", padx=12)

        list_frame = tk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=12, pady=8)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        self.voice_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                                        selectmode="single", activestyle="dotbox")
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

        self._update_listbox()
        if current_voice_name:
            for i, v in enumerate(self.filtered_voices):
                if v["ShortName"] == current_voice_name:
                    self.voice_listbox.selection_set(i)
                    self.voice_listbox.see(i)
                    break

    def _on_search(self, *args):
        query = self.search_var.get().lower()
        self.filtered_voices = [v for v in self.voices
                                 if query in v["ShortName"].lower() or query in v["Locale"].lower()]
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
            if self.filtered_voices:
                voice = self.filtered_voices[0]
            else:
                messagebox.showwarning("No selection", "Please select a voice.", parent=self)
                return
        else:
            voice = self.filtered_voices[selection[0]]
        self.on_select(voice)
        self.destroy()

# --- File Row for Batch Table ---

BORDER = "#aaaaaa"

class FileRow:
    """One row in the batch file table, drawn with cell borders."""

    def __init__(self, parent_frame, on_remove):
        self.file_path = None
        self.on_remove = on_remove

        # Left cell
        self.path_cell = tk.Frame(parent_frame,
                                  highlightthickness=1, highlightbackground=BORDER)
        inner_l = tk.Frame(self.path_cell)
        inner_l.pack(fill="both", expand=True, padx=5, pady=4)

        self.select_btn = tk.Button(inner_l, text="Select", width=8,
                                    command=self._select_file)
        self.select_btn.pack(side="left")

        self.path_label = tk.Label(inner_l, text="No file selected",
                                   fg="gray", anchor="w")
        self.path_label.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # Right cell
        self.name_cell = tk.Frame(parent_frame,
                                  highlightthickness=1, highlightbackground=BORDER)
        inner_r = tk.Frame(self.name_cell)
        inner_r.pack(fill="both", expand=True, padx=5, pady=4)

        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(inner_r, textvariable=self.name_var)
        self.name_entry.pack(side="left", fill="x", expand=True)

        self.remove_btn = tk.Button(inner_r, text="✕", width=3,
                                    command=lambda: self.on_remove(self))
        self.remove_btn.pack(side="right", padx=(6, 0))

    def _select_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            self.file_path = path
            basename = os.path.basename(path)
            self.path_label.config(text=basename, fg="black")
            if not self.name_var.get():
                self.name_var.set(os.path.splitext(basename)[0])

    def grid(self, row):
        self.path_cell.grid(row=row, column=0, sticky="ew")
        self.name_cell.grid(row=row, column=1, sticky="ew")

    def destroy(self):
        self.path_cell.destroy()
        self.name_cell.destroy()

# --- Main Application ---

class EdgeTTSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Edge TTS GUI")
        self.root.geometry("980x580")
        self.voices = []
        self.selected_voice_name = None
        self.file_rows = []

        pygame.mixer.init()
        self._stop_flag = threading.Event()
        self._build_ui()
        self._load_voices()

    def _build_ui(self):
        # Outer frame: left content | divider | right settings
        outer = tk.Frame(self.root)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        # Left panel
        left = tk.Frame(outer)
        left.pack(side="left", fill="both", expand=True)

        # Vertical divider line
        tk.Frame(outer, width=1, bg=BORDER).pack(side="left", fill="y", padx=10)

        # Right panel
        right = tk.Frame(outer)
        right.pack(side="left", fill="y")

        # ── Mode toggle ──
        toggle_frame = tk.Frame(left)
        toggle_frame.pack(anchor="w", pady=(0, 6))

        self.input_mode = tk.StringVar(value="text")

        tk.Radiobutton(toggle_frame, text="Option 1 – Paste Text",
                       variable=self.input_mode, value="text",
                       indicatoron=False, width=20,
                       command=self._switch_mode).pack(side="left", padx=(0, 4))

        tk.Radiobutton(toggle_frame, text="Option 2 – Text Files",
                       variable=self.input_mode, value="files",
                       indicatoron=False, width=20,
                       command=self._switch_mode).pack(side="left")

        # ── Option 1: text area ──
        self.text_frame = tk.Frame(left)
        self.text_frame.pack(fill="both", expand=True)

        self.text_box = tk.Text(self.text_frame, wrap="word")
        text_scroll = tk.Scrollbar(self.text_frame, command=self.text_box.yview)
        self.text_box.config(yscrollcommand=text_scroll.set)
        text_scroll.pack(side="right", fill="y")
        self.text_box.pack(fill="both", expand=True)

        # ── Option 2: file batch table ──
        self.files_frame = tk.Frame(left)
        # hidden initially

        # Outer table border
        table_border = tk.Frame(self.files_frame,
                                highlightthickness=1, highlightbackground=BORDER)
        table_border.pack(fill="both", expand=True)
        table_border.columnconfigure(0, weight=1)
        table_border.rowconfigure(1, weight=1)

        # Header
        header = tk.Frame(table_border, bg=BORDER)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=1)

        tk.Label(header, text="File Path", bg=BORDER, anchor="center",
                 font=("TkDefaultFont", 9, "bold"),
                 padx=8, pady=5).grid(row=0, column=0, sticky="ew")

        tk.Label(header, text="Output File Name", bg=BORDER, anchor="center",
                 font=("TkDefaultFont", 9, "bold"),
                 padx=8, pady=5).grid(row=0, column=1, sticky="ew")

        # Scrollable rows area
        canvas_wrap = tk.Frame(table_border)
        canvas_wrap.grid(row=1, column=0, sticky="nsew")

        self.rows_canvas = tk.Canvas(canvas_wrap, highlightthickness=0)
        rows_scrollbar = tk.Scrollbar(canvas_wrap, orient="vertical",
                                      command=self.rows_canvas.yview)
        self.rows_canvas.config(yscrollcommand=rows_scrollbar.set)
        rows_scrollbar.pack(side="right", fill="y")
        self.rows_canvas.pack(side="left", fill="both", expand=True)

        self.rows_inner = tk.Frame(self.rows_canvas)
        self._canvas_win = self.rows_canvas.create_window(
            (0, 0), window=self.rows_inner, anchor="nw")
        self.rows_inner.bind("<Configure>", self._on_rows_configure)
        self.rows_canvas.bind("<Configure>", self._on_canvas_resize)
        self.rows_inner.columnconfigure(0, weight=1)
        self.rows_inner.columnconfigure(1, weight=1)

        # Add row button
        tk.Button(self.files_frame, text="+ Add File",
                  command=self._add_file_row).pack(anchor="w", pady=4)

        self._add_file_row()
        self._add_file_row()

        # ── Right: settings (no decorative colours) ──
        pad = {"pady": 5}

        tk.Label(right, text="Voice:").pack(anchor="w", **pad)
        self.selected_voice_var = tk.StringVar(value="No voice selected")
        tk.Label(right, textvariable=self.selected_voice_var,
                 wraplength=200, justify="left").pack(anchor="w")
        tk.Button(right, text="Choose Voice…",
                  command=self._open_voice_picker).pack(anchor="w", pady=(4, 10))

        tk.Label(right, text="Rate (speed):").pack(anchor="w", **pad)
        self.rate_var = tk.IntVar(value=0)
        tk.Scale(right, from_=-50, to=50, orient="horizontal",
                 variable=self.rate_var, label="% (0 = normal)").pack(fill="x", **pad)

        btn_frame = tk.Frame(right)
        btn_frame.pack(pady=12)
        tk.Button(btn_frame, text="▶ Preview", width=12,
                  command=self._preview).pack(side="left", padx=3)
        tk.Button(btn_frame, text="💾 Save MP3", width=12,
                  command=self._save).pack(side="left", padx=3)

        self.stop_btn = tk.Button(right, text="⏹ Stop", width=12,
                                  command=self._stop, state="disabled")
        self.stop_btn.pack()

        # ── Status bar ──
        self.status_var = tk.StringVar(value="Loading voices...")
        tk.Label(self.root, textvariable=self.status_var, anchor="w").pack(
            side="bottom", fill="x", padx=10, pady=4)

    # ── Mode switching ──

    def _switch_mode(self):
        if self.input_mode.get() == "text":
            self.files_frame.pack_forget()
            self.text_frame.pack(fill="both", expand=True)
        else:
            self.text_frame.pack_forget()
            self.files_frame.pack(fill="both", expand=True)

    # ── Table helpers ──

    def _on_rows_configure(self, event):
        self.rows_canvas.configure(scrollregion=self.rows_canvas.bbox("all"))

    def _on_canvas_resize(self, event):
        self.rows_canvas.itemconfig(self._canvas_win, width=event.width)

    def _add_file_row(self):
        row = FileRow(self.rows_inner, self._remove_file_row)
        self.file_rows.append(row)
        self._refresh_rows_grid()

    def _remove_file_row(self, row):
        if row in self.file_rows:
            self.file_rows.remove(row)
            row.destroy()
            self._refresh_rows_grid()

    def _refresh_rows_grid(self):
        for i, row in enumerate(self.file_rows):
            row.grid(i)

    # ── Voice picker ──

    def _open_voice_picker(self):
        if not self.voices:
            messagebox.showinfo("Please wait", "Voices are still loading.")
            return
        VoicePickerModal(self.root, self.voices, self.selected_voice_name,
                         self._on_voice_selected)

    def _on_voice_selected(self, voice):
        self.selected_voice_name = voice["ShortName"]
        self.selected_voice_var.set(f"{voice['ShortName']} ({voice['Locale']})")

    # ── Voice loading ──

    def _load_voices(self):
        def task():
            voices = asyncio.run(get_voices())
            self.voices = sorted(voices, key=lambda v: v["ShortName"])
            for v in self.voices:
                if v["ShortName"] == "en-US-AriaNeural":
                    self.root.after(0, lambda: self._on_voice_selected(v))
                    break
            self.root.after(0, lambda: self.status_var.set("Ready."))
        threading.Thread(target=task, daemon=True).start()

    # ── Synthesis ──

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
            if self._stop_flag.is_set():
                return
            asyncio.run(synthesize(text, voice, self.rate_var.get(), output_path))
            if not self._stop_flag.is_set():
                self.root.after(0, callback)
            else:
                self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
        threading.Thread(target=task, daemon=True).start()

    def _run_batch_synthesis(self, save_dir):
        voice = self._get_selected_voice()
        if not voice:
            return
        valid_rows = [(r.file_path, r.name_var.get().strip())
                      for r in self.file_rows if r.file_path]
        if not valid_rows:
            messagebox.showerror("Error", "Please select at least one text file.")
            return
        self._stop_flag.clear()
        self.stop_btn.config(state="normal")

        def task():
            total = len(valid_rows)
            for idx, (file_path, out_name) in enumerate(valid_rows, 1):
                if self._stop_flag.is_set():
                    break
                if not out_name:
                    out_name = os.path.splitext(os.path.basename(file_path))[0]
                out_path = os.path.join(save_dir, out_name + ".mp3")
                self.root.after(0, lambda i=idx, t=total:
                                self.status_var.set(f"Processing file {i} of {t}..."))
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read().strip()
                    asyncio.run(synthesize(text, voice, self.rate_var.get(), out_path))
                except Exception as e:
                    self.root.after(0, lambda err=e:
                                    messagebox.showerror("Error", str(err)))

            def on_done():
                self.stop_btn.config(state="disabled")
                if not self._stop_flag.is_set():
                    self.status_var.set(f"Done. Files saved to: {save_dir}")
                    messagebox.showinfo("Done", f"All files saved to:\n{save_dir}")
                else:
                    self.status_var.set("Stopped.")
            self.root.after(0, on_done)

        threading.Thread(target=task, daemon=True).start()

    def _stop(self):
        self._stop_flag.set()
        pygame.mixer.music.stop()
        self.stop_btn.config(state="disabled")
        self.status_var.set("Stopped.")

    def _preview(self):
        if self.input_mode.get() == "files":
            messagebox.showinfo("Preview",
                                "Preview is only available in Option 1 (Paste Text) mode.")
            return
        self._stop_flag.clear()
        self.stop_btn.config(state="normal")
        self.temp_file = os.path.join(tempfile.gettempdir(), "edge_tts_preview.mp3")

        def on_done():
            if self._stop_flag.is_set():
                return
            pygame.mixer.music.load(self.temp_file)
            pygame.mixer.music.play()
            self.status_var.set("Playing preview...")
            self._poll_playback()
        self._run_synthesis(self.temp_file, on_done)

    def _poll_playback(self):
        if pygame.mixer.music.get_busy() and not self._stop_flag.is_set():
            self.root.after(200, self._poll_playback)
        else:
            self.stop_btn.config(state="disabled")
            if not self._stop_flag.is_set():
                self.status_var.set("Ready.")

    def _save(self):
        if self.input_mode.get() == "files":
            save_dir = filedialog.askdirectory(title="Select output folder")
            if save_dir:
                self._run_batch_synthesis(save_dir)
        else:
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