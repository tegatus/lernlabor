#!/usr/bin/env bash
# LernLabor aktualisieren: neuesten Stand holen, Abhängigkeiten aktualisieren, Dienst neu starten.
#   sudo /opt/lernlabor/deploy/update.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Bitte mit sudo ausführen." >&2; exit 1; }
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dienst() {
  if [[ -d /run/systemd/system ]]; then systemctl "$@"; else echo "   (systemd nicht aktiv – übersprungen: systemctl $*)"; fi
}
cd "$APP_DIR"
echo "==> Sicherung vor dem Update"
/usr/local/sbin/lernlabor-backup
echo "==> Code aktualisieren"
git pull --ff-only
echo "==> Abhängigkeiten"
.venv/bin/pip install -q -r deploy/requirements-server.txt
install -m 700 deploy/backup.sh /usr/local/sbin/lernlabor-backup
echo "==> Dienst neu starten (neue Tabellen/Spalten werden beim Start automatisch ergänzt)"
dienst restart lernlabor
sleep 3
if curl -fsk -o /dev/null https://127.0.0.1/login; then
  echo "LernLabor läuft. Version: $(git log -1 --format='%h %s')"
else
  echo "Achtung: die Anmeldeseite antwortet nicht. Protokoll: journalctl -u lernlabor -n 50" >&2
  exit 1
fi
