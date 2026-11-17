# Antoti – Releases

Hier liegen die Installationsdateien der neuesten Version von **Antoti** („Anything to Ticket“) und ihr signiertes Manifest (`antoti-release.json`). Ältere Releases löscht der Workflow „Alte Releases löschen“, sobald ein neues erscheint.

- **Installieren:** Unter [Releases](../../releases/latest) die Datei für das eigene System laden: `Antoti-Setup-<Version>.exe` für Windows 10 oder 11 (64 Bit), `Antoti-<Version>-macos-arm64.dmg` für einen Mac mit Apple-Chip, `Antoti-<Version>-linux-x86_64.tar.gz` für Linux (darin `./install.sh`).
- **Updates:** Ein installiertes Antoti sucht hier selbst nach neuen Versionen. Es nimmt eine Datei nur an, wenn das Manifest mit dem Schlüssel des Herstellers signiert ist und Größe und SHA-256 der Datei dazu passen.
- **Gebaut** werden die Dateien hier mit dem Workflow „Installer bauen“ auf Rechnern von GitHub, je System auf seinem eigenen. Signiert wird das Manifest beim Hersteller, nicht hier.
- **Quellcode und Fehlerberichte:** Dieses Repository enthält nur die Veröffentlichungen. Fragen und Fehler bitte per E-Mail an den Hersteller.

Hersteller: Altmann Digital Studio, Julian Dominic Altmann · https://altmann-digital-studio.de
