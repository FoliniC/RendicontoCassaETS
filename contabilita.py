"""
contabilita.py — Motore contabile per Rendiconto per Cassa ETS (Mod. D)
Legge CSV, calcola bilancio, esporta JSON/CSV/PDF-A
"""

import csv
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional


# ── Piano dei conti fisso (D.M. 39/2020) ───────────────────────────────────

PIANO_DEI_CONTI: list[dict] = [
    # --- USCITE OPERATIVE ---
    {"codice": "U.A",   "label": "A) Uscite da attività di interesse generale", "riga": 2,  "tipo": "intestazione"},
    {"codice": "U.A.1", "label": "1) Materie prime, sussidiarie, di consumo e di merci",   "riga": 4,  "tipo": "voce"},
    {"codice": "U.A.2", "label": "2) Servizi",                                               "riga": 5,  "tipo": "voce"},
    {"codice": "U.A.3", "label": "3) Godimento beni di terzi",                               "riga": 7,  "tipo": "voce"},
    {"codice": "U.A.4", "label": "4) Personale",                                             "riga": 8,  "tipo": "voce"},
    {"codice": "U.A.5", "label": "5) Uscite diverse di gestione",                            "riga": 10, "tipo": "voce"},
    {"codice": "Z.U.1", "label": "Totale",                                                   "riga": 13, "tipo": "totale_sezione", "n": 5},

    {"codice": "U.B",   "label": "B) Uscite da attività diverse",                           "riga": 15, "tipo": "intestazione"},
    {"codice": "U.B.1", "label": "1) Materie prime, sussidiarie, di consumo e di merci",   "riga": 16, "tipo": "voce"},
    {"codice": "U.B.2", "label": "2) Servizi",                                               "riga": 17, "tipo": "voce"},
    {"codice": "U.B.3", "label": "3) Godimento beni di terzi",                               "riga": 18, "tipo": "voce"},
    {"codice": "U.B.4", "label": "4) Personale",                                             "riga": 19, "tipo": "voce"},
    {"codice": "U.B.5", "label": "5) Uscite diverse di gestione",                            "riga": 20, "tipo": "voce"},
    {"codice": "Z.U.2", "label": "Totale",                                                   "riga": 22, "tipo": "totale_sezione", "n": 5},

    {"codice": "U.C",   "label": "C) Uscite da attività di raccolta fondi",                 "riga": 24, "tipo": "intestazione"},
    {"codice": "U.C.1", "label": "1) Uscite per raccolte fondi abituali",                    "riga": 25, "tipo": "voce"},
    {"codice": "U.C.2", "label": "2) Uscite per raccolte fondi occasionali",                 "riga": 26, "tipo": "voce"},
    {"codice": "U.C.3", "label": "3) Altre uscite",                                          "riga": 27, "tipo": "voce"},
    {"codice": "Z.U.3", "label": "Totale",                                                   "riga": 28, "tipo": "totale_sezione", "n": 3},

    {"codice": "U.D",   "label": "D) Uscite da attività finanziarie e patrimoniali",        "riga": 30, "tipo": "intestazione"},
    {"codice": "U.D.1", "label": "1) Su rapporti bancari",                                   "riga": 31, "tipo": "voce"},
    {"codice": "U.D.2", "label": "2) Su investimenti finanziari",                            "riga": 32, "tipo": "voce"},
    {"codice": "U.D.3", "label": "3) Su patrimonio edilizio",                                "riga": 33, "tipo": "voce"},
    {"codice": "U.D.4", "label": "4) Su altri beni patrimoniali",                            "riga": 34, "tipo": "voce"},
    {"codice": "U.D.5", "label": "5) Altre uscite",                                          "riga": 35, "tipo": "voce"},
    {"codice": "Z.U.4", "label": "Totale",                                                   "riga": 36, "tipo": "totale_sezione", "n": 5},

    {"codice": "U.E",   "label": "E) Uscite di supporto generale",                          "riga": 38, "tipo": "intestazione"},
    {"codice": "U.E.1", "label": "1) Materie prime, sussidiarie, di consumo e di merci",   "riga": 39, "tipo": "voce"},
    {"codice": "U.E.2", "label": "2) Servizi",                                               "riga": 40, "tipo": "voce"},
    {"codice": "U.E.3", "label": "3) Godimento beni di terzi",                               "riga": 41, "tipo": "voce"},
    {"codice": "U.E.4", "label": "4) Personale",                                             "riga": 42, "tipo": "voce"},
    {"codice": "U.E.5", "label": "5) Uscite diverse di gestione",                            "riga": 43, "tipo": "voce"},
    {"codice": "Z.U.5", "label": "Totale",                                                   "riga": 44, "tipo": "totale_sezione", "n": 5},

    {"codice": "Z.U.11","label": "Totale uscite della gestione",                             "riga": 46, "tipo": "totale_gestione"},

    # --- ENTRATE OPERATIVE ---
    {"codice": "E.A",    "label": "A) Entrate da attività di interesse generale",            "riga": 2,  "tipo": "intestazione"},
    {"codice": "E.A.1",  "label": "1) Entrate da quote associative e apporti dei fondatori","riga": 3,  "tipo": "voce"},
    {"codice": "E.A.2",  "label": "2) Entrate dagli associati per attività mutuali",         "riga": 4,  "tipo": "voce"},
    {"codice": "E.A.3",  "label": "3) Entrate per prestazioni e cessioni ad associati",      "riga": 5,  "tipo": "voce"},
    {"codice": "E.A.4",  "label": "4) Erogazioni liberali",                                  "riga": 6,  "tipo": "voce"},
    {"codice": "E.A.5",  "label": "5) Entrate del 5 per mille",                              "riga": 7,  "tipo": "voce"},
    {"codice": "E.A.6",  "label": "6) Contributi da soggetti privati",                       "riga": 8,  "tipo": "voce"},
    {"codice": "E.A.7",  "label": "7) Entrate per prestazioni e cessioni a terzi",           "riga": 9,  "tipo": "voce"},
    {"codice": "E.A.8",  "label": "8) Contributi da enti pubblici",                          "riga": 10, "tipo": "voce"},
    {"codice": "E.A.9",  "label": "9) Entrate da contratti con enti pubblici",               "riga": 11, "tipo": "voce"},
    {"codice": "E.A.10", "label": "10) Altre entrate",                                       "riga": 12, "tipo": "voce"},
    {"codice": "Z.E.1",  "label": "Totale",                                                  "riga": 13, "tipo": "totale_sezione", "n": 10},
    {"codice": "Z.E.2",  "label": "Avanzo/disavanzo attività di interesse generale",         "riga": 14, "tipo": "avanzo"},

    {"codice": "E.B",    "label": "B) Entrate da attività diverse",                          "riga": 15, "tipo": "intestazione"},
    {"codice": "E.B.1",  "label": "1) Entrate per prestazioni e cessioni ad associati",      "riga": 16, "tipo": "voce"},
    {"codice": "E.B.2",  "label": "2) Contributi da soggetti privati",                       "riga": 17, "tipo": "voce"},
    {"codice": "E.B.3",  "label": "3) Entrate per prestazioni e cessioni a terzi",           "riga": 18, "tipo": "voce"},
    {"codice": "E.B.4",  "label": "4) Personale",                                            "riga": 19, "tipo": "voce"},
    {"codice": "E.B.5",  "label": "5) Contributi da enti pubblici",                          "riga": 20, "tipo": "voce"},
    {"codice": "E.B.6",  "label": "6) Altre entrate",                                        "riga": 21, "tipo": "voce"},
    {"codice": "Z.E.3",  "label": "Totale",                                                  "riga": 22, "tipo": "totale_sezione", "n": 6},
    {"codice": "Z.E.4",  "label": "Avanzo/disavanzo attività diverse",                       "riga": 23, "tipo": "avanzo"},

    {"codice": "E.C",    "label": "C) Entrate da attività di raccolta fondi",                "riga": 24, "tipo": "intestazione"},
    {"codice": "E.C.1",  "label": "1) Entrate da raccolte fondi abituali",                   "riga": 25, "tipo": "voce"},
    {"codice": "E.C.2",  "label": "2) Entrate da raccolte fondi occasionali",                "riga": 26, "tipo": "voce"},
    {"codice": "E.C.3",  "label": "3) Altre entrate",                                        "riga": 27, "tipo": "voce"},
    {"codice": "Z.E.5",  "label": "Totale",                                                  "riga": 28, "tipo": "totale_sezione", "n": 3},
    {"codice": "Z.E.6",  "label": "Avanzo/disavanzo attività di raccolta fondi",             "riga": 29, "tipo": "avanzo"},

    {"codice": "E.D",    "label": "D) Entrate da attività finanziarie e patrimoniali",       "riga": 30, "tipo": "intestazione"},
    {"codice": "E.D.1",  "label": "1) Da rapporti bancari",                                  "riga": 31, "tipo": "voce"},
    {"codice": "E.D.2",  "label": "2) Da investimenti finanziari",                           "riga": 32, "tipo": "voce"},
    {"codice": "E.D.3",  "label": "3) Da patrimonio edilizio",                               "riga": 33, "tipo": "voce"},
    {"codice": "E.D.4",  "label": "4) Da altri beni patrimoniali",                           "riga": 34, "tipo": "voce"},
    {"codice": "E.D.5",  "label": "5) Altre entrate",                                        "riga": 35, "tipo": "voce"},
    {"codice": "Z.E.7",  "label": "Totale",                                                  "riga": 36, "tipo": "totale_sezione", "n": 5},
    {"codice": "Z.E.8",  "label": "Avanzo/disavanzo attività finanziarie e patrimoniali",    "riga": 37, "tipo": "avanzo"},

    {"codice": "E.E",    "label": "E) Entrate di supporto generale",                         "riga": 38, "tipo": "intestazione"},
    {"codice": "E.E.1",  "label": "1) Entrate da distacco del personale",                    "riga": 39, "tipo": "voce"},
    {"codice": "E.E.2",  "label": "2) Altre entrate di supporto generale",                   "riga": 40, "tipo": "voce"},
    {"codice": "Z.E.9",  "label": "Totale",                                                  "riga": 44, "tipo": "totale_sezione", "n": 2},
    {"codice": "Z.E.10", "label": "Avanzo/disavanzo di supporto generale",                   "riga": 45, "tipo": "avanzo"},

    # --- RIGHE FINALI ---
    {"codice": "Z.U.11", "label": "Totale uscite della gestione",                            "riga": 46, "tipo": "totale_gestione"},
    {"codice": "Z.E.11", "label": "Totale entrate della gestione",                           "riga": 46, "tipo": "totale_gestione"},
    {"codice": "Z.E.12", "label": "Avanzo/disavanzo d'esercizio prima delle imposte",        "riga": 47, "tipo": "avanzo_esercizio"},
    {"codice": "Z.E.13", "label": "Imposte",                                                 "riga": 48, "tipo": "imposte"},
    {"codice": "Z.E.14", "label": "Avanzo/disavanzo prima di investimenti patrimoniali",     "riga": 49, "tipo": "avanzo_finale"},
    {"codice": "Z.U.12", "label": "Cassa",                                                   "riga": 50, "tipo": "saldo"},
    {"codice": "Z.U.13", "label": "Conto corrente",                                          "riga": 51, "tipo": "saldo"},
    {"codice": "Z.U.14", "label": "Totale generale",                                         "riga": 52, "tipo": "totale_generale"},
]

