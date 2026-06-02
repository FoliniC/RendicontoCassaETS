# RendicontoCassaETS — CassaETS

![Licenza](https://img.shields.io/badge/Licenza-MIT-green)  
![Python](https://img.shields.io/badge/-Python_3.11+-3776ab?logo=python&logoColor=white)  
![Stelle](https://img.shields.io/github/stars/FoliniC/RendicontoCassaETS?style=flat)

Applicazione desktop leggera per la gestione della prima nota e la generazione automatica del **Rendiconto per Cassa (Mod. D)** e dei **verbali di assemblea** per gli ETS (Enti del Terzo Settore).

---

## ⚠️ Avviso Importante: Versione Modernizzata

**La versione Excel legacy non è più mantenuta.** Questa versione Python offre:
- Maggiore flessibilità e scalabilità
- Performance migliori
- Manutenzione continuativa e aggiornamenti

Se desideri utilizzare la versione Excel precedente, è disponibile nel branch `excel-legacy`: https://github.com/FoliniC/RendicontoCassaETS/tree/excel-legacy

---

## ✨ Funzionalità Principali

- **Prima Nota**: Gestione dei movimenti di cassa e banca con codifica Ministeriale (D.M. 39/2020)
- **Bilancio Automatico**: Calcolo in tempo reale di avanzi, disavanzi e saldi finali
- **Esportazione PDF**: Generazione del Rendiconto per Cassa ufficiale pronto per il RUNTS
- **Generazione Verbali DOCX**: Creazione automatica del verbale di assemblea da template Word con aggiornamento automatico di date e tabelle
- **Export Multi-formato**: Supporto per CSV e JSON per analisi esterne
- **Interfaccia Desktop**: Applicazione desktop intuitiva basata su Tkinter (no server, nessun hosting, tutti i dati in CSV locali)

## 📋 Requisiti

- **Python 3.11** o superiore
- Connessione internet (solo per l'installazione iniziale delle dipendenze)

## 🚀 Installazione

1. Scarica Python da [python.org](https://www.python.org/) se non lo hai già
2. Scarica questo repositorio (il tasto verde "Code" → "Download ZIP" oppure:
   ```bash
   git clone https://github.com/FoliniC/RendicontoCassaETS.git
   cd RendicontoCassaETS
   ```
3. Apri il Prompt dei comandi nella cartella del progetto
4. Installa le librerie necessarie:
   ```bash
   pip install reportlab docxtpl python-docx
   ```

## 💻 Utilizzo

Per avviare l'applicazione:

```bash
python app.py
```

L'interfaccia grafica ti guiderà attraverso:
- **Registrazione movimenti**: Gestione della cassa con codifica ministeriale
- **Calcolo bilancio**: Totalizzazione automatica secondo il Mod. D
- **Esportazione**: Generazione di PDF, DOCX, CSV e JSON

### 📄 Generazione Verbale DOCX

L'applicazione genera automaticamente il verbale dell'assemblea di bilancio:

1. Vai nella sezione **Export**
2. Clicca su **Genera Verbale DOCX**
3. Seleziona il template Word (l'app cercherà automaticamente il file dell'anno precedente o uno con il nome `template_*.docx`)
4. Il programma creerà il nuovo file Word con dati aggiornati

#### Template Word: Variabili Disponibili

Nel file Word puoi utilizzare questi "segnaposti" tra doppie graffe:

- `{{ ente }}`: Nome dell'associazione
- `{{ anno_consuntivo }}`: Anno del bilancio (es. 2024)
- `{{ anno_precedente }}`: Anno precedente (es. 2023)
- `{{ anno_preventivo }}`: Anno successivo (es. 2025)
- `{{ data_oggi }}`: Data corrente (formato GG/MM/AAAA)
- `{{ totale_entrate }}`: Somma entrate
- `{{ totale_uscite }}`: Somma uscite
- `{{ avanzo }}`: Avanzo/disavanzo d'esercizio

**Cicli nelle tabelle**: Usa `{% for r in righe_bilancio %}` e `{% endfor %}` per popolare automaticamente le tabelle.

## 📁 Struttura Progetto

```
├── app.py                      # Interfaccia grafica (Tkinter)
├── contabilita.py              # Motore di calcolo e logica contabile
├── pdf_generator.py            # Generazione PDF ufficiale
├── docx_generator.py           # Generazione verbale Word
├── piano_dei_conti.csv         # Piano dei conti ministeriale
├── template_rendiconto.html    # Template PDF
└── cassa_*.csv                 # Dati (generato automaticamente per ogni anno)
```

## 📊 Piano dei Conti

Le voci seguono il **Decreto 5 marzo 2020** (Gazzetta Ufficiale n. 102, 18 aprile 2020):
- **Voci E**: Entrate
- **Voci U**: Uscite  
- **Voci Z**: Strumentali (saldi iniziali/finali, giroconti, totali)

Solo le voci di **terzo livello e inferiori** sono utilizzabili nella registrazione.

## 📝 Changelog

### v2.0.0 — Python (Giugno 2026)
- ✅ Modernizzazione completa: da Excel a Python
- ✅ Interfaccia desktop nativa (Tkinter)
- ✅ Gestione cassa e conto corrente
- ✅ Export PDF, DOCX, CSV, JSON
- ✅ Generazione automatica verbali di assemblea
- ✅ Nessun server, tutti i dati in CSV locali
- ✅ Codice sorgente aperto e mantenuto

### v1.x — Excel (Legacy - Non mantenuto)
Per la versione Excel originale e la cronologia completa, vedi il branch `excel-legacy`.

## 📄 Licenza

MIT License — Vedi il file [LICENSE](LICENSE) per i dettagli.

---

**Domande o suggerimenti?** Crea una [Issue](https://github.com/FoliniC/RendicontoCassaETS/issues)
