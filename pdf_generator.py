"""
pdf_generator.py — Genera il Rendiconto per Cassa ETS in PDF
usando reportlab (puro Python, nessuna dipendenza di sistema).

Installazione: pip install reportlab
Funziona su Windows, macOS e Linux senza GTK né altre librerie C.
"""

import io
from datetime import date
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle
)
from reportlab.platypus.flowables import HRFlowable

from contabilita import Bilancio, PIANO_DEI_CONTI

# ── Palette colori ───────────────────────────────────────────────────────────

C_NAVY      = colors.HexColor("#1a3a5c")
C_BLUE_LT   = colors.HexColor("#dbeafe")
C_BLUE_MID  = colors.HexColor("#bfdbfe")
C_GREEN_LT  = colors.HexColor("#dcfce7")
C_RED_LT    = colors.HexColor("#fee2e2")
C_GRAY_LT   = colors.HexColor("#f5f7fa")
C_GRAY_MID  = colors.HexColor("#e8eef5")
C_WHITE     = colors.white
C_BLACK     = colors.HexColor("#111111")
C_MUTED     = colors.HexColor("#6b7280")
C_GREEN     = colors.HexColor("#16a34a")
C_RED       = colors.HexColor("#dc2626")


# ── Stili testo ──────────────────────────────────────────────────────────────

def _stili():
    return {
        "title": ParagraphStyle(
            "title", fontName="Helvetica-Bold", fontSize=13,
            textColor=C_NAVY, spaceAfter=1*mm
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName="Helvetica", fontSize=9,
            textColor=C_MUTED, spaceAfter=0.5*mm
        ),
        "footer": ParagraphStyle(
            "footer", fontName="Helvetica", fontSize=6.5,
            textColor=C_MUTED
        ),
        "nota": ParagraphStyle(
            "nota", fontName="Helvetica-Oblique", fontSize=6.5,
            textColor=C_MUTED, spaceAfter=0
        ),
    }


# ── Costruzione dati tabella ─────────────────────────────────────────────────

def _fmt(v: Optional[float], vuoto_se_zero: bool = False) -> str:
    if v is None:
        return ""
    if vuoto_se_zero and v == 0.0:
        return ""
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _costruisci_dati_tabella(bil: Bilancio) -> list[tuple]:
    """
    Restituisce lista di tuple:
    (label_u, val_u, val_u_prec, label_e, val_e, val_e_prec, tipo_riga)
    tipo_riga: 'intestazione'|'voce'|'totale_sezione'|'avanzo'|
               'totale_gestione'|'finale'|'saldo'|'totale_generale'|'vuota'
    """

    # Mappa codice → (corrente, precedente)
    val: dict[str, tuple[float, float]] = {}
    for r in bil.righe:
        val[r.codice] = (r.importo_corrente, r.importo_precedente)

    # Raggruppa per numero riga
    by_row: dict[int, dict] = {}
    for voce in PIANO_DEI_CONTI:
        cod  = voce["codice"]
        riga = voce["riga"]
        tipo = voce["tipo"]
        lbl  = voce["label"]
        c, p = val.get(cod, (0.0, 0.0))

        entry = {"codice": cod, "label": lbl, "tipo": tipo, "c": c, "p": p}
        if cod.startswith("U.") or cod in ("Z.U.1","Z.U.2","Z.U.3","Z.U.4","Z.U.5"):
            by_row.setdefault(riga, {})["u"] = entry
        elif cod.startswith("E.") or cod.startswith("Z.E."):
            by_row.setdefault(riga, {})["e"] = entry

    righe = []

    for rn in sorted(by_row.keys()):
        u = by_row[rn].get("u")
        e = by_row[rn].get("e")
        tipo = (u or e)["tipo"]

        # Label con indentazione per le voci operative
        def lbl_fmt(entry, side):
            if not entry:
                return ""
            if entry["tipo"] == "voce":
                return "   " + entry["label"]
            return entry["label"]

        # Valori
        val_u = _fmt(u["c"], vuoto_se_zero=(tipo == "voce")) if u and tipo != "intestazione" else ""
        prec_u = _fmt(u["p"], vuoto_se_zero=True) if u and tipo == "voce" else ""
        val_e = _fmt(e["c"], vuoto_se_zero=(tipo == "voce")) if e and tipo != "intestazione" else ""
        prec_e = _fmt(e["p"], vuoto_se_zero=True) if e and tipo == "voce" else ""

        righe.append((
            lbl_fmt(u, "u"), val_u, prec_u,
            lbl_fmt(e, "e"), val_e, prec_e,
            tipo
        ))

    # Righe finali
    anno = bil.anno
    righe += [
        ("Totale uscite della gestione",
         _fmt(bil.totale_uscite), "",
         "Totale entrate della gestione",
         _fmt(bil.totale_entrate), "",
         "totale_gestione"),

        ("", "", "",
         "Avanzo/disavanzo d'esercizio prima delle imposte",
         _fmt(bil.avanzo_esercizio), "",
         "avanzo" if bil.avanzo_esercizio >= 0 else "avanzo_neg"),

        ("", "", "",
         "Imposte",
         _fmt(bil.imposte, vuoto_se_zero=True), "",
         "finale"),

        ("", "", "",
         "Avanzo/disavanzo prima di investimenti patrimoniali",
         _fmt(bil.avanzo_finale), "",
         "avanzo" if bil.avanzo_finale >= 0 else "avanzo_neg"),

        ("Cassa",
         _fmt(bil.saldo_cassa), "",
         "", "", "",
         "saldo"),

        ("Conto corrente",
         _fmt(bil.saldo_cc), "",
         "", "", "",
         "saldo"),

        ("Totale generale",
         _fmt(bil.totale_generale), "",
         "", "", "",
         "totale_generale"),
    ]

    return righe


