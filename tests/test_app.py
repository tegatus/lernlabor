import base64
import io
import json

import pytest
from PIL import Image
from pypdf import PdfReader

from app import create_app
from app.importers import parse_kompetenzen_xlsx, parse_lernziele
from app.models import Aufgabe, Lernziel, Thema, Uebungsblatt, User, db
from app.seed import seed_basisdaten, seed_demo
from app.selection import stelle_pruefung_zusammen


@pytest.fixture
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/t.sqlite",
                      "UPLOAD_DIR": str(tmp_path / "dateien"), "TESTING": True, "TESTING_NO_CSRF": True})
    with app.app_context():
        seed_basisdaten()
        seed_demo()
    yield app


def login(client, name, pw):
    return client.post("/login", data={"benutzername": name, "passwort": pw}, follow_redirects=True)


def pdf_text(daten):
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(daten)).pages)


def test_parser_auf_benutzerdateien():
    with open("app/seed_data/lernziele_molek1.txt", encoding="utf-8") as f:
        e = parse_lernziele(f.read())
    assert len(e) == 33
    assert sum(1 for x in e if x["bereich"] == "a") == 15
    assert e[13]["codes"] == ["a.4.1", "a.4.2"] and e[13]["k_stufe"] == 2
    b, h, l = parse_kompetenzen_xlsx("app/seed_data/Kompetenzen_BiVo.xlsx")
    assert [x["code"] for x in b] == ["a", "b", "e", "f", "g"]
    assert len(l) == 71 and l[0] == {"code": "a.1.1", "hk": "a.1", "text": "Sie erklären die Zielsetzung eines Laborauftrags.",
                                     "k_stufe": 2, "sort": 0}


def test_lernziele_mit_bivo_verknuepft(app):
    with app.app_context():
        lz = Lernziel.query.join(Thema).filter(Thema.name == "qPCR", Lernziel.bereich == "b", Lernziel.nummer == 16).one()
        assert [l.code for l in lz.leistungsziele] == ["b.5.3", "b.5.4"]
        # Aufgaben erben BiVo-Codes ihrer Lernziele
        a = Aufgabe.query.filter_by(titel="Master-Mix für eine qPCR-Platte").one()
        assert {"a.2.3", "b.1.3"} <= {l.code for l in a.leistungsziele}


