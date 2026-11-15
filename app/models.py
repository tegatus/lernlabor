"""Datenmodell der Übungsplattform.

Taxonomie:
  Bereich (a, b, e, …) → Handlungskompetenz (a.1) → Leistungsziel (a.1.1, K-Stufe)   [Bildungsverordnung]
  Thema (qPCR, Neubauer-Zählkammer, …) → Lernziel (konkret, "Ich kann …")  ↔ Leistungsziele
  Aufgabe ↔ Themen, Leistungsziele, Lernziele
"""
from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- Benutzer

class Klasse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    lp_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    lp = db.relationship("User", foreign_keys=[lp_id], backref="eigene_klassen")
    lernende = db.relationship("User", foreign_keys="User.klasse_id", back_populates="klasse",
                               order_by="User.anzeigename")


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    benutzername = db.Column(db.String(80), unique=True, nullable=False)
    anzeigename = db.Column(db.String(120), nullable=False)
    passwort_hash = db.Column(db.String(255), nullable=False)
    rolle = db.Column(db.String(20), nullable=False, default="lernende")  # "lp" | "lernende"
    klasse_id = db.Column(db.Integer, db.ForeignKey("klasse.id"))
    klasse = db.relationship("Klasse", foreign_keys=[klasse_id], back_populates="lernende")
    aktiv = db.Column(db.Boolean, default=True, nullable=False)

    def set_passwort(self, pw):
        self.passwort_hash = generate_password_hash(pw)

    def check_passwort(self, pw):
        return check_password_hash(self.passwort_hash, pw)

    @property
    def ist_lp(self):
        return self.rolle == "lp"

    @property
    def is_active(self):
        return self.aktiv

    def betreut(self, lernende):
        """True, wenn diese LP die lernende Person (über eine Klasse) betreut."""
        return self.ist_lp and lernende.klasse is not None and lernende.klasse.lp_id == self.id


# ---------------------------------------------------------------- Bildungsverordnung

class Bereich(db.Model):
    code = db.Column(db.String(4), primary_key=True)  # "a"
    titel = db.Column(db.String(255), nullable=False)
    handlungskompetenzen = db.relationship("Handlungskompetenz", back_populates="bereich",
                                           order_by="Handlungskompetenz.sort")


class Handlungskompetenz(db.Model):
    code = db.Column(db.String(10), primary_key=True)  # "a.1"
    titel = db.Column(db.Text, nullable=False)
    sort = db.Column(db.Integer, default=0)
    bereich_code = db.Column(db.String(4), db.ForeignKey("bereich.code"), nullable=False)
    bereich = db.relationship("Bereich", back_populates="handlungskompetenzen")
    leistungsziele = db.relationship("Leistungsziel", back_populates="handlungskompetenz",
                                     order_by="Leistungsziel.sort")


class Leistungsziel(db.Model):
    """Kompetenzziel gemäss BiVo / Bildungsplan, z. B. a.1.1 (K2)."""
    code = db.Column(db.String(12), primary_key=True)  # "a.1.1"
    text = db.Column(db.Text, nullable=False)
    k_stufe = db.Column(db.Integer)
    sort = db.Column(db.Integer, default=0)
    hk_code = db.Column(db.String(10), db.ForeignKey("handlungskompetenz.code"), nullable=False)
    handlungskompetenz = db.relationship("Handlungskompetenz", back_populates="leistungsziele")


# ---------------------------------------------------------------- Themen & Lernziele

