"""Aufgabentypen und variable Zahlen.

Jede Aufgabe hat einen Typ und optionale strukturierte Daten (JSON). `rendern(aufgabe, seed)` erzeugt daraus
Aufgabentext und Lösung in der normalen Auszeichnungssprache. Der Seed wird pro Übungsblatt-/Prüfungsaufgabe
gespeichert, damit Aufgabenblatt und Lösungsblatt dieselben Zahlen bzw. dieselbe Reihenfolge zeigen.

  frei       Text und Lösung wie geschrieben
  rechnung   Variablen {name} mit Zufallswerten, Ergebnisse aus Formeln, z. B. {c} = n * 2 * 1e4
  mc         Multiple Choice (Optionen werden gemischt, Buchstaben in der Lösung passen dazu)
  zuordnung  Begriffe ↔ Beschreibungen (Beschreibungen gemischt)
  luecken    Lückentext: {{Antwort}} im Text wird zur Lücke, optional mit Wortliste
"""
import ast
import json
import math
import operator
import random
import re
from dataclasses import dataclass, field

TYPEN = {
    "frei": "Freie Aufgabe",
    "rechnung": "Rechenaufgabe mit variablen Zahlen",
    "mc": "Multiple Choice",
    "zuordnung": "Zuordnung",
    "luecken": "Lückentext",
}
ANTWORTFORMAT_VORSCHLAG = {"rechnung": "karo", "mc": "keins", "zuordnung": "keins", "luecken": "keins"}


@dataclass
class Gerendert:
    text: str
    loesung: str
    werte: dict = field(default_factory=dict)
    fehler: list = field(default_factory=list)


def daten_von(aufgabe):
    roh = getattr(aufgabe, "daten", None) or "{}"
    if isinstance(roh, dict):
        return roh
    try:
        d = json.loads(roh)
        return d if isinstance(d, dict) else {}
    except (ValueError, TypeError):
        return {}


def rendern(aufgabe, seed=0):
    typ = getattr(aufgabe, "typ", None) or "frei"
    d = daten_von(aufgabe)
    rng = random.Random(seed or 0)
    text, loesung = aufgabe.text or "", aufgabe.loesung or ""
    try:
        if typ == "rechnung":
            return _rechnung(text, loesung, d, rng)
        if typ == "mc":
            return _mc(text, loesung, d, rng)
        if typ == "zuordnung":
            return _zuordnung(text, loesung, d, rng)
        if typ == "luecken":
            return _luecken(text, loesung, d, rng)
    except FormelFehler as e:
        return Gerendert(text, loesung, fehler=[str(e)])
    return Gerendert(text, loesung)


# ---------------------------------------------------------------- Zahlen formatieren (Schweizer Schreibweise)

def zahl(v, stellen=3):
    """Gerundet auf `stellen` gültige Ziffern, Dezimalkomma, grosse/kleine Zahlen als a · 10^{n}."""
    if v is None or isinstance(v, bool):
        return str(v)
    if v == 0:
        return "0"
    if float(v).is_integer() and abs(v) < 1e5:
        return str(int(v))
    exp = math.floor(math.log10(abs(v)))
    if abs(v) >= 1e5 or abs(v) < 1e-3:
        mant = round(v / 10 ** exp, max(stellen - 1, 0))
        if abs(mant) >= 10:
            mant, exp = mant / 10, exp + 1
        m = f"{mant:.{max(stellen - 1, 0)}f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"{m} · 10^{{{exp}}}"
    ndigits = stellen - 1 - exp
    r = round(v, ndigits)
    if abs(r) >= 1e5:                       # durch Rundung über die Grenze gerutscht
        return zahl(r, stellen)
    if ndigits <= 0:
        return str(int(r))
    s = f"{r:.{ndigits}f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _schritt_nachkomma(schritt):
    s = f"{schritt:.10f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0


# ---------------------------------------------------------------- Sichere Formelauswertung