# ── Stile tabella per riga ───────────────────────────────────────────────────

def _build_table_style(dati: list[tuple], header_rows: int = 1) -> TableStyle:
    cmds = [
        # Header
        ("BACKGROUND",    (0,0), (-1, header_rows-1), C_NAVY),
        ("TEXTCOLOR",     (0,0), (-1, header_rows-1), C_WHITE),
        ("FONTNAME",      (0,0), (-1, header_rows-1), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1, header_rows-1), 8.5),
        ("ALIGN",         (1,0), (2,0), "CENTER"),
        ("ALIGN",         (4,0), (5,0), "CENTER"),
        # Tutte le celle
        ("FONTSIZE",      (0,1), (-1,-1), 8),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ("TOPPADDING",    (0,0), (-1,-1), 2.5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2.5),
        # Numeri a destra
        ("ALIGN",         (1,1), (2,-1), "RIGHT"),
        ("ALIGN",         (4,1), (5,-1), "RIGHT"),
        # Griglia leggera
        ("GRID",          (0,0), (-1,-1), 0.25, colors.HexColor("#d1d5db")),
        ("LINEBELOW",     (0,0), (-1,0),  1.0,  C_NAVY),
    ]

    for i, row in enumerate(dati[header_rows:], start=header_rows):
        tipo = row[6] if len(row) > 6 else "voce"

        if tipo == "intestazione":
            cmds += [
                ("BACKGROUND", (0,i), (-1,i), C_BLUE_LT),
                ("FONTNAME",   (0,i), (-1,i), "Helvetica-Bold"),
                ("FONTSIZE",   (0,i), (-1,i), 8.5),
            ]
        elif tipo in ("totale_sezione",):
            cmds += [
                ("BACKGROUND", (0,i), (-1,i), C_BLUE_MID),
                ("FONTNAME",   (0,i), (-1,i), "Helvetica-Bold"),
                ("LINEABOVE",  (0,i), (-1,i), 1.0, C_NAVY),
            ]
        elif tipo == "totale_gestione":
            cmds += [
                ("BACKGROUND", (0,i), (-1,i), C_BLUE_MID),
                ("FONTNAME",   (0,i), (-1,i), "Helvetica-Bold"),
                ("FONTSIZE",   (0,i), (-1,i), 8.5),
                ("LINEABOVE",  (0,i), (-1,i), 1.5, C_NAVY),
            ]
        elif tipo == "avanzo":
            cmds += [
                ("BACKGROUND", (0,i), (-1,i), C_GREEN_LT),
                ("FONTNAME",   (0,i), (-1,i), "Helvetica-Bold"),
                ("TEXTCOLOR",  (4,i), (4,i),  C_GREEN),
            ]
        elif tipo == "avanzo_neg":
            cmds += [
                ("BACKGROUND", (0,i), (-1,i), C_RED_LT),
                ("FONTNAME",   (0,i), (-1,i), "Helvetica-Bold"),
                ("TEXTCOLOR",  (4,i), (4,i),  C_RED),
            ]
        elif tipo == "saldo":
            cmds += [
                ("BACKGROUND", (0,i), (-1,i), C_GRAY_MID),
                ("FONTNAME",   (0,i), (-1,i), "Helvetica-Bold"),
            ]
        elif tipo == "totale_generale":
            cmds += [
                ("BACKGROUND", (0,i), (-1,i), C_NAVY),
                ("TEXTCOLOR",  (0,i), (-1,i), C_WHITE),
                ("FONTNAME",   (0,i), (-1,i), "Helvetica-Bold"),
                ("FONTSIZE",   (0,i), (-1,i), 9),
                ("LINEABOVE",  (0,i), (-1,i), 1.5, C_NAVY),
            ]
        elif tipo == "finale":
            cmds += [
                ("BACKGROUND", (0,i), (-1,i), C_GRAY_LT),
            ]
        elif i % 2 == 0:
            cmds += [("BACKGROUND", (0,i), (-1,i), C_GRAY_LT)]

    return TableStyle(cmds)