class Thema(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    beschreibung = db.Column(db.Text, default="")
    lernziele = db.relationship("Lernziel", back_populates="thema", order_by="[Lernziel.bereich, Lernziel.nummer]",
                                cascade="all, delete-orphan")


lernziel_leistungsziel = db.Table(
    "lernziel_leistungsziel",
    db.Column("lernziel_id", db.Integer, db.ForeignKey("lernziel.id"), primary_key=True),
    db.Column("leistungsziel_code", db.String(12), db.ForeignKey("leistungsziel.code"), primary_key=True),
)


class Lernziel(db.Model):
    """Konkretes Lernziel ("Ich kann …"), basiert auf einem oder mehreren Leistungszielen."""
    id = db.Column(db.Integer, primary_key=True)
    thema_id = db.Column(db.Integer, db.ForeignKey("thema.id"), nullable=False)
    thema = db.relationship("Thema", back_populates="lernziele")
    bereich = db.Column(db.String(4), nullable=False)  # "a"
    nummer = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    k_stufe = db.Column(db.Integer)
    leistungsziele = db.relationship("Leistungsziel", secondary=lernziel_leistungsziel,
                                     order_by="Leistungsziel.sort")

    @property
    def kuerzel(self):
        return f"{self.bereich}{self.nummer}"

    @property
    def label(self):
        return f"{self.thema.name} {self.kuerzel}"


# ---------------------------------------------------------------- Aufgaben

aufgabe_thema = db.Table(
    "aufgabe_thema",
    db.Column("aufgabe_id", db.Integer, db.ForeignKey("aufgabe.id"), primary_key=True),
    db.Column("thema_id", db.Integer, db.ForeignKey("thema.id"), primary_key=True),
)
aufgabe_leistungsziel = db.Table(
    "aufgabe_leistungsziel",
    db.Column("aufgabe_id", db.Integer, db.ForeignKey("aufgabe.id"), primary_key=True),
    db.Column("leistungsziel_code", db.String(12), db.ForeignKey("leistungsziel.code"), primary_key=True),
)
aufgabe_lernziel = db.Table(
    "aufgabe_lernziel",
    db.Column("aufgabe_id", db.Integer, db.ForeignKey("aufgabe.id"), primary_key=True),
    db.Column("lernziel_id", db.Integer, db.ForeignKey("lernziel.id"), primary_key=True),
)

ANTWORTFORMATE = {"linien": "Linien", "karo": "Karo (Rechnungen)", "leer": "Leeres Feld", "keins": "Kein Antwortfeld"}
VERWENDUNGEN = {"beide": "Übung & Prüfung", "uebung": "Nur Übung", "pruefung": "Nur Prüfung (geheim)"}


class Aufgabe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titel = db.Column(db.String(200), nullable=False)
    text = db.Column(db.Text, nullable=False)       # einfache Auszeichnung, siehe pdfgen.markup
    loesung = db.Column(db.Text, nullable=False, default="")
    punkte = db.Column(db.Float, nullable=False, default=2)
    k_stufe = db.Column(db.Integer)
    schwierigkeit = db.Column(db.Integer, default=2)  # 1 leicht – 3 schwer
    antwortformat = db.Column(db.String(10), default="linien")
    antwortraum_cm = db.Column(db.Float, default=5.0)
    verwendung = db.Column(db.String(10), default="beide")
    bild = db.Column(db.String(255))  # Dateiname in uploads/aufgabenbilder
    aktiv = db.Column(db.Boolean, default=True, nullable=False)
    erstellt_am = db.Column(db.DateTime, default=now)
    geaendert_am = db.Column(db.DateTime, default=now, onupdate=now)

    themen = db.relationship("Thema", secondary=aufgabe_thema, order_by="Thema.name")
    leistungsziele = db.relationship("Leistungsziel", secondary=aufgabe_leistungsziel, order_by="Leistungsziel.sort")
    lernziele = db.relationship("Lernziel", secondary=aufgabe_lernziel)

    def to_dict(self):
        return {
            "titel": self.titel, "text": self.text, "loesung": self.loesung, "punkte": self.punkte,
            "k_stufe": self.k_stufe, "schwierigkeit": self.schwierigkeit, "antwortformat": self.antwortformat,
            "antwortraum_cm": self.antwortraum_cm, "verwendung": self.verwendung,
            "themen": [t.name for t in self.themen],
            "leistungsziele": [l.code for l in self.leistungsziele],
            "lernziele": [f"{l.thema.name}|{l.kuerzel}" for l in self.lernziele],
        }


# ---------------------------------------------------------------- Übungsblätter der Lernenden

class Uebungsblatt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lernende_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    lernende = db.relationship("User", backref=db.backref("uebungsblaetter", order_by="Uebungsblatt.erstellt_am.desc()"))
    titel = db.Column(db.String(200), nullable=False)
    auswahl = db.Column(db.Text, default="")  # lesbare Beschreibung der Filter
    erstellt_am = db.Column(db.DateTime, default=now)
    status = db.Column(db.String(20), default="offen")  # offen | eingereicht | korrigiert
    loesung_freigegeben = db.Column(db.Boolean, default=False)
    gesamtkommentar = db.Column(db.Text, default="")
    korrigiert_am = db.Column(db.DateTime)
    aufgaben = db.relationship("BlattAufgabe", order_by="BlattAufgabe.position", cascade="all, delete-orphan",
                               back_populates="blatt")
    abgaben = db.relationship("Abgabe", order_by="Abgabe.hochgeladen_am", cascade="all, delete-orphan",
                              back_populates="blatt")

    @property
    def code(self):
        return f"UE-{self.id:05d}"

    @property
    def max_punkte(self):
        return sum(a.aufgabe.punkte for a in self.aufgaben)

    @property
    def erreichte_punkte(self):
        werte = [a.punkte_erreicht for a in self.aufgaben if a.punkte_erreicht is not None]
        return sum(werte) if werte else None

    @property
    def letzte_abgabe(self):
        return self.abgaben[-1] if self.abgaben else None


class BlattAufgabe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    blatt_id = db.Column(db.Integer, db.ForeignKey("uebungsblatt.id"), nullable=False)
    blatt = db.relationship("Uebungsblatt", back_populates="aufgaben")
    aufgabe_id = db.Column(db.Integer, db.ForeignKey("aufgabe.id"), nullable=False)
    aufgabe = db.relationship("Aufgabe")
    position = db.Column(db.Integer, nullable=False)
    punkte_erreicht = db.Column(db.Float)
    kommentar = db.Column(db.Text, default="")


class Abgabe(db.Model):
    """Eine Einreichung (Fotos/Scan) zu einem Übungsblatt."""
    id = db.Column(db.Integer, primary_key=True)
    blatt_id = db.Column(db.Integer, db.ForeignKey("uebungsblatt.id"), nullable=False)
    blatt = db.relationship("Uebungsblatt", back_populates="abgaben")
    hochgeladen_am = db.Column(db.DateTime, default=now)
    seiten = db.relationship("AbgabeSeite", order_by="AbgabeSeite.nr", cascade="all, delete-orphan",
                             back_populates="abgabe")


class AbgabeSeite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    abgabe_id = db.Column(db.Integer, db.ForeignKey("abgabe.id"), nullable=False)
    abgabe = db.relationship("Abgabe", back_populates="seiten")
    nr = db.Column(db.Integer, nullable=False)
    bild = db.Column(db.String(255), nullable=False)            # Originalfoto (normalisiert)
    annotationen = db.Column(db.Text)                           # JSON (Vektordaten, wieder editierbar)
    bild_korrigiert = db.Column(db.String(255))                 # Foto mit eingebrannten Korrekturen


# ---------------------------------------------------------------- Prüfungen

class Pruefung(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titel = db.Column(db.String(200), nullable=False)
    lp_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    lp = db.relationship("User")
    klasse_id = db.Column(db.Integer, db.ForeignKey("klasse.id"))
    klasse = db.relationship("Klasse")
    datum = db.Column(db.String(40), default="")
    dauer_min = db.Column(db.Integer)
    hinweise = db.Column(db.Text, default="")
    parameter = db.Column(db.Text, default="{}")  # JSON der Generator-Parameter
    erstellt_am = db.Column(db.DateTime, default=now)
    aufgaben = db.relationship("PruefungAufgabe", order_by="PruefungAufgabe.position",
                               cascade="all, delete-orphan", back_populates="pruefung")

    @property
    def max_punkte(self):
        return sum(a.aufgabe.punkte for a in self.aufgaben)


class PruefungAufgabe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pruefung_id = db.Column(db.Integer, db.ForeignKey("pruefung.id"), nullable=False)
    pruefung = db.relationship("Pruefung", back_populates="aufgaben")
    aufgabe_id = db.Column(db.Integer, db.ForeignKey("aufgabe.id"), nullable=False)
    aufgabe = db.relationship("Aufgabe")
    position = db.Column(db.Integer, nullable=False)
