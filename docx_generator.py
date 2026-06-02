"""
docx_generator.py — Generazione del Verbale di Bilancio in formato DOCX
Utilizza docxtpl per iniettare i dati in un template Word.
"""

import os
from datetime import date
from pathlib import Path
from docxtpl import DocxTemplate
from contabilita import Bilancio

def genera_verbale_docx(bil: Bilancio, template_path: str | Path, output_path: str | Path):
    """
    Genera un file DOCX partendo da un template e inserendo i dati del bilancio.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template non trovato: {template_path}")

    doc = DocxTemplate(template_path)
    
    # Prepariamo i dati per il template
    # Scorporiamo le righe per facilitare l'uso nel Word (es. tabelle separate o filtri)
    uscite = [r for r in bil.righe if r.codice.startswith("U") or r.codice.startswith("Z.U.")]
    entrate = [r for r in bil.righe if r.codice.startswith("E") or r.codice.startswith("Z.E.")]
    
    context = {
        'ente': bil.ente,
        'anno_consuntivo': bil.anno,
        'anno_precedente': bil.anno - 1,
        'anno_preventivo': bil.anno + 1,
        'data_oggi': date.today().strftime("%d/%m/%Y"),
        
        # Dati riassuntivi
        'totale_uscite': f"{bil.totale_uscite:.2f}",
        'totale_entrate': f"{bil.totale_entrate:.2f}",
        'avanzo': f"{bil.avanzo_esercizio:.2f}",
        'imposte': f"{bil.imposte:.2f}",
        'avanzo_finale': f"{bil.avanzo_finale:.2f}",
        'saldo_cassa': f"{bil.saldo_cassa:.2f}",
        'saldo_cc': f"{bil.saldo_cc:.2f}",
        'totale_generale': f"{bil.totale_generale:.2f}",
        
        # Liste per le tabelle nel Word
        'righe_bilancio': [
            {
                'riga': r.riga,
                'codice': r.codice,
                'label': r.label,
                'corrente': f"{r.importo_corrente:.2f}" if r.importo_corrente != 0 else "-",
                'precedente': f"{r.importo_precedente:.2f}" if r.importo_precedente != 0 else "-"
            }
            for r in bil.righe
        ],
        'uscite': [
             {'label': r.label, 'val': f"{r.importo_corrente:.2f}"} 
             for r in uscite if r.tipo == "voce" and r.importo_corrente > 0
        ],
        'entrate': [
             {'label': r.label, 'val': f"{r.importo_corrente:.2f}"} 
             for r in entrate if r.tipo == "voce" and r.importo_corrente > 0
        ]
    }

    doc.render(context)
    doc.save(output_path)
