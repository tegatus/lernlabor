"""Die einfache Aufgaben-Auszeichnung (siehe pdfgen) als HTML für die Weboberfläche."""
import html
import re

from markupsafe import Markup


def tabellen_abtrennen(text):
    """Leerzeile zwischen Tabellen- und Textzeilen einfügen, damit Tabellen eigene Blöcke bilden."""
    text = (text or "").replace("\r\n", "\n")
    text = re.sub(r"(?m)^([ \t]*[^|\s].*)\n(?=[ \t]*\|)", r"\1\n\n", text)
    return re.sub(r"(?m)^([ \t]*\|.*)\n(?=[ \t]*[^|\s])", r"\1\n\n", text)


def _inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"_\{(.+?)\}", r"<sub>\1</sub>", t)
    t = re.sub(r"\^\{(.+?)\}", r"<sup>\1</sup>", t)
    return t


def markup_html(text):
    out = []
    for block in re.split(r"\n\s*\n", tabellen_abtrennen(text).strip()):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        if all(l.startswith("|") for l in lines):
            rows = [[z.strip() for z in l.strip("|").split("|")] for l in lines]
            rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", z) for z in r if z)]
            body = "".join("<tr>" + "".join(f"<{'th' if i == 0 else 'td'}>{_inline(z)}</{'th' if i == 0 else 'td'}>"
                                            for z in r) + "</tr>" for i, r in enumerate(rows))
            out.append(f'<table class="mini">{body}</table>')
            continue
        teile, liste = [], []
        for l in lines:
            if re.match(r"^[-•]\s+", l):
                liste.append(f"<li>{_inline(re.sub(r'^[-•]\s+', '', l))}</li>")
            else:
                if liste:
                    teile.append("<ul>" + "".join(liste) + "</ul>")
                    liste = []
                teile.append(_inline(l) + "<br>")
        if liste:
            teile.append("<ul>" + "".join(liste) + "</ul>")
        out.append("<p>" + "".join(teile).removesuffix("<br>") + "</p>")
    return Markup("".join(out))
