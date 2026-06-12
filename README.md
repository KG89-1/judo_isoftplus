# JUDO i-soft plus – Home Assistant Integration

Custom Integration für die **JUDO i-soft plus** Enthärtungsanlage über die lokale HTTPS-JSON-API (Port 8124). Keine Cloud, kein JUDO-Konto erforderlich – die Abfrage erfolgt ausschließlich im lokalen Netzwerk (`local_polling`).

> Inoffizielles Community-Projekt, nicht mit der JUDO Wasseraufbereitung GmbH verbunden.

## Funktionen

- Einrichtung vollständig über die UI (Config Flow), keine YAML-Konfiguration
- **Steuerbares Wasserstop-Ventil** (Valve-Entität): Öffnen/Schließen direkt aus HA, z. B. für Leckage-Automationen
- Pro Gerät genau ein Eintrag (Seriennummer als `unique_id`), bei IP-Wechsel wird der Host automatisch aktualisiert
- **Effizientes Polling:** Es werden nur die Werte abgefragt, die zu aktivierten Entitäten gehören – schont den langsamen Embedded-Controller des Geräts
- Einstellbares Aktualisierungsintervall (60–3600 s, Standard 300 s) über die Integrationsoptionen
- Deutsche und englische Übersetzungen

## Wasserstop-Ventil

Die Integration legt eine standardmäßig aktivierte Valve-Entität **Wasserstop** an, über die sich das Absperrventil der Anlage öffnen und schließen lässt – per Dashboard-Karte, Service-Aufruf (`valve.open_valve` / `valve.close_valve`) oder in Automationen, etwa:

```yaml
automation:
  - alias: "Leckage -> Wasser zu"
    triggers:
      - trigger: state
        entity_id: binary_sensor.wassersensor_keller
        to: "on"
    actions:
      - action: valve.close_valve
        target:
          entity_id: valve.judo_i_soft_plus_wasserstop
```

⚠️ Das Schließen sperrt die gesamte Wasserzufuhr hinter der Anlage. Verwendung auf eigene Verantwortung.

## Sensoren

Standardmäßig aktiviert ist nur **Gesamtwasserverbrauch Live** (`water_total_live`, m³, `total_increasing`): Das Gerät schreibt den Stundenverbrauch nur einmal pro Stunde in den Gesamtzähler. Dieser Sensor kombiniert „water total" mit dem laufenden Stundenwert („water current") zu einem live aktualisierten, streng monotonen Zählerstand – direkt nutzbar im Energie-Dashboard (Wasser). Ein monotoner Guard verhindert Statistik-Korruption beim stündlichen Rollover; nur ein Einbruch von mehr als 50 L wird als echter Zähler-Reset gewertet.

Alle weiteren Sensoren sind standardmäßig deaktiviert und können bei Bedarf einzeln aktiviert werden (sie werden dann automatisch beim nächsten Zyklus mit abgefragt):

| Sensor | Einheit | Hinweis |
|---|---|---|
| Gesamtwasserverbrauch | L | Roher Gerätezähler (stündliche Aktualisierung) |
| Wasserverbrauch Aktuell | L | Laufende Stunde |
| Wasserverbrauch Heute / Woche / Monat / Jahr | L | Periodenzähler |
| Durchflussrate | L/h | |
| Restmenge | L | |
| Salzmenge | g | |
| Reichweite Salz | d | |
| Resthärte / Natürliche Härte | °dH | |
| Wasserstop Ventil / Urlaubsmodus / Standby | – | Statuswerte |
| Max. Entnahmedauer / Durchfluss / Entnahmemenge | min / L/h / L | Wasserstop-Grenzwerte (Diagnose-Entitäten) |

## Voraussetzungen

- Home Assistant **2024.12.0 oder neuer**
- JUDO i-soft plus mit erreichbarer lokaler API (`https://<gerät>:8124`)
- Benutzername, Passwort und Seriennummer des Geräts

Hinweis: Das Gerät verwendet ein selbstsigniertes Zertifikat und ältere TLS-Cipher; die Integration akzeptiert dies bewusst (lokale Verbindung).

## Installation

### Über HACS (empfohlen)

1. HACS → Menü (⋮) → **Benutzerdefinierte Repositories**
2. Repository-URL `https://github.com/KG89-1/judo-isoftplus` eintragen, Typ **Integration**
3. „JUDO i-soft plus" installieren und Home Assistant neu starten

### Manuell

1. Den Ordner `custom_components/judo_isoftplus` aus diesem Repository nach `config/custom_components/` kopieren
2. Home Assistant neu starten

## Einrichtung

**Einstellungen → Geräte & Dienste → Integration hinzufügen → „JUDO i-soft plus"**, dann Host (IP oder Hostname), Benutzername, Passwort und Seriennummer eingeben. Das Aktualisierungsintervall lässt sich anschließend über **Konfigurieren** am Integrationseintrag anpassen.

## Breaking Changes in v0.2.0

- Sensor `water_today` entfernt (war ein Duplikat von `water_daily`) – ggf. verwaiste Entität manuell löschen
- Einheit von „Reichweite Salz" von `days` auf `d` geändert (Standard-HA-Einheit, `device_class: duration`)
- Mindestversion Home Assistant 2024.12

## Fehlerbehebung

- **Sensoren „nicht verfügbar":** Einzelne Lesefehler betreffen nur die jeweilige Entität; erst wenn alle Abfragen fehlschlagen, gilt das Gerät als offline. Details stehen im Log (`custom_components.judo_isoftplus`).
- Debug-Logging aktivieren:

```yaml
logger:
  logs:
    custom_components.judo_isoftplus: debug
```

Zugangsdaten und Session-Token werden im Log automatisch geschwärzt.
