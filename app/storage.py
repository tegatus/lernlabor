"""Dateiablage (Fotos, Aufgabenbilder, PDF-Schnappschüsse) im Upload-Verzeichnis."""
import io
import os
import uuid

from flask import current_app
from PIL import Image, ImageOps

MAX_KANTE = 2200  # px – genug für gut lesbare Handschrift, klein genug für schnelle Korrektur
ERLAUBTE_BILDER = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic"}


def pfad(*teile):
    p = os.path.join(current_app.config["UPLOAD_DIR"], *teile)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def relativ(*teile):
    return "/".join(teile)


def absolut(rel):
    """Sicherer absoluter Pfad zu einer relativen Ablage-Angabe."""
    base = os.path.realpath(current_app.config["UPLOAD_DIR"])
    p = os.path.realpath(os.path.join(base, rel))
    if not p.startswith(base + os.sep):
        raise ValueError("Ungültiger Pfad")
    return p


def speichere_bytes(rel, daten):
    with open(pfad(rel), "wb") as f:
        f.write(daten)
    return rel


def _normalisiere(im):
    im = ImageOps.exif_transpose(im)  # Handyfotos richtig drehen
    if im.mode not in ("RGB", "L"):
        bg = Image.new("RGB", im.size, "white")
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
    im.thumbnail((MAX_KANTE, MAX_KANTE))
    return im.convert("RGB")


def upload_zu_seitenbildern(datei_storage):
    """Nimmt ein hochgeladenes Foto oder PDF entgegen und gibt eine Liste von PIL-Bildern (eine pro Seite) zurück."""
    name = (datei_storage.filename or "").lower()
    daten = datei_storage.read()
    if name.endswith(".pdf") or daten[:4] == b"%PDF":
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(daten)
        bilder = []
        for i in range(len(doc)):
            seite = doc[i]
            scale = min(MAX_KANTE / max(seite.get_size()), 3.0)
            bilder.append(_normalisiere(seite.render(scale=scale).to_pil()))
        return bilder
    ext = os.path.splitext(name)[1]
    if ext == ".heic":
        try:
            import pillow_heif  # optional
            pillow_heif.register_heif_opener()
        except ImportError:
            raise ValueError("HEIC-Fotos werden nicht unterstützt. Bitte am Handy 'Kompatibel/JPEG' wählen.")
    try:
        im = Image.open(io.BytesIO(daten))
        im.load()
    except Exception:
        raise ValueError(f"Die Datei '{datei_storage.filename}' ist kein lesbares Bild oder PDF.")
    return [_normalisiere(im)]


def speichere_bild(im, *ordner):
    rel = relativ(*ordner, f"{uuid.uuid4().hex}.jpg")
    im.save(pfad(rel), "JPEG", quality=85, optimize=True)
    return rel
