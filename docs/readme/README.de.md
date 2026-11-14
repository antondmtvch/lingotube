# lingotube

![version](https://img.shields.io/badge/version-0.1.0-blue)
![python](https://img.shields.io/badge/python-%E2%89%A53.14-3776AB?logo=python&logoColor=white)
![coverage cli](https://img.shields.io/badge/coverage_cli-96%25-brightgreen)
![coverage extension](https://img.shields.io/badge/coverage_extension-99%25-brightgreen)

[English](../../README.md) · [Русский](README.ru.md) · [简体中文](README.zh-Hans.md) · [繁體中文](README.zh-Hant.md) · [हिन्दी](README.hi.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [বাংলা](README.bn.md) · [Português](README.pt.md) · [ไทย](README.th.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · **Deutsch**

Ein Kommandozeilenwerkzeug, das Untertitel, ein Transkript und eine Zusammenfassung eines YouTube-Videos liefert.
Der Text stammt aus dem integrierten YouTube-Chat („Fragen“, Gemini) auf der Videoseite.
Alle Anfragen werden im Namen Ihres YouTube-Kontos gestellt.

> [!WARNING]
> Das Werkzeug nutzt eine **interne, undokumentierte** Anfrage des YouTube-Chats. YouTube kann sie
> jederzeit ohne Vorankündigung ändern, und das Werkzeug funktioniert dann bis zu einem Update nicht mehr.
> Die Nutzungsbedingungen von YouTube erlauben keinen automatisierten Zugriff: Sie nutzen das Werkzeug
> auf eigenes Risiko. Die Anfragen werden nacheinander mit einer Pause dazwischen gesendet, aber es gibt
> keine Garantie, dass Ihr Konto nicht eingeschränkt wird.

> [!NOTE]
> Fragen und Antworten bleiben im Chatverlauf Ihres Kontos. Der Chat ist in Russland und in den meisten
> EU-Ländern nicht verfügbar, ebenso unter manchen Videos nicht.

## Funktionen

- **Untertitel** in jeder Sprache, in den Formaten `srt`, `vtt` und `json`.
- **Transkript** in der Originalsprache mit Zeitmarken.
- **Zusammenfassung** des Videos.
- **Drei Übersetzungsmodi**: der integrierte YouTube-Chat, Ihr eigenes Modell mit OpenAI-kompatibler API
  oder ein KI-Agent, der das Transkript selbst übersetzt.
- **Cache und Fortsetzung**: Lange Videos werden in Teilen verarbeitet, und nach einem Fehler geht die Arbeit dort weiter, wo sie aufgehört hat.
- **Maschinenlesbare Ausgabe** mit `--json` für Skripte und KI-Agenten.

## Installation

Sie benötigen [uv](https://docs.astral.sh/uv/). uv lädt die passende Python-Version selbst herunter.

```sh
uv tool install git+https://github.com/antondmtvch/lingotube
```

Oder aus einer lokalen Kopie des Repositorys:

```sh
uv tool install .
```

Aktualisieren und deinstallieren:

```sh
uv tool upgrade lingotube
uv tool uninstall lingotube
```

## Schnellstart

1. Melden Sie sich bei YouTube an. In Chrome oder Edge geht das am einfachsten so:

   ```sh
   lingotube login
   ```

   Es öffnet sich ein Browserfenster mit einem separaten lingotube-Profil. Melden Sie sich in Ihrem Konto an und **schließen Sie das
   Browserfenster**: Der Befehl wartet, bis Sie es schließen. In Firefox genügt es, sich wie gewohnt bei YouTube anzumelden.

2. Prüfen Sie die Bereitschaft:

   ```sh
   lingotube doctor
   ```

   `doctor` prüft die Cookie-Quellen, die Anmeldung beim Konto und die Verfügbarkeit des Chats auf einem Testvideo.
   Er öffnet nur den Chat und schreibt nichts hinein.

3. Holen Sie die Untertitel:

   ```sh
   lingotube subs https://www.youtube.com/watch?v=XXXXXXXXXXX --lang de
   ```

## Befehle

| Befehl | Was er tut |
|---|---|
| `lingotube subs <Link> --lang de` | Erstellt eine Untertiteldatei in der gewählten Sprache. |
| `lingotube summary <Link> --lang de` | Gibt eine Zusammenfassung in der gewählten Sprache aus. |
| `lingotube transcript <Link>` | Erstellt ein Transkript in der Originalsprache mit Zeitmarken (standardmäßig JSON). |
| `lingotube build <Link> --lang de --from <Datei>` | Nimmt eine fertige Übersetzung, gleicht sie mit dem Original ab und baut die Untertitel. |
| `lingotube login [--browser chrome\|edge]` | Öffnet ein YouTube-Anmeldefenster und speichert die Cookies. |
| `lingotube logout` | Löscht das Anmeldeprofil und die gespeicherten Cookies. |
| `lingotube doctor` | Prüft die Bereitschaft: Cookies, Kontoanmeldung und Chat auf einem Testvideo. |

`<Link>` ist ein beliebiger YouTube-Videolink oder eine Video-ID.

Wichtige Optionen:

- `--lang <Code>` — Sprache des Ergebnisses (`ru`, `en`, `es` usw.). Ohne sie wird die Sprache aus den Einstellungen genommen.
- `--format srt|vtt|json` — Untertitelformat, standardmäßig `srt`.
- `-o <Pfad>` — wohin das Ergebnis geschrieben wird. Mit `-o -` geht das Ergebnis auf die Standardausgabe.
- `--offset <Sekunden>` — verschiebt alle Untertitel; Dezimal- und negative Zahlen sind erlaubt.
- `--cookies-file <Pfad>` / `--browser <Name>` — Cookie-Quelle.
- `--no-cache` — den Cache nicht verwenden.
- `--json` — ein einzelnes JSON-Dokument `{"ok", "result", "warnings", "error"}`.

Eine ID, die mit einem Bindestrich beginnt, übergeben Sie nach `--`:

```sh
lingotube subs --lang de -- -n5MqamatXE
```

## Cookies und Anmeldung

Das Werkzeug nimmt die erste passende Quelle in dieser Reihenfolge:

1. Eine `cookies.txt`-Datei: die Option `--cookies-file`, die Variable `LINGOTUBE_COOKIES_FILE` oder der Pfad aus den Einstellungen.
2. Ein ausdrücklich gewählter Browser: die Option `--browser` oder `browser` in den Einstellungen.
3. Das lingotube-Anmeldeprofil, falls es mit `lingotube login` erstellt wurde.
4. Andernfalls werden Firefox, Chrome, Edge und Brave nacheinander probiert.

Unter Windows schützen Chrome und Edge ihre Cookies, und sie lassen sich meist nicht direkt lesen.
Verwenden Sie dafür `lingotube login`. Der Export einer Datei bleibt ein Ausweichweg.

> [!CAUTION]
> Die Datei `cookies.txt` gewährt Zugriff auf Ihr Konto. Behandeln Sie sie wie ein Passwort und legen Sie
> sie nicht in Repositorys oder freigegebenen Ordnern ab. Cookies, Tokens und Autorisierungs-Header
> erscheinen nie in der Ausgabe, in Fehlermeldungen oder in `--json`: Stattdessen wird `***` ausgegeben.

Wenn die Cookies nicht mehr funktionieren (Exit-Code `4`), führen Sie `lingotube login` erneut aus oder exportieren Sie eine frische Datei.

## Übersetzungsmodi

| Modus | Wann er aktiv ist | Wer übersetzt |
|---|---|---|
| **Chat** (Standard) | nichts ist konfiguriert | der YouTube-Chat liefert den Text sofort in der gewünschten Sprache |
| **Eigenes Modell** | der Abschnitt `[translator]` ist in den Einstellungen gesetzt | Ihr Modell mit OpenAI-kompatibler API |
| **Agent** | `transcript` → Übersetzung → `build` | ein KI-Agent oder Sie |

Die Einstellungen liegen in `settings.toml`:

- Windows: `%LOCALAPPDATA%\lingotube\settings.toml`
- macOS: `~/Library/Application Support/lingotube/settings.toml`
- Linux: `~/.config/lingotube/settings.toml`

Beispiel für den Modus „eigenes Modell“:

```toml
lang = "de"

[translator]
base_url = "https://api.openai.com/v1"   # oder ein lokales Modell, z. B. http://127.0.0.1:11434/v1
model = "gpt-4o-mini"
api_key_env = "LINGOTUBE_API_KEY"        # Name der Umgebungsvariablen mit dem Schlüssel
batch_size = 40
```

Der Schlüssel wird nie in die Einstellungsdatei geschrieben: Das Werkzeug liest ihn nur aus der Umgebungsvariablen.

Modus „Agent“:

```sh
lingotube transcript <Link> -o orig.json          # das Original als JSON
# das Feld text jeder Zeile übersetzen, id und Zeit unverändert lassen, als de.json speichern
lingotube build <Link> --lang de --from de.json   # Prüfung und Aufbau der Untertitel
```

> [!TIP]
> Für eine wörtliche Übersetzung nutzen Sie den Modus „eigenes Modell“ oder „Agent“: Sie holen zuerst
> das Original, und die Übersetzung wird anhand der Zeilennummern geprüft. Der Chat kann Sätze umschreiben oder zusammenfassen.

## Exit-Codes

| Code | Bedeutung |
|---|---|
| `0` | Erfolg. |
| `1` | Sonstiger Fehler. |
| `2` | Ungültige Befehlsoptionen. |
| `3` | Der Chat ist für dieses Video oder Konto nicht verfügbar. |
| `4` | Anmeldeproblem: Cookies nicht gefunden oder abgelaufen, oder der Modellschlüssel fehlt. |
| `5` | Unvollständiges Ergebnis: Die Datei ist geschrieben, aber das Transkript reicht nicht bis zum Videoende. |
| `6` | Netzwerkfehler nach Ausschöpfen der Wiederholungen. |
| `7` | Die Daten haben die Prüfung nicht bestanden. |
| `130` | Vom Benutzer abgebrochen (Strg+C). |

## Einschränkungen

- Der Chat funktioniert nur für angemeldete Nutzer über 13 Jahren, ist nicht in jedem Land verfügbar
  und nicht unter jedem Video vorhanden.
- Markenkonten werden nicht unterstützt: Es wird das Hauptkonto des Browsers verwendet.
- Eine Stunde Video braucht mehrere Minuten: Die Anfragen gehen nacheinander raus.
- Die Zeiten der Zeilen legt der Chat fest. Bei langen Videos können einzelne Zeilen um einige
  Sekunden abweichen; eine konstante Verschiebung korrigieren Sie mit der Option `--offset`.
- Der Text langer Videos ist nicht garantiert wortwörtlich: Der Chat antwortet manchmal mit einem
  sinngemäß ähnlichen Text, und das Werkzeug erkennt das nicht. Prüfen Sie das Ergebnis bei wichtigen Anwendungen anhand der Aufnahme.
- Proxys werden nicht unterstützt.

## Skill für KI-Agenten

Das Repository enthält einen Skill im offenen Agent-Skills-Format. Damit fasst ein KI-Agent (Claude Code, Codex,
Cursor, Gemini CLI und andere) Videos zusammen, erstellt Transkripte und Untertitel, findet
einen Moment anhand einer Beschreibung und hilft bei Installation und Anmeldung.

```sh
npx skills add antondmtvch/lingotube
```

Ohne Node.js kopieren Sie den Ordner `skills/lingotube/` in den Skills-Ordner Ihres Agenten
(`~/.claude/skills/` für Claude Code oder `~/.agents/skills/` für die meisten anderen).

## Browser-Erweiterung

Der Ordner `extension/` enthält eine Erweiterung mit übersetzten Untertiteln über dem YouTube-Player.
Sie ist in Entwicklung und noch nicht im Hauptzweig.

## Entwicklung

Abhängigkeiten und Umgebung werden mit uv verwaltet:

```sh
uv sync
uv run pytest
uv run ruff check
```

Testabdeckung (die Werte in den Badges oben wurden mit diesen Befehlen gemessen und werden von Hand aktualisiert):

```sh
uv run --with pytest-cov pytest --cov=lingotube
cd extension && node --test --experimental-test-coverage --test-coverage-exclude='tests/**' tests/
```

Projektstruktur:

- `src/lingotube/` — der Kern: CLI, Autorisierung, Chat, Übersetzung, Cache und Schreiben der Ergebnisse.
- `skills/lingotube/` — der Skill für KI-Agenten.
- `extension/` — die Browser-Erweiterung.
- `tests/` — Python-Tests, `probe/` — manuelle Sonden für Anfragen an YouTube.
- `docs/readme/` — Übersetzungen dieser README.
