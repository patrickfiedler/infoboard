# Projektideen & Roadmap – Infoboard

Diese Datei sammelt Ideen, Erweiterungswünsche und Konzepte für die Weiterentwicklung von Infoboard, bevor sie umgesetzt werden.

---

## 💡 Offene Ideen

- [ ] **Standard- bzw. Fallback-Anzeige-Inhalte (Thüringer Design Handbuch)**  
  Standard- bzw. Fallback-Inhalte gemäß dem offiziellen Thüringer Design Handbuch erstellen und als Standardbespielung hinzufügen.

- [ ] **Ticker-Editor implementieren**  
  Einen eigenen Editor in der Verwaltungsoberfläche schaffen, um Lauftexte / Ticker-Meldungen direkt im Browser zu erstellen und zu bearbeiten (ohne dafür PDFs oder externe Webseiten anlegen zu müssen).

- [ ] **Layouts um einen Tickerbalken unten ergänzen**  
  Die 2- und 3-Spalten-Ansicht (bzw. grundsätzlich alle Layout-Ansichten) um einen optionalen oder integrierten Tickerbalken am unteren Bildschirmrand erweitern.

---

## 🗓️ Als Nächstes geplant

*(Hier können Ideen aus der Liste oben aufgenommen werden, sobald sie konkret ausgearbeitet und umgesetzt werden sollen.)*

---

## ✅ Bereits umgesetzt

- [x] Einstellungsbereich für Displays hinter einem Einstellungs-Button ein- und ausklappbar gemacht (`templates/admin.html`)
- [x] Bereich „Neues Display hinzufügen“ hinter einem Button verborgen (`templates/admin.html`)
- [x] Größe der Render-Voransicht pro Display verdoppelt (`240 × 136 px`)
- [x] Normale Vollbild-Playlist bei aktivem Mehr-Zonen-Layout in der Admin-Oberfläche ausgeblendet und Rückkehr zum Vollbild im Backend abgesichert (`app.py`, `templates/admin.html`)
- [x] Mehrbenutzer-System mit eigenen Medienbibliotheken, gemeinsamen Playlists, Zugriff pro Display oder Zone und Wochentagen pro Playlist-Eintrag (`models.py`, `app.py`, `templates/admin.html`)
