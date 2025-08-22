import ast # Libreria analisi codice python
import os
from random import randint
import time
from bs4 import BeautifulSoup # Libreria lettura pagine HTML
import requests # Libreria download pagine HTML
from tqdm import tqdm # Libreria per creare barre d'avanzamento
import pandas as pd # Libreria per analizzare e gestire dati strutturati
from loguru import logger # Gestione dei messaggi debbuger e terminale

ruoli = ["Portieri", "Difensori", "Centrocampisti", "Trequartisti", "Attaccanti"]

skills = {
    "Fuoriclasse": 1,
    "Titolare": 3,
    "Buona Media": 2,
    "Goleador": 4,
    "Assistman": 2,
    "Piazzati": 2,
    "Rigorista": 5,
    "Giovane talento": 2,
    "Panchinaro": -4,
    "Falloso": -2,
    "Outsider": 2,
}

# FUNCTION MODULES
# Estrazione url giocatore singolo
def get_giocatori(ruolo: str) -> list:

    html = requests.get(
        "https://www.fantacalciopedia.com/lista-calciatori-serie-a/"
        + ruolo.lower()
        + "/"
    )
    soup = BeautifulSoup(html.content, "html.parser")
    calciatori = []
    giocatori = soup.find_all("article")
    for giocatore in giocatori:
        calciatore = giocatore.find("a").get("href")
        calciatori.append(calciatore)

    return calciatori


# Gestione Attributi Giocatori
def get_attributi(url: str) -> dict:
    """Scarica e analizza i dati di un singolo giocatore da Fantacalciopedia"""
    time.sleep(randint(500, 1500) / 1000)  # delay per non stressare il server
    attributi = {}

    try:
        html = requests.get(url.strip(), timeout=10)
        html.raise_for_status()
    except Exception as e:
        logger.error(f"Errore nel download {url}: {e}")
        return attributi

    soup = BeautifulSoup(html.content, "html.parser")

    # Nome
    attributi["Nome"] = soup.select_one("h1").get_text(strip=True) if soup.select_one("h1") else "Sconosciuto"

    # Punteggio
    sel = "div.col_one_fourth:nth-of-type(1) span.stickdan"
    val = soup.select_one(sel)
    attributi["Punteggio"] = val.get_text(strip=True).replace("/100", "") if val else "0"

    # Fantamedie storiche
    sel = "div.col_one_fourth:nth-of-type(n+2) div"
    for el in soup.select(sel):
        anno = el.find("strong").get_text(strip=True).split()[-1] if el.find("strong") else "NA"
        media = el.find("span").get_text(strip=True) if el.find("span") else "0"
        attributi[f"Fantamedia {anno}"] = media

    # Statistiche ultimo anno
    sel = "div.col_one_third:nth-of-type(2) div"
    stats = soup.select_one(sel)
    if stats:
        keys = [el.get_text(strip=True).replace(":", "") for el in stats.find_all("strong")]
        vals = [el.get_text(strip=True) for el in stats.find_all("span")]
        attributi.update(dict(zip(keys, vals)))

    # Statistiche previste
    sel = ".col_one_third.col_last div"
    stats_prev = soup.select_one(sel)
    if stats_prev:
        keys = [el.get_text(strip=True).replace(":", "") for el in stats_prev.find_all("strong")]
        vals = [el.get_text(strip=True) for el in stats_prev.find_all("span")]
        attributi.update(dict(zip(keys, vals)))

    # Ruolo
    val = soup.select_one(".label12 span.label")
    attributi["Ruolo"] = val.get_text(strip=True) if val else "NA"

    # Skills
    attributi["Skills"] = [el.get_text(strip=True) for el in soup.select("span.stickdanpic")]

    # Investimento & resistenza
    vals = soup.select("div.progress-percent")
    attributi["Buon investimento"] = vals[2].get_text(strip=True).replace("%", "") if len(vals) > 2 else "0"
    attributi["Resistenza infortuni"] = vals[3].get_text(strip=True).replace("%", "") if len(vals) > 3 else "0"

    # Consigliato prossima giornata
    consigliato = soup.select_one("img.inf_calc")
    if consigliato and "Consigliato per la giornata" in consigliato.get("title", ""):
        attributi["Consigliato prossima giornata"] = True
    else:
        attributi["Consigliato prossima giornata"] = False

    # Nuovo acquisto
    attributi["Nuovo acquisto"] = soup.select_one("span.new_calc") is not None

    # Infortunato
    infort = soup.select_one("img.inf_calc")
    if infort and "Infortunato" in infort.get("title", ""):
        attributi["Infortunato"] = True
    else:
        attributi["Infortunato"] = False

    # Squadra
    #sel = "#content div.section div.col_three_fifth div.promo img"
    sel = "#content > div > div.section.nobg.nomargin > div > div > div:nth-child(2) > div.col_three_fifth > div.promo.promo-border.promo-light.row > div:nth-child(3) > div:nth-child(1) > div > img"
    val = soup.select_one(sel)
    if val and "title" in val.attrs:
        attributi["Squadra"] = val["title"].split(":")[-1].strip()
    else:
        attributi["Squadra"] = "NA"

    # Trend
    sel = "div.col_one_fourth:nth-of-type(n+2) div"
    trend_el = soup.select(sel)
    if trend_el and trend_el[0].find("i"):
        cl = trend_el[0].find("i").get("class", [])
        if "icon-arrow-up" in cl:
            attributi["Trend"] = "UP"
        elif "icon-arrow-down" in cl:
            attributi["Trend"] = "DOWN"
        else:
            attributi["Trend"] = "STABLE"
    else:
        attributi["Trend"] = "STABLE"

    # Presenze campionato
    sel = "div.col_one_fourth:nth-of-type(2) span.rouge"
    val = soup.select_one(sel)
    attributi["Presenze campionato corrente"] = val.get_text(strip=True) if val else "0"

    return attributi


