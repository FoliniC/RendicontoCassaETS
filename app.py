"""
app.py — CassaETS: applicazione desktop per il Rendiconto per Cassa ETS
Requisiti: Python 3.11+ (tkinter incluso), weasyprint, jinja2
Nessun server, nessun hosting. Tutti i dati in CSV locali.

Avvio: python app.py
"""

import csv
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk, simpledialog

# Configurazione Logging base
logger = logging.getLogger("CassaETS")

def setup_logging(level_name: str = "INFO", log_path: str | Path = None):
    if level_name.upper() == "NONE":
        logging.disable(logging.CRITICAL)
        return
    else:
        logging.disable(logging.NOTSET) # Riabilita se era disabilitato

    level = getattr(logging, level_name.upper(), logging.INFO)
    
    # Rimuove eventuali handler esistenti per evitare duplicati al cambio impostazioni
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handlers = [logging.StreamHandler()]
    if log_path:
        try:
            log_path = Path(log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
        except Exception as e:
            print(f"Impossibile creare il file di log in {log_path}: {e}")

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    logger.setLevel(level)
    logger.info(f"Logging inizializzato a livello: {level_name} su {log_path}")

# Aggiungi la directory corrente al path per importare i moduli locali
sys.path.insert(0, str(Path(__file__).parent))
from contabilita import (
    PIANO_DEI_CONTI, Movimento, Bilancio,
    leggi_cassa, calcola_bilancio,
    esporta_cassa_json, esporta_bilancio_json,
    esporta_cassa_csv, esporta_bilancio_csv,
)
# Importazione pdf_generator opzionale: richiede reportlab
try:
    from pdf_generator import genera_pdf
    PDF_DISPONIBILE = True
except ModuleNotFoundError:
    PDF_DISPONIBILE = False
    genera_pdf = None

# Importazione docx_generator opzionale: richiede docxtpl
try:
    from docx_generator import genera_verbale_docx
    DOCX_DISPONIBILE = True
except ModuleNotFoundError:
    DOCX_DISPONIBILE = False
    genera_verbale_docx = None

# Importazione excel_importer opzionale: richiede openpyxl
try:
    from excel_importer import import_excel_data
    EXCEL_DISPONIBILE = True
except ModuleNotFoundError:
    EXCEL_DISPONIBILE = False
    import_excel_data = None

def _controlla_docxtpl() -> bool:
    """Mostra istruzioni di installazione se docxtpl non è disponibile."""
    if DOCX_DISPONIBILE:
        return True
    pip_cmd = f'"{sys.executable}" -m pip install docxtpl'
    messagebox.showerror(
        "Libreria mancante — docxtpl",
        "Per generare i verbali Word è necessaria la libreria docxtpl.\n\n"
        "Per installarla apri il Prompt dei comandi e digita:\n\n"
        f"    {pip_cmd}"
    )
    return False
    
def _controlla_reportlab() -> bool:
    """
    Mostra istruzioni di installazione se reportlab non è disponibile.
    Restituisce True se si può procedere, False se bisogna fermarsi.
    """
    if PDF_DISPONIBILE:
        return True

    import tkinter as tk
    from tkinter import messagebox

    # Determina il comando pip corretto per il sistema
    import sys
    pip_cmd = f'"{sys.executable}" -m pip install reportlab'

    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Libreria mancante — reportlab",
        "Per generare i PDF è necessaria la libreria reportlab,\n"
        "che non risulta installata.\n\n"
        "Per installarla apri il Prompt dei comandi (o Terminale)\n"
        "e digita il comando seguente:\n\n"
        f"    {pip_cmd}\n\n"
        "Dopo l'installazione riavvia l'applicazione.\n\n"
        "Se non sai come aprire il Prompt dei comandi:\n"
        "  Windows: tasto Start → cerca 'cmd' → Esegui come amministratore\n"
        "  macOS/Linux: apri il Terminale"
    )
    root.destroy()
    return False


# ── Costanti ────────────────────────────────────────────────────────────────

APP_TITLE   = "CassaETS"
APP_VERSION = "1.0"
# CONFIG_DIR è la cartella dell'applicazione (dove risiede il file app.py)
CONFIG_DIR  = Path(__file__).resolve().parent
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# DATA_DIR viene letta dal config all'avvio; può essere cambiata dall'utente
def _init_data_dir() -> Path:
    """Legge la directory dati dal config prima ancora di creare la GUI."""
    cfg_path = CONFIG_DIR / "config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            saved = cfg.get("data_dir", "")
            if saved:
                saved_path = Path(saved)
                if not saved_path.is_absolute():
                    saved_path = (CONFIG_DIR / saved_path).resolve()
                if saved_path.exists():
                    return saved_path
        except Exception:
            pass
    return CONFIG_DIR

DATA_DIR = _init_data_dir()
# Colori palette
C_BG       = "#f4f6fa"
C_SIDEBAR  = "#1a3a5c"
C_ACCENT   = "#2e6da4"
C_ACCENT2  = "#4a9ede"
C_WHITE    = "#ffffff"
C_TEXT     = "#1a1a2e"
C_MUTED    = "#6b7280"
C_SUCCESS  = "#16a34a"
C_WARNING  = "#d97706"
C_DANGER   = "#dc2626"
C_ROW_ODD  = "#f8fafc"
C_ROW_EVEN = "#edf2f7"
C_HEADER   = "#dbeafe"

# Codici voce per autocomplete (solo voci operative)
CODICI_VOCE = sorted([
    v["codice"] for v in PIANO_DEI_CONTI
    if v["tipo"] == "voce"
] + ["Z.Z.1", "Z.Z.5"])

DESCRIZIONI_VOCE = {v["codice"]: v["label"] for v in PIANO_DEI_CONTI}


# ── Utility ─────────────────────────────────────────────────────────────────

def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def path_cassa(anno: int) -> Path:
    return DATA_DIR / f"cassa_{anno}.csv"


def path_config() -> Path:
    return CONFIG_DIR / "config.json"


def leggi_config() -> dict:
    default = {
        "ente": "", "cf": "", "runts": "", 
        "data_dir": str(CONFIG_DIR), 
        "log_level": "INFO", 
        "log_path": str(CONFIG_DIR / "cassaets.log"),
        "sync_log_path": True,
        "config_in_data_dir": False,
        "ultimo_anno": datetime.now().year,
        "firme": ["Il Presidente", "Il Tesoriere", "Il Revisore dei Conti"],
        "mostra_firme": True,
        "data_documento": date.today().strftime("%d/%m/") + "{{ anno_consuntivo }}",
        "nota_legale": "I dati originali sono conservati in formato CSV aperto. Documento generato con CassaETS (reportlab).",
        "nota_footer": "Rendiconto redatto ai sensi dell'art. 13 co. 2 D.Lgs. 117/2017 (Codice del Terzo Settore) e del D.M. 39/2020 Modello D.",
        "mostra_data": True,
        "mostra_nota_legale": True,
        "mostra_nota_footer": True,
        "mostra_pagine": True,
        # Configurazioni specifiche per i verbali DOCX
        "verbale": {
            "mostra_firme": True,
            "mostra_data": True,
            "mostra_pagine": True,
            "data_documento": date.today().strftime("%d/%m/") + "{{ anno_consuntivo }}",
            "firme": ["Il Presidente", "Il Segretario"],
        },
        "approvazione": {
            "mostra_firme": True,
            "mostra_data": True,
            "mostra_pagine": True,
            "data_documento": date.today().strftime("%d/%m/") + "{{ anno_consuntivo }}",
            "firme": ["Il Presidente", "Il Segretario"],
        }
    }
    p = CONFIG_DIR / "config.json"
    saved = {}
    if p.exists():
        try:
            saved = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            saved = {}

    if saved.get("config_in_data_dir") and saved.get("data_dir"):
        data_dir = Path(saved["data_dir"])
        if not data_dir.is_absolute():
            data_dir = (CONFIG_DIR / data_dir).resolve()
        alt = data_dir / "config.json"
        if alt.exists():
            try:
                saved = json.loads(alt.read_text(encoding="utf-8"))
            except Exception:
                pass

    if isinstance(saved.get("data_dir"), str) and saved["data_dir"]:
        data_dir = Path(saved["data_dir"])
        if not data_dir.is_absolute():
            saved["data_dir"] = str((CONFIG_DIR / data_dir).resolve())
        else:
            saved["data_dir"] = str(data_dir)

    if isinstance(saved.get("log_path"), str) and saved["log_path"]:
        log_path = Path(saved["log_path"])
        if not log_path.is_absolute():
            saved["log_path"] = str((CONFIG_DIR / log_path).resolve())
        else:
            saved["log_path"] = str(log_path)

    # Uniamo i dati salvati con i default
    for k, v in saved.items():
        if k in default:
            if isinstance(v, str) and not v.strip() and k in ("nota_legale", "nota_footer"):
                continue
            if k == "firme" and not v:
                continue
            if isinstance(v, dict) and k in ("verbale", "approvazione"):
                default[k].update(v)
                continue
            default[k] = v
    return default


