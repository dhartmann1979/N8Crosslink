# Umstieg von SvxLink (FRN↔DMR) und der alten Zello-Bridge

N8 Crosslink ersetzt beide Ketten durch einen Dienst:

```
vorher:  FRN ⇄ SvxLink(ModuleFrn) ⇄ Analog_Bridge ⇄ MMDVM_Bridge ⇄ HBlink4/FreeDMR
         Zello ⇄ ZelloBridge (Tinker Board)
nachher: FRN ⇄ N8 Crosslink ⇄ HBlink4/FreeDMR
                     ⇅
                   Zello
```

## Vorgehen

1. **Daten notieren** aus den alten Konfigurationen:
   * SvxLink `ModuleFrn.conf`: `SERVER`, `PORT`, `EMAIL_ADDRESS`, `DYN_PASSWORD`, `CALLSIGN_AND_USER`, `NET`, `CITY_CITY_PART`, `COUNTRY` → Installer Schritt 5.
   * `MMDVM_Bridge.ini` (Abschnitt `[DMR Network]`): `Address`, `Port`, `Password`, `Id` (→ Peer-ID), `Options` (→ RPTO) → Schritt 6.
   * `Analog_Bridge.ini`: `txTg`, `slot`, Vocoder (`[DV3000]` Adresse/Port bzw. md380-emu) → Schritt 6 und 8.
   * Zello-Bridge: Kanal, Benutzer, Passwort, Token/Key → Schritt 7.
2. **Installer starten.** In Schritt 9 erkennt er `svxlink`, `mmdvm_bridge`, `analog_bridge` und Dienste mit `zello` im Namen und fragt, ob sie gestoppt und deaktiviert werden sollen (`systemctl disable --now`). Rückgängig: `systemctl enable --now <dienst>`.
3. **Peer-ID am DMR-Server:** Läuft die alte MMDVM_Bridge noch mit derselben Peer-ID, verdrängen sich beide gegenseitig. Entweder die alte Bridge abschalten oder N8 Crosslink eine eigene Peer-ID geben (in HBlink4 freischalten).
4. **FRN-Konto:** Dasselbe FRN-Konto darf nicht gleichzeitig von SvxLink und N8 Crosslink benutzt werden.
5. Im Dashboard prüfen: Statusleiste FRN/DMR/Zello/Vocoder grün → eine Testdurchsage aus jedem Netz.

## Läuft auf derselben Maschine (z. B. „Crosslink“)

Das geht problemlos. Der bisherige Auto-Neustart-Watchdog für svxlink/MMDVM_Bridge wird nicht mehr gebraucht: N8 Crosslink verbindet sich bei Ausfällen selbst neu (FRN mit Backoff bis 2 min, DMR mit erneutem Login, Zello mit Refresh-Token), und systemd startet den Dienst bei einem Absturz nach 3 s neu.