def test_ganzer_ablauf_lernende_und_lp(app):
    c = app.test_client()
    assert "Meine Übungsblätter" in login(c, "lea", "lernen-2026").get_data(as_text=True)
    with app.app_context():
        qpcr = Thema.query.filter_by(name="qPCR").one().id
    r = c.post("/lernende/neu", data={"thema": qpcr, "bivo": "a.2.3", "anzahl": 3}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        blatt = Uebungsblatt.query.one()
        ids = [ba.aufgabe for ba in blatt.aufgaben]
        assert ids and all(a.verwendung != "pruefung" for a in ids)
        assert all("a.2.3" in [l.code for l in a.leistungsziele] for a in ids)
        bid = blatt.id
    pdf = c.get(f"/blatt/{bid}/aufgaben.pdf")
    assert pdf.status_code == 200 and "Aufgabe 1" in pdf_text(pdf.data)
    assert c.get(f"/blatt/{bid}/loesung.pdf").status_code == 403  # Lösung noch nicht freigegeben

    # Foto hochladen
    buf = io.BytesIO()
    Image.new("RGB", (800, 1100), "white").save(buf, "JPEG")
    buf.seek(0)
    r = c.post(f"/blatt/{bid}/hochladen", data={"dateien": (buf, "seite1.jpg")},
               content_type="multipart/form-data", follow_redirects=True)
    assert "1 Seite(n) hochgeladen" in r.get_data(as_text=True)

    # Andere Lernende dürfen nichts sehen
    c2 = app.test_client()
    login(c2, "noah", "lernen-2026")
    assert c2.get(f"/blatt/{bid}/aufgaben.pdf").status_code == 403

    # LP korrigiert
    lp = app.test_client()
    login(lp, "lp", "lp-demo-2026")
    assert "Zu korrigieren" in lp.get("/lp/").get_data(as_text=True)
    assert lp.get(f"/blatt/{bid}/loesung.pdf").status_code == 200
    with app.app_context():
        blatt = db.session.get(Uebungsblatt, bid)
        seite_id = blatt.abgaben[0].seiten[0].id
        aufg = [{"id": ba.id, "punkte": "2", "kommentar": "gut"} for ba in blatt.aufgaben]
    png = io.BytesIO()
    Image.new("RGB", (800, 1100), "pink").save(png, "PNG")
    data_url = "data:image/png;base64," + base64.b64encode(png.getvalue()).decode()
    r = lp.post(f"/lp/korrektur/{bid}", json={
        "aufgaben": aufg, "gesamtkommentar": "Weiter so!", "loesung_freigeben": True, "abschliessen": True,
        "seiten": [{"id": seite_id, "annotationen": [{"t": "haken", "x": 10, "y": 10, "farbe": "#f00"}], "bild": data_url}]})
    assert r.get_json()["status"] == "korrigiert"

    # Lernende sehen Rückmeldung + Lösung
    seite = c.get(f"/lernende").get_data(as_text=True)
    assert "korrigiert" in seite
    rm = c.get(f"/blatt/{bid}/rueckmeldung.pdf")
    assert rm.status_code == 200 and "Weiter so!" in pdf_text(rm.data)
    assert c.get(f"/blatt/{bid}/loesung.pdf").status_code == 200
    assert c.get(f"/seite/{seite_id}.jpg?korrigiert=1").status_code == 200


def test_pruefungsgenerator_deckt_lernziele_ab(app):
    with app.app_context():
        qpcr = Thema.query.filter_by(name="qPCR").one()
        ziele = [lz.id for lz in qpcr.lernziele if lz.kuerzel in ("a9", "b16", "a7")]
        res = stelle_pruefung_zusammen(themen_ids=[qpcr.id], lernziel_ids=ziele, ziel_punkte=20, seed=1)
        assert not res["nicht_abgedeckt"]
        assert res["punkte"] <= 20 * 1.15
        assert all(a.verwendung in ("pruefung", "beide") for a in res["aufgaben"])
        nur = stelle_pruefung_zusammen(themen_ids=[qpcr.id], nur_pruefungsaufgaben=True, ziel_punkte=50, seed=1)
        assert {a.verwendung for a in nur["aufgaben"]} == {"pruefung"}


def test_pruefung_ueber_web_und_pdf(app):
    lp = app.test_client()
    login(lp, "lp", "lp-demo-2026")
    with app.app_context():
        ids = [t.id for t in Thema.query]
        klasse = User.query.filter_by(benutzername="lp").one().eigene_klassen[0].id
    r = lp.post("/lp/pruefungen/neu", data={"titel": "Test-Prüfung", "thema": ids, "bivo": ["b.5.6"],
                                            "ziel_punkte": "25", "klasse_id": klasse, "ohne_geuebte": "1",
                                            "dauer_min": "45"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Test-Prüfung" in html and "Abdeckung der Ziele" in html
    pdf = lp.get("/lp/pruefungen/1/pruefung.pdf")
    text = pdf_text(pdf.data)
    assert "Test-Prüfung" in text and "Name" in text
    assert "Lösung" in pdf_text(lp.get("/lp/pruefungen/1/loesung.pdf").data)


def test_lernende_haben_keinen_lp_zugang(app):
    c = app.test_client()
    login(c, "lea", "lernen-2026")
    assert c.get("/lp/aufgaben").status_code == 403
    assert c.get("/lp/pruefungen/neu").status_code == 403


def test_aufgabe_anlegen_und_export(app):
    lp = app.test_client()
    login(lp, "lp", "lp-demo-2026")
    with app.app_context():
        lz = Lernziel.query.join(Thema).filter(Thema.name == "qPCR", Lernziel.bereich == "a", Lernziel.nummer == 13).one().id
    r = lp.post("/lp/aufgaben/neu", data={"titel": "Ökologie der Verbrauchsmaterialien", "text": "a) Nenne **zwei** Punkte.",
                                          "loesung": "Filterspitzen …", "punkte": "3", "k_stufe": "2", "lernziel": lz,
                                          "neues_thema": "Nachhaltigkeit", "antwortformat": "linien",
                                          "antwortraum_cm": "4", "verwendung": "beide", "aktiv": "1"},
                follow_redirects=True)
    assert "Aufgabe gespeichert" in r.get_data(as_text=True)
    daten = json.loads(lp.get("/lp/aufgaben/export.json").data)
    neu = [d for d in daten if d["titel"].startswith("Ökologie")][0]
    assert neu["leistungsziele"] == ["a.3.1"] and set(neu["themen"]) == {"Nachhaltigkeit"}


def test_csrf_schutz(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/c.sqlite", "UPLOAD_DIR": str(tmp_path / "d")})
    assert app.test_client().post("/login", data={"benutzername": "x", "passwort": "y"}).status_code == 400


# ---------------------------------------------------------------- Grafiken in Aufgaben

def _bild(farbe, groesse=(400, 300)):
    buf = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(buf, "PNG")
    buf.seek(0)
    return buf


def _anzahl_bilder(pdf_bytes):
    return sum(len(p.images) for p in PdfReader(io.BytesIO(pdf_bytes)).pages)


def test_mehrere_bilder_platziert_und_nur_loesung(app):
    from app.models import AufgabeBild
    lp = app.test_client()
    login(lp, "lp", "lp-demo-2026")
    basis = {"titel": "Gel auswerten", "punkte": "4", "k_stufe": "3", "antwortformat": "linien",
             "antwortraum_cm": "4", "verwendung": "beide", "aktiv": "1", "neues_thema": "Gelelektrophorese"}
    r = lp.post("/lp/aufgaben/neu", data={**basis, "text": "Schau dir das Gel an.", "loesung": "Siehe Bild.",
                                          "bilder_neu": [(_bild("red"), "gel.png"), (_bild("blue"), "marker.png")],
                                          "neu_groesse": "halb"},
                content_type="multipart/form-data", follow_redirects=True)
    assert "Aufgabe gespeichert" in r.get_data(as_text=True)
    with app.app_context():
        a = Aufgabe.query.filter_by(titel="Gel auswerten").one()
        assert [(b.nr, b.groesse) for b in a.bilder] == [(1, "halb"), (2, "halb")]
        aid, b1, b2 = a.id, a.bilder[0].id, a.bilder[1].id
    # drittes Bild nur für die Lösung, Bilder 1+2 nebeneinander, Bild 3 in der Lösung platziert, Tippfehler-Marker
    r = lp.post(f"/lp/aufgaben/{aid}", data={
        **basis, "text": "Schau dir das Gel an.\n[[bild:1]] [[bild:2|drittel]]\nWelche Bande ist das Produkt?\n[[bild:7]]",
        "loesung": "Bande bei 500 bp:\n[[bild:3]]", f"bild_{b1}_groesse": "halb", f"bild_{b1}_text": "Agarosegel 1 %",
        f"bild_{b2}_groesse": "halb", "bilder_neu": [(_bild("green"), "loesung.png")], "neu_loesung": "1"},
        content_type="multipart/form-data", follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "[[bild:7]] verweist auf ein Bild, das es nicht gibt" in html
    with app.app_context():
        a = db.session.get(Aufgabe, aid)
        assert [(b.nr, b.nur_loesung) for b in a.bilder] == [(1, False), (2, False), (3, True)]
        assert a.bilder[0].beschriftung == "Agarosegel 1 %"
        from app.lernende import bild_pfad
        from app import pdfgen
        from datetime import datetime
        with db.session.no_autoflush:
            blatt = Uebungsblatt(id=9999, lernende=User.query.filter_by(benutzername="lea").one(), titel="Gel",
                                 erstellt_am=datetime(2026, 11, 16))
            from app.models import BlattAufgabe
            blatt.aufgaben.append(BlattAufgabe(aufgabe=a, position=1))
            aufgabenblatt = pdfgen.uebungsblatt_pdf(blatt, bild_pfad)
            loesungsblatt = pdfgen.uebungsblatt_pdf(blatt, bild_pfad, loesung=True)
        db.session.rollback()
    assert _anzahl_bilder(aufgabenblatt) == 2          # Lösungsbild ist NICHT auf dem Aufgabenblatt
    assert _anzahl_bilder(loesungsblatt) == 3
    assert "Agarosegel 1 %" in pdf_text(aufgabenblatt)
    assert "[[bild" not in pdf_text(aufgabenblatt)

    # Bild löschen: Nummern der übrigen bleiben stabil
    lp.post(f"/lp/aufgaben/{aid}", data={**basis, "text": "x", "loesung": "y", f"bild_{b1}_loeschen": "1",
                                          f"bild_{b2}_groesse": "voll"}, content_type="multipart/form-data")
    with app.app_context():
        assert [b.nr for b in db.session.get(Aufgabe, aid).bilder] == [2, 3]
        bid = AufgabeBild.query.first().id
    # Lernende kommen nicht an die Bilddateien heran
    c = app.test_client()
    login(c, "lea", "lernen-2026")
    assert c.get(f"/lp/aufgabenbild/{bid}").status_code == 403
    assert lp.get(f"/lp/aufgabenbild/{bid}").status_code == 200


def test_bildzeile_skaliert_nebeneinander():
    from types import SimpleNamespace
    import tempfile, os
    from app.pdfgen import CONTENT_W, _bildzeile, _styles
    d = tempfile.mkdtemp()
    pfade = []
    for i, f in enumerate(["red", "blue", "green"]):
        p = os.path.join(d, f"{i}.png")
        Image.new("RGB", (800, 400), f).save(p)
        pfade.append(p)
    bilder = [SimpleNamespace(groesse="halb", beschriftung="", p=p) for p in pfade]
    t = _bildzeile([(b, None) for b in bilder], _styles(), CONTENT_W, lambda b: b.p)
    assert sum(t._colWidths) <= CONTENT_W + 0.01   # 3 × halb passt nicht → wird verkleinert
    t2 = _bildzeile([(bilder[0], "viertel")], _styles(), CONTENT_W, lambda b: b.p)
    assert abs(t2._colWidths[0] - CONTENT_W / 4) < 0.01


def test_altes_einzelbild_wird_migriert(app):
    from app.models import migriere_einzelbilder
    with app.app_context():
        a = Aufgabe.query.first()
        a.bild = "aufgabenbilder/alt.jpg"
        db.session.commit()
        migriere_einzelbilder()
        a = db.session.get(Aufgabe, a.id)
        assert a.bild is None and [(b.nr, b.datei) for b in a.bilder] == [(1, "aufgabenbilder/alt.jpg")]
