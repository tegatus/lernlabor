"""KI-Assistent für Lehrpersonen (Claude API) – im Standby, bis ANTHROPIC_API_KEY gesetzt ist.

Funktionen: Aufgabenentwurf aus Lernzielen, Lösung prüfen, Tags vorschlagen, Variante erstellen.
Übermittelt werden nur Aufgabeninhalte und Lernziele – keine Daten von Lernenden.

Konfiguration (Umgebungsvariablen):
  ANTHROPIC_API_KEY   API-Schlüssel aus der Claude Console (ohne Schlüssel bleibt der Assistent aus)
  KI_MODELL           Modell, Standard: claude-opus-5-5
  KI_AKTIV=0          Assistent trotz Schlüssel ausschalten
  KI_PREIS_INPUT / KI_PREIS_OUTPUT / KI_PREIS_CACHE_LESEN
                      USD pro Million Tokens für die Kostenschätzung (Standard Claude Opus 5.5: 4 / 20 / 0.20)
"""
import json
import os

from flask import current_app
from flask_login import current_user

from .aufgabentypen import TYPEN, pruefen as typ_pruefen, rendern
from .models import ANTWORTFORMATE, KiProtokoll, db

STANDARD_MODELL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class KiFehler(Exception):
    """Fehler mit einer Meldung, die der Lehrperson angezeigt werden kann."""


def konfig(name, standard=None):
    return current_app.config.get(name) or os.environ.get(name) or standard


def ki_aktiv():
    return bool(konfig("ANTHROPIC_API_KEY")) and str(konfig("KI_AKTIV", "1")) != "0"


def modell():
    return konfig("KI_MODELL", STANDARD_MODELL)


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=konfig("ANTHROPIC_API_KEY"), timeout=180.0, max_retries=2)


# ---------------------------------------------------------------- Anfrage an die Claude API

def _anfrage(aktion, system, prompt, schema, effort="medium"):
    """Eine Anfrage mit strukturierter JSON-Antwort. Gibt das geparste dict zurück, protokolliert den Verbrauch."""
    import anthropic
    if not ki_aktiv():
        raise KiFehler("Der KI-Assistent ist nicht aktiviert.")
    client = _client()
    params = dict(
        model=modell(),
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        cache_control={"type": "ephemeral"},  # System-Prompt und Katalog werden bei Folgeanfragen günstiger
    )
    try:
        try:
            # Bei einer Ablehnung durch Sicherheitsfilter springt serverseitig ein Ersatzmodell ein
            antwort = client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **params)
        except anthropic.BadRequestError as e:
            if "fallback" not in str(e).lower():
                raise
            antwort = client.messages.create(**params)  # Konto/Modell ohne Fallback-Unterstützung
    except anthropic.AuthenticationError:
        raise KiFehler("Der API-Schlüssel ist ungültig. Bitte in der Claude Console prüfen.")
    except anthropic.PermissionDeniedError:
        raise KiFehler("Der API-Schlüssel hat keine Berechtigung für dieses Modell.")
    except anthropic.RateLimitError:
        raise KiFehler("Zu viele Anfragen oder Guthaben/Ausgabenlimit erreicht. Bitte später erneut versuchen.")
    except anthropic.BadRequestError as e:
        current_app.logger.warning("KI-Anfrage abgelehnt: %s", e)
        raise KiFehler("Die Anfrage wurde von der API abgelehnt (Details im Server-Log).")
    except anthropic.APIStatusError as e:
        raise KiFehler(f"Die Claude API meldet einen Fehler ({e.status_code}). Bitte später erneut versuchen.")
    except anthropic.APIConnectionError:
        raise KiFehler("Keine Verbindung zur Claude API. Netzwerk/Firewall des Servers prüfen.")

    _protokollieren(aktion, antwort)
    if antwort.stop_reason == "refusal":
        raise KiFehler("Die KI hat diese Anfrage abgelehnt. Bitte anders formulieren.")
    if antwort.stop_reason == "max_tokens":
        raise KiFehler("Die Antwort war zu lang und wurde abgeschnitten. Bitte die Anfrage eingrenzen.")
    text = next((b.text for b in antwort.content if getattr(b, "type", None) == "text"), None)
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        raise KiFehler("Die Antwort der KI war nicht lesbar. Bitte erneut versuchen.")


