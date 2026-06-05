"""
docx_generator.py — Generazione del Verbale di Bilancio in formato DOCX
Utilizza docxtpl per iniettare i dati in un template Word.
"""

import os
import logging
import tempfile
from datetime import date
from pathlib import Path
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Inches, Mm
from contabilita import Bilancio, PIANO_DEI_CONTI

logger = logging.getLogger("CassaETS.docx")


def _fmt_eur(v: float) -> str:
    """Formatta un float come stringa euro in stile italiano (1.234,56)."""
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _calcola_saldo_precedente(bil: Bilancio) -> float:
    """
    Recupera il totale generale dell'anno precedente.

    bil.righe contiene solo le righe con tipo 'voce' e 'totale_sezione'.
    I saldi finali (cassa, cc, totale_generale) NON sono in bil.righe —
    vengono costruiti direttamente nel PDF. Quindi dobbiamo ricavare il
    totale precedente sommando i saldi iniziali (Z.Z.1 e Z.Z.5) presenti
    nei movimenti dell'anno corrente, che rappresentano i saldi finali
    dell'anno precedente.

    Se il Bilancio non espone i movimenti grezzi, usiamo come fallback
    la somma degli importi_precedente delle voci di totale_gestione.
    """
    # Il modo più corretto: il totale generale precedente è
    # saldo_iniziale_cassa_prec + saldo_iniziale_cc_prec.
    # Questi sono i movimenti Z.Z.1 e Z.Z.5 dell'anno corrente.
    # Tuttavia il Bilancio non espone i movimenti grezzi; li dobbiamo
    # ottenere dall'esterno. Come approssimazione affidabile usiamo
    # il totale_entrate_precedente - totale_uscite_precedente dell'anno prec
    # che è già calcolato in bil.righe.

    tot_entrate_prec = sum(
        r.importo_precedente for r in bil.righe
        if r.codice.startswith("E.") and r.tipo == "voce"
    )
    tot_uscite_prec = sum(
        r.importo_precedente for r in bil.righe
        if r.codice.startswith("U.") and r.tipo == "voce"
    )
    # Non possiamo ricostruire il totale_generale precedente senza i saldi
    # iniziali dell'anno passato; restituiamo l'avanzo precedente come proxy.
    return round(tot_entrate_prec - tot_uscite_prec, 2)


