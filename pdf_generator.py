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
        prec_u = _fmt(u["p"], vuoto_se_zero=True) if u and tipo != "intestazione" else ""
        val_e = _fmt(e["c"], vuoto_se_zero=(tipo == "voce")) if e and tipo != "intestazione" else ""
        prec_e = _fmt(e["p"], vuoto_se_zero=True) if e and tipo != "intestazione" else ""

        righe.append((
            lbl_fmt(u, "u"), val_u, prec_u,
            lbl_fmt(e, "e"), val_e, prec_e,
            tipo
        ))

    # Righe finali
    # Estraiamo i dati dell'anno precedente per i totali se disponibili
    val_p = {}
    for r in bil.righe:
        val_p[r.codice] = r.importo_precedente

    def get_p(cod):
        return val_p.get(cod, 0.0)

    righe += [
        # Riga 46: Totale gestione
        ("Totale uscite della gestione", _fmt(bil.totale_uscite), _fmt(get_p("Z.U.11"), True),
         "Totale entrate della gestione", _fmt(bil.totale_entrate), _fmt(get_p("Z.E.11"), True),
         "totale_gestione"),

        # Riga 47: Avanzo/disavanzo prima imposte
        ("", "", "",
         "Avanzo/disavanzo d'esercizio prima delle imposte", _fmt(bil.avanzo_esercizio), _fmt(get_p("Z.E.12"), True),
         "avanzo" if bil.avanzo_esercizio >= 0 else "avanzo_neg"),

        # Riga 48: Imposte
        ("", "", "",
         "Imposte", _fmt(bil.imposte, vuoto_se_zero=True), _fmt(get_p("Z.E.13"), True),
         "finale"),

        # Riga 49: Avanzo/disavanzo finale
        ("", "", "",
         "Avanzo/disavanzo prima di investimenti patrimoniali", _fmt(bil.avanzo_finale), _fmt(get_p("Z.E.14"), True),
         "avanzo" if bil.avanzo_finale >= 0 else "avanzo_neg"),

        # Righe 50-51: Saldi di Cassa e CC
        ("Cassa", _fmt(bil.saldo_cassa), _fmt(get_p("Z.U.12"), True),
         "", "", "",
         "saldo"),

        ("Conto corrente", _fmt(bil.saldo_cc), _fmt(get_p("Z.U.13"), True),
         "", "", "",
         "saldo"),

        # Riga 52: Totale generale
        ("Totale generale", _fmt(bil.totale_generale), _fmt(get_p("Z.U.14"), True),
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
        ("ALIGN",         (1,1), (2,-1), "RIGHT"), # Valori Uscite
        ("ALIGN",         (5,1), (6,-1), "RIGHT"), # Valori Entrate
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
                ("TEXTCOLOR",  (5,i), (5,i),  C_GREEN), # Colonna Entrate corrente
            ]
        elif tipo == "avanzo_neg":
            cmds += [
                ("BACKGROUND", (0,i), (-1,i), C_RED_LT),
                ("FONTNAME",   (0,i), (-1,i), "Helvetica-Bold"),
                ("TEXTCOLOR",  (5,i), (5,i),  C_RED), # Colonna Entrate corrente
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

# ── Header e footer di pagina ────────────────────────────────────────────────

def _make_page_header_footer(ente, anno, cf, runts, data_stampa, nota_footer=None, mostra_data=True, mostra_pagine=True, is_one_page=False):
    """Restituisce una funzione callable per il canvas di ogni pagina."""

    def on_page(canvas, doc):
        canvas.saveState()
        W, H = doc.pagesize

        # ── Header ──
        # Spostiamo l'header leggermente più in basso e aumentiamo lo spazio sopra
        header_y = H - 25*mm
        canvas.setFillColor(C_NAVY)
        canvas.rect(10*mm, header_y, W - 20*mm, 14*mm, fill=1, stroke=0)

        canvas.setFillColor(C_WHITE)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(14*mm, header_y + 8.5*mm, ente)

        canvas.setFont("Helvetica", 8)
        canvas.drawString(14*mm, header_y + 3.5*mm,
                          "Rendiconto per Cassa — Modello D (D.M. 39/2020 art. 13)")

        canvas.setFont("Helvetica-Bold", 22)
        anno_str = str(anno)
        # Più spazio sopra il numero dell'anno
        canvas.drawRightString(W - 14*mm, header_y + 5.5*mm, anno_str)

        canvas.setFont("Helvetica", 7.5)
        info_parts = []
        if cf:
            info_parts.append(f"CF: {cf}")
        if runts:
            info_parts.append(f"RUNTS: {runts}")
        if mostra_data:
            info_parts.append(f"Stampato il {data_stampa}")
        
        if info_parts:
            canvas.drawRightString(W - 14*mm, header_y + 1*mm, "  |  ".join(info_parts))

        # ── Footer ──
        # Se siamo in modalità pagina singola (per Word), il footer lo mettiamo nella Story
        # così non lascia spazio vuoto a fine pagina.
        if not is_one_page:
            if nota_footer:
                canvas.setFillColor(C_MUTED)
                canvas.setFont("Helvetica", 7)
                canvas.drawString(10*mm, 8*mm, nota_footer)
            
            if mostra_pagine:
                canvas.setFillColor(C_MUTED)
                canvas.setFont("Helvetica", 7)
                canvas.drawRightString(W - 10*mm, 8*mm, f"Pagina {doc.page}")

            # Linea separatrice footer (solo se c'è qualcosa da separare)
            if nota_footer or mostra_pagine:
                canvas.setStrokeColor(colors.HexColor("#d1d5db"))
                canvas.setLineWidth(0.5)
                canvas.line(10*mm, 12*mm, W - 10*mm, 12*mm)

        canvas.restoreState()

    return on_page


# ── Blocco firma ─────────────────────────────────────────────────────────────

def _firma_table(firme=None) -> Table:
    if not firme:
        firme = ["Il Presidente", "Il Tesoriere", "Il Revisore dei Conti"]
    
    data = [
        firme,
        ["\n\n\n_______________________"] * len(firme),
    ]
    # Calcoliamo larghezze basate sul numero di firme (max 270mm area utile landscape)
    avail_w = 270 * mm
    col_w = [avail_w / len(firme)] * len(firme)
    
    t = Table(data, colWidths=col_w)
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
    una_pagina: bool = False,
    firme: list[str] = None,
    nota_legale: str = None,
    nota_footer: str = None,
    mostra_data: bool = True,
    mostra_pagine: bool = True,
    data_stampa_manuale: str = None,
) -> None:
    """
    Genera il Rendiconto per Cassa Mod. D in PDF.
    Usa reportlab: puro Python, nessuna dipendenza di sistema.

    Se una_pagina=True, usa un'altezza maggiore per far stare tutto
    in un'unica pagina (utile per esportazione immagine in Word).
    """
    W_A4, H_A4 = landscape(A4)
    if una_pagina:
        W, H = W_A4, 450 * mm  # Altezza sufficiente per contenere tutte le righe
    else:
        W, H = W_A4, H_A4

    data_stampa = data_stampa_manuale if data_stampa_manuale else date.today().strftime("%d/%m/%Y")
    ente = bil.ente or "Associazione"

    on_page = _make_page_header_footer(ente, bil.anno, cf, iscrizione_runts, data_stampa, 
                                       nota_footer, mostra_data, mostra_pagine,
                                       is_one_page=una_pagina)

    # ── Template pagina ──
    # Aumentiamo il topMargin per evitare troncamenti dell'anno
    doc = BaseDocTemplate(
        str(path_output),
        pagesize=(W, H),
        leftMargin=10*mm, rightMargin=10*mm,
        topMargin=30*mm, bottomMargin=16*mm,
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        leftPadding=0, rightPadding=0,
        topPadding=2*mm, bottomPadding=0,
        id="main"
    )
    page_tpl = PageTemplate(id="main", frames=[frame], onPage=on_page)
    doc.addPageTemplates([page_tpl])

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
    # Aggiungiamo una colonna vuota per il separatore centrale tra Uscite ed Entrate
    table_data = [[header_row[0], header_row[1], header_row[2], "", header_row[4], header_row[5], header_row[6]]]
    for r in dati_righe:
        table_data.append([r[0], r[1], r[2], "", r[3], r[4], r[5]])

    # Larghezze colonne: lbl_u | val_u | prec_u | sep | lbl_e | val_e | prec_e
    avail = W - 20*mm
    col_w = [
        avail * 0.40,   # label uscite (più larga)
        avail * 0.065,  # val uscite (stretta)
        avail * 0.065,  # prec uscite (stretta)
        avail * 0.005,  # separatore
        avail * 0.335,  # label entrate (bilanciata)
        avail * 0.065,  # val entrate (stretta)
        avail * 0.065,  # prec entrate (stretta)
    ]

    ts = _build_table_style(
        [("", "", "", "", "", "", "header")] + dati_righe,
        header_rows=1
    )
    t = Table(table_data, colWidths=col_w, repeatRows=1)
    t.setStyle(ts)
    story.append(t)

    # ── Firma ──
    if firme:
        story.append(Spacer(1, 8*mm))
        story.append(_firma_table(firme))

    # ── Nota legale ──
    if nota_legale:
        story.append(Spacer(1, 4*mm))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                 color=colors.HexColor("#d1d5db")))
        story.append(Spacer(1, 1*mm))
        story.append(Paragraph(nota_legale, stili["nota"]))

    # ── Footer (solo se una_pagina=True) ──
    if una_pagina:
        if nota_footer:
            story.append(Spacer(1, 6*mm))
            story.append(Paragraph(nota_footer, stili["footer"]))
        if mostra_pagine:
            story.append(Paragraph("Pagina 1", stili["footer"]))

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
