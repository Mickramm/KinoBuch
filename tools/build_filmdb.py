#!/usr/bin/env python3
"""
Baut die Film-Datenbank (filmdb.json) für das Kinobuch aus den
IMDb Non-Commercial Datasets (https://developer.imdb.com/non-commercial-datasets/).
Die Daten dürfen nur privat und nicht-kommerziell genutzt werden.

Nur Python-Standardbibliothek. Aufruf:
    python3 tools/build_filmdb.py --out filmdb.json
Optionen:
    --films 10000     Anzahl Filme (die mit den meisten IMDb-Stimmen)
    --series 2500     Anzahl Serien/Miniserien
    --cast 6          Hauptdarsteller pro Titel
    --data imdb-data  Ordner für die heruntergeladenen Rohdaten
"""
import argparse, gzip, json, os, sys, time, urllib.request, datetime

BASE = "https://datasets.imdbws.com/"
FILES = ["title.ratings", "title.basics", "title.crew", "title.episode",
         "title.akas", "title.principals", "name.basics"]
FILM_TYPES = {"movie"}
SERIES_TYPES = {"tvSeries", "tvMiniSeries"}
CAST_CATS = {"actor", "actress", "self"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def download(data_dir, max_age_h=20):
    os.makedirs(data_dir, exist_ok=True)
    for f in FILES:
        p = os.path.join(data_dir, f + ".tsv.gz")
        if os.path.exists(p) and time.time() - os.path.getmtime(p) < max_age_h * 3600:
            continue
        log("lade", f)
        tmp = p + ".part"
        with urllib.request.urlopen(BASE + f + ".tsv.gz", timeout=120) as r, open(tmp, "wb") as out:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                out.write(b)
        os.replace(tmp, p)


def rows(data_dir, name):
    """Liest eine IMDb-TSV-Datei zeilenweise (ohne Kopfzeile)."""
    with gzip.open(os.path.join(data_dir, name + ".tsv.gz"), "rt", encoding="utf-8", newline="\n") as fh:
        next(fh)
        for line in fh:
            yield line.rstrip("\n").split("\t")


def nz(v):
    return None if v == "\\N" or v == "" else v


def build(data_dir, n_films, n_series, n_cast):
    log("Bewertungen")
    votes, rating = {}, {}
    for tconst, avg, num in rows(data_dir, "title.ratings"):
        votes[tconst] = int(num)
        rating[tconst] = float(avg)

    log("Titel-Grunddaten")
    films, series = [], []
    basics = {}
    for r in rows(data_dir, "title.basics"):
        tconst, ttype, primary, original, adult, sy, ey, rt, genres = r[:9]
        if adult == "1" or tconst not in votes:
            continue
        if ttype in FILM_TYPES:
            films.append(tconst)
        elif ttype in SERIES_TYPES:
            series.append(tconst)
        else:
            continue
        basics[tconst] = (ttype, primary, original, nz(sy), nz(ey), nz(rt), nz(genres))
    films.sort(key=lambda t: -votes[t])
    series.sort(key=lambda t: -votes[t])
    chosen = films[:n_films] + series[:n_series]
    sel = set(chosen)
    basics = {t: basics[t] for t in chosen}
    series_set = set(series[:n_series])
    log(f"ausgewählt: {min(n_films, len(films))} Filme, {min(n_series, len(series))} Serien")

    log("Regie")
    directors = {}
    for tconst, dirs, _w in rows(data_dir, "title.crew"):
        if tconst in sel and nz(dirs):
            directors[tconst] = dirs.split(",")[:3]

    log("Folgen")
    eps, seasons = {}, {}
    for _t, parent, sn, _en in rows(data_dir, "title.episode"):
        if parent in series_set:
            eps[parent] = eps.get(parent, 0) + 1
            s = nz(sn)
            if s and s.isdigit():
                seasons[parent] = max(seasons.get(parent, 0), int(s))

    log("Besetzung")
    cast = {}
    for r in rows(data_dir, "title.principals"):
        tconst, ordering, nconst, cat = r[0], r[1], r[2], r[3]
        if tconst in sel and cat in CAST_CATS:
            cast.setdefault(tconst, []).append((int(ordering), nconst))
    for t in cast:
        cast[t] = [n for _o, n in sorted(cast[t])[:n_cast]]

    log("Deutsche Titel")
    # Priorität: offizieller Anzeigetitel > normaler Titel > sonstige
    de = {}
    prio_of = lambda types: 0 if "imdbDisplay" in types else (1 if types in ("\\N", "") else 2)
    for r in rows(data_dir, "title.akas"):
        tid, ordering, title, region, _lang, types = r[0], r[1], r[2], r[3], r[4], r[5]
        if region != "DE" or tid not in sel:
            continue
        if any(x in types for x in ("working", "festival", "video", "tv")):
            continue
        p = (prio_of(types), int(ordering))
        if tid not in de or p < de[tid][0]:
            de[tid] = (p, title)

    log("Namen")
    need = set()
    for t in chosen:
        need.update(directors.get(t, []))
        need.update(cast.get(t, []))
    names = {}
    for r in rows(data_dir, "name.basics"):
        if r[0] in need:
            names[r[0]] = r[1]

    log("Zusammenbauen")
    name_idx, name_list = {}, []
    genre_idx, genre_list = {}, []

    def ni(n):
        if n not in names:
            return None
        if n not in name_idx:
            name_idx[n] = len(name_list)
            name_list.append(names[n])
        return name_idx[n]

    def gi(g):
        if g not in genre_idx:
            genre_idx[g] = len(genre_list)
            genre_list.append(g)
        return genre_idx[g]

    out = []
    for t in chosen:
        ttype, primary, original, sy, ey, rt, genres = basics[t]
        is_series = ttype in SERIES_TYPES
        de_title = de.get(t, (None, ""))[1]
        out.append([
            int(t[2:]),                                    # 0 IMDb-ID (Zahl)
            1 if is_series else 0,                          # 1 Serie?
            primary,                                        # 2 Titel
            original if original != primary else "",       # 3 Originaltitel
            de_title if de_title not in (primary, original) else "",  # 4 deutscher Titel
            int(sy) if sy else 0,                           # 5 Jahr
            int(ey) if ey else 0,                           # 6 Endjahr (Serien)
            int(rt) if rt and rt.isdigit() else 0,          # 7 Laufzeit
            [gi(g) for g in genres.split(",")] if genres else [],  # 8 Genres
            rating[t],                                      # 9 IMDb-Wertung
            votes[t],                                       # 10 Stimmen
            [x for x in (ni(n) for n in directors.get(t, [])) if x is not None],  # 11 Regie
            [x for x in (ni(n) for n in cast.get(t, [])) if x is not None],       # 12 Besetzung
            eps.get(t, 0) if is_series else 0,              # 13 Folgen
            seasons.get(t, 0) if is_series else 0,          # 14 Staffeln
        ])
    return {
        "v": 1,
        "built": datetime.date.today().isoformat(),
        "source": "IMDb Non-Commercial Datasets – nur private, nicht-kommerzielle Nutzung",
        "cols": ["id", "serie", "titel", "original", "de", "jahr", "endjahr", "laufzeit",
                 "genres", "wertung", "stimmen", "regie", "besetzung", "folgen", "staffeln"],
        "genres": genre_list,
        "names": name_list,
        "t": out,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="filmdb.json")
    ap.add_argument("--data", default="imdb-data")
    ap.add_argument("--films", type=int, default=10000)
    ap.add_argument("--series", type=int, default=2500)
    ap.add_argument("--cast", type=int, default=6)
    ap.add_argument("--no-download", action="store_true", help="vorhandene Dateien im Datenordner verwenden")
    a = ap.parse_args()
    if not a.no_download:
        download(a.data)
    db = build(a.data, a.films, a.series, a.cast)
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(db, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, a.out)
    log(f"fertig: {len(db['t'])} Titel, {len(db['names'])} Namen, {os.path.getsize(a.out)/1e6:.1f} MB -> {a.out}")


if __name__ == "__main__":
    sys.exit(main())