# ── Header e footer di pagina ────────────────────────────────────────────────

def _make_page_header_footer(ente, anno, cf, runts, data_stampa):
    """Restituisce una funzione callable per il canvas di ogni pagina."""

    def on_page(canvas, doc):
        canvas.saveState()
        W, H = landscape(A4)

        # ── Header ──
        canvas.setFillColor(C_NAVY)
        canvas.rect(10*mm, H - 22*mm, W - 20*mm, 14*mm, fill=1, stroke=0)

        canvas.setFillColor(C_WHITE)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(14*mm, H - 12*mm, ente)

        canvas.setFont("Helvetica", 8)
        canvas.drawString(14*mm, H - 17.5*mm,
                          "Rendiconto per Cassa — Modello D (D.M. 39/2020 art. 13)")

        canvas.setFont("Helvetica-Bold", 22)
        anno_str = str(anno)
        canvas.drawRightString(W - 14*mm, H - 12*mm, anno_str)

        canvas.setFont("Helvetica", 7.5)
        info_parts = []
        if cf:
            info_parts.append(f"CF: {cf}")
        if runts:
            info_parts.append(f"RUNTS: {runts}")
        info_parts.append(f"Stampato il {data_stampa}")
        canvas.drawRightString(W - 14*mm, H - 18*mm, "  |  ".join(info_parts))

        # ── Footer ──
        canvas.setFillColor(C_MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(10*mm, 8*mm,
            "Rendiconto redatto ai sensi dell'art. 13 co. 2 D.Lgs. 117/2017 "
            "(Codice del Terzo Settore) e del D.M. 39/2020 Modello D.")
        canvas.drawRightString(W - 10*mm, 8*mm,
            f"Pagina {doc.page}")

        # Linea separatrice footer
        canvas.setStrokeColor(colors.HexColor("#d1d5db"))
        canvas.setLineWidth(0.5)
        canvas.line(10*mm, 12*mm, W - 10*mm, 12*mm)

        canvas.restoreState()

    return on_page


# ── Blocco firma ─────────────────────────────────────────────────────────────

def _firma_table() -> Table:
    data = [
        ["Il Presidente", "Il Tesoriere", "Il Revisore dei Conti"],
        ["\n\n\n_______________________",
         "\n\n\n_______________________",
         "\n\n\n_______________________"],
    ]
    t = Table(data, colWidths=[90*mm, 90*mm, 90*mm])
    t.setStyle(TableStyle([
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 8.5),
        ("TEXTCOLOR",     (0,0), (-1,0),  C_NAVY),
        ("TOPPADDING",    (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("LINEBELOW",     (0,1), (-1,1),  0, C_WHITE),
    ]))
    return t


# ── Funzione principale ──────────────────────────────────────────────────────

def genera_pdf(
    bil: Bilancio,
    path_output: str | Path,
    cf: str = "",
    iscrizione_runts: str = "",
) -> None:
    """
    Genera il Rendiconto per Cassa Mod. D in PDF.
    Usa reportlab: puro Python, nessuna dipendenza di sistema.

    pip install reportlab
    """
    W, H = landscape(A4)
    data_stampa = date.today().strftime("%d/%m/%Y")
    ente = bil.ente or "Associazione"

    on_page = _make_page_header_footer(ente, bil.anno, cf, iscrizione_runts, data_stampa)

    # ── Template pagina ──
    frame = Frame(
        10*mm, 16*mm,          # x, y (bottom-left del frame)
        W - 20*mm,             # larghezza
        H - 16*mm - 26*mm,     # altezza (tolti header 22mm + margini)
        leftPadding=0, rightPadding=0,
        topPadding=2*mm, bottomPadding=0,
        id="main"
    )
    page_tpl = PageTemplate(id="main", frames=[frame], onPage=on_page)
    doc = BaseDocTemplate(
        str(path_output),
        pagesize=landscape(A4),
        pageTemplates=[page_tpl],
        leftMargin=10*mm, rightMargin=10*mm,
        topMargin=26*mm, bottomMargin=16*mm,
    )

    stili = _stili()
    story = []

    # ── Tabella rendiconto ──
    anno = bil.anno
    header_row = [
        "Uscite", str(anno), str(anno-1), "",
        "Entrate", str(anno), str(anno-1)
    ]

    dati_righe = _costruisci_dati_tabella(bil)

    # Costruisce righe tabella (senza colonna tipo nel PDF)
    table_data = [header_row] + [list(r[:6]) for r in dati_righe]

    # Larghezze colonne: lbl_u | val_u | prec_u | sep | lbl_e | val_e | prec_e
    avail = W - 20*mm
    col_w = [
        avail * 0.34,   # label uscite
        avail * 0.09,   # val uscite
        avail * 0.08,   # prec uscite
        avail * 0.01,   # separatore
        avail * 0.34,   # label entrate
        avail * 0.09,   # val entrate
        avail * 0.05,   # prec entrate (un po' meno per bilanciare)
    ]

    ts = _build_table_style(
        [("", "", "", "", "", "", "header")] + dati_righe,
        header_rows=1
    )
    t = Table(table_data, colWidths=col_w, repeatRows=1)
    t.setStyle(ts)
    story.append(t)

    # ── Firma ──
    story.append(Spacer(1, 8*mm))
    story.append(_firma_table())

    # ── Nota legale ──
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=colors.HexColor("#d1d5db")))
    story.append(Spacer(1, 1*mm))
    story.append(Paragraph(
        "I dati originali sono conservati in formato CSV aperto. "
        "Documento generato con CassaETS (reportlab).",
        stili["nota"]
    ))

    doc.build(story)
    print(f"PDF generato: {path_output}")


# ── Test standalone ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    from contabilita import leggi_cassa, calcola_bilancio
    base = Path(__file__).parent
    mvs  = leggi_cassa(base / "cassa_2025.csv")
    bil  = calcola_bilancio(2025, mvs, ente="APS Il Viale della Formica")
    genera_pdf(bil, base / "rendiconto_2025.pdf",
               cf="XXXXXXXXXX",
               iscrizione_runts="SO-XXXXXX")
