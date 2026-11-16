# LernLabor auf einem Ubuntu-Server installieren

Für Ubuntu 26.04 LTS (auch 24.04) mit PostgreSQL, Gunicorn und nginx. Dauer: ca. 10 Minuten.

## Was eingerichtet wird

| Teil | Wo | Bemerkung |
|---|---|---|
| Programmcode | `/opt/lernlabor` | gehört root, für die App nur lesbar |
| Daten (Uploads, PDFs) | `/var/lib/lernlabor` | gehört dem Dienstkonto `lernlabor` |
| Konfiguration | `/etc/lernlabor/lernlabor.env` | Secret Key, Datenbank, optional KI-Schlüssel; nur root/lernlabor lesbar |
| Datenbank | PostgreSQL, Datenbank `lernlabor` | Anmeldung über lokalen Socket – **es gibt kein Datenbank-Passwort** |
| App-Server | systemd-Dienst `lernlabor` (Gunicorn auf 127.0.0.1:8000) | gehärtet: darf nur in `/var/lib/lernlabor` schreiben |
| Webserver | nginx, HTTPS | ohne Domain mit selbstsigniertem Zertifikat, später Let's Encrypt |
| Sicherung | täglich 02:30 nach `/var/backups/lernlabor` | Datenbank + Dateien, 14 Tage aufbewahrt |

## Installation

Alle Befehle als Benutzer mit sudo-Rechten auf dem Server.

**1. Code holen**

```bash
sudo git clone https://github.com/tegatus/lernlabor.git /opt/lernlabor
```

**2. Installationsskript ausführen**

```bash
sudo /opt/lernlabor/deploy/install.sh
```

Optionen:
- `--ip 203.0.113.10` – öffentliche IP-Adresse für das Zertifikat angeben (sonst wird die erste Adresse des Servers verwendet)
- `--firewall` – aktiviert die Firewall `ufw` und lässt nur SSH, HTTP und HTTPS zu. Nur verwenden, wenn SSH über den
  Standardport 22 läuft und beim Hoster keine eigene Firewall vorgesehen ist.

Das Skript kann gefahrlos erneut ausgeführt werden; Daten, Schlüssel und Zertifikate bleiben erhalten.

**3. Erstes Lehrpersonen-Konto anlegen** (das Passwort wird verdeckt abgefragt)

```bash
sudo lernlabor-flask create-lp vorname.name "Vorname Name"
```

**4. Im Browser öffnen:** `https://<IP-Adresse des Servers>`

Ohne Domain verwendet der Server ein selbstsigniertes Zertifikat. Der Browser zeigt deshalb einmal eine Warnung
(«Verbindung nicht privat») – die Verbindung ist trotzdem verschlüsselt. Über «Erweitert → Weiter» gelangt man zur App.
**Empfehlung:** echte Daten von Lernenden erst erfassen, wenn die Domain mit gültigem Zertifikat eingerichtet ist.

## Domain einrichten (später)

1. Beim Domain-Anbieter einen DNS-Eintrag (Typ A, bei IPv6 zusätzlich AAAA) auf die IP-Adresse des Servers setzen.
2. Warten, bis der Eintrag aktiv ist (`ping lernlabor.example.ch` zeigt die Server-IP).
3. Zertifikat holen – erneuert sich danach automatisch:

```bash
sudo /opt/lernlabor/deploy/domain.sh lernlabor.example.ch it@schule.ch
```

## Aktualisieren

Erstellt zuerst eine Sicherung, holt den neuesten Stand von GitHub, aktualisiert die Pakete und startet neu.
Neue Tabellen und Spalten werden beim Start automatisch ergänzt.

```bash
sudo /opt/lernlabor/deploy/update.sh
```

## KI-Assistent einschalten (optional)

In `/etc/lernlabor/lernlabor.env` die Zeile `#ANTHROPIC_API_KEY=` durch `ANTHROPIC_API_KEY=<Schlüssel>` ersetzen
(Schlüssel aus der Claude Console, dort auch ein Ausgabenlimit setzen), dann:

```bash
sudo systemctl restart lernlabor
```

## Sicherungen

- Täglich um 02:30 (verpasste Läufe werden nachgeholt): `/var/backups/lernlabor/datenbank_<Datum>.dump` und
  `dateien_<Datum>.tar.gz`. Manuell: `sudo lernlabor-backup`
- **Wichtig:** Sicherungen auf dem gleichen Server schützen nicht vor einem Serverausfall. Den Ordner regelmässig
  an einen anderen Ort kopieren (z. B. Schul-NAS, verschlüsselt).

### Sicherung zurückspielen

```bash
sudo systemctl stop lernlabor
```
```bash
sudo -u postgres dropdb lernlabor && sudo -u postgres createdb -O lernlabor lernlabor
```
```bash
sudo cat /var/backups/lernlabor/datenbank_DATUM.dump | sudo -u postgres pg_restore -d lernlabor --no-owner --role=lernlabor
```
```bash
sudo tar -xzf /var/backups/lernlabor/dateien_DATUM.tar.gz -C /var/lib/lernlabor && sudo chown -R lernlabor:lernlabor /var/lib/lernlabor/dateien
```
```bash
sudo systemctl start lernlabor
```

(Die Sicherungsdateien sind nur für root lesbar; deshalb liest `sudo cat` die Datei und übergibt sie an `pg_restore`.)

## Fehlersuche

| Frage | Befehl |
|---|---|
| Läuft die App? | `systemctl status lernlabor` |
| Fehlermeldungen der App | `journalctl -u lernlabor -n 100` |
| nginx-Konfiguration prüfen | `sudo nginx -t` |
| Wann läuft die nächste Sicherung? | `systemctl list-timers lernlabor-backup.timer` |
| Passwort einer Lehrperson vergessen | `sudo lernlabor-flask create-lp neuer.name "Name"` (neues Konto) – Lernende setzt die Lehrperson in der App zurück |

## Arbeiten mit Claude Code auf dem Server

Wird die Installation mit Claude Code auf dem Server durchgeführt, läuft Claude Code als eigener Benutzer
(z. B. `simon_claude`) und **ohne** dauerhafte sudo-Rechte. Die Schritte 1–3 oben benötigen sudo: entweder führt sie
eine Administratorin selbst aus, oder der Benutzer erhält vorübergehend sudo-Rechte, die danach wieder entzogen werden:

```bash
sudo deluser simon_claude sudo
```

Passwörter werden nie im Chat weitergegeben; sudo fragt sie im eigenen Terminal ab.