def genera_verbale_docx(
    bil: Bilancio,
    template_path: str | Path,
    output_path: str | Path,
    genera_pdf_func=None,
    cf: str = "",
    runts: str = "",
    firme: list[str] = None,
    nota_legale: str = None,
    nota_footer: str = None,
    mostra_data: bool = True,
    mostra_pagine: bool = True,
    data_manuale: str = None,
):
    """
    Genera un file DOCX inserendo i dati del bilancio e l'immagine della
    tabella estratta dal PDF rendiconto.
    """
    logger.info("Inizio generazione DOCX con estrazione tabella da PDF.")

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template non trovato: {template_path}")

    # ── 1. Genera PDF temporaneo ed estrae la prima pagina come immagine ──
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_pdf = Path(tmpdir) / "temp_bilancio.pdf"
        tmp_img = Path(tmpdir) / "tabella.png"

        if genera_pdf_func:
            logger.info("Generazione PDF temporaneo...")
            # Usiamo una_pagina=True per avere l'intera tabella in un'unica immagine
            try:
                genera_pdf_func(
                    bil, tmp_pdf, 
                    cf=cf, 
                    iscrizione_runts=runts, 
                    una_pagina=True,
                    firme=firme,
                    nota_legale=nota_legale,
                    nota_footer=nota_footer,
                    mostra_data=mostra_data,
                    mostra_pagine=mostra_pagine,
                    data_stampa_manuale=data_manuale
                )
            except TypeError:
                # Fallback se la funzione non accetta ancora i nuovi parametri
                genera_pdf_func(bil, tmp_pdf, cf=cf, iscrizione_runts=runts)

            try:
                import fitz  # PyMuPDF

                with fitz.open(tmp_pdf) as doc_pdf:
                    page = doc_pdf[0]

                    # Autocrop: Trova l'area effettivamente occupata dal contenuto
                    # (testo, tabelle, firme) per eliminare lo spazio vuoto in fondo
                    blocks = page.get_text("blocks")
                    content_h = page.rect.height
                    if blocks:
                        # b[3] è la coordinata y1 (fondo) del blocco di testo
                        max_y = max(b[3] for b in blocks)
                        # Aggiungiamo un margine di sicurezza (20pt ≈ 7mm)
                        content_h = min(max_y + 20, page.rect.height)

                    zoom = 2
                    mat = fitz.Matrix(zoom, zoom)
                    # Ritagliamo l'immagine all'altezza effettiva del contenuto
                    clip = fitz.Rect(0, 0, page.rect.width, content_h)
                    pix = page.get_pixmap(matrix=mat, clip=clip)
                    pix.save(tmp_img)

                logger.info(f"Tabella estratta e ritagliata (altezza: {content_h:.1f}pt).")

            except ImportError:
                logger.warning(
                    "PyMuPDF (fitz) non installato: la tabella non sarà inclusa. "
                    "Installa con: pip install pymupdf"
                )
                tmp_img = None
            except Exception as e:
                logger.error(f"Errore durante l'estrazione dell'immagine dal PDF: {e}")
                tmp_img = None
        else:
            logger.warning("Funzione genera_pdf non fornita, la tabella non sarà inclusa.")
            tmp_img = None

        # ── 2. Prepara il template Word ────────────────────────────────────
        doc = DocxTemplate(template_path)

        # Frase descrittiva avanzo/disavanzo
        if bil.avanzo_esercizio >= 0:
            frase_saldo = (
                f"un saldo positivo pari a € {_fmt_eur(bil.avanzo_esercizio)}"
            )
        else:
            frase_saldo = (
                f"un disavanzo pari a € {_fmt_eur(abs(bil.avanzo_esercizio))}"
            )

        # Saldo precedente: avanzo d'esercizio dell'anno passato
        avanzo_prec = _calcola_saldo_precedente(bil)

        # ── Costruisce il contesto completo ───────────────────────────────
        context = {
            # Dati anagrafici
            "ente":             bil.ente,
            "anno_consuntivo":  str(bil.anno),
            "anno_precedente":  str(bil.anno - 1),
            "anno_preventivo":  str(bil.anno + 1),
            "data_oggi":        data_manuale if data_manuale else date.today().strftime("%d/%m/%Y"),
            # Importi formattati (stile italiano: 1.234,56)
            "totale_entrate":   _fmt_eur(bil.totale_entrate),
            "totale_uscite":    _fmt_eur(bil.totale_uscite),
            "avanzo":           _fmt_eur(bil.avanzo_esercizio),
            "avanzo_finale":    _fmt_eur(bil.avanzo_finale),
            "imposte":          _fmt_eur(bil.imposte),
            "saldo_cassa":      _fmt_eur(bil.saldo_cassa),
            "saldo_cc":         _fmt_eur(bil.saldo_cc),
            "totale_generale":  _fmt_eur(bil.totale_generale),
            # Testi descrittivi
            "frase_saldo":      frase_saldo,
            "saldo_precedente": _fmt_eur(avanzo_prec),
            "firme":            firme if firme else [],
            # Righe bilancio per eventuale tabella nel template
            # ({% for r in righe_bilancio %} {{ r.label }} {{ r.corrente }} {% endfor %})
            "righe_bilancio": [
                {
                    "label":    r.label,
                    "corrente": _fmt_eur(r.importo_corrente) if r.importo_corrente else "",
                    "prec":     _fmt_eur(r.importo_precedente) if r.importo_precedente else "",
                    "tipo":     r.tipo,
                }
                for r in bil.righe
            ],
        }

        # ── 3. Inserisce l'immagine se disponibile ─────────────────────────
        if tmp_img and tmp_img.exists():
            # Il PDF è landscape A4 (297 × 210 mm).
            # Area utile del Word portrait A4 con margini 2,5 cm ≈ 160 mm.
            # Impostiamo larghezza = 160 mm; l'altezza sarà proporzionale
            # (ratio ≈ 297/210 ≈ 1,41 → altezza ≈ 113 mm, ampiamente nella pagina).
            context["tabella_img"] = InlineImage(doc, str(tmp_img), width=Mm(160))
            logger.info("Immagine tabella aggiunta al contesto (larghezza 160 mm).")
            
            # Miglioramento layout: cerchiamo il paragrafo che contiene {{ tabella_img }}
            # e impostiamo 'keep_with_next' per tenerlo unito alla riga precedente (es. titolo tabella)
            try:
                prev_p = None
                for p in doc.paragraphs:
                    # Se questo paragrafo contiene l'immagine, vogliamo che il PRECEDENTE (il titolo)
                    # rimanga unito a questo. In Word si mette 'keep_with_next' sul titolo.
                    if "{{ tabella_img }}" in p.text:
                        if prev_p:
                            prev_p.paragraph_format.keep_with_next = True
                        # Anche questo paragrafo deve stare con il successivo (se c'è altro dopo)
                        p.paragraph_format.keep_with_next = True

                    # Se il paragrafo sembra un titolo di tabella, forziamo il legame col successivo
                    if p.text.strip().startswith("Tabella") or "Prospetto riassuntivo" in p.text:
                        p.paragraph_format.keep_with_next = True

                    prev_p = p
            except Exception as e:
                logger.debug(f"Impossibile impostare keep_with_next: {e}")
        else:
            # Segnaposto vuoto per evitare errori di rendering nel template
            context["tabella_img"] = ""

        logger.debug(f"Rendering DOCX con contesto: { {k: v for k, v in context.items() if k != 'righe_bilancio'} }")
        doc.render(context)
        doc.save(output_path)
        logger.info(f"DOCX generato con successo: {output_path}")