def _protokollieren(aktion, antwort):
    u = getattr(antwort, "usage", None)
    db.session.add(KiProtokoll(
        lp_id=current_user.id if current_user and current_user.is_authenticated else None, aktion=aktion,
        modell=getattr(antwort, "model", modell()),
        input_tokens=getattr(u, "input_tokens", 0) or 0, output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_lesen=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_schreiben=getattr(u, "cache_creation_input_tokens", 0) or 0))
    db.session.commit()


def kosten_usd(p):
    """Grobe Kostenschätzung eines Protokolleintrags. Standardpreise: Claude Opus 5.5 (USD pro Million Tokens:
    Input 4, Output 20, Cache lesen 0.20, Cache schreiben 1.25 × Input). Bei anderem Modell per Umgebung anpassen."""
    pin = float(konfig("KI_PREIS_INPUT", 4.0)) / 1e6
    pout = float(konfig("KI_PREIS_OUTPUT", 20.0)) / 1e6
    pcache = float(konfig("KI_PREIS_CACHE_LESEN", 0.20)) / 1e6
    return p.input_tokens * pin + p.cache_lesen * pcache + p.cache_schreiben * pin * 1.25 + p.output_tokens * pout


# ---------------------------------------------------------------- Gemeinsamer Kontext

SYSTEM_BASIS = """Du unterstützt Lehrpersonen einer Schweizer Berufsfachschule in der Ausbildung \
Laborantin/Laborant EFZ, Fachrichtung Biologie, beim Erstellen von Übungs- und Prüfungsaufgaben.

Sprache: Deutsch in Schweizer Rechtschreibung (immer «ss», nie «ß»), sachlich, klar, für Lernende im 1.–3. Lehrjahr.
Fachlich korrekt und praxisnah (Laboralltag, SOPs, GLP, Biosicherheit). Rechne jede Zahl selbst nach.

K-Stufen (Taxonomie der Bildungsverordnung): K1 Wissen (wiedergeben), K2 Verstehen (erklären, beschreiben), \
K3 Anwenden (berechnen, durchführen), K4 Analysieren (vergleichen, beurteilen, Fehler finden), \
K5 Synthese (entwickeln, planen), K6 Bewerten (begründet entscheiden).

Auszeichnung in Aufgaben- und Lösungstexten (keine andere Formatierung verwenden):
- Leerzeile = neuer Absatz; «- » am Zeilenanfang = Aufzählung; «a) », «b) » = Teilaufgaben (eigene Zeile)
- **fett**, *kursiv*, tiefgestellt H_{2}O, hochgestellt 10^{6}, Ionen SO_{4}^{2-}
- Tabellen: Zeilen der Form «| Probe | Ct |», erste Zeile ist die Kopfzeile
- Sonderzeichen direkt: µ ° × · ± ≈ → ⇌ Δ

Aufgabentypen und ihr Feld «daten_json» (JSON-Text):
- frei: "{}"
- rechnung: Platzhalter {name} in Text und Lösung. daten_json = {"variablen":[{"name":"n","min":40,"max":70,"schritt":1}],\
"ergebnisse":[{"name":"c","formel":"n * 2 * 10^4","stellen":3}]}. Formeln: + - * / ^ ( ), sqrt, log10, ln, exp, round, pi. \
Wähle Bereiche so, dass jede Kombination realistisch und lösbar ist (keine Division durch null).
- mc: Text = Frage. daten_json = {"optionen":[{"text":"…","korrekt":true},{"text":"…","korrekt":false}],"mischen":true}. \
3–5 plausible Optionen, typische Fehlvorstellungen als Distraktoren. Die Lösung enthält die Begründung.
- zuordnung: daten_json = {"paare":[["Begriff","Beschreibung"],…],"mischen":true}, 4–6 Paare.
- luecken: Lücken im Text als {{Antwort}} oder {{Antwort|Alternative}}. daten_json = {"wortliste":true|false}.

Musterlösungen: vollständig und nachvollziehbar, mit Punkteverteilung (z. B. «(2 P.)»), Rechenwege mit Einheiten.
Antwortfeld: «linien» für Text, «karo» für Rechnungen, «leer» für Skizzen, «keins» bei mc/zuordnung/luecken. \
Höhe in cm ungefähr: 1 cm pro erwarteter Textzeile, Rechnungen 6–9 cm."""