# ── Struttura dati ──────────────────────────────────────────────────────────

@dataclass
class Movimento:
    data: date
    descrizione: str
    codice_voce: str
    importo: float        # positivo = entrata, negativo = uscita
    tipo_conto: str       # 'cassa' | 'cc'

    def is_saldo_iniziale(self) -> bool:
        return self.codice_voce in ("Z.Z.1", "Z.Z.5")


@dataclass
class RigaBilancio:
    codice: str
    label: str
    riga: int
    tipo: str
    importo_corrente: float = 0.0
    importo_precedente: float = 0.0
    n: int = 0            # sottovoci per totali sezione


@dataclass
class Bilancio:
    anno: int
    ente: str
    righe: list[RigaBilancio] = field(default_factory=list)
    saldo_cassa: float = 0.0
    saldo_cc: float = 0.0
    totale_uscite: float = 0.0
    totale_entrate: float = 0.0
    avanzo_esercizio: float = 0.0
    imposte: float = 0.0
    avanzo_finale: float = 0.0
    totale_generale: float = 0.0


# ── Lettura CSV ─────────────────────────────────────────────────────────────

def leggi_cassa(path: str | Path) -> list[Movimento]:
    """Legge un file CSV cassa e restituisce lista di Movimento."""
    movimenti = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                d = datetime.strptime(row["data"].strip(), "%Y-%m-%d").date()
                importo = float(row["importo"].replace(",", "."))
                tipo = row["tipo_conto"].strip().lower()
                assert tipo in ("cassa", "cc"), f"tipo_conto non valido: {tipo}"
                movimenti.append(Movimento(
                    data=d,
                    descrizione=row["descrizione"].strip(),
                    codice_voce=row["codice_voce"].strip(),
                    importo=importo,
                    tipo_conto=tipo,
                ))
            except Exception as e:
                print(f"  [WARN] Riga ignorata: {row} → {e}")
    return sorted(movimenti, key=lambda m: m.data)