class FormelFehler(ValueError):
    pass


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNKTIONEN = {"sqrt": math.sqrt, "log10": math.log10, "log": math.log10, "ln": math.log, "exp": math.exp,
               "abs": abs, "round": round, "min": min, "max": max, "floor": math.floor, "ceil": math.ceil}
_KONSTANTEN = {"pi": math.pi, "e": math.e}


def formel_auswerten(formel, werte):
    """Wertet eine Formel aus (nur Zahlen, Variablen, + - * / ** %, erlaubte Funktionen). Dezimalkomma erlaubt."""
    quelle = re.sub(r"(\d),(\d)", r"\1.\2", str(formel)).replace("^", "**").replace("·", "*").replace("×", "*")
    try:
        baum = ast.parse(quelle, mode="eval")
    except SyntaxError:
        raise FormelFehler(f"Formel «{formel}» ist nicht lesbar.")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 100:
                raise FormelFehler("Exponent zu gross.")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Name):
            if n.id in werte:
                return werte[n.id]
            if n.id in _KONSTANTEN:
                return _KONSTANTEN[n.id]
            raise FormelFehler(f"Unbekannter Name «{n.id}» in «{formel}».")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNKTIONEN and not n.keywords:
            return _FUNKTIONEN[n.func.id](*[ev(x) for x in n.args])
        raise FormelFehler(f"In Formeln sind nur Zahlen, Variablen, + − × ÷ ^ und Funktionen wie sqrt, log10, ln "
                           f"erlaubt («{formel}»).")
    try:
        return ev(baum)
    except FormelFehler:
        raise
    except ZeroDivisionError:
        raise FormelFehler(f"Division durch null in «{formel}».")
    except (ValueError, OverflowError, TypeError) as e:
        raise FormelFehler(f"Formel «{formel}» kann nicht berechnet werden ({e}).")


RE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,30}$")
RE_PLATZHALTER = re.compile(r"(?<![_^{])\{([A-Za-z][A-Za-z0-9_]*)\}")


def _rechnung(text, loesung, d, rng):
    werte, anzeige = {}, {}
    for v in d.get("variablen", []):
        name = str(v.get("name", "")).strip()
        if not RE_NAME.match(name):
            raise FormelFehler(f"Ungültiger Variablenname «{name}» (Buchstaben, Ziffern, _).")
        lo, hi = float(v.get("min", 0)), float(v.get("max", 0))
        schritt = float(v.get("schritt") or 1)
        if schritt <= 0 or hi < lo:
            raise FormelFehler(f"Variable {name}: Bereich {lo}–{hi} mit Schritt {schritt} ist ungültig.")
        n = int(round((hi - lo) / schritt))
        wert = round(lo + rng.randint(0, n) * schritt, 10)
        nk = max(_schritt_nachkomma(schritt), _schritt_nachkomma(lo))
        if nk == 0:
            wert = int(round(wert))
        werte[name] = wert
        if abs(wert) >= 1e5:
            anzeige[name] = zahl(wert, 4)
        else:
            anzeige[name] = f"{wert:.{nk}f}".replace(".", ",") if nk else str(wert)
    for r in d.get("ergebnisse", []):
        name = str(r.get("name", "")).strip()
        if not RE_NAME.match(name):
            raise FormelFehler(f"Ungültiger Ergebnisname «{name}».")
        wert = formel_auswerten(r.get("formel", ""), werte)
        werte[name] = wert
        anzeige[name] = zahl(wert, int(r.get("stellen") or 3))

    fehler = []

    def ersetzen(t):
        def f(m):
            if m[1] in anzeige:
                return anzeige[m[1]]
            fehler.append(f"Platzhalter {{{m[1]}}} ist weder Variable noch Ergebnis.")
            return m[0]
        return RE_PLATZHALTER.sub(f, t)

    return Gerendert(ersetzen(text), ersetzen(loesung), werte, sorted(set(fehler)))


# ---------------------------------------------------------------- Multiple Choice, Zuordnung, Lückentext

def _buchstabe(i):
    return chr(ord("A") + i)