AUFGABE_SCHEMA = {
    "type": "object",
    "properties": {
        "titel": {"type": "string"},
        "typ": {"type": "string", "enum": list(TYPEN)},
        "text": {"type": "string"},
        "loesung": {"type": "string"},
        "daten_json": {"type": "string"},
        "punkte": {"type": "number"},
        "k_stufe": {"type": "integer", "enum": [1, 2, 3, 4, 5, 6]},
        "antwortformat": {"type": "string", "enum": list(ANTWORTFORMATE)},
        "antwortraum_cm": {"type": "number"},
        "kommentar": {"type": "string", "description": "Kurze Notiz an die Lehrperson (z. B. Annahmen)"},
    },
    "required": ["titel", "typ", "text", "loesung", "daten_json", "punkte", "k_stufe", "antwortformat",
                 "antwortraum_cm", "kommentar"],
    "additionalProperties": False,
}


def _aufgabe_als_text(d):
    teile = [f"Titel: {d.get('titel', '')}", f"Typ: {d.get('typ', 'frei')}",
             f"Punkte: {d.get('punkte', '')}", f"K-Stufe: {d.get('k_stufe') or '–'}",
             f"Aufgabentext:\n{d.get('text', '')}", f"Musterlösung:\n{d.get('loesung', '')}"]
    daten = d.get("daten")
    if daten and daten not in ("{}", {}):
        teile.append("daten_json: " + (daten if isinstance(daten, str) else json.dumps(daten, ensure_ascii=False)))
    return "\n".join(teile)


def _lernziele_text(lernziele, leistungsziele):
    zeilen = [f"- {lz.label}: {lz.text} (BiVo {', '.join(l.code for l in lz.leistungsziele)}, K{lz.k_stufe})"
              for lz in lernziele]
    zeilen += [f"- BiVo {l.code}: {l.text} (K{l.k_stufe})" for l in leistungsziele]
    return "\n".join(zeilen)


def _aufgabe_bereinigen(roh):
    """Prüft und normalisiert eine von der KI gelieferte Aufgabe; gibt (aufgabe, hinweise) zurück."""
    from types import SimpleNamespace
    hinweise = []
    try:
        daten = json.loads(roh.get("daten_json") or "{}")
        if not isinstance(daten, dict):
            raise ValueError
    except ValueError:
        daten, hinweise = {}, ["Die strukturierten Daten der KI waren ungültig und wurden verworfen."]
    typ = roh.get("typ") if roh.get("typ") in TYPEN else "frei"
    a = {
        "titel": (roh.get("titel") or "").strip()[:200], "typ": typ, "text": roh.get("text") or "",
        "loesung": roh.get("loesung") or "", "daten": daten if typ != "frei" else {},
        "punkte": max(0.5, min(float(roh.get("punkte") or 2), 50)),
        "k_stufe": roh.get("k_stufe") if roh.get("k_stufe") in range(1, 7) else None,
        "antwortformat": roh.get("antwortformat") if roh.get("antwortformat") in ANTWORTFORMATE else "linien",
        "antwortraum_cm": max(0.0, min(float(roh.get("antwortraum_cm") or 0), 25)),
        "kommentar": roh.get("kommentar") or "",
    }
    hinweise += typ_pruefen(SimpleNamespace(**{**a, "daten": json.dumps(a["daten"])}))
    return a, hinweise


# ---------------------------------------------------------------- 1. Aufgabenentwurf

def entwurf(lernziele, leistungsziele, themen, typ, k_stufe, punkte, wunsch, beispiele):
    ziele = _lernziele_text(lernziele, leistungsziele) or "(keine Lernziele gewählt)"
    bsp = "\n\n---\n\n".join(_aufgabe_als_text(b.to_dict()) for b in beispiele[:2])
    prompt = f"""Erstelle eine neue Aufgabe.

Lernziele, die die Aufgabe abdecken soll:
{ziele}

Thema: {', '.join(t.name for t in themen) or 'frei wählbar, passend zu den Lernzielen'}
Gewünschter Aufgabentyp: {typ if typ in TYPEN and typ != 'frei' else 'frei wählbar (am besten passend zum Lernziel)'}
Gewünschte K-Stufe: {f'K{k_stufe}' if k_stufe else 'passend zu den Lernzielen'}
Punkte: {punkte or 'angemessen (2–8)'}
Wünsche der Lehrperson: {wunsch or '–'}
"""
    if bsp:
        prompt += f"\nZur Orientierung (Stil und Niveau) bestehende Aufgaben aus der Sammlung – nicht kopieren:\n\n{bsp}\n"
    roh = _anfrage("entwurf", SYSTEM_BASIS, prompt, AUFGABE_SCHEMA, effort="medium")
    return _aufgabe_bereinigen(roh)


# ---------------------------------------------------------------- 2. Lösung prüfen

PRUEF_SCHEMA = {
    "type": "object",
    "properties": {
        "urteil": {"type": "string", "enum": ["in_ordnung", "kleine_hinweise", "fehler_gefunden"]},
        "zusammenfassung": {"type": "string"},
        "befunde": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "schwere": {"type": "string", "enum": ["fehler", "hinweis"]},
                "bereich": {"type": "string", "enum": ["aufgabe", "loesung", "punkte", "sprache", "fachlich"]},
                "beschreibung": {"type": "string"},
                "vorschlag": {"type": "string"},
            },
            "required": ["schwere", "bereich", "beschreibung", "vorschlag"],
            "additionalProperties": False,
        }},
    },
    "required": ["urteil", "zusammenfassung", "befunde"],
    "additionalProperties": False,
}


def loesung_pruefen(d):
    from types import SimpleNamespace
    entwurf_obj = SimpleNamespace(typ=d.get("typ") or "frei", daten=d.get("daten") or {}, text=d.get("text", ""),
                                  loesung=d.get("loesung", ""))
    varianten = ""
    if entwurf_obj.typ != "frei":
        for seed in (1, 2):
            g = rendern(entwurf_obj, seed)
            werte = ", ".join(f"{k} = {v:g}" for k, v in g.werte.items()) if g.werte else ""
            varianten += f"\n\nGerenderte Variante {seed}{' (' + werte + ')' if werte else ''}:\nAufgabe:\n{g.text}\nLösung:\n{g.loesung}"
    prompt = f"""Prüfe diese Aufgabe mit Musterlösung sorgfältig:
- Rechne alle Zahlen und Formeln nach (auch in den gerenderten Varianten), prüfe Einheiten und gültige Ziffern.
- Passt die Lösung zur Aufgabenstellung? Ist die Aufgabe eindeutig lösbar? Fehlen Angaben?
- Fachliche Korrektheit (Laborpraxis, Biologie), Punkteverteilung, Sprache (Schweizer Rechtschreibung).
Melde nur echte Probleme; wenn alles stimmt, ist die Liste leer.

{_aufgabe_als_text(d)}{varianten}"""
    return _anfrage("pruefen", SYSTEM_BASIS, prompt, PRUEF_SCHEMA, effort="high")


# ---------------------------------------------------------------- 3. Tags vorschlagen

TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "themen": {"type": "array", "items": {"type": "string"}},
        "lernziele": {"type": "array", "items": {"type": "string"}},
        "bivo": {"type": "array", "items": {"type": "string"}},
        "k_stufe": {"type": "integer", "enum": [1, 2, 3, 4, 5, 6]},
        "begruendung": {"type": "string"},
    },
    "required": ["themen", "lernziele", "bivo", "k_stufe", "begruendung"],
    "additionalProperties": False,
}


def tags_vorschlagen(d, themen, lernziele, leistungsziele):
    # Katalog zuerst und stabil sortiert: wird so per Prompt-Caching wiederverwendet
    katalog = ("Themen:\n" + "\n".join(f"- {t.name}" for t in themen)
               + "\n\nKonkrete Lernziele (Kennung: Text):\n"
               + "\n".join(f"- {lz.label}: {lz.text}" for lz in lernziele)
               + "\n\nBiVo-Leistungsziele (Code: Text):\n"
               + "\n".join(f"- {l.code}: {l.text} (K{l.k_stufe})" for l in leistungsziele))
    system = SYSTEM_BASIS + "\n\nKatalog für die Zuordnung:\n" + katalog
    prompt = f"""Ordne diese Aufgabe zu. Wähle nur Einträge aus dem Katalog, exakt wie dort geschrieben
(Themen per Name, Lernziele per Kennung wie «qPCR a9», BiVo per Code wie «a.2.3»).
Wähle nur, was die Aufgabe wirklich prüft (meist 1–3 Lernziele). BiVo-Codes zusätzlich nur, wenn sie nicht schon
über ein gewähltes Lernziel abgedeckt sind. Bestimme die K-Stufe nach dem höchsten verlangten Denkniveau.

{_aufgabe_als_text(d)}"""
    roh = _anfrage("tags", system, prompt, TAG_SCHEMA, effort="low")
    namen = {t.name: t.id for t in themen}
    labels = {lz.label: lz.id for lz in lernziele}
    codes = {l.code for l in leistungsziele}
    return {
        "themen": [namen[x] for x in roh.get("themen", []) if x in namen],
        "lernziele": [labels[x] for x in roh.get("lernziele", []) if x in labels],
        "bivo": [x for x in roh.get("bivo", []) if x in codes],
        "k_stufe": roh.get("k_stufe"),
        "begruendung": roh.get("begruendung", ""),
    }


# ---------------------------------------------------------------- 4. Variante

VARIANTEN = {
    "zahlen": "dieselbe Aufgabe mit anderen Zahlenwerten bzw. einer anderen konkreten Laborsituation, gleiches Niveau",
    "einfacher": "eine einfachere Version (eine K-Stufe tiefer, mehr Hilfestellung, weniger Schritte)",
    "schwieriger": "eine anspruchsvollere Version (eine K-Stufe höher, z. B. Beurteilen/Fehlersuche statt Berechnen)",
    "englisch": "dieselbe Aufgabe auf Englisch (Fachbegriffe wie im Labor üblich), Lösung ebenfalls auf Englisch",
    "anderer_typ": "dieselben Inhalte als anderer Aufgabentyp (z. B. Multiple Choice oder Lückentext statt freier Text)",
}


def variante(d, art):
    beschreibung = VARIANTEN.get(art, VARIANTEN["zahlen"])
    prompt = f"""Erstelle {beschreibung}.
Behalte das Lernziel bei. Platzhalter für Bilder ([[bild:N]]) dürfen übernommen werden, wenn die Grafik weiterhin passt.

Ausgangsaufgabe:
{_aufgabe_als_text(d)}"""
    roh = _anfrage("variante", SYSTEM_BASIS, prompt, AUFGABE_SCHEMA, effort="medium")
    return _aufgabe_bereinigen(roh)