# ── Calcolo bilancio ────────────────────────────────────────────────────────

def calcola_bilancio(
    anno: int,
    movimenti: list[Movimento],
    movimenti_prec: list[Movimento] | None = None,
    ente: str = "",
    imposte: float = 0.0,
) -> Bilancio:
    """
    Calcola il Rendiconto per Cassa Mod. D a partire dai movimenti CSV.
    Tutti i valori sono calcolati: nessun valore viene memorizzato nel CSV.
    """

    def somma_per_codice(mvs: list[Movimento], codice: str) -> float:
        return sum(
            abs(m.importo) for m in mvs
            if m.codice_voce == codice and not m.is_saldo_iniziale()
        )

    def saldo_finale(mvs: list[Movimento], tipo: str) -> float:
        """Saldo iniziale + tutti i movimenti del tipo (con segno)."""
        return sum(m.importo for m in mvs if m.tipo_conto == tipo)

    bil = Bilancio(anno=anno, ente=ente, imposte=imposte)

    # Valori correnti e precedenti per ogni voce operativa
    totali_correnti:   dict[str, float] = {}
    totali_precedenti: dict[str, float] = {}

    for voce in PIANO_DEI_CONTI:
        cod = voce["codice"]
        if voce["tipo"] == "voce":
            totali_correnti[cod]   = somma_per_codice(movimenti, cod)
            totali_precedenti[cod] = somma_per_codice(movimenti_prec, cod) if movimenti_prec else 0.0

    # Costruisce le righe del bilancio
    # Usiamo una lista piatta per non perdere dati tra U e E che condividono la riga
    righe_bilancio: list[RigaBilancio] = []

    totali_sezione_u: dict[str, float] = {}  # codice Z.U.x → valore
    totali_sezione_e: dict[str, float] = {}

    for i, voce in enumerate(PIANO_DEI_CONTI):
        cod  = voce["codice"]
        riga = voce["riga"]
        tipo = voce["tipo"]

        if tipo == "voce":
            val_c = totali_correnti.get(cod, 0.0)
            val_p = totali_precedenti.get(cod, 0.0)
            righe_bilancio.append(RigaBilancio(
                codice=cod, label=voce["label"], riga=riga, tipo=tipo,
                importo_corrente=val_c, importo_precedente=val_p
            ))

        elif tipo == "totale_sezione":
            n = voce.get("n", 0)
            # Somma le n voci precedenti della stessa sezione basandosi sulla posizione in lista
            prefix = "U." if cod.startswith("Z.U.") else "E."
            voci_prec = [v for v in PIANO_DEI_CONTI[:i] if v["tipo"] == "voce" and v["codice"].startswith(prefix)]
            
            tot_c = sum(totali_correnti.get(v["codice"], 0.0) for v in voci_prec[-n:])
            tot_p = sum(totali_precedenti.get(v["codice"], 0.0) for v in voci_prec[-n:])
            
            if cod.startswith("Z.U."):
                totali_sezione_u[cod] = tot_c
            else:
                totali_sezione_e[cod] = tot_c
                
            righe_bilancio.append(RigaBilancio(
                codice=cod, label=voce["label"], riga=riga, tipo=tipo, n=n,
                importo_corrente=tot_c, importo_precedente=tot_p
            ))

    # Totale uscite/entrate della gestione (riga 46)
    tot_uscite_c = sum(totali_sezione_u.values())
    tot_uscite_p = sum(totali_precedenti.get(v["codice"], 0.0) for v in PIANO_DEI_CONTI if v["tipo"] == "voce" and v["codice"].startswith("U."))
    
    tot_entrate_c = sum(totali_sezione_e.values())
    tot_entrate_p = sum(totali_precedenti.get(v["codice"], 0.0) for v in PIANO_DEI_CONTI if v["tipo"] == "voce" and v["codice"].startswith("E."))

    # Saldi finali
    saldo_cassa = saldo_finale(movimenti, "cassa")
    saldo_cc    = saldo_finale(movimenti, "cc")

    # Avanzo/disavanzo
    avanzo_esercizio = tot_entrate_c - tot_uscite_c
    avanzo_finale    = avanzo_esercizio - imposte

    # Popola i campi del bilancio
    bil.saldo_cassa       = round(saldo_cassa, 2)
    bil.saldo_cc          = round(saldo_cc, 2)
    bil.totale_uscite     = round(tot_uscite_c, 2)
    bil.totale_entrate    = round(tot_entrate_c, 2)
    bil.avanzo_esercizio  = round(avanzo_esercizio, 2)
    bil.avanzo_finale     = round(avanzo_finale, 2)
    bil.totale_generale   = round(saldo_cassa + saldo_cc, 2)

    # Costruisci lista righe
    bil.righe = righe_bilancio

    return bil


