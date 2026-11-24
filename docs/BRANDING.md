# Branding & Site-Icons (gilt für alle N8schicht-Repositories)

Jede N8schicht-Weboberfläche bekommt das komplette Icon-Set. Nur ein Favicon reicht nicht: iOS, Android, Windows und Link-Vorschauen nutzen jeweils eigene Dateien.

| Datei | Zweck |
|---|---|
| `n8crosslink-icon.svg` | Logo (Nachthimmel-Badge, Mond, Antenne, „N8“, Pill) – Kopfzeile, README |
| `n8crosslink-favicon.svg` | vereinfachtes Favicon (Mond + „N8“), damit es auch bei 16/32 px lesbar bleibt |
| `icons/favicon.ico` | 16/32/48 px, wird von Browsern unter `/favicon.ico` abgefragt |
| `icons/favicon-16.png`, `favicon-32.png` | PNG-Favicons |
| `icons/apple-touch-icon.png` | 180 px randlos ohne Transparenz (iOS-Homescreen), auch unter `/apple-touch-icon.png` |
| `icons/icon-192.png`, `icon-512.png` | PWA/Android |
| `icons/icon-maskable-512.png` | Android „maskable“ (Logo in der 80-%-Safe-Zone) |
| `icons/og-image.png` | 1200×630 Vorschau für Messenger/Social (Open Graph, Twitter Card) |
| `icons/site.webmanifest` | Web-App-Manifest (Name, Farben, Icons), unter `/site.webmanifest` |

Farben: Hintergrund/Theme `#070b17`, Badge `#0c1230`, Akzent `#5ac8fa`, Mond `#ffd60a → #ff9f0a`.

## Erzeugen

```bash
sudo apt install librsvg2-bin && pip install pillow
python3 tools/make_icons.py <logo.svg> <zielordner> "<Titel>" "<Untertitel>" [favicon.svg]
# hier:
python3 tools/make_icons.py n8crosslink/web/static/n8crosslink-icon.svg n8crosslink/web/static/icons \
        "N8 Crosslink" "FRN · DMR · Zello Bridge" n8crosslink/web/static/n8crosslink-favicon.svg
```

Das Skript lässt sich unverändert in den anderen Repos nutzen (DMR Die N8schicht, Auf der Nachtschicht, N8-HotSpot …).