def salva_config(cfg: dict) -> None:
    # Assicurati che le chiavi essenziali esistano
    default = {
        "ente": "", "cf": "", "runts": "", 
        "data_dir": str(CONFIG_DIR), 
        "log_level": "INFO",
        "log_path": str(CONFIG_DIR / "cassaets.log"),
        "sync_log_path": True,
        "config_in_data_dir": False,
        "ultimo_anno": datetime.now().year,
        "firme": ["Il Presidente", "Il Tesoriere", "Il Revisore dei Conti"],
        "mostra_firme": True,
        "data_documento": date.today().strftime("%d/%m/") + "{{ anno_consuntivo }}",
        "nota_legale": "I dati originali sono conservati in formato CSV aperto. Documento generato con CassaETS (reportlab).",
        "nota_footer": "Rendiconto redatto ai sensi dell'art. 13 co. 2 D.Lgs. 117/2017 (Codice del Terzo Settore) e del D.M. 39/2020 Modello D.",
        "mostra_data": True,
        "mostra_nota_legale": True,
        "mostra_nota_footer": True,
        "mostra_pagine": True
    }
    default.update(cfg)

    # Normalize paths for consistent startup behavior
    data_dir = Path(default.get("data_dir", str(CONFIG_DIR))).expanduser()
    if not data_dir.is_absolute():
        data_dir = (CONFIG_DIR / data_dir).resolve()
    default["data_dir"] = str(data_dir)

    log_path = Path(default.get("log_path", str(CONFIG_DIR / "cassaets.log"))).expanduser()
    if not log_path.is_absolute():
        log_path = (CONFIG_DIR / log_path).resolve()
    default["log_path"] = str(log_path)

    p = CONFIG_DIR / "config.json"
    if default.get("config_in_data_dir", False):
        p = data_dir / "config.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        # Keep a mirror in the execution folder so startup trova sempre la configurazione.
        mirror = CONFIG_DIR / "config.json"
        mirror.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        p.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
    
import re

def anni_disponibili() -> list[int]:
    ensure_data_dir()
    anni = set()
    # Pattern regex per beccare esattamente cassa_ seguito da 4 cifre e basta
    pattern = re.compile(r"^cassa_(\d{4})\.csv$")
    
    for f in DATA_DIR.glob("cassa_*.csv"):
        match = pattern.match(f.name)
        if match:
            try:
                anni.add(int(match.group(1)))
            except ValueError:
                pass
    return sorted(list(anni), reverse=True)


def nuovo_anno_csv(anno: int) -> None:
    """Crea un CSV vuoto con soli saldi iniziali per un nuovo anno."""
    p = path_cassa(anno)
    if p.exists():
        return
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["data", "descrizione", "codice_voce", "importo", "tipo_conto"])
        w.writerow([f"{anno}-01-01", "Saldo iniziale cassa", "Z.Z.1", "0.00", "cassa"])
        w.writerow([f"{anno}-01-01", "Saldo iniziale conto corrente", "Z.Z.5", "0.00", "cc"])


# ── Widget personalizzati ────────────────────────────────────────────────────

class AutocompleteCombobox(ttk.Combobox):
    """Combobox con filtro autocomplete sui codici voce."""

    def __init__(self, master, values, **kw):
        super().__init__(master, **kw)
        self._all_values = sorted(values)
        self["values"] = self._all_values
        self.bind("<KeyRelease>", self._on_key)

    def _on_key(self, event):
        typed = self.get().upper()
        if not typed:
            self["values"] = self._all_values
        else:
            filtered = [v for v in self._all_values if typed in v.upper()]
            self["values"] = filtered
        try:
            self.event_generate("<Down>")
        except Exception:
            pass


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text   = text
        self.tip    = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 24
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(self.tip, text=self.text, background="#fffbe6",
                       relief="solid", borderwidth=1, font=("Helvetica", 9),
                       wraplength=260, justify="left", padx=6, pady=3)
        lbl.pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


# ── Finestra principale ─────────────────────────────────────────────────────

class AutocompleteEntry(ttk.Frame):
    """
    Campo di testo con listbox flottante per autocomplete sui codici voce.
    Digita per filtrare, frecce su/giù per navigare, Invio per selezionare.
    """

    def __init__(self, master, values: list[str], textvariable: tk.StringVar,
                 on_select=None, width=16, **kw):
        super().__init__(master, style="Content.TFrame", **kw)
        self._all_values  = sorted(values)
        self._var         = textvariable
        self._on_select   = on_select
        self._listbox_win = None
        self._listbox     = None
        self._after_id    = None

        self._entry = ttk.Entry(self, textvariable=textvariable,
                                width=width, font=("Helvetica", 10))
        self._entry.pack(fill="x")

        self._var.trace_add("write", self._on_write)
        self._entry.bind("<KeyRelease>", self._on_key)
        self._entry.bind("<FocusOut>",   self._on_focus_out)
        self._entry.bind("<Escape>",     lambda _: self._chiudi())
        self._entry.bind("<Return>",     self._on_enter)
        self._entry.bind("<Down>",       self._freccia_giu)
        self._entry.bind("<Up>",         self._freccia_su)

    def _on_write(self, *_):
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(80, self._aggiorna_lista)

    def _on_key(self, event):
        if event.keysym in ("Down", "Up", "Return", "Escape", "Tab"):
            return
        self._aggiorna_lista()

    def _on_focus_out(self, event):
        self.after(150, self._chiudi_se_non_focus)

    def _chiudi_se_non_focus(self):
        if self._listbox_win and self._listbox_win.winfo_exists():
            try:
                focused = self.winfo_toplevel().focus_get()
                if focused not in (self._listbox, self._entry):
                    self._chiudi()
            except Exception:
                self._chiudi()

    def _on_enter(self, _=None):
        if self._listbox and self._listbox.winfo_exists():
            self._seleziona_corrente()
        self._chiudi()

    def _freccia_giu(self, _=None):
        if not self._listbox or not self._listbox.winfo_exists():
            self._aggiorna_lista()
            return
        sel = self._listbox.curselection()
        n   = self._listbox.size()
        if n == 0:
            return
        idx = (sel[0] + 1) if sel else 0
        idx = min(idx, n - 1)
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(idx)
        self._listbox.see(idx)
        self._entry.focus_set()

    def _freccia_su(self, _=None):
        if not self._listbox or not self._listbox.winfo_exists():
            return
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = max(sel[0] - 1, 0)
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(idx)
        self._listbox.see(idx)
        self._entry.focus_set()

    def _filtra(self) -> list[str]:
        typed = self._var.get().strip().upper()
        if not typed:
            return self._all_values
        starts   = [v for v in self._all_values if v.upper().startswith(typed)]
        contains = [v for v in self._all_values
                    if typed in v.upper() and v not in starts]
        return starts + contains

    def _aggiorna_lista(self):
        risultati = self._filtra()
        if not risultati:
            self._chiudi()
            return
        if len(risultati) == 1 and risultati[0].upper() == self._var.get().strip().upper():
            self._chiudi()
            return
        self._apri_listbox(risultati)

    def _apri_listbox(self, voci: list[str]):
        x = self._entry.winfo_rootx()
        y = self._entry.winfo_rooty() + self._entry.winfo_height()
        w = max(self._entry.winfo_width(), 320)

        if self._listbox_win and self._listbox_win.winfo_exists():
            win = self._listbox_win
        else:
            win = tk.Toplevel(self)
            win.wm_overrideredirect(True)
            win.wm_attributes("-topmost", True)
            win.configure(bg="#1a3a5c")

            frame = tk.Frame(win, bg="#1a3a5c", bd=1, relief="solid")
            frame.pack(fill="both", expand=True)

            sb = tk.Scrollbar(frame, orient="vertical")
            lb = tk.Listbox(
                frame,
                yscrollcommand=sb.set,
                selectmode="single",
                font=("Helvetica", 10),
                bg=C_WHITE, fg=C_TEXT,
                selectbackground=C_ACCENT,
                selectforeground=C_WHITE,
                activestyle="none",
                relief="flat", borderwidth=0,
                highlightthickness=0,
            )
            sb.config(command=lb.yview)
            sb.pack(side="right", fill="y")
            lb.pack(side="left", fill="both", expand=True)

            lb.bind("<ButtonRelease-1>", self._on_click_listbox)
            lb.bind("<Return>",          self._on_enter)
            lb.bind("<Escape>",          lambda _: self._chiudi())
            lb.bind("<Double-Button-1>", self._on_click_listbox)

            self._listbox_win = win
            self._listbox     = lb

        self._listbox.delete(0, "end")
        n_show = min(len(voci), 10)
        for v in voci:
            desc = DESCRIZIONI_VOCE.get(v, "")
            riga = f"  {v:<12}  {desc[:45]}" if desc else f"  {v}"
            self._listbox.insert("end", riga)

        altezza = n_show * 22 + 4
        self._listbox_win.wm_geometry(f"{w}x{altezza}+{x}+{y}")
        self._listbox_win.lift()

        if voci:
            self._listbox.selection_set(0)

    def _on_click_listbox(self, _=None):
        self._seleziona_corrente()
        self._chiudi()
        self._entry.focus_set()

    def _seleziona_corrente(self):
        if not self._listbox:
            return
        sel = self._listbox.curselection()
        if not sel:
            return
        codice = self._listbox.get(sel[0]).strip().split()[0]
        self._var.set(codice)
        if self._on_select:
            self._on_select(codice)

    def _chiudi(self):
        if self._listbox_win and self._listbox_win.winfo_exists():
            self._listbox_win.destroy()
        self._listbox_win = None
        self._listbox     = None

    def focus_set(self):
        self._entry.focus_set()