def _mc(text, loesung, d, rng):
    optionen = [o for o in d.get("optionen", []) if str(o.get("text", "")).strip()]
    fehler = [] if any(o.get("korrekt") for o in optionen) else ["Keine Antwort ist als richtig markiert."]
    if d.get("mischen", True):
        rng.shuffle(optionen)
    n_richtig = sum(1 for o in optionen if o.get("korrekt"))
    hinweis = "*(Mehrere Antworten können richtig sein.)*" if d.get("mehrfach") or n_richtig > 1 \
        else "*(Kreuze die richtige Antwort an.)*"
    zeilen = [f"☐ {_buchstabe(i)}) {o['text'].strip()}" for i, o in enumerate(optionen)]
    aufgabe = f"{text.rstrip()}\n\n{hinweis}\n" + "\n".join(zeilen)
    richtig = [f"☑ **{_buchstabe(i)}) {o['text'].strip()}**" for i, o in enumerate(optionen) if o.get("korrekt")]
    loes = "Richtig: " + ", ".join(_buchstabe(i) for i, o in enumerate(optionen) if o.get("korrekt")) + "\n" \
        + "\n".join(richtig)
    if loesung.strip():
        loes += "\n\n" + loesung.strip()
    return Gerendert(aufgabe, loes, fehler=fehler)


def _zuordnung(text, loesung, d, rng):
    paare = [(str(a).strip(), str(b).strip()) for a, b in d.get("paare", []) if str(a).strip() and str(b).strip()]
    fehler = [] if len(paare) >= 2 else ["Mindestens zwei Paare erfassen."]
    rechts = list(range(len(paare)))
    if d.get("mischen", True):
        rng.shuffle(rechts)
    buchst = {orig: _buchstabe(pos) for pos, orig in enumerate(rechts)}
    tab = ["| Nr. | Begriff | Buchstabe | | Beschreibung |"]
    for i, (links, _) in enumerate(paare):
        rechts_txt = paare[rechts[i]][1]
        tab.append(f"| {i + 1} | {links} | | {_buchstabe(i)} | {rechts_txt} |")
    aufgabe = f"{text.rstrip()}\n\n" + "\n".join(tab)
    loes_tab = ["| Nr. | Begriff | Lösung |"] + [f"| {i + 1} | {a} | **{buchst[i]}** – {b} |"
                                                for i, (a, b) in enumerate(paare)]
    loes = "\n".join(loes_tab) + ("\n\n" + loesung.strip() if loesung.strip() else "")
    return Gerendert(aufgabe, loes, fehler=fehler)


RE_LUECKE = re.compile(r"\{\{(.+?)\}\}")


def _luecken(text, loesung, d, rng):
    antworten = [m.split("|")[0].strip() for m in RE_LUECKE.findall(text)]
    fehler = [] if antworten else ["Keine Lücke gefunden – Antworten im Text mit {{Antwort}} markieren."]
    zaehler = iter(range(1, len(antworten) + 1))

    def luecke(m):
        laenge = max(8, len(m[1].split("|")[0]) + 4)
        return f"{'_' * laenge} ({next(zaehler)})"
    aufgabe = RE_LUECKE.sub(luecke, text)
    if d.get("wortliste") and antworten:
        liste = antworten[:]
        rng.shuffle(liste)
        aufgabe = aufgabe.rstrip() + "\n\n**Wortliste:** " + " · ".join(liste)
    loes = RE_LUECKE.sub(lambda m: "**" + m[1].replace("|", " / ") + "**", text)
    if loesung.strip():
        loes += "\n\n" + loesung.strip()
    return Gerendert(aufgabe, loes, fehler=fehler)


# ---------------------------------------------------------------- Prüfen beim Speichern

def pruefen(aufgabe, versuche=25):
    """Rendert mit mehreren Seeds und sammelt Fehler (z. B. Division durch null bei bestimmten Werten)."""
    fehler = []
    for s in range(1, versuche + 1 if aufgabe.typ == "rechnung" else 2):
        g = rendern(aufgabe, s)
        for f in g.fehler:
            if f not in fehler:
                fehler.append(f)
    return fehler


def neuer_seed():
    return random.randint(1, 2_000_000_000)