# Gestione dati appetibilità
def appetibilita(df: pd.DataFrame) -> pd.Series:
    """Calcola l'indice di appetibilità dei giocatori"""

    # Conversioni numeriche robuste
    num_cols = ["Punteggio", "Presenze campionato corrente", "Buon investimento", "Resistenza infortuni"]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Normalizza fantamedie (cerca colonne che iniziano con 'Fantamedia')
    fantamedie_cols = [c for c in df.columns if c.startswith("Fantamedia")]
    for col in fantamedie_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    res = []

    for _, row in df.iterrows():
        score = 0

        # Media fantamedia più recente
        if fantamedie_cols:
            ultima_media = row[fantamedie_cols[-1]]
            score += float(ultima_media)

        # Punteggio generale
        score *= (row.get("Punteggio", 0) / 100)

        # Skills
        try:
            valori = row["Skills"] if isinstance(row["Skills"], list) else ast.literal_eval(str(row["Skills"]))
            for skill in valori:
                score += skills.get(skill, 0)
        except Exception:
            pass

        # Bonus/malus da flag
        if row.get("Nuovo acquisto", False): score -= 2
        if row.get("Buon investimento", 0) >= 60: score += 3
        if row.get("Consigliato prossima giornata", False): score += 1
        if row.get("Trend") == "UP": score += 2
        if row.get("Infortunato", False): score -= 1
        if row.get("Resistenza infortuni", 0) > 60: score += 4

        res.append(score)

    return pd.Series(res, index=df.index)


"""
    Riordina le colonne del DataFrame in un ordine logico e robusto.
    Se alcune colonne mancano, vengono ignorate.
"""
def riordina_colonne(df: pd.DataFrame) -> pd.DataFrame:

    ordine_desiderato = [
        "Ruolo",
        "Nome",
        "Squadra",
        "Punteggio",
        "Convenienza",
        "Presenze campionato corrente",
        "Fantamedia 2022",
        "Fantamedia 2023",
        "Fantamedia 2024",  # se disponibile
        "Skills",
        "Buon investimento",
        "Resistenza infortuni",
        "Consigliato prossima giornata",
        "Nuovo acquisto",
        "Infortunato",
        "Trend",
    ]

    # Prendo solo quelle che esistono davvero nel df
    colonne_finali = [col for col in ordine_desiderato if col in df.columns]

    # Aggiungo eventuali altre colonne rimaste in coda
    altre_colonne = [col for col in df.columns if col not in colonne_finali]
    colonne_finali.extend(altre_colonne)

    return df[colonne_finali]



#---------------------------------------------------------------------------#
# START OF SELECTION 
if __name__ == "__main__":
    giocatori_urls = []
    # Se non c'è il file txt url giocatori lo si crea
    if not os.path.exists("giocatori_urls.txt"):
        for i in tqdm(range(0, len(ruoli), 1)):
            lista = get_giocatori(ruoli[i])
            [giocatori_urls.append(el) for el in lista]
        with open(r"giocatori_urls.txt", "w", encoding="utf-8") as fp:
            for item in giocatori_urls:
                fp.write("%s\n" % item)
            logger.debug("URL scritti")
    else:
        logger.debug("Leggo la lista giocatori")
        with open("giocatori_urls.txt", "r", encoding="utf-8") as fp:
            giocatori_urls = fp.readlines()

    if not os.path.exists("giocatori.csv"):
        giocatori = []
        for i in tqdm(range(0, len(giocatori_urls), 1)):
            giocatore = get_attributi(giocatori_urls[i])
            giocatori.append(giocatore)
        df = pd.DataFrame.from_dict(giocatori)
        df.to_csv("giocatori.csv", index=False)
        
        logger.debug("CSV scritto")
    else:
        logger.debug("Leggo il dataset giocatori")
        df = pd.read_csv("giocatori.csv")

    df["Convenienza"] = appetibilita(df)

    # riordino le colonne come piace a me
    df = riordina_colonne(df)


    df.sort_values(by="Convenienza", ascending=False)

    # df.to_csv("giocatori_appet.csv", index=False)
    #df.to_excel("giocatori_excel.xls")
    df.to_csv("giocatori_finali.csv", index=False)
    df.to_json("giocatori_finali.json", orient="records", indent=4)

    logger.debug("Finito!")