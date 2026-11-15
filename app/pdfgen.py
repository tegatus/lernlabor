"""PDF-Erzeugung: Übungsblätter, Lösungsblätter, Prüfungen und Korrektur-Rückmeldungen.

Auszeichnung in Aufgaben- und Lösungstexten (bewusst einfach gehalten):
  Leerzeile            neuer Absatz
  - Punkt              Aufzählung
  1) Punkt / a) Punkt  nummerierte Teilaufgabe (bleibt so stehen, mit Einzug)
  | A | B |            Tabellenzeile (erste Zeile = Kopfzeile)
  **fett**  *kursiv*   Hervorhebung
  H_{2}O  10^{6}       tief-/hochgestellt
"""
import html
import io
import os
import re
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (CondPageBreak, Flowable, Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

FONT_DIR = os.path.join(os.path.dirname(__file__), "static", "fonts")
_fonts_ok = False


def _register_fonts():
    global _fonts_ok
    if _fonts_ok:
        return
    for name, datei in [("LS", "LiberationSans-Regular.ttf"), ("LS-B", "LiberationSans-Bold.ttf"),
                        ("LS-I", "LiberationSans-Italic.ttf"), ("LS-BI", "LiberationSans-BoldItalic.ttf")]:
        pdfmetrics.registerFont(TTFont(name, os.path.join(FONT_DIR, datei)))
    pdfmetrics.registerFontFamily("LS", normal="LS", bold="LS-B", italic="LS-I", boldItalic="LS-BI")
    # Ersatzschrift für Zeichen, die Liberation Sans nicht kennt (z. B. ≙ ✓ ⇌)
    pdfmetrics.registerFont(TTFont("DV", os.path.join(FONT_DIR, "DejaVuSans.ttf")))
    _GLYPHEN.update(pdfmetrics.getFont("LS").face.charToGlyph.keys())
    _fonts_ok = True


_GLYPHEN = set()


def _ersatzschrift(t):
    """Umhüllt Zeichen ohne Glyphe in der Hauptschrift mit der Ersatzschrift."""
    return "".join(c if (ord(c) in _GLYPHEN or c in "\n\t") else f'<font name="DV">{c}</font>' for c in t)


GRAU = colors.HexColor("#666666")
HELLGRAU = colors.HexColor("#c8c8c8")
AKZENT = colors.HexColor("#1f5f8b")
LOESUNG_BG = colors.HexColor("#eef6ee")

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN - 12  # Frame hat links/rechts je 6 pt Innenabstand


def _styles():
    _register_fonts()
    base = ParagraphStyle("base", fontName="LS", fontSize=10.5, leading=14.5)
    return {
        "base": base,
        "titel": ParagraphStyle("titel", parent=base, fontName="LS-B", fontSize=17, leading=21, textColor=AKZENT,
                                spaceAfter=4),
        "untertitel": ParagraphStyle("ut", parent=base, fontSize=9, leading=12, textColor=GRAU),
        "aufg_kopf": ParagraphStyle("ak", parent=base, fontName="LS-B", fontSize=11.5, leading=15),
        "aufg_punkte": ParagraphStyle("ap", parent=base, fontName="LS-B", fontSize=11, alignment=TA_RIGHT),
        "meta": ParagraphStyle("meta", parent=base, fontSize=8, leading=10, textColor=GRAU),
        "text": ParagraphStyle("text", parent=base, spaceAfter=4),
        "liste": ParagraphStyle("liste", parent=base, leftIndent=14, bulletIndent=3, spaceAfter=1),
        "teil": ParagraphStyle("teil", parent=base, leftIndent=18, firstLineIndent=-18, spaceAfter=2),
        "zelle": ParagraphStyle("zelle", parent=base, fontSize=9.5, leading=12),
        "zelle_b": ParagraphStyle("zelleb", parent=base, fontName="LS-B", fontSize=9.5, leading=12),
        "klein": ParagraphStyle("klein", parent=base, fontSize=9, leading=12),
    }


# ---------------------------------------------------------------- Auszeichnung → Flowables

def inline(text):
    _register_fonts()
    t = _ersatzschrift(html.escape(text, quote=False))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"_\{(.+?)\}", r"<sub>\1</sub>", t)
    t = re.sub(r"\^\{(.+?)\}", r"<super>\1</super>", t)
    return t