# ── Export ──────────────────────────────────────────────────────────────────

def esporta_cassa_json(movimenti: list[Movimento], path: str | Path) -> None:
    """Esporta la prima nota in JSON."""
    data = [
        {
            "data": m.data.isoformat(),
            "descrizione": m.descrizione,
            "codice_voce": m.codice_voce,
            "importo": m.importo,
            "tipo_conto": m.tipo_conto,
        }
        for m in movimenti
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"movimenti": data}, f, ensure_ascii=False, indent=2)


def esporta_bilancio_json(bil: Bilancio, path: str | Path) -> None:
    """Esporta il bilancio calcolato in JSON."""
    out = {
        "anno": bil.anno,
        "ente": bil.ente,
        "generato_il": datetime.now().isoformat(timespec="seconds"),
        "uscite": [
            {
                "codice": r.codice, "voce": r.label,
                "riga": r.riga,
                "importo_corrente": round(r.importo_corrente, 2),
                "importo_precedente": round(r.importo_precedente, 2),
            }
            for r in bil.righe if r.codice.startswith("U") or r.codice in ("Z.U.1","Z.U.2","Z.U.3","Z.U.4","Z.U.5","Z.U.11")
        ],
        "entrate": [
            {
                "codice": r.codice, "voce": r.label,
                "riga": r.riga,
                "importo_corrente": round(r.importo_corrente, 2),
                "importo_precedente": round(r.importo_precedente, 2),
            }
            for r in bil.righe if r.codice.startswith("E") or r.codice.startswith("Z.E.")
        ],
        "riepilogo": {
            "totale_uscite": bil.totale_uscite,
            "totale_entrate": bil.totale_entrate,
            "avanzo_esercizio_prima_imposte": bil.avanzo_esercizio,
            "imposte": bil.imposte,
            "avanzo_esercizio": bil.avanzo_finale,
            "saldo_cassa": bil.saldo_cassa,
            "saldo_cc": bil.saldo_cc,
            "totale_generale": bil.totale_generale,
        }
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def esporta_cassa_csv(movimenti: list[Movimento], path: str | Path) -> None:
    """Riesporta la prima nota in CSV normalizzato."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["data", "descrizione", "codice_voce", "importo", "tipo_conto"])
        for m in movimenti:
            w.writerow([m.data.isoformat(), m.descrizione, m.codice_voce,
                        f"{m.importo:.2f}", m.tipo_conto])


def esporta_bilancio_csv(bil: Bilancio, path: str | Path) -> None:
    """Esporta il bilancio in CSV con struttura piatta."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["riga", "codice", "voce", "importo_corrente", "importo_precedente"])
        for r in bil.righe:
            w.writerow([r.riga, r.codice, r.label,
                        f"{r.importo_corrente:.2f}", f"{r.importo_precedente:.2f}"])
        w.writerow(["46", "Z.U.11/Z.E.11", "Totale uscite / entrate gestione",
                    f"{bil.totale_uscite:.2f} / {bil.totale_entrate:.2f}", ""])
        w.writerow(["47", "Z.E.12", "Avanzo/disavanzo d'esercizio prima imposte",
                    f"{bil.avanzo_esercizio:.2f}", ""])
        w.writerow(["48", "Z.E.13", "Imposte", f"{bil.imposte:.2f}", ""])
        w.writerow(["49", "Z.E.14", "Avanzo/disavanzo prima investimenti",
                    f"{bil.avanzo_finale:.2f}", ""])
        w.writerow(["50", "Z.U.12", "Cassa",  f"{bil.saldo_cassa:.2f}", ""])
        w.writerow(["51", "Z.U.13", "Conto corrente", f"{bil.saldo_cc:.2f}", ""])
        w.writerow(["52", "Z.U.14", "Totale generale", f"{bil.totale_generale:.2f}", ""])


# ── Test rapido ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    base = Path(__file__).parent
    mvs = leggi_cassa(base / "cassa_2025.csv")
    print(f"Movimenti letti: {len(mvs)}")
    for m in mvs:
        print(f"  {m.data} | {m.codice_voce:<10} | {m.importo:>10.2f} | {m.tipo_conto} | {m.descrizione[:50]}")

    bil = calcola_bilancio(2025, mvs, ente="APS Il Viale della Formica")
    print(f"\n{'='*50}")
    print(f"Totale uscite:   {bil.totale_uscite:>10.2f}")
    print(f"Totale entrate:  {bil.totale_entrate:>10.2f}")
    print(f"Avanzo:          {bil.avanzo_esercizio:>10.2f}")
    print(f"Saldo cassa:     {bil.saldo_cassa:>10.2f}")
    print(f"Saldo CC:        {bil.saldo_cc:>10.2f}")
    print(f"Totale generale: {bil.totale_generale:>10.2f}")

    esporta_cassa_json(mvs, base / "cassa_2025_export.json")
    esporta_bilancio_json(bil, base / "bilancio_2025_export.json")
    esporta_cassa_csv(mvs, base / "cassa_2025_export.csv")
    esporta_bilancio_csv(bil, base / "bilancio_2025_export.csv")
    print("\nExport completati.")
