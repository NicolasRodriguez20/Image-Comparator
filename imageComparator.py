import os
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw
import imagehash
from concurrent.futures import ThreadPoolExecutor
import webbrowser
from datetime import datetime
import threading
import send2trash

# ─────────────────────────────────────────────
#  PALETA DE COLORES 
# ─────────────────────────────────────────────
BG_DEEP      = "#0d1117"
BG_CARD      = "#161b22"
BG_PANEL     = "#1c2333"
BG_HOVER     = "#21262d"
BORDER       = "#30363d"
BORDER_LIGHT = "#444c56"
TEXT_PRIMARY = "#e6edf3"
TEXT_SECOND  = "#8b949e"
TEXT_DIM     = "#484f58"
ACCENT_BLUE  = "#58a6ff"
ACCENT_RING  = "#388bfd"
BTN_DELETE   = "#da3633"
BTN_DEL_HOV  = "#f85149"
BTN_NORMAL   = "#21262d"
BTN_NOR_HOV  = "#30363d"
MATCH_GREEN  = "#3fb950"
PROGRESS_FG  = "#388bfd"


def make_rounded_rect(width, height, radius, fill, outline=None, outline_width=1):
    """Crea una imagen PIL con rectángulo redondeado."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=radius,
                            fill=fill, outline=outline, width=outline_width)
    return img


def hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def make_rounded_photo(width, height, radius, fill_hex, outline_hex=None, outline_w=1):
    fill = hex_to_rgb(fill_hex) + (255,)
    outline = hex_to_rgb(outline_hex) + (255,) if outline_hex else None
    pil = make_rounded_rect(width, height, radius, fill, outline, outline_w)
    return ImageTk.PhotoImage(pil)


# ─────────────────────────────────────────────
#  WIDGETS PERSONALIZADOS
# ─────────────────────────────────────────────

class DarkButton(tk.Canvas):
    """Botón con fondo redondeado y estilo oscuro."""

    def __init__(self, parent, text, command=None, icon="", accent=False,
                 danger=False, width=180, height=36, **kw):
        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bg=BG_DEEP, **kw)
        self.command = command
        self.accent = accent
        self.danger = danger
        self.btn_width = width
        self.btn_height = height
        self.text = icon + ("  " if icon else "") + text

        if danger:
            self.bg_normal  = BTN_DELETE
            self.bg_hover   = BTN_DEL_HOV
            self.border_col = "#6e2020"
        elif accent:
            self.bg_normal  = "#1f3a5f"
            self.bg_hover   = "#264f80"
            self.border_col = ACCENT_RING
        else:
            self.bg_normal  = BTN_NORMAL
            self.bg_hover   = BTN_NOR_HOV
            self.border_col = BORDER_LIGHT

        self.bind("<Enter>", lambda e: self._draw(self.bg_hover))
        self.bind("<Leave>", lambda e: self._draw(self.bg_normal))
        self.bind("<Button-1>", lambda e: self.command() if self.command else None)
        self.after(10, lambda: self._draw(self.bg_normal))

    def _draw(self, bg):
        self.delete("all")
        pil = make_rounded_rect(
            self.btn_width,
            self.btn_height,
            8,
            fill=hex_to_rgb(bg) + (255,),
            outline=hex_to_rgb(self.border_col) + (255,),
            outline_width=1
        )

        self._img = ImageTk.PhotoImage(pil)
        self.create_image(0, 0, anchor="nw", image=self._img)
        fg = TEXT_PRIMARY if not self.danger else "#ffffff"
        self.create_text(
            self.btn_width // 2,
            self.btn_height // 2,
            text=self.text,
            fill=fg,
            font=("Segoe UI", 10, "bold")
        )

    def set_state(self, state):
        if state == "disabled":
            self.unbind("<Enter>")
            self.unbind("<Leave>")
            self.unbind("<Button-1>")
            self._draw(TEXT_DIM)
        else:
            self.bind("<Enter>", lambda e: self._draw(self.bg_hover))
            self.bind("<Leave>", lambda e: self._draw(self.bg_normal))
            self.bind("<Button-1>", lambda e: self.command() if self.command else None)
            self._draw(self.bg_normal)


class ArcProgressBar(tk.Canvas):
    """Barra de progreso circular estilo macOS."""

    def __init__(self, parent, size=160, **kw):
        super().__init__(parent, width=size, height=size,
                         bg=BG_DEEP, highlightthickness=0, **kw)
        self.size = size
        self.progress = 0
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self.size
        m = 12
        self.create_arc(m, m, s - m, s - m, start=90, extent=360,
                         style="arc", outline=BG_PANEL, width=10)
        if self.progress > 0:
            extent = -3.6 * self.progress
            self.create_arc(m, m, s - m, s - m, start=90, extent=extent,
                             style="arc", outline=ACCENT_RING, width=10)
        ig = 30
        self.create_oval(ig, ig, s - ig, s - ig, fill=BG_CARD, outline=BORDER)

    def set_progress(self, value):
        self.progress = max(0, min(100, value))
        self._draw()


# ─────────────────────────────────────────────
#  VENTANA PRINCIPAL
# ─────────────────────────────────────────────

class DuplicateImageFinder:
    def __init__(self, root):
        self.root = root
        self.folder_path = ""
        self.similarity_threshold = 10
        self.duplicates_window = None
        self.total_images = 0
        self.processed_images = 0

        self._init_main_ui()

    def _init_main_ui(self):
        self.root.title("Image Comparator")
        self.root.configure(bg=BG_DEEP)
        self.root.geometry("560x380")
        self.root.resizable(False, False)

        try:
            self.root.iconbitmap("./icono.ico")
        except Exception:
            pass

        header = tk.Frame(self.root, bg=BG_CARD, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        logo_canvas = tk.Canvas(header, width=40, height=40, bg=BG_CARD,
                                highlightthickness=0)
        logo_canvas.pack(side="left", padx=(14, 0), pady=12)
        logo_canvas.create_oval(4, 4, 36, 36, fill=BG_PANEL, outline=BORDER_LIGHT)
        logo_canvas.create_text(20, 20, text="✦", fill=ACCENT_BLUE, font=("Segoe UI", 14))

        btn_frame = tk.Frame(header, bg=BG_CARD)
        btn_frame.place(relx=0.5, rely=0.5, anchor="center")

        self.btn_select = DarkButton(btn_frame, "Seleccionar Carpeta",
                                     command=self.select_folder,
                                     icon="📁", accent=True, width=200)
        self.btn_select.pack(side="left", padx=(0, 8), pady=14)

        self.btn_reload = DarkButton(btn_frame, "Recargar",
                                     command=self.reload_folder,
                                     icon="↻", width=140)
        self.btn_reload.pack(side="left", pady=14)
        self.btn_reload.set_state("disabled")
        self._reload_enabled = False

        subtitle = tk.Label(self.root,
                            text="Analiza imágenes idénticas en una carpeta seleccionada.",
                            bg=BG_DEEP, fg=TEXT_SECOND, font=("Segoe UI", 9))
        subtitle.pack(pady=(12, 0))

        self.arc = ArcProgressBar(self.root, size=160)
        self.arc.pack(pady=18)

        self.status_label = tk.Label(self.root, text="",
                                     font=("Segoe UI", 14, "bold"),
                                     bg=BG_DEEP, fg=TEXT_PRIMARY)
        self.status_label.pack()
        self.rotation = 0
        
    # ── Lógica ────────────────────────────────

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path = folder
            if not self._reload_enabled:
                self.btn_reload.set_state("normal")
                self._reload_enabled = True
            self._start_analysis()

    def reload_folder(self):
        if self.folder_path:
            self._start_analysis()

    def _start_analysis(self):
        self.processed_images = 0
        self.arc.set_progress(0)
        self.status_label.config(text="Cargando... (0%)")
        threading.Thread(target=self._find_duplicates_thread, daemon=True).start()

    def _find_duplicates_thread(self):
        duplicates = self._find_duplicate_images(self.folder_path)
        self.root.after(0, self._on_analysis_done, duplicates)

    def _on_analysis_done(self, duplicates):
        self.arc.set_progress(100)
        self.status_label.config(text="")
        if duplicates:
            self._show_duplicates(duplicates)
        else:
            if self.duplicates_window:
                self.duplicates_window.destroy()
                self.duplicates_window = None
            messagebox.showinfo("Resultado", "No se encontraron imágenes duplicadas.")

    def _find_duplicate_images(self, folder_path):
        image_hashes = {}
        duplicate_groups = {}   # original_path -> [paths]

        all_paths = list(self._get_all_image_paths(folder_path))
        self.total_images = max(len(all_paths), 1)

        def process(fp):
            try:
                with Image.open(fp) as img:
                    if img.mode == 'P' and 'transparency' in img.info:
                        img = img.convert('RGBA')
                    return fp, (imagehash.average_hash(img),
                                imagehash.phash(img),
                                imagehash.dhash(img),
                                imagehash.whash(img))
            except Exception as e:
                print(f"Error procesando {fp}: {e}")
                return fp, None

        with ThreadPoolExecutor() as ex:
            results = list(ex.map(process, all_paths))

        for i, (fp, hashes) in enumerate(results):
            if hashes:
                avg, ph, dh, wh = hashes
                matched_key = None
                for key, existing in image_hashes.items():
                    ea, ep, ed, ew = existing
                    if (avg - ea < self.similarity_threshold and
                            ph - ep < self.similarity_threshold and
                            dh - ed < self.similarity_threshold and
                            wh - ew < self.similarity_threshold):
                        matched_key = key
                        break
                if matched_key:
                    duplicate_groups[matched_key].append(fp)
                else:
                    image_hashes[fp] = (avg, ph, dh, wh)
                    duplicate_groups[fp] = [fp]

            self.processed_images = i + 1
            pct = (self.processed_images / self.total_images) * 100
            self.root.after(0, self._update_progress, pct)

        # Solo grupos con más de 1 imagen
        return {k: v for k, v in duplicate_groups.items() if len(v) > 1}

    def _update_progress(self, pct):
        self.arc.set_progress(pct)
        self.status_label.config(text=f"Cargando... ({int(pct)}%)")

   
    def _get_all_image_paths(self, folder):
        exts = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}
        for root, _, files in os.walk(folder):
            for f in files:
                if any(f.lower().endswith(e) for e in exts):
                    yield os.path.join(root, f)

    # ── Ventana de duplicados ─────────────────

    def _show_duplicates(self, groups):
        if self.duplicates_window and self.duplicates_window.winfo_exists():
            self.duplicates_window.destroy()

        win = tk.Toplevel(self.root)
        win.title("Imágenes Duplicadas")
        win.configure(bg=BG_DEEP)
        win.geometry("700x620")
        win.resizable(True, True)
        self.duplicates_window = win

        try:
            win.iconbitmap("./icono.ico")
        except Exception:
            pass

        # Header
        hdr = tk.Frame(win, bg=BG_CARD, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="✦  Imágenes Duplicadas",
                 bg=BG_CARD, fg=TEXT_PRIMARY,
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=16, pady=10)
        count = sum(len(v) for v in groups.values())
        tk.Label(hdr, text=f"{count} archivos · {len(groups)} grupos",
                 bg=BG_CARD, fg=TEXT_SECOND,
                 font=("Segoe UI", 9)).pack(side="right", padx=16)

        outer = tk.Frame(win, bg=BG_DEEP)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=BG_DEEP, highlightthickness=0)
        vbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=BG_DEEP)
        win_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win_id, width=canvas.winfo_width())

        body.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        for orig, paths in groups.items():
            self._render_group(body, paths)

    def _render_group(self, parent, paths):
        """Renderiza un grupo de imágenes duplicadas."""
        group_frame = tk.Frame(parent, bg=BG_CARD,
                               highlightbackground=BORDER,
                               highlightthickness=1)
        group_frame.pack(fill="x", padx=12, pady=6)

        badge_row = tk.Frame(group_frame, bg=BG_CARD)
        badge_row.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(badge_row, text=f"✓  {len(paths)} coincidencias",
                 bg=BG_CARD, fg=MATCH_GREEN,
                 font=("Segoe UI", 9, "bold")).pack(side="left")

        grid_frame = tk.Frame(group_frame, bg=BG_CARD)
        grid_frame.pack(fill="x", padx=6, pady=(0, 8))

        cols = min(len(paths), 4)   
        for idx, fp in enumerate(paths):
            col = idx % cols
            row = idx // cols
            self._render_image_card(grid_frame, fp, row, col)

    def _render_image_card(self, parent, fp, row, col):
        card = tk.Frame(parent, bg=BG_PANEL,
                        highlightbackground=BORDER,
                        highlightthickness=1)
        card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
        parent.columnconfigure(col, weight=1)

        try:
            with Image.open(fp) as img:
                w_orig, h_orig = img.size
                img.thumbnail((140, 100))
                thumb = ImageTk.PhotoImage(img)
        except Exception:
            thumb = None
            w_orig, h_orig = 0, 0

        if thumb:
            lbl = tk.Label(card, image=thumb, bg=BG_PANEL, cursor="hand2")
            lbl.image = thumb
            lbl.pack(padx=6, pady=(8, 4))
            lbl.bind("<Button-1>", lambda e, p=fp: webbrowser.open(p))

        name_var = tk.StringVar(value=os.path.basename(fp))
        name_entry = tk.Entry(card, textvariable=name_var, state="readonly",
                              readonlybackground=BG_PANEL, fg=TEXT_PRIMARY,
                              relief="flat", font=("Segoe UI", 8),
                              insertbackground=TEXT_PRIMARY, width=22)
        name_entry.pack(padx=6, fill="x")

        try:
            cdate = datetime.fromtimestamp(os.path.getctime(fp)).strftime('%Y-%m-%d  %H:%M:%S')
        except Exception:
            cdate = "—"

        date_entry = tk.Entry(card, state="readonly",
                              readonlybackground=BG_PANEL, fg=TEXT_SECOND,
                              relief="flat", font=("Segoe UI", 8), width=22)
        date_entry.insert(0, f"🕐  {cdate}")
        date_entry.config(state="readonly")
        date_entry.pack(padx=6, fill="x")

        tk.Label(card, text=f"{w_orig}×{h_orig} px",
                 bg=BG_PANEL, fg=TEXT_SECOND,
                 font=("Segoe UI", 8)).pack(pady=(2, 4))

        trash_btn = DarkButton(card, "Mover a la papelera",
                                command=lambda p=fp, c=card: self._trash_file(p, c),
                                icon="🗑", danger=True, width=170, height=30)
        trash_btn.pack(pady=(2, 8))

    def _trash_file(self, fp, card_widget):
        try:
            fp = os.path.abspath(os.path.normpath(fp))
            send2trash.send2trash(fp)
            card_widget.destroy()

        except Exception as e:
            messagebox.showerror(
                "Error",
                f"No se pudo mover a la papelera:\n{e}"
            )


if __name__ == "__main__":
    root = tk.Tk()
    app = DuplicateImageFinder(root)
    root.mainloop()