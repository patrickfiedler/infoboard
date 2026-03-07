# Infoboard Installation als systemd Service

## Voraussetzungen

1. Python 3 und pip installiert
2. Alle Abhängigkeiten installiert: `pip install -r requirements.txt`
3. Konfiguration erstellt: `config.json` mit Admin-Passwort

## Installation

### 1. Systemd Service-Datei anpassen

Öffnen Sie `infoboard.service` und passen Sie folgende Werte an:

- **User**: Ersetzen Sie `patrick` mit Ihrem Benutzernamen
- **Group**: Ersetzen Sie `patrick` mit Ihrer Gruppe
- **WorkingDirectory**: Passen Sie den Pfad an, falls Ihr Projekt woanders liegt
- **ExecStart**: Passen Sie den Pfad zur `app.py` an

### 2. Service-Datei nach /etc/systemd/system kopieren

```bash
sudo cp infoboard.service /etc/systemd/system/
```

### 3. Systemd neu laden

```bash
sudo systemctl daemon-reload
```

### 4. Service aktivieren (automatischer Start beim Booten)

```bash
sudo systemctl enable infoboard
```

### 5. Service starten

```bash
sudo systemctl start infoboard
```

## Verwaltung des Service

### Status überprüfen

```bash
sudo systemctl status infoboard
```

### Logs anzeigen

```bash
# Alle Logs
sudo journalctl -u infoboard

# Logs in Echtzeit verfolgen
sudo journalctl -u infoboard -f

# Nur die letzten 50 Zeilen
sudo journalctl -u infoboard -n 50
```

### Service neu starten

```bash
sudo systemctl restart infoboard
```

### Service stoppen

```bash
sudo systemctl stop infoboard
```

### Service deaktivieren (kein automatischer Start)

```bash
sudo systemctl disable infoboard
```

## Automatischer Neustart

Der Service ist so konfiguriert, dass er:
- **Automatisch neu startet**, wenn die Anwendung abstürzt (`Restart=always`)
- **10 Sekunden wartet** vor dem Neustart (`RestartSec=10`)
- **Beim Systemstart automatisch startet**, wenn aktiviert (`WantedBy=multi-user.target`)

## Fehlerbehebung

### Service startet nicht

1. Überprüfen Sie die Logs:
   ```bash
   sudo journalctl -u infoboard -n 50
   ```

2. Stellen Sie sicher, dass:
   - Der Pfad in `WorkingDirectory` korrekt ist
   - Der Pfad in `ExecStart` korrekt ist
   - Der Benutzer Leserechte auf die Dateien hat
   - Die `config.json` existiert
   - Alle Python-Abhängigkeiten installiert sind

3. Testen Sie die Anwendung manuell:
   ```bash
   cd /mnt/Speicherplatz/Nextcloud/Dokumente/coding/infoboard
   python3 app.py
   ```

### Berechtigungsprobleme

Stellen Sie sicher, dass der Benutzer Schreibrechte hat:
```bash
sudo chown -R patrick:patrick /mnt/Speicherplatz/Nextcloud/Dokumente/coding/infoboard
```

### Port bereits belegt

Wenn Port 8080 bereits verwendet wird, ändern Sie den Port in `config.json`:
```json
{
  "port": 8081
}
```

Dann Service neu starten:
```bash
sudo systemctl restart infoboard
```

## Zugriff auf die Anwendung

Nach dem Start ist die Anwendung erreichbar unter:
- **Anzeige**: http://localhost:8080/display
- **Admin**: http://localhost:8080/admin

Falls der Server über das Netzwerk erreichbar sein soll, verwenden Sie die IP-Adresse:
- http://192.168.x.x:8080/display
- http://192.168.x.x:8080/admin