# ── Finestra principale ─────────────────────────────────────────
class CassaETS(tk.Tk):

    def __init__(self):
        super().__init__()
        ensure_data_dir()
        self.config_data = leggi_config()
        setup_logging(
            self.config_data.get("log_level", "INFO"),
            self.config_data.get("log_path", CONFIG_DIR / "cassaets.log")
        )
        
        # Ripristina l'ultimo anno salvato
        ultimo = self.config_data.get("ultimo_anno", datetime.now().year)
        self.anno_corrente = tk.IntVar(value=ultimo)
        self.movimenti: list[Movimento] = []

        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.geometry("1200x720")
        self.minsize(900, 600)
        self.configure(bg=C_BG)

        # Stile ttk
        self._setup_stile()
        self._build_ui()
        self._carica_anno()

    # ── Setup stile ────────────────────────────────────────────────────────

    def _setup_stile(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Sidebar.TFrame",    background=C_SIDEBAR)
        s.configure("Content.TFrame",    background=C_BG)
        s.configure("Card.TFrame",       background=C_WHITE, relief="flat")
        s.configure("TLabel",            background=C_BG, foreground=C_TEXT,
                    font=("Helvetica", 10))
        s.configure("Title.TLabel",      background=C_BG, foreground=C_TEXT,
                    font=("Helvetica", 14, "bold"))
        s.configure("Sidebar.TLabel",    background=C_SIDEBAR, foreground=C_WHITE,
                    font=("Helvetica", 10))
        s.configure("SidebarTitle.TLabel", background=C_SIDEBAR, foreground=C_WHITE,
                    font=("Helvetica", 13, "bold"))
        s.configure("Accent.TButton",    background=C_ACCENT, foreground=C_WHITE,
                    font=("Helvetica", 10, "bold"), borderwidth=0, padding=(10, 5))
        s.map("Accent.TButton",
              background=[("active", C_ACCENT2), ("pressed", "#1a5a8f")])
        s.configure("Danger.TButton",    background=C_DANGER, foreground=C_WHITE,
                    font=("Helvetica", 10), borderwidth=0, padding=(8, 4))
        s.map("Danger.TButton",
              background=[("active", "#f87171")])
        s.configure("Treeview",          background=C_WHITE, foreground=C_TEXT,
                    rowheight=24, font=("Helvetica", 9), fieldbackground=C_WHITE)
        s.configure("Treeview.Heading",  background=C_HEADER, foreground=C_TEXT,
                    font=("Helvetica", 9, "bold"), relief="flat")
        s.map("Treeview", background=[("selected", C_ACCENT)])

    # ── Layout UI ─────────────────────────────────────────────────────────

    def _build_ui(self):
        # Sidebar sinistra
        self.sidebar = ttk.Frame(self, style="Sidebar.TFrame", width=210)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Area contenuto
        self.content = ttk.Frame(self, style="Content.TFrame")
        self.content.pack(side="left", fill="both", expand=True)

        self._build_sidebar()

        # Notebook pagine
        self.nb = ttk.Notebook(self.content)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.page_prima_nota = ttk.Frame(self.nb, style="Content.TFrame")
        self.page_bilancio   = ttk.Frame(self.nb, style="Content.TFrame")
        self.page_export     = ttk.Frame(self.nb, style="Content.TFrame")
        self.page_impostazioni = ttk.Frame(self.nb, style="Content.TFrame")

        self.nb.add(self.page_prima_nota,   text="  📒  Prima Nota  ")
        self.nb.add(self.page_bilancio,     text="  📊  Bilancio  ")
        self.nb.add(self.page_export,       text="  📤  Export  ")
        self.nb.add(self.page_impostazioni, text="  ⚙️  Impostazioni  ")

        self._build_prima_nota()
        self._build_bilancio()
        self._build_export()
        self._build_impostazioni()

    def _build_sidebar(self):
        pad = {"padx": 16, "pady": 6}

        ttk.Label(self.sidebar, text="CassaETS",
                  style="SidebarTitle.TLabel").pack(anchor="w", padx=16, pady=(20, 2))
        ttk.Label(self.sidebar, text="Rendiconto ETS Mod. D",
                  style="Sidebar.TLabel", font=("Helvetica", 8)).pack(anchor="w", padx=16)

        ttk.Separator(self.sidebar).pack(fill="x", padx=12, pady=10)

        # Selezione anno
        ttk.Label(self.sidebar, text="Anno contabile",
                  style="Sidebar.TLabel").pack(anchor="w", **pad)

        anni = anni_disponibili()
        if not anni:
            anni = [datetime.now().year]

        if self.anno_corrente.get() not in anni:
            self.anno_corrente.set(anni[0])

        self.combo_anno = ttk.Combobox(
            self.sidebar,
            textvariable=self.anno_corrente,
            values=anni,
            width=10, state="readonly"
        )
        self.combo_anno.pack(anchor="w", padx=16)
        self.combo_anno.bind("<<ComboboxSelected>>", lambda _: self._carica_anno())

        ttk.Button(self.sidebar, text="+ Nuovo anno",
                   command=self._nuovo_anno).pack(anchor="w", padx=16, pady=(4, 0))

        ttk.Separator(self.sidebar).pack(fill="x", padx=12, pady=10)

        # Riepilogo saldi (aggiornato al caricamento)
        ttk.Label(self.sidebar, text="Saldi correnti",
                  style="Sidebar.TLabel", font=("Helvetica", 9, "bold")).pack(anchor="w", **pad)

        self.lbl_saldo_cassa = ttk.Label(self.sidebar, text="Cassa:  —",
                                          style="Sidebar.TLabel", font=("Helvetica", 9))
        self.lbl_saldo_cassa.pack(anchor="w", padx=16)

        self.lbl_saldo_cc = ttk.Label(self.sidebar, text="CC:     —",
                                       style="Sidebar.TLabel", font=("Helvetica", 9))
        self.lbl_saldo_cc.pack(anchor="w", padx=16)

        ttk.Separator(self.sidebar).pack(fill="x", padx=12, pady=10)

        # Link rapidi
        ttk.Button(self.sidebar, text="📊 Genera Bilancio",
                   style="Accent.TButton",
                   command=self._genera_bilancio).pack(fill="x", padx=16, pady=3)

        ttk.Button(self.sidebar, text="📄 Esporta PDF",
                   command=self._esporta_pdf_quick).pack(fill="x", padx=16, pady=3)

        # Versione in fondo
        ttk.Label(self.sidebar, text=f"v{APP_VERSION}",
                  style="Sidebar.TLabel", font=("Helvetica", 7),
                  foreground="#8899bb").pack(side="bottom", padx=16, pady=10)

    # ── Pagina Prima Nota ─────────────────────────────────────────────────

    def _build_prima_nota(self):
        p = self.page_prima_nota

        # Toolbar
        bar = ttk.Frame(p, style="Content.TFrame")
        bar.pack(fill="x", pady=(0, 6))

        ttk.Button(bar, text="➕ Aggiungi movimento",
                   style="Accent.TButton",
                   command=self._dialog_aggiungi).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="✏️ Modifica",
                   command=self._dialog_modifica).pack(side="left", padx=3)
        ttk.Button(bar, text="🗑️ Elimina",
                   style="Danger.TButton",
                   command=self._elimina_movimento).pack(side="left", padx=3)

        # Filtro
        ttk.Label(bar, text="Filtro:").pack(side="left", padx=(20, 4))
        self.var_filtro = tk.StringVar()
        self.var_filtro.trace_add("write", lambda *_: self._aggiorna_tabella())
        ttk.Entry(bar, textvariable=self.var_filtro, width=20).pack(side="left")

        # Treeview
        cols = ("data", "descrizione", "codice", "importo", "conto")
        self.tree = ttk.Treeview(p, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("data",        text="Data")
        self.tree.heading("descrizione", text="Descrizione")
        self.tree.heading("codice",      text="Codice voce")
        self.tree.heading("importo",     text="Importo")
        self.tree.heading("conto",       text="Conto")

        self.tree.column("data",        width=90,  anchor="center")
        self.tree.column("descrizione", width=480, anchor="w")
        self.tree.column("codice",      width=100, anchor="center")
        self.tree.column("importo",     width=100, anchor="e")
        self.tree.column("conto",       width=100, anchor="center")

        self.tree.tag_configure("entrata", foreground=C_SUCCESS)
        self.tree.tag_configure("uscita",  foreground=C_DANGER)
        self.tree.tag_configure("saldo",   foreground=C_MUTED, font=("Helvetica", 9, "italic"))
        self.tree.tag_configure("odd",     background=C_ROW_ODD)
        self.tree.tag_configure("even",    background=C_ROW_EVEN)

        scroll_y = ttk.Scrollbar(p, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="left", fill="y")

        self.tree.bind("<Double-1>", lambda _: self._dialog_modifica())

        # Barra stato
        self.lbl_stato = ttk.Label(p, text="", style="TLabel",
                                   font=("Helvetica", 9), foreground=C_MUTED)
        self.lbl_stato.pack(anchor="w", pady=(4, 0))

    def _aggiorna_tabella(self):
        """Ricarica il Treeview dai movimenti in memoria."""
        filtro = self.var_filtro.get().lower()
        self.tree.delete(*self.tree.get_children())

        for idx, m in enumerate(self.movimenti):
            row_str = f"{m.data} {m.descrizione} {m.codice_voce} {m.importo} {m.tipo_conto}".lower()
            if filtro and filtro not in row_str:
                continue

            imp_str = f"{m.importo:+.2f}"
            is_saldo = m.codice_voce in ("Z.Z.1", "Z.Z.5")

            if is_saldo:
                tag = ("saldo", "odd" if idx % 2 == 0 else "even")
            elif m.importo >= 0:
                tag = ("entrata", "odd" if idx % 2 == 0 else "even")
            else:
                tag = ("uscita", "odd" if idx % 2 == 0 else "even")

            self.tree.insert("", "end", iid=str(idx), tags=tag,
                             values=(m.data.strftime("%d/%m/%Y"),
                                     m.descrizione[:80],
                                     m.codice_voce,
                                     imp_str,
                                     "Cassa" if m.tipo_conto == "cassa" else "C/C"))

        n = len(self.movimenti)
        saldo_c = sum(m.importo for m in self.movimenti if m.tipo_conto == "cassa")
        saldo_cc = sum(m.importo for m in self.movimenti if m.tipo_conto == "cc")
        self.lbl_stato.config(
            text=f"{n} movimenti  |  Saldo cassa: {saldo_c:.2f}  |  Saldo CC: {saldo_cc:.2f}"
        )
        self.lbl_saldo_cassa.config(text=f"Cassa:  {saldo_c:.2f}")
        self.lbl_saldo_cc.config(text=f"CC:     {saldo_cc:.2f}")

    def _dialog_aggiungi(self):
        self._dialog_movimento(None)

    def _dialog_modifica(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Seleziona un movimento da modificare.")
            return
        idx = int(sel[0])
        self._dialog_movimento(idx)

    def _dialog_movimento(self, idx: int | None):
        """Finestra di dialogo per aggiungere/modificare un movimento."""
        mv = self.movimenti[idx] if idx is not None else None

        dlg = tk.Toplevel(self)
        dlg.title("Aggiungi movimento" if mv is None else "Modifica movimento")
        dlg.geometry("540x320")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.configure(bg=C_BG)

        def lbl(parent, text, row, col=0):
            tk.Label(parent, text=text, bg=C_BG, font=("Helvetica", 10),
                     anchor="e").grid(row=row, column=col, sticky="e", padx=8, pady=6)

        fr = tk.Frame(dlg, bg=C_BG)
        fr.pack(fill="both", expand=True, padx=20, pady=12)

        lbl(fr, "Data (YYYY-MM-DD):", 0)
        var_data = tk.StringVar(value=mv.data.isoformat() if mv else date.today().isoformat())
        tk.Entry(fr, textvariable=var_data, width=16,
                 font=("Helvetica", 10)).grid(row=0, column=1, sticky="w", padx=4)

        lbl(fr, "Descrizione:", 1)
        var_desc = tk.StringVar(value=mv.descrizione if mv else "")
        tk.Entry(fr, textvariable=var_desc, width=40,
                 font=("Helvetica", 10)).grid(row=1, column=1, sticky="ew", padx=4)

        lbl(fr, "Codice voce:", 2)
        var_cod = tk.StringVar(value=mv.codice_voce if mv else "")

        # Descrizione voce auto-fill (deve stare PRIMA di AutocompleteEntry)
        lbl_voce_desc = tk.Label(fr, text="", bg=C_BG, fg=C_MUTED,
                                  font=("Helvetica", 8), anchor="w")
        lbl_voce_desc.grid(row=3, column=1, sticky="w", padx=4)

        def aggiorna_desc_voce(*_):
            d = DESCRIZIONI_VOCE.get(var_cod.get(), "")
            lbl_voce_desc.config(text=d[:60])

        var_cod.trace_add("write", aggiorna_desc_voce)
        aggiorna_desc_voce()

        combo_cod = AutocompleteEntry(fr, CODICI_VOCE,
                                       textvariable=var_cod,
                                       on_select=aggiorna_desc_voce,
                                       width=16)
        combo_cod.grid(row=2, column=1, sticky="w", padx=4)

        # Descrizione voce auto-fill
        lbl_voce_desc = tk.Label(fr, text="", bg=C_BG, fg=C_MUTED,
                                  font=("Helvetica", 8), anchor="w")
        lbl_voce_desc.grid(row=3, column=1, sticky="w", padx=4)

        def aggiorna_desc_voce(*_):
            d = DESCRIZIONI_VOCE.get(var_cod.get(), "")
            lbl_voce_desc.config(text=d[:60])
        var_cod.trace_add("write", aggiorna_desc_voce)
        aggiorna_desc_voce()

        lbl(fr, "Importo (+ entrata, - uscita):", 4)
        var_imp = tk.StringVar(value=f"{mv.importo:.2f}" if mv else "")
        tk.Entry(fr, textvariable=var_imp, width=14,
                 font=("Helvetica", 10)).grid(row=4, column=1, sticky="w", padx=4)

        lbl(fr, "Conto:", 5)
        var_conto = tk.StringVar(value=mv.tipo_conto if mv else "cc")
        tk.Radiobutton(fr, text="Cassa", variable=var_conto, value="cassa",
                       bg=C_BG, font=("Helvetica", 10)).grid(row=5, column=1, sticky="w", padx=4)
        tk.Radiobutton(fr, text="Conto corrente", variable=var_conto, value="cc",
                       bg=C_BG, font=("Helvetica", 10)).grid(row=5, column=1, sticky="w", padx=70)

        fr.columnconfigure(1, weight=1)

        def salva():
            try:
                d     = datetime.strptime(var_data.get().strip(), "%Y-%m-%d").date()
                desc  = var_desc.get().strip()
                cod   = var_cod.get().strip()
                imp   = float(var_imp.get().replace(",", "."))
                conto = var_conto.get()
                if not desc:
                    raise ValueError("Descrizione obbligatoria")
                if not cod:
                    raise ValueError("Codice voce obbligatorio")
                if conto not in ("cassa", "cc"):
                    raise ValueError("Conto non valido")

                nuovo = Movimento(data=d, descrizione=desc, codice_voce=cod,
                                  importo=imp, tipo_conto=conto)
                if idx is None:
                    self.movimenti.append(nuovo)
                else:
                    self.movimenti[idx] = nuovo

                self.movimenti.sort(key=lambda m: m.data)
                self._salva_csv()
                self._aggiorna_tabella()
                dlg.destroy()
            except Exception as e:
                messagebox.showerror("Errore", str(e), parent=dlg)

        btn_fr = tk.Frame(dlg, bg=C_BG)
        btn_fr.pack(pady=8)
        tk.Button(btn_fr, text="💾 Salva", command=salva,
                  bg=C_ACCENT, fg="white", font=("Helvetica", 10, "bold"),
                  relief="flat", padx=14, pady=5).pack(side="left", padx=6)
        tk.Button(btn_fr, text="Annulla", command=dlg.destroy,
                  bg="#e5e7eb", fg=C_TEXT, font=("Helvetica", 10),
                  relief="flat", padx=10, pady=5).pack(side="left")

    def _elimina_movimento(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        mv = self.movimenti[idx]
        if messagebox.askyesno("Conferma",
                               f"Eliminare il movimento del {mv.data}\n«{mv.descrizione[:50]}»?"):
            del self.movimenti[idx]
            self._salva_csv()
            self._aggiorna_tabella()

    # ── Pagina Bilancio ───────────────────────────────────────────────────

    def _build_bilancio(self):
        p = self.page_bilancio

        bar = ttk.Frame(p, style="Content.TFrame")
        bar.pack(fill="x", pady=(0, 6))

        ttk.Button(bar, text="🔄 Calcola bilancio",
                   style="Accent.TButton",
                   command=self._genera_bilancio).pack(side="left", padx=(0, 8))

        self.lbl_bil_info = ttk.Label(bar, text="Premi 'Calcola bilancio' per generare il prospetto.",
                                       foreground=C_MUTED, font=("Helvetica", 9))
        self.lbl_bil_info.pack(side="left")

        # Treeview bilancio
        cols_bil = ("riga", "voce", "importo", "importo_prec")
        self.tree_bil = ttk.Treeview(p, columns=cols_bil, show="headings", selectmode="none")
        self.tree_bil.heading("riga",        text="Riga")
        self.tree_bil.heading("voce",        text="Voce")
        self.tree_bil.heading("importo",     text=f"Anno")
        self.tree_bil.heading("importo_prec",text="Anno prec.")

        self.tree_bil.column("riga",        width=45,  anchor="center")
        self.tree_bil.column("voce",        width=520, anchor="w")
        self.tree_bil.column("importo",     width=120, anchor="e")
        self.tree_bil.column("importo_prec",width=120, anchor="e")

        self.tree_bil.tag_configure("intestazione", background="#dbeafe",
                                     font=("Helvetica", 9, "bold"))
        self.tree_bil.tag_configure("totale",       background="#bfdbfe",
                                     font=("Helvetica", 9, "bold"))
        self.tree_bil.tag_configure("avanzo_pos",   background="#dcfce7",
                                     foreground=C_SUCCESS)
        self.tree_bil.tag_configure("avanzo_neg",   background="#fee2e2",
                                     foreground=C_DANGER)
        self.tree_bil.tag_configure("finale",       background="#1a3a5c",
                                     foreground="white", font=("Helvetica", 9, "bold"))
        self.tree_bil.tag_configure("saldo",        background="#e8eef5")
        self.tree_bil.tag_configure("odd",          background=C_ROW_ODD)
        self.tree_bil.tag_configure("even",         background=C_ROW_EVEN)

        scroll_bil = ttk.Scrollbar(p, orient="vertical", command=self.tree_bil.yview)
        self.tree_bil.configure(yscrollcommand=scroll_bil.set)
        self.tree_bil.pack(side="left", fill="both", expand=True)
        scroll_bil.pack(side="left", fill="y")

    def _genera_bilancio(self):
        """Calcola e visualizza il bilancio nella pagina apposita."""
        if not self.movimenti:
            messagebox.showinfo("Info", "Nessun movimento caricato.")
            return

        anno = self.anno_corrente.get()

        # Carica anno precedente se disponibile
        mvs_prec = None
        p_prec = path_cassa(anno - 1)
        if p_prec.exists():
            try:
                mvs_prec = leggi_cassa(p_prec)
            except Exception:
                pass

        cfg = leggi_config()
        self.bilancio_corrente = calcola_bilancio(
            anno, self.movimenti, mvs_prec,
            ente=cfg.get("ente", ""),
        )

        self._aggiorna_tabella_bilancio()
        self.nb.select(1)  # Vai alla pagina Bilancio
        self.lbl_bil_info.config(
            text=f"Bilancio {anno} — Avanzo: {self.bilancio_corrente.avanzo_esercizio:+.2f} €  "
                 f"Totale generale: {self.bilancio_corrente.totale_generale:.2f} €",
            foreground=C_SUCCESS if self.bilancio_corrente.avanzo_esercizio >= 0 else C_DANGER
        )

    def _aggiorna_tabella_bilancio(self):
        self.tree_bil.delete(*self.tree_bil.get_children())
        if not hasattr(self, "bilancio_corrente"):
            return

        bil = self.bilancio_corrente
        anno = bil.anno

        # Aggiorna intestazioni colonne anno
        self.tree_bil.heading("importo",      text=str(anno))
        self.tree_bil.heading("importo_prec", text=str(anno - 1))

        def ins(riga, label, val_c, val_p, tag):
            c_str = f"{val_c:.2f}" if val_c is not None else ""
            p_str = f"{val_p:.2f}" if val_p is not None else ""
            self.tree_bil.insert("", "end", tags=(tag,),
                                 values=(riga or "", label, c_str, p_str))

        # Mostra le righe del bilancio
        for r in bil.righe:
            tipo = r.tipo
            val_c = r.importo_corrente
            val_p = r.importo_precedente
            lbl   = ("  " if tipo == "voce" else "") + r.label

            if tipo == "intestazione":
                tag = "intestazione"
            elif tipo in ("totale_sezione", "totale_gestione"):
                tag = "totale"
            elif tipo == "avanzo":
                tag = "avanzo_pos" if val_c >= 0 else "avanzo_neg"
            else:
                tag = "odd"

            ins(r.riga, lbl, val_c, val_p, tag)

        # Righe finali
        ins(46, "Totale uscite della gestione",  bil.totale_uscite,    None, "totale")
        ins(46, "Totale entrate della gestione", bil.totale_entrate,   None, "totale")
        ins(47, "Avanzo/disavanzo prima delle imposte",
            bil.avanzo_esercizio, None,
            "avanzo_pos" if bil.avanzo_esercizio >= 0 else "avanzo_neg")
        ins(48, "Imposte", bil.imposte, None, "odd")
        ins(49, "Avanzo/disavanzo prima di investimenti",
            bil.avanzo_finale, None,
            "avanzo_pos" if bil.avanzo_finale >= 0 else "avanzo_neg")
        ins(50, "Cassa",           bil.saldo_cassa, None, "saldo")
        ins(51, "Conto corrente",  bil.saldo_cc,    None, "saldo")
        ins(52, "Totale generale", bil.totale_generale, None, "finale")

    # ── Pagina Export ────────────────────────────────────────────────────

    def _build_export(self):
        p = self.page_export

        ttk.Label(p, text="Esportazione dati", style="Title.TLabel").pack(anchor="w", pady=(8, 16))

        def card(parent, titolo, sottotitolo, btn_label, cmd, tooltip_text=""):
            fr = ttk.Frame(parent, style="Card.TFrame", relief="ridge")
            fr.pack(fill="x", pady=6, padx=4)
            inner = ttk.Frame(fr, style="Card.TFrame")
            inner.pack(fill="x", padx=14, pady=10)
            ttk.Label(inner, text=titolo, font=("Helvetica", 11, "bold"),
                      background=C_WHITE).pack(anchor="w")
            ttk.Label(inner, text=sottotitolo, font=("Helvetica", 9),
                      foreground=C_MUTED, background=C_WHITE,
                      wraplength=620, justify="left").pack(anchor="w", pady=(2, 8))
            btn = ttk.Button(inner, text=btn_label, style="Accent.TButton", command=cmd)
            btn.pack(anchor="w")
            if tooltip_text:
                Tooltip(btn, tooltip_text)

        card(p,
             "📄 PDF Rendiconto (per RUNTS)",
             "Genera il Rendiconto per Cassa Mod. D in formato PDF. "
             "Pronto per essere firmato e caricato sul portale RUNTS.",
             "Genera PDF →",
             self._esporta_pdf,
             "Richiede che il bilancio sia stato calcolato almeno una volta.")

        card(p,
             "📝 Verbale di Bilancio (DOCX)",
             "Genera la bozza del verbale di assemblea in formato Word. "
             "Richiede un template .docx con i segnaposto appropriati.",
             "Genera Verbale DOCX →",
             self._esporta_verbale_docx,
             "Utilizza il file template_verbale.docx (se presente) o permette di caricarne uno.")

        card(p,
             "📝 Verbale di Approvazione (DOCX)",
             "Genera la bozza del verbale di approvazione bilancio in formato Word.",
             "Genera Verbale Approvazione →",
             self._esporta_verbale_approvazione_docx,
             "Utilizza il file template_verbale_approvazione.docx (se presente) o permette di caricarne uno.")

        card(p,
             "📋 JSON Prima Nota",
             "Esporta tutti i movimenti dell'anno in formato JSON. "
             "Formato aperto, importabile in qualsiasi applicazione.",
             "Esporta JSON →",
             lambda: self._esporta_generico("cassa", "json"))

        card(p,
             "📋 JSON Bilancio",
             "Esporta il prospetto di bilancio calcolato in formato JSON, "
             "inclusi tutti i totali e gli avanzi/disavanzi per sezione.",
             "Esporta JSON →",
             lambda: self._esporta_generico("bilancio", "json"))

        card(p,
             "📊 CSV Prima Nota",
             "Esporta i movimenti in CSV normalizzato. "
             "Compatibile con Excel, LibreOffice, Google Sheets, Banana Contabilità.",
             "Esporta CSV →",
             lambda: self._esporta_generico("cassa", "csv"))

        card(p,
             "📊 CSV Bilancio",
             "Esporta il prospetto di bilancio in CSV con struttura piatta.",
             "Esporta CSV →",
             lambda: self._esporta_generico("bilancio", "csv"))

    def _esporta_pdf(self):
        if not _controlla_reportlab():
            return
        if not hasattr(self, "bilancio_corrente"):
            self._genera_bilancio()
            if not hasattr(self, "bilancio_corrente"):
                return
        
        # Recupera configurazione aggiornata (contingente ai check in UI se presenti)
        cfg = leggi_config()
        # Se siamo nella pagina impostazioni, potremmo voler usare i valori a video
        # Ma di norma usiamo quelli salvati. Per sicurezza aggiorniamo cfg dai widget
        # se l'utente ha modificato qualcosa ma non ha salvato.
        if hasattr(self, "var_mostra_data"):
             cfg["mostra_data"] = self.var_mostra_data.get()
             cfg["mostra_pagine"] = self.var_mostra_pagine.get()
             cfg["mostra_nota_legale"] = self.var_mostra_nota_legale.get()
             cfg["mostra_nota_footer"] = self.var_mostra_nota_footer.get()
             cfg["mostra_firme"] = self.var_mostra_firme.get()
             cfg["data_documento"] = self.var_data_documento.get().strip()

        # Risolvi placeholder data
        data_risolta = cfg.get("data_documento", "").replace("{{ anno_consuntivo }}", str(self.anno_corrente.get()))

        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"rendiconto_{self.anno_corrente.get()}.pdf",
            title="Salva PDF Rendiconto"
        )
        if not path:
            return
        try:
            genera_pdf(self.bilancio_corrente, path,
                       cf=cfg.get("cf", ""),
                       iscrizione_runts=cfg.get("runts", ""),
                       firme=cfg.get("firme") if cfg.get("mostra_firme", True) else None,
                       nota_legale=cfg.get("nota_legale") if cfg.get("mostra_nota_legale", True) else "",
                       nota_footer=cfg.get("nota_footer") if cfg.get("mostra_nota_footer", True) else "",
                       mostra_data=cfg.get("mostra_data", True),
                       mostra_pagine=cfg.get("mostra_pagine", True),
                       data_stampa_manuale=data_risolta)
            messagebox.showinfo("PDF generato", f"File salvato:\n{path}")
            self._apri_file(path)
        except Exception as e:
            messagebox.showerror("Errore PDF", str(e))

    def _esporta_pdf_quick(self):
        if not _controlla_reportlab():
            return
        if not hasattr(self, "bilancio_corrente"):
            self._genera_bilancio()
        self._esporta_pdf()

    def _esporta_verbale_docx(self):
        self._esporta_verbale_base("template_verbale.docx", "Verbale_Assemblea", includi_tabella=True, cfg_key="verbale")

    def _esporta_verbale_approvazione_docx(self):
        # In questo verbale non va messo il pdf del bilancio
        self._esporta_verbale_base("template_verbale_approvazione.docx", "Verbale_Approvazione", includi_tabella=False, cfg_key="approvazione")

    def _esporta_verbale_base(self, template_nome: str, prefix_output: str, includi_tabella: bool = True, cfg_key: str = "verbale"):
        if not _controlla_docxtpl():
            return
        if not hasattr(self, "bilancio_corrente"):
            self._genera_bilancio()
            if not hasattr(self, "bilancio_corrente"):
                return

        # Cerca il template
        template_path = Path(__file__).resolve().parent / template_nome
        if not template_path.exists():
            tried_dirs = []
            if self.var_data_dir.get().strip():
                tried_dirs.append(Path(self.var_data_dir.get().strip()))
            tried_dirs.append(DATA_DIR)
            tried_dirs.extend([Path(__file__).resolve().parent, Path.cwd()])
            found = False
            for candidate_dir in dict.fromkeys(tried_dirs):
                candidate = candidate_dir / template_nome
                if candidate.exists():
                    template_path = candidate
                    logger.info(f"Trovato template '{template_nome}' in {candidate_dir}: {template_path}")
                    found = True
                    break
            if not found:
                logger.info(
                    f"Template '{template_nome}' non trovato in app dir ({Path(__file__).resolve().parent}), "
                    f"cwd ({Path.cwd()}) o data dir ({DATA_DIR})"
                )
                messagebox.showinfo("Template non trovato",
                                    f"Il file template '{template_nome}' non è stato trovato.\n\n"
                                    "Per favore, seleziona il file template DOCX da utilizzare.")
                template_path_str = filedialog.askopenfilename(
                    filetypes=[("Word Document", "*.docx")],
                    title=f"Seleziona il template per {template_nome}"
                )
                if not template_path_str:
                    return
                template_path = Path(template_path_str)

        if not template_path.exists():
            messagebox.showerror("Template non valido",
                                 f"Il file selezionato non esiste:\n{template_path}")
            return
            
        out_path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word Document", "*.docx")],
            initialfile=f"{prefix_output}_{self.anno_corrente.get()}.docx",
            title="Salva Documento Word"
        )
        if not out_path:
            return
            
        try:
            cfg_full = leggi_config()
            # Estraiamo la configurazione specifica
            cfg = cfg_full.get(cfg_key, {})
            
            # Se siamo nella pagina impostazioni, potremmo voler usare i valori a video
            # (Ma per semplicità qui ricarichiamo dal file salvato o usiamo i default)

            # Risolvi placeholder data
            data_risolta = cfg.get("data_documento", "").replace("{{ anno_consuntivo }}", str(self.anno_corrente.get()))

            logger.info(f"Generating DOCX using template {template_path} -> {out_path}")
            genera_verbale_docx(
                self.bilancio_corrente, 
                template_path, 
                out_path,
                genera_pdf_func=genera_pdf if includi_tabella else None,
                cf=cfg_full.get("cf", ""),
                runts=cfg_full.get("runts", ""),
                firme=cfg.get("firme") if cfg.get("mostra_firme", True) else None,
                nota_legale=cfg_full.get("nota_legale") if cfg_full.get("mostra_nota_legale", True) else "",
                nota_footer=cfg_full.get("nota_footer") if cfg_full.get("mostra_nota_footer", True) else "",
                mostra_data=cfg.get("mostra_data", True),
                mostra_pagine=cfg.get("mostra_pagine", True),
                data_manuale=data_risolta
            )
            logger.info(f"Generated DOCX document: {out_path}")
            messagebox.showinfo("Documento generato", f"File salvato:\n{out_path}")
            self._apri_file(out_path)
        except Exception as e:
            messagebox.showerror("Errore DOCX", str(e))

    def _esporta_generico(self, tipo: str, fmt: str):
        anno = self.anno_corrente.get()
        nome_default = f"{tipo}_{anno}_export.{fmt}"
        ext_label = fmt.upper()
        path = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}",
            filetypes=[(ext_label, f"*.{fmt}"), ("Tutti", "*.*")],
            initialfile=nome_default,
            title=f"Esporta {tipo} in {ext_label}"
        )
        if not path:
            return
        try:
            if tipo == "cassa" and fmt == "json":
                esporta_cassa_json(self.movimenti, path)
            elif tipo == "cassa" and fmt == "csv":
                esporta_cassa_csv(self.movimenti, path)
            elif tipo == "bilancio":
                if not hasattr(self, "bilancio_corrente"):
                    self._genera_bilancio()
                if fmt == "json":
                    esporta_bilancio_json(self.bilancio_corrente, path)
                else:
                    esporta_bilancio_csv(self.bilancio_corrente, path)
            messagebox.showinfo("Export completato", f"File salvato:\n{path}")
        except Exception as e:
            messagebox.showerror("Errore export", str(e))

    @staticmethod
    def _apri_file(path: str):
        """Apre il file con l'applicazione predefinita del sistema."""
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        except Exception:
            pass

    # ── Pagina Impostazioni ───────────────────────────────────────────────

    def _build_impostazioni(self):
        p = self.page_impostazioni

        # Crea un canvas scorrevole per le impostazioni
        canvas = tk.Canvas(p, bg=C_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(p, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas, style="Content.TFrame")

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        canvas.bind("<Configure>", _on_canvas_configure)
        scroll_frame.bind("<Enter>", _bind_mousewheel)
        scroll_frame.bind("<Leave>", _unbind_mousewheel)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        ttk.Label(scroll_frame, text="Impostazioni ente", style="Title.TLabel").pack(anchor="w", pady=(8, 16), padx=20)

        fr = ttk.Frame(scroll_frame, style="Content.TFrame")
        fr.pack(anchor="w", padx=20, fill="x")

        cfg = leggi_config()

        def riga(parent, label, var, width=40):
            row = ttk.Frame(parent, style="Content.TFrame")
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=label, width=24, anchor="e").pack(side="left", padx=(0, 8))
            ttk.Entry(row, textvariable=var, width=width,
                      font=("Helvetica", 10)).pack(side="left")

        self.var_ente  = tk.StringVar(value=cfg.get("ente", ""))
        self.var_cf    = tk.StringVar(value=cfg.get("cf", ""))
        self.var_runts = tk.StringVar(value=cfg.get("runts", ""))
        self.var_log_level = tk.StringVar(value=cfg.get("log_level", "INFO"))
        self.var_log_path = tk.StringVar(value=cfg.get("log_path", str(CONFIG_DIR / "cassaets.log")))
        self.var_config_in_data_dir = tk.BooleanVar(value=cfg.get("config_in_data_dir", False))
        self.var_config_path = tk.StringVar()

        riga(fr, "Nome ente:",        self.var_ente, 50)
        riga(fr, "Codice fiscale:",   self.var_cf,   20)
        riga(fr, "Iscrizione RUNTS:", self.var_runts, 20)

        row_log_level = ttk.Frame(fr, style="Content.TFrame")
        row_log_level.pack(fill="x", pady=5)
        ttk.Label(row_log_level, text="Livello log:", width=24, anchor="e").pack(side="left", padx=(0, 8))
        ttk.Combobox(row_log_level, textvariable=self.var_log_level,
                     values=["NONE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                     width=12, state="readonly").pack(side="left")

        row_log = ttk.Frame(fr, style="Content.TFrame")
        row_log.pack(fill="x", pady=5)
        ttk.Label(row_log, text="Percorso log:", width=24, anchor="e").pack(side="left", padx=(0, 8))
        ttk.Entry(row_log, textvariable=self.var_log_path, width=40,
                  font=("Helvetica", 10)).pack(side="left")

        def scegli_log_dir():
            iniziale = Path(self.var_log_path.get() or CONFIG_DIR)
            if iniziale.is_file():
                iniziale = iniziale.parent
            nuova_dir = filedialog.askdirectory(
                title="Scegli la directory dei log",
                initialdir=str(iniziale)
            )
            if nuova_dir:
                self.var_log_path.set(str(Path(nuova_dir) / "cassaets.log"))

        ttk.Button(row_log, text="📂 Sfoglia…", command=scegli_log_dir).pack(side="left", padx=(6, 0))

        ttk.Checkbutton(fr,
                        text="Memorizza config.json nella cartella dati",
                        variable=self.var_config_in_data_dir,
                        command=self._refresh_config_path_display).pack(anchor="w", pady=(8, 4))

        row_cfg = ttk.Frame(fr, style="Content.TFrame")
        row_cfg.pack(fill="x", pady=5)
        ttk.Label(row_cfg, text="Percorso config.json:", width=24, anchor="e").pack(side="left", padx=(0, 8))
        ttk.Entry(row_cfg, textvariable=self.var_config_path, width=40,
                  font=("Helvetica", 10), state="readonly").pack(side="left")
        self._refresh_config_path_display()
        
        # --- PERSONALIZZAZIONE DOCUMENTI ---
        ttk.Separator(fr).pack(fill="x", pady=15)
        ttk.Label(fr, text="Personalizzazione Rendiconto PDF",
                  font=("Helvetica", 10, "bold")).pack(anchor="w")

        self.var_firme = tk.StringVar(value=", ".join(cfg["firme"]))
        self.var_mostra_firme = tk.BooleanVar(value=cfg["mostra_firme"])
        row_firme = ttk.Frame(fr, style="Content.TFrame")
        row_firme.pack(fill="x", pady=5)
        ttk.Label(row_firme, text="Firme (separate da virgola):", width=24, anchor="e").pack(side="left", padx=(0, 8))
        ttk.Entry(row_firme, textvariable=self.var_firme, width=40, font=("Helvetica", 10)).pack(side="left")
        ttk.Checkbutton(row_firme, text="Includi", variable=self.var_mostra_firme).pack(side="left", padx=10)
        
        self.var_nota_legale = tk.StringVar(value=cfg["nota_legale"])
        self.var_mostra_nota_legale = tk.BooleanVar(value=cfg["mostra_nota_legale"])
        row_nl = ttk.Frame(fr, style="Content.TFrame")
        row_nl.pack(fill="x", pady=5)
        ttk.Label(row_nl, text="Nota finale:", width=24, anchor="e").pack(side="left", padx=(0, 8))
        ttk.Entry(row_nl, textvariable=self.var_nota_legale, width=40, font=("Helvetica", 10)).pack(side="left")
        ttk.Checkbutton(row_nl, text="Includi", variable=self.var_mostra_nota_legale).pack(side="left", padx=10)
        
        self.var_nota_footer = tk.StringVar(value=cfg["nota_footer"])
        self.var_mostra_nota_footer = tk.BooleanVar(value=cfg["mostra_nota_footer"])
        row_nf = ttk.Frame(fr, style="Content.TFrame")
        row_nf.pack(fill="x", pady=5)
        ttk.Label(row_nf, text="Nota a piè pagina:", width=24, anchor="e").pack(side="left", padx=(0, 8))
        ttk.Entry(row_nf, textvariable=self.var_nota_footer, width=40, font=("Helvetica", 10)).pack(side="left")
        ttk.Checkbutton(row_nf, text="Includi", variable=self.var_mostra_nota_footer).pack(side="left", padx=10)
        
        self.var_data_documento = tk.StringVar(value=cfg["data_documento"])
        row_dd = ttk.Frame(fr, style="Content.TFrame")
        row_dd.pack(fill="x", pady=5)
        ttk.Label(row_dd, text="Data documento:", width=24, anchor="e").pack(side="left", padx=(0, 8))
        ttk.Entry(row_dd, textvariable=self.var_data_documento, width=40, font=("Helvetica", 10)).pack(side="left")
        ttk.Label(row_dd, text="(usa {{ anno_consuntivo }})", foreground=C_MUTED, font=("Helvetica", 8)).pack(side="left", padx=5)

        self.var_mostra_data = tk.BooleanVar(value=cfg["mostra_data"])
        self.var_mostra_pagine = tk.BooleanVar(value=cfg["mostra_pagine"])
        row_data = ttk.Frame(fr, style="Content.TFrame")
        row_data.pack(fill="x", pady=5)
        ttk.Label(row_data, text="", width=24).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(row_data, text="Mostra data di stampa", variable=self.var_mostra_data).pack(side="left")
        ttk.Checkbutton(row_data, text="Mostra numeri di pagina", variable=self.var_mostra_pagine).pack(side="left", padx=20)

        # --- DOCX VERBALE ASSEMBLEA ---
        ttk.Separator(fr).pack(fill="x", pady=15)
        ttk.Label(fr, text="Personalizzazione Verbale Assemblea (DOCX)",
                  font=("Helvetica", 10, "bold")).pack(anchor="w")

        v_cfg = cfg.get("verbale", {})
        self.var_v_firme = tk.StringVar(value=", ".join(v_cfg.get("firme", [])))
        self.var_v_mostra_firme = tk.BooleanVar(value=v_cfg.get("mostra_firme", True))
        row_v_firme = ttk.Frame(fr, style="Content.TFrame")
        row_v_firme.pack(fill="x", pady=5)
        ttk.Label(row_v_firme, text="Firme:", width=24, anchor="e").pack(side="left", padx=(0, 8))
        ttk.Entry(row_v_firme, textvariable=self.var_v_firme, width=40, font=("Helvetica", 10)).pack(side="left")
        ttk.Checkbutton(row_v_firme, text="Includi", variable=self.var_v_mostra_firme).pack(side="left", padx=10)

        self.var_v_data_doc = tk.StringVar(value=v_cfg.get("data_documento", ""))
        row_v_dd = ttk.Frame(fr, style="Content.TFrame")
        row_v_dd.pack(fill="x", pady=5)
        ttk.Label(row_v_dd, text="Data verbale:", width=24, anchor="e").pack(side="left", padx=(0, 8))
        ttk.Entry(row_v_dd, textvariable=self.var_v_data_doc, width=40, font=("Helvetica", 10)).pack(side="left")

        # --- DOCX VERBALE APPROVAZIONE ---
        ttk.Separator(fr).pack(fill="x", pady=15)
        ttk.Label(fr, text="Personalizzazione Verbale Approvazione (DOCX)",
                  font=("Helvetica", 10, "bold")).pack(anchor="w")

        a_cfg = cfg.get("approvazione", {})
        self.var_a_firme = tk.StringVar(value=", ".join(a_cfg.get("firme", [])))
        self.var_a_mostra_firme = tk.BooleanVar(value=a_cfg.get("mostra_firme", True))
        row_a_firme = ttk.Frame(fr, style="Content.TFrame")
        row_a_firme.pack(fill="x", pady=5)
        ttk.Label(row_a_firme, text="Firme:", width=24, anchor="e").pack(side="left", padx=(0, 8))
        ttk.Entry(row_a_firme, textvariable=self.var_a_firme, width=40, font=("Helvetica", 10)).pack(side="left")
        ttk.Checkbutton(row_a_firme, text="Includi", variable=self.var_a_mostra_firme).pack(side="left", padx=10)

        self.var_a_data_doc = tk.StringVar(value=a_cfg.get("data_documento", ""))
        row_a_dd = ttk.Frame(fr, style="Content.TFrame")
        row_a_dd.pack(fill="x", pady=5)
        ttk.Label(row_a_dd, text="Data approvazione:", width=24, anchor="e").pack(side="left", padx=(0, 8))
        ttk.Entry(row_a_dd, textvariable=self.var_a_data_doc, width=40, font=("Helvetica", 10)).pack(side="left")

        ttk.Button(fr, text="💾 Salva impostazioni",
                   style="Accent.TButton",
                   command=self._salva_impostazioni).pack(anchor="w", pady=12)

        ttk.Separator(fr).pack(fill="x", pady=12)

        # ── Directory dati ──────────────────────────────────────────────────
        ttk.Label(fr, text="Directory dati",
                  font=("Helvetica", 10, "bold")).pack(anchor="w")
        ttk.Label(fr,
                  text="Cartella dove vengono letti e salvati i file CSV.",
                  foreground=C_MUTED, font=("Helvetica", 9),
                  wraplength=560, justify="left").pack(anchor="w", pady=(2, 6))

        row_dir = ttk.Frame(fr, style="Content.TFrame")
        row_dir.pack(fill="x", pady=4)

        self.var_data_dir = tk.StringVar(value=str(DATA_DIR))
        entry_dir = ttk.Entry(row_dir, textvariable=self.var_data_dir,
                              width=52, font=("Helvetica", 9))
        entry_dir.pack(side="left", padx=(0, 6))

        def scegli_directory():
            nuova = filedialog.askdirectory(
                title="Scegli la directory dei dati",
                initialdir=self.var_data_dir.get()
            )
            if nuova:
                self.var_data_dir.set(nuova)

        ttk.Button(row_dir, text="📂 Sfoglia…",
                   command=scegli_directory).pack(side="left")

        self.var_sync_log = tk.BooleanVar(value=cfg.get("sync_log_path", True))
        ttk.Checkbutton(fr, text="Aggiorna automaticamente il percorso log quando cambia la directory dati",
                        variable=self.var_sync_log,
                        command=self._salva_impostazioni).pack(anchor="w", pady=(2, 8))

        ttk.Button(fr, text="✅ Applica directory",
                   style="Accent.TButton",
                   command=self._applica_data_dir).pack(anchor="w", pady=(8, 4))

        ttk.Label(fr,
                  text="Dopo aver applicato, l'applicazione ricarica i dati dalla nuova directory.",
                  foreground=C_MUTED, font=("Helvetica", 9)).pack(anchor="w")

        ttk.Separator(fr).pack(fill="x", pady=12)

        ttk.Button(fr, text="📂 Apri directory corrente",
                   command=lambda: self._apri_file(str(DATA_DIR))).pack(anchor="w")

        ttk.Separator(fr).pack(fill="x", pady=12)

        # ── Importazione Excel ──────────────────────────────────────────────
        ttk.Label(fr, text="Importazione Excel",
                  font=("Helvetica", 10, "bold")).pack(anchor="w")
        ttk.Label(fr,
                  text="Importa i movimenti dai fogli 'Cassa_XXXX' di un file .xlsm. "
                       "I dati verranno convertiti in file CSV nella directory corrente.",
                  foreground=C_MUTED, font=("Helvetica", 9),
                  wraplength=560, justify="left").pack(anchor="w", pady=(2, 6))

        ttk.Button(fr, text="📊 Importa dati da Excel (.xlsm)",
                   command=self._importa_excel).pack(anchor="w", pady=4)

    def _importa_excel(self):
        if not EXCEL_DISPONIBILE:
            pip_cmd = f'"{sys.executable}" -m pip install openpyxl'
            messagebox.showerror(
                "Libreria mancante — openpyxl",
                "Per importare da Excel è necessaria la libreria openpyxl.\n\n"
                "Per installarla apri il Prompt dei comandi e digita:\n\n"
                f"    {pip_cmd}"
            )
            return

        file_path = filedialog.askopenfilename(
            title="Seleziona il file Excel (.xlsm)",
            filetypes=[("Excel Macro-Enabled Workbook", "*.xlsm"), ("Excel Workbook", "*.xlsx")]
        )
        if not file_path:
            return

        try:
            import_excel_data(file_path, str(DATA_DIR))
            messagebox.showinfo("Importazione completata", 
                                "I dati sono stati importati correttamente.\n"
                                "Riavvia l'applicazione o cambia anno per vedere i nuovi dati.")
            # Aggiorna gli anni disponibili
            anni = anni_disponibili()
            self.combo_anno["values"] = anni
        except Exception as e:
            messagebox.showerror("Errore importazione", str(e))

    def _applica_data_dir(self):
        global DATA_DIR
        nuova = Path(self.var_data_dir.get().strip())
        if not nuova.exists():
            if messagebox.askyesno("Directory non trovata",
                                   f"La directory\n{nuova}\nnon esiste. Crearla?"):
                nuova.mkdir(parents=True, exist_ok=True)
            else:
                return

        DATA_DIR = nuova

        # Persisti la scelta nel config e aggiorna il percorso log se richiesto
        cfg = leggi_config()
        cfg["data_dir"] = str(DATA_DIR)
        
        if self.var_sync_log.get():
            nuovo_log = DATA_DIR / "cassaets.log"
            cfg["log_path"] = str(nuovo_log)
            self.var_log_path.set(str(nuovo_log))
            setup_logging(self.var_log_level.get(), str(nuovo_log))
        
        cfg["config_in_data_dir"] = self.var_config_in_data_dir.get()
        salva_config(cfg)

        # Aggiorna combo anni con i file trovati nella nuova directory
        anni = anni_disponibili()
        self.combo_anno["values"] = anni if anni else [datetime.now().year]

        if anni:
            self.anno_corrente.set(anni[0])
            self._carica_anno()
            self._refresh_config_path_display()
            logger.info("Directory dati aggiornata: %s. Anni trovati: %s", DATA_DIR, ", ".join(str(a) for a in anni))
            messagebox.showinfo("Directory aggiornata",
                                f"Directory impostata:\n{DATA_DIR}\n\n"
                                f"Anni trovati: {', '.join(str(a) for a in anni)}")
        else:
            logger.warning("Nessun file cassa_*.csv trovato nella directory dati: %s", DATA_DIR)
            messagebox.showinfo("Directory aggiornata",
                                f"Directory impostata:\n{DATA_DIR}\n\n"
                                "Nessun file cassa_ANNO.csv trovato.\n"
                                "Copia i tuoi CSV qui oppure usa '+ Nuovo anno'.")

    def _get_config_path_for_ui(self) -> str:
        if getattr(self, "var_config_in_data_dir", None) and self.var_config_in_data_dir.get():
            cartella = Path(self.var_data_dir.get().strip() or str(DATA_DIR))
            return str((cartella / "config.json").resolve())
        return str((CONFIG_DIR / "config.json").resolve())

    def _refresh_config_path_display(self) -> None:
        if hasattr(self, "var_config_path"):
            self.var_config_path.set(self._get_config_path_for_ui())

    def _salva_impostazioni(self):
        new_level = self.var_log_level.get()
        new_path = self.var_log_path.get().strip()
        
        # Parsa le firme dalla stringa
        firme_list = [f.strip() for f in self.var_firme.get().split(",") if f.strip()]
        if not firme_list:
            firme_list = ["Il Presidente", "Il Tesoriere", "Il Revisore dei Conti"]

        salva_config({
            "ente":  self.var_ente.get().strip(),
            "cf":    self.var_cf.get().strip(),
            "runts": self.var_runts.get().strip(),
            "data_dir": self.var_data_dir.get().strip(),
            "log_level": new_level,
            "log_path": new_path,
            "sync_log_path": self.var_sync_log.get(),
            "config_in_data_dir": self.var_config_in_data_dir.get(),
            "firme": firme_list,
            "mostra_firme": self.var_mostra_firme.get(),
            "data_documento": self.var_data_documento.get().strip(),
            "nota_legale": self.var_nota_legale.get().strip(),
            "nota_footer": self.var_nota_footer.get().strip(),
            "mostra_data": self.var_mostra_data.get(),
            "mostra_nota_legale": self.var_mostra_nota_legale.get(),
            "mostra_nota_footer": self.var_mostra_nota_footer.get(),
            "mostra_pagine": self.var_mostra_pagine.get(),
            "verbale": {
                "firme": [f.strip() for f in self.var_v_firme.get().split(",") if f.strip()],
                "mostra_firme": self.var_v_mostra_firme.get(),
                "data_documento": self.var_v_data_doc.get().strip(),
                "mostra_data": True,
                "mostra_pagine": True
            },
            "approvazione": {
                "firme": [f.strip() for f in self.var_a_firme.get().split(",") if f.strip()],
                "mostra_firme": self.var_a_mostra_firme.get(),
                "data_documento": self.var_a_data_doc.get().strip(),
                "mostra_data": True,
                "mostra_pagine": True
            }
        })
        setup_logging(new_level, new_path)
        self._refresh_config_path_display()
        messagebox.showinfo("Salvato", "Impostazioni aggiornate.")

    # ── Gestione anni e CSV ───────────────────────────────────────────────

    def _carica_anno(self):
        anno = self.anno_corrente.get()
        # Salva l'anno corrente come ultimo anno nel config
        cfg = leggi_config()
        cfg["ultimo_anno"] = anno
        salva_config(cfg)
        
        p = path_cassa(anno)
        if p.exists():
            try:
                self.movimenti = leggi_cassa(p)
            except Exception as e:
                logger.exception("Errore lettura CSV da %s", p)
                messagebox.showerror("Errore lettura CSV", str(e))
                self.movimenti = []
        else:
            logger.warning("CSV non trovato per l'anno %s: %s", anno, p)
            self.movimenti = []
        self._aggiorna_tabella()
        # Reset bilancio corrente
        if hasattr(self, "bilancio_corrente"):
            del self.bilancio_corrente
        self.tree_bil.delete(*self.tree_bil.get_children()) if hasattr(self, "tree_bil") else None

    def _salva_csv(self):
        anno = self.anno_corrente.get()
        esporta_cassa_csv(self.movimenti, path_cassa(anno))

    def _nuovo_anno(self):
        anno = simpledialog.askinteger(
            "Nuovo anno contabile",
            "Inserisci l'anno da creare:",
            minvalue=2000, maxvalue=2099,
            parent=self
        )
        if anno is None:
            return
        if path_cassa(anno).exists():
            messagebox.showinfo("Info", f"Il file per il {anno} esiste già.")
        else:
            nuovo_anno_csv(anno)
            messagebox.showinfo("Creato", f"File cassa_{anno}.csv creato.\nInserisci i saldi iniziali.")

        # Aggiorna combo anni
        anni = anni_disponibili()
        self.combo_anno["values"] = anni
        self.anno_corrente.set(anno)
        self._carica_anno()


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = CassaETS()
    signal.signal(signal.SIGINT, lambda signum, frame: app.quit())
    try:
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Interruzione da tastiera ricevuta, chiusura pulita.")
        try:
            app.destroy()
        except Exception:
            pass
