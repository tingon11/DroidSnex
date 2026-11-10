# Componenti di terze parti

DroidSnex è distribuito con licenza **GPL-3.0-or-later** (vedi `LICENSE`).
Questo file elenca ciò che il progetto usa, include o scarica, con la licenza
e l'attribuzione richiesta. Le voci marcate **[incluso]** sono nel repository o
nei file distribuiti; quelle **[scaricato]** vengono scaricate dall'utente a
runtime da siti terzi e non sono ridistribuite con DroidSnex; quelle
**[build]** servono solo per compilare o testare.

Ultima verifica: novembre 2026.

---

## 1. Programma PC (Python)

| Componente | Uso | Licenza | Note |
|---|---|---|---|
| Python e libreria standard | [requisito] | PSF License 2.0 | https://docs.python.org/3/license.html |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | GUI (`requirements-gui.txt`) | MIT, © 2023 Tom Schimansky | installato con pip |
| ↳ font Roboto inclusi in CustomTkinter | GUI | Apache-2.0, © Google | file del pacchetto customtkinter |
| ↳ [darkdetect](https://github.com/albertosottile/darkdetect) | dipendenza di CustomTkinter | BSD-3-Clause, © 2019 Alberto Sottile | |
| ↳ [packaging](https://github.com/pypa/packaging) | dipendenza di CustomTkinter | Apache-2.0 oppure BSD-2-Clause (a scelta) | |
| [Pillow](https://python-pillow.org) | GUI, mappa vettoriale, logo | MIT-CMU (HPND), © 1997-2011 Secret Labs AB, © 1995-2011 Fredrik Lundh e contributori, © 2010 Jeffrey A. Clark e contributori | |
| [windows-curses](https://github.com/zephyrproject-rtos/windows-curses) | facoltativo, tabella live su Windows | BSD-3-Clause (modulo) + PDCurses (pubblico dominio) | solo Windows |

Le dipendenze Python non sono incluse nel repository: le installa l'utente con
`pip`. Se in futuro DroidSnex venisse distribuito come eseguibile
(PyInstaller o simili), i testi di licenza di questi pacchetti vanno copiati
accanto all'eseguibile.

Il lettore del formato MaxMind DB (`geo.py`) è scritto da zero seguendo la
specifica pubblica (https://maxmind.github.io/MaxMind-DB/, CC BY-SA 3.0 per il
testo della specifica); non usa librerie MaxMind.

## 2. App Android (agent)

| Componente | Uso | Licenza | Note |
|---|---|---|---|
| Kotlin standard library | [incluso] nell'APK | Apache-2.0, © JetBrains s.r.o. e contributori del linguaggio Kotlin | testo in `LICENSES/Apache-2.0.txt` |
| Android framework (SDK 35) | API di sistema | Apache-2.0 (AOSP); SDK soggetto all'Android SDK License Agreement | non incluso nell'APK |
| Android Gradle Plugin 8.7.3 | [build] | Apache-2.0 | |
| Kotlin Gradle Plugin 2.0.21 | [build] | Apache-2.0 | |
| Gradle Wrapper (`gradle-wrapper.jar`) | [incluso] nel repository, [build] | Apache-2.0, © Gradle Inc. | |
| JUnit 4.13.2 | [build] solo test | Eclipse Public License 1.0 | non incluso nell'APK |

L'agent non ha altre dipendenze a runtime (niente AndroidX, niente librerie di rete).

## 3. Strumenti scaricati

### Android SDK Platform-Tools (adb) [scaricato]
`platform_tools.py` scarica `platform-tools-latest-<os>.zip` da
`dl.google.com` nella cartella `pc/tools/platform-tools/` (esclusa da git).
Il pacchetto è di Google ed è soggetto ai **termini dell'Android SDK**
(https://developer.android.com/studio/terms); i componenti open source al suo
interno hanno le licenze elencate nel `NOTICE.txt` del pacchetto stesso.
Scaricando il pacchetto l'utente accetta quei termini. **Non ridistribuire**
la cartella `platform-tools` dentro release o archivi di DroidSnex: i termini
dell'SDK non lo permettono; si continua a scaricarla da Google.

## 4. Dati geografici e di rete

### DB-IP City Lite / ASN Lite [scaricato] — attribuzione obbligatoria
- Fonte: https://db-ip.com/db/lite.php (file `dbip-city-lite-AAAA-MM.mmdb.gz`,
  facoltativo `dbip-asn-lite.mmdb`).
- Licenza: **Creative Commons Attribution 4.0 International (CC BY 4.0)**,
  https://creativecommons.org/licenses/by/4.0/
- Attribuzione richiesta da DB-IP, da mostrare dove si usano i dati:
  **"IP Geolocation by DB-IP"** con link a https://db-ip.com.
  È mostrata nella finestra *Informazioni e licenze* della GUI e in `NOTICE`.
- I database restano in `pc/data/` (esclusa da git) e non sono ridistribuiti.

### MaxMind GeoLite2 (alternativa facoltativa)
DroidSnex legge anche `GeoLite2-City.mmdb` / `GeoLite2-ASN.mmdb` se l'utente li
procura da sé. Sono soggetti alla GeoLite2 EULA di MaxMind (account
obbligatorio, attribuzione: *"This product includes GeoLite2 data created by
MaxMind, available from https://www.maxmind.com"*). DroidSnex non li scarica
né li ridistribuisce.

### iptoasn.com (alternativa facoltativa)
`ip2asn-*.tsv` da https://iptoasn.com: dati rilasciati con
Public Domain Dedication and License (PDDL). Nessun obbligo di attribuzione.

### Natural Earth — pubblico dominio
- `pc/droidsnex/gui/assets/world.json` (1:110m) e `vector-50m.json.gz` (1:50m)
  [incluso], generati con `tools/make_world.py` e `tools/make_vector.py`.
- 1:10m [scaricato] da `raw.githubusercontent.com/nvkelso/natural-earth-vector`.
- Licenza: pubblico dominio (https://www.naturalearthdata.com/about/terms-of-use/).
  L'attribuzione non è obbligatoria; per cortesia si indica
  "Made with Natural Earth".
- È l'unica mappa del programma: la GUI disegna il mondo da questi dati
  vettoriali e non scarica tile da server terzi (OpenStreetMap, CARTO,
  OpenTopoMap ecc.), quindi non ci sono condizioni d'uso di tile da rispettare.

### Servizi web
- **ipify** (`api.ipify.org`): solo per conoscere l'IP pubblico del PC.
  Servizio gratuito, nessuna licenza sui dati.
- **Reverse DNS**: usa il resolver di sistema, nessun servizio terzo.

### Liste di reputazione
Al momento DroidSnex **non** usa liste di reputazione o blocklist esterne.
Se se ne aggiungono, ecco le condizioni delle più comuni da riportare qui:
- StevenBlack/hosts: MIT (le liste sorgenti hanno licenze proprie).
- abuse.ch URLhaus / ThreatFox / Feodo Tracker: CC0.
- Spamhaus DROP: uso gratuito solo non commerciale, condizioni Spamhaus.
- FireHOL blocklist-ipsets: ogni lista mantiene la licenza della fonte.

## 5. Grafica

### Logo DroidSnex e carattere Panchang
Il logo (`pc/assets/`, `pc/droidsnex/gui/assets/`, `android/.../assets/logo.png`
e icone mipmap) è di Andrea Cumini ed è disegnato con il carattere
**Panchang** di Indian Type Foundry, distribuito da Fontshare
(https://www.fontshare.com/fonts/panchang) con la licenza gratuita
ITF/Fontshare: uso personale e commerciale consentito, nessuna attribuzione
obbligatoria, **vietato ridistribuire i file del carattere**.
Il carattere serve solo a `tools/make_logo.py`, che va lanciato su un PC dove
Panchang è installato; nel progetto ci sono solo le immagini già disegnate e
nessun file `.ttf`/`.otf`. Non aggiungere Panchang al repository.

### Caratteri di sistema
La GUI usa i caratteri già presenti nel sistema (Segoe UI, Cascadia Mono,
Consolas, Segoe Fluent Icons, ecc.) senza includerli.

---

## Testi di licenza

- `LICENSE` — GNU GPL v3 (DroidSnex)
- `LICENSES/Apache-2.0.txt` — Apache License 2.0 (Kotlin stdlib, Gradle Wrapper, Roboto, AGP)
- Le altre licenze sono brevi e consultabili ai link indicati; i pacchetti
  Python installati con pip portano il proprio testo di licenza nella
  cartella `*.dist-info`.