def markup_flowables(text, st, width=CONTENT_W):
    """Wandelt die einfache Auszeichnung in eine Liste von Flowables um."""
    out = []
    blocks = re.split(r"\n\s*\n", (text or "").strip().replace("\r\n", "\n"))
    for block in blocks:
        lines = [l.rstrip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        if all(l.lstrip().startswith("|") for l in lines):
            out.append(_tabelle(lines, st, width))
            out.append(Spacer(1, 4))
            continue
        absatz = []

        def flush():
            if absatz:
                out.append(Paragraph(inline(" ".join(absatz)), st["text"]))
                absatz.clear()

        for l in lines:
            s = l.strip()
            if re.match(r"^[-•]\s+", s):
                flush()
                out.append(Paragraph(inline(re.sub(r"^[-•]\s+", "", s)), st["liste"], bulletText="•"))
            elif re.match(r"^(\d+|[a-z])\)\s+", s):
                flush()
                out.append(Paragraph(inline(s), st["teil"]))
            elif s.startswith("|"):
                flush()
                out.append(_tabelle([s], st, width))
            else:
                absatz.append(s)
        flush()
    return out


def _tabelle(lines, st, width):
    rows = []
    for l in lines:
        zellen = [z.strip() for z in l.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", z) for z in zellen if z):  # Markdown-Trennzeile ignorieren
            continue
        rows.append(zellen)
    ncol = max(len(r) for r in rows)
    data = [[Paragraph(inline(z), st["zelle_b"] if i == 0 else st["zelle"]) for z in r + [""] * (ncol - len(r))]
            for i, r in enumerate(rows)]
    t = Table(data, colWidths=[min(width / ncol, 4.5 * cm)] * ncol, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


class Antwortfeld(Flowable):
    """Leerraum zum Beantworten: Linien, Karo oder leeres Feld."""

    def __init__(self, hoehe_cm, art="linien", width=CONTENT_W):
        super().__init__()
        self.h = max(0.0, float(hoehe_cm or 0)) * cm
        self.art = art
        self.w = width

    def wrap(self, aw, ah):
        return self.w, self.h + 4

    def draw(self):
        c = self.canv
        w, h = self.w, self.h
        if h <= 0 or self.art == "keins":
            return
        c.saveState()
        if self.art == "karo":
            step = 0.5 * cm
            c.setStrokeColor(colors.HexColor("#d9d9d9"))
            c.setLineWidth(0.35)
            x = 0
            while x <= w + 0.1:
                c.line(x, 0, x, h)
                x += step
            y = h
            while y >= -0.1:
                c.line(0, y, w, y)
                y -= step
        elif self.art == "linien":
            step = 0.85 * cm
            c.setStrokeColor(HELLGRAU)
            c.setLineWidth(0.5)
            y = h - step
            while y >= 0:
                c.line(0, y, w, y)
                y -= step
        else:  # leer
            c.setStrokeColor(HELLGRAU)
            c.setLineWidth(0.6)
            c.rect(0, 0, w, h)
        c.restoreState()


def _bild_flowable(pfad, max_w=CONTENT_W, max_h=9 * cm):
    if not pfad or not os.path.exists(pfad):
        return None
    from PIL import Image as PILImage
    with PILImage.open(pfad) as im:
        w, h = im.size
    f = min(max_w / w, max_h / h)
    img = Image(pfad, width=w * f, height=h * f)
    img.hAlign = "LEFT"
    return img


def _punkte_str(p):
    return f"{p:g} P." if p is not None else ""


# ---------------------------------------------------------------- Seitenrahmen

def _seitenrahmen_factory(kopf_links, kopf_rechts):
    class Rahmen(rl_canvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._seiten = []

        def showPage(self):
            self._seiten.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._seiten)
            for state in self._seiten:
                self.__dict__.update(state)
                self._zeichne(n)
                super().showPage()
            super().save()

        def _zeichne(self, n):
            _register_fonts()
            self.saveState()
            self.setFont("LS", 8)
            self.setFillColor(GRAU)
            self.drawString(MARGIN, PAGE_H - 1.2 * cm, kopf_links)
            self.drawRightString(PAGE_W - MARGIN, PAGE_H - 1.2 * cm, kopf_rechts)
            self.setStrokeColor(HELLGRAU)
            self.line(MARGIN, PAGE_H - 1.35 * cm, PAGE_W - MARGIN, PAGE_H - 1.35 * cm)
            self.drawRightString(PAGE_W - MARGIN, 1.1 * cm, f"Seite {self._pageNumber} / {n}")
            self.drawString(MARGIN, 1.1 * cm, kopf_rechts)
            self.restoreState()

    return Rahmen


def _doc(buf, titel):
    return SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                             topMargin=1.8 * cm, bottomMargin=1.7 * cm, title=titel, author="LaborÜben")


def _kopfblock(st, titel, felder, untertitel=None):
    """Titel + Tabelle mit Name/Datum/Punkte usw. (felder: Liste von (Label, Wert))."""
    out = [Paragraph(html.escape(titel), st["titel"])]
    if untertitel:
        out.append(Paragraph(untertitel, st["untertitel"]))
    out.append(Spacer(1, 6))
    data, row = [], []
    for label, wert in felder:
        row += [Paragraph(f"<b>{html.escape(label)}</b>", st["klein"]),
                Paragraph(html.escape(wert or ""), st["klein"])]
        if len(row) == 4:
            data.append(row)
            row = []
    if row:
        data.append(row + [""] * (4 - len(row)))
    t = Table(data, colWidths=[2.6 * cm, 5.9 * cm, 2.6 * cm, 5.9 * cm], rowHeights=0.85 * cm)
    t.setStyle(TableStyle([
        ("LINEBELOW", (1, 0), (1, -1), 0.5, GRAU), ("LINEBELOW", (3, 0), (3, -1), 0.5, GRAU),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))
    out += [t, Spacer(1, 14)]
    return out


def _aufgaben_kopf(st, nr, aufgabe, zusatz_meta=True):
    kopf = Table([[Paragraph(f"Aufgabe {nr}&nbsp;&nbsp;<font color='#1f5f8b'>{html.escape(aufgabe.titel)}</font>",
                             st["aufg_kopf"]),
                   Paragraph(_punkte_str(aufgabe.punkte), st["aufg_punkte"])]],
                 colWidths=[CONTENT_W - 2.2 * cm, 2.2 * cm])
    kopf.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.8, AKZENT),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    out = [kopf, Spacer(1, 3)]
    if zusatz_meta:
        teile = []
        if aufgabe.k_stufe:
            teile.append(f"K{aufgabe.k_stufe}")
        if aufgabe.lernziele:
            teile.append("Lernziele: " + ", ".join(l.label for l in aufgabe.lernziele))
        elif aufgabe.leistungsziele:
            teile.append("BiVo: " + ", ".join(l.code for l in aufgabe.leistungsziele))
        if teile:
            out.append(Paragraph(html.escape(" · ".join(teile)), st["meta"]))
            out.append(Spacer(1, 3))
    return out


def _aufgaben_story(st, aufgaben, bild_pfad, mit_meta=True):
    story = []
    for nr, a in enumerate(aufgaben, 1):
        teile = _aufgaben_kopf(st, nr, a, mit_meta) + markup_flowables(a.text, st)
        bild = _bild_flowable(bild_pfad(a)) if a.bild else None
        if bild:
            teile += [Spacer(1, 4), bild]
        if a.antwortformat != "keins" and a.antwortraum_cm:
            teile += [Spacer(1, 6), Antwortfeld(a.antwortraum_cm, a.antwortformat)]
        # Aufgabe möglichst nicht über einen Seitenumbruch verteilen
        story.append(KeepTogether(teile))
        story.append(Spacer(1, 16))
    return story


def _loesungs_story(st, aufgaben, bild_pfad):
    story = []
    for nr, a in enumerate(aufgaben, 1):
        teile = _aufgaben_kopf(st, nr, a, True)
        aufgabe_txt = markup_flowables(a.text, st)
        teile += aufgabe_txt
        bild = _bild_flowable(bild_pfad(a), max_h=6 * cm) if a.bild else None
        if bild:
            teile.append(bild)
        loes = markup_flowables(a.loesung or "(keine Musterlösung hinterlegt)", st, CONTENT_W - 0.6 * cm)
        box = Table([[Paragraph("<b>Lösung</b>", st["klein"])]] + [[f] for f in loes], colWidths=[CONTENT_W])
        box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LOESUNG_BG),
                                 ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#7aa87a")),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 1),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        story.append(CondPageBreak(4 * cm))
        story += teile + [Spacer(1, 4), box, Spacer(1, 16)]
    return story


# ---------------------------------------------------------------- Öffentliche Funktionen

APP_NAME = "LaborÜben · Laborant/in EFZ Biologie"


def uebungsblatt_pdf(blatt, bild_pfad, loesung=False):
    st = _styles()
    buf = io.BytesIO()
    aufgaben = [ba.aufgabe for ba in blatt.aufgaben]
    titel = ("Lösungen: " if loesung else "") + blatt.titel
    doc = _doc(buf, titel)
    lern = blatt.lernende
    felder = [("Name", lern.anzeigename), ("Klasse", lern.klasse.name if lern.klasse else ""),
              ("Datum", blatt.erstellt_am.strftime("%d.%m.%Y")),
              ("Punkte", f"_____ / {blatt.max_punkte:g}")]
    story = _kopfblock(st, titel, felder, html.escape(blatt.auswahl or ""))
    if loesung:
        story += _loesungs_story(st, aufgaben, bild_pfad)
    else:
        story.append(Paragraph(
            "Löse die Aufgaben direkt auf diesem Blatt. Fotografiere danach jede Seite gut lesbar "
            "(gerade, ohne Schatten) und lade die Fotos in der App beim Übungsblatt "
            f"<b>{blatt.code}</b> hoch.", st["klein"]))
        story.append(Spacer(1, 12))
        story += _aufgaben_story(st, aufgaben, bild_pfad)
    doc.build(story, canvasmaker=_seitenrahmen_factory(APP_NAME, blatt.code + (" · LÖSUNG" if loesung else "")))
    return buf.getvalue()


def pruefung_pdf(pruefung, bild_pfad, loesung=False):
    st = _styles()
    buf = io.BytesIO()
    aufgaben = [pa.aufgabe for pa in pruefung.aufgaben]
    titel = ("Lösungen: " if loesung else "") + pruefung.titel
    doc = _doc(buf, titel)
    felder = [("Name", ""), ("Klasse", pruefung.klasse.name if pruefung.klasse else ""),
              ("Datum", pruefung.datum or ""), ("Punkte", f"_____ / {pruefung.max_punkte:g}"),
              ("Dauer", f"{pruefung.dauer_min} min" if pruefung.dauer_min else ""), ("Note", "")]
    story = _kopfblock(st, titel, felder)
    if pruefung.hinweise:
        story += markup_flowables(pruefung.hinweise, st) + [Spacer(1, 10)]
    if loesung:
        story += _loesungs_story(st, aufgaben, bild_pfad)
    else:
        story += _aufgaben_story(st, aufgaben, bild_pfad, mit_meta=False)
    code = f"PR-{pruefung.id:05d}"
    doc.build(story, canvasmaker=_seitenrahmen_factory(APP_NAME, code + (" · LÖSUNG" if loesung else "")))
    return buf.getvalue()


def aufgabe_vorschau_pdf(aufgabe, bild_pfad):
    st = _styles()
    buf = io.BytesIO()
    doc = _doc(buf, aufgabe.titel)
    story = [Paragraph("Vorschau Aufgabe", st["titel"]), Spacer(1, 8)]
    story += _aufgaben_story(st, [aufgabe], bild_pfad)
    story += [PageBreak()] + _loesungs_story(st, [aufgabe], bild_pfad)
    doc.build(story, canvasmaker=_seitenrahmen_factory(APP_NAME, f"Aufgabe #{aufgabe.id}"))
    return buf.getvalue()


def rueckmeldung_pdf(blatt, seiten_pfade):
    """Korrigierte Seiten (Bilder mit Annotationen) + Übersicht der Punkte und Kommentare."""
    st = _styles()
    buf = io.BytesIO()
    doc = _doc(buf, f"Rückmeldung {blatt.code}")
    lern = blatt.lernende
    erreicht = blatt.erreichte_punkte
    felder = [("Name", lern.anzeigename), ("Blatt", blatt.code),
              ("Korrigiert", blatt.korrigiert_am.strftime("%d.%m.%Y") if blatt.korrigiert_am else ""),
              ("Punkte", f"{erreicht:g} / {blatt.max_punkte:g}" if erreicht is not None else "–")]
    story = _kopfblock(st, f"Rückmeldung: {blatt.titel}", felder)
    data = [[Paragraph("<b>Nr.</b>", st["zelle"]), Paragraph("<b>Aufgabe</b>", st["zelle"]),
             Paragraph("<b>Punkte</b>", st["zelle"]), Paragraph("<b>Kommentar</b>", st["zelle"])]]
    for ba in blatt.aufgaben:
        p = f"{ba.punkte_erreicht:g}" if ba.punkte_erreicht is not None else "–"
        data.append([Paragraph(str(ba.position), st["zelle"]), Paragraph(html.escape(ba.aufgabe.titel), st["zelle"]),
                     Paragraph(f"{p} / {ba.aufgabe.punkte:g}", st["zelle"]),
                     Paragraph(html.escape(ba.kommentar or "").replace("\n", "<br/>"), st["zelle"])])
    t = Table(data, colWidths=[1.1 * cm, 5.4 * cm, 2.2 * cm, CONTENT_W - 8.7 * cm], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, HELLGRAU), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee"))]))
    story.append(t)
    if blatt.gesamtkommentar:
        story += [Spacer(1, 12), Paragraph("<b>Kommentar der Lehrperson</b>", st["text"])]
        story += markup_flowables(blatt.gesamtkommentar, st)
    for pfad in seiten_pfade:
        bild = _bild_flowable(pfad, CONTENT_W, PAGE_H - 4.0 * cm)
        if bild:
            bild.hAlign = "CENTER"
            story += [PageBreak(), bild]
    doc.build(story, canvasmaker=_seitenrahmen_factory(APP_NAME, blatt.code + " · RÜCKMELDUNG"))
    return buf.getvalue()


def heute():
    return date.today().strftime("%d.%m.%Y")
