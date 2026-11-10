# DroidSnex

Monitor delle connessioni di rete di un telefono Android, visto dal PC via cavo USB.
Mostra in tempo reale **verso quali destinazioni (IP, dominio, porta) si collega ogni app**.
Non serve il root, i certificati non vengono intercettati e il contenuto non viene decifrato:
si raccolgono solo i metadati di destinazione. È pensato per analizzare **i propri dispositivi**.

L'approccio (VPN locale + stack TCP/UDP in user space) è lo stesso di strumenti come PCAPdroid;
il codice di questo repository è scritto da zero.

```
 ┌──────────────── Telefono ────────────────┐            ┌────────────── PC ──────────────┐
 │  App ──► TUN (VpnService) ──► agent      │            │                                │
 │                │  legge gli header       │            │  droidsnex (Python)            │
 │                │  DNS / SNI / Host       │   USB      │   ├─ adb install / appops      │
 │                ▼                         │  (adb      │   ├─ adb forward tcp:8888      │
 │       socket "protetti" ──► Internet     │  forward)  │   ├─ tabella live              │
 │                                          │◄──────────►│   ├─ reverse DNS, ASN          │
 │  server 127.0.0.1:8888 (JSON-lines) ─────┼────────────┼──►└─ export CSV/JSON/pcapng     │
 └──────────────────────────────────────────┘            └────────────────────────────────┘
```

## Struttura

```
android/                 App "agent" (Kotlin, nessuna dipendenza esterna)
  app/src/main/java/com/droidsnex/agent/
    CaptureService.kt    VpnService: configura il TUN, thread lettore, eventi JSON
    net/Forwarder.kt     stack TCP/UDP in user space (pass-through verso socket protetti)
    net/Packet.kt        parsing e costruzione di pacchetti IPv4/IPv6, TCP, UDP, checksum
    inspect/Dns.kt       parsing query/risposte DNS (cache IP -> dominio, eventi "dns" al PC)
    AppInfoReporter.kt   scheda dell'app (etichetta, icona, versione, permessi) -> evento "app" al PC
    inspect/HostSniffer.kt  SNI dal ClientHello TLS, header Host HTTP
    AppResolver.kt       connessione -> UID -> nome pacchetto
    EventServer.kt       server TCP 127.0.0.1:8888, buffer per la ripresa dopo disconnessione
    MainActivity.kt      UI minimale: stato, contatore, avvia/ferma
  app/src/test/...       test JVM dello stack di rete
pc/                      Programma PC (Python 3.9+, solo libreria standard)
  run.py                 punto di ingresso (riga di comando)
  gui.py                 interfaccia grafica CustomTkinter (droidsnex/gui/, asset in droidsnex/gui/assets/)
  droidsnex/             adb, stream, aggregazione, risoluzione, TUI, export
    geo.py               lettore .mmdb (DB-IP City Lite / GeoLite2) e download del database
    platform_tools.py    download di adb (Android Platform Tools) nella cartella pc/tools
    scrcpy.py            download di scrcpy (release ufficiale) in pc/tools/scrcpy e avvio del mirroring
    ipinfo.py            dettaglio IP: PTR, RDAP, range cloud, certificato TLS, servizi con chiave API
    gui/ipdetail.py      finestra "Dettaglio IP" e salvataggio collegamento + IP
    vector.py            mappa vettoriale Natural Earth: conversione, download 1:10m, disegno delle tile
    gui/mapview.py       mappa del mondo con le connessioni animate
    gui/graphview.py     grafo a forze in stile OsintGraph (telefono, app, organizzazioni, destinazioni)
    gui/timeline.py      traffico per app nel tempo
    gui/analysis.py      schede Grafo, Timeline, DNS, Alert, Sessioni e profilo dell'app
    gui/welcome.py       finestra iniziale bloccante: scelta della lingua e accettazione dei termini
    gui/manual.py        finestra del manuale: Markdown formattato, indice, immagini, link
    risk.py              scala di pericolosità (bianco -> viola) delle destinazioni non fidate
    alerts.py            regole degli alert
    reputation.py        liste di reputazione (tracker, malware, Tor) e riconoscimento VPN
    sessions.py          sessioni salvate (con eventi e segnalibri) e confronto
    apkinfo.py           package e versione di un file APK (manifest binario), per il riquadro Agent Android
    guard.py             guardiano: processo a parte che disinstalla l'agent se il programma PC crasha
    paths.py             cartelle: risorse incluse nell'exe (BUNDLE_DIR) e file di lavoro (HOME_DIR)
    terms.py             termini d'uso ed esclusione di responsabilita' in 9 lingue (finestra iniziale, TERMS.md)
    proc.py              processi esterni (adb, scrcpy, guardiano) senza finestre di console su Windows
    replay.py            replay di una sessione: eventi rimandati a un monitor dedicato, timeline ricalcolata
    report.py            report HTML della sessione (un file solo, stampabile in PDF dal browser)
    updates.py           controllo di una nuova versione, solo dal pulsante in Config
  data/                  (creata da Config) database città e ASN, mappa, liste di reputazione
  sessions/              (creata da Start) sessioni registrate, una cartella per telefono
  tools/make_world.py    rigenera i contorni degli stati con il codice ISO (sfondo semplice, stati colorati, report)
  tools/make_vector.py   rigenera la mappa vettoriale 1:50m inclusa
  tools/fake_agent.py    agent simulato per provare il PC senza telefono
  tools/build_exe.py     DroidSnex.exe in cartella (PyInstaller), con --apk ricompila l'agent
.github/workflows/       build automatica dell'APK su GitHub Actions
```

## Prerequisiti

**Telefono**
- Android 7.0 o superiore (consigliato Android 10+: l'attribuzione delle connessioni alle app è più affidabile).
- Opzioni sviluppatore attive: *Impostazioni > Info sul telefono > tocca 7 volte "Numero build"*.
- *Debug USB* attivo (*Impostazioni > Sistema > Opzioni sviluppatore > Debug USB*).
- Alla prima connessione accetta il popup **"Consentire il debug USB?"** spuntando *Consenti sempre da questo computer*.
- Su Xiaomi/MIUI/HyperOS attiva anche *Installa tramite USB* e *Debug USB (impostazioni di sicurezza)*.

**PC**
- `adb` (Android Platform Tools), **solo quello nella cartella del programma**: DroidSnex non usa mai l'adb
  del sistema (`PATH`) né quello dell'Android SDK, e non lo scarica mai da solo. Al primo avvio apri la GUI e
  premi **Config > ADB · Android Platform Tools > Scarica / aggiorna da Google**: il programma scarica lo zip
  ufficiale (`dl.google.com/android/repository/platform-tools-latest-<os>.zip`) e lo estrae in
  `pc/tools/platform-tools/`, senza installare nulla nel sistema e senza toccare il `PATH`. Finché manca,
  la GUI mostra un avviso e la riga di comando si ferma con lo stesso messaggio.
- Python 3.9 o superiore. Nessun pacchetto obbligatorio.
  Facoltativi: `pip install windows-curses` su Windows per la tabella a schermo intero.
- Per compilare l'APK: JDK 17 e Android SDK (installati da Android Studio), oppure GitHub Actions (vedi sotto).

Verifica:
```bash
pc/tools/platform-tools/adb version     # Windows: pc\tools\platform-tools\adb.exe
pc/tools/platform-tools/adb devices     # deve comparire il seriale con stato "device"
```

## Compilare l'APK

**Da riga di comando** (con Android SDK installato; se serve crea `android/local.properties` con `sdk.dir=/percorso/Android/Sdk`):
```bash
cd android
./gradlew assembleDebug          # Windows: gradlew.bat assembleDebug
./gradlew testDebugUnitTest      # facoltativo: test dello stack di rete
```
L'APK si trova in `android/app/build/outputs/apk/debug/app-debug.apk`: il programma PC lo trova lì automaticamente.
In alternativa copialo in `pc/agent.apk` o passalo con `--apk`.

**Con Android Studio**: *File > Open* sulla cartella `android/`, poi *Build > Build App Bundle(s)/APK(s) > Build APK(s)*.

**Senza installare nulla**: fai push del repository su GitHub; il workflow `.github/workflows/android.yml`
compila l'APK e lo pubblica come artifact `droidsnex-agent-apk` nella pagina della run (scheda *Actions*).

## Prima apertura: lingua e termini d'uso

Alla prima apertura (o quando i termini cambiano versione) compare una finestra in primo piano, senza barra
del titolo e che blocca il resto del programma: se la lingua non è ancora in `config.json` si sceglie fra le 9
disponibili, poi vengono mostrati nella lingua scelta i **termini d'uso ed esclusione di responsabilità**
completi, per il programma PC e per l'app Android (uso solo su dispositivi propri o autorizzati, nessuna
garanzia "AS IS", esclusione di responsabilità, dati inviati ai servizi terzi tramite API, licenze delle
componenti, legge applicabile). *Accetto* si attiva dopo aver fatto scorrere il testo fino in fondo: salva in
`config.json` la versione accettata e la data (`terms_accepted`, `terms_accepted_at`) e il programma parte.
*Rifiuto* chiude il programma. Il testo è in `pc/droidsnex/terms.py` (9 lingue), nel file `TERMS.md` (generato
con `cd pc && python -m droidsnex.terms > ../TERMS.md`) e nella finestra *Informazioni e licenze* (pulsante
*Termini d'uso*).

## Eseguibile Windows

`pc/tools/build_exe.py` crea la cartella `pc/dist/DroidSnex/` con `DroidSnex.exe`, l'agent
`DroidSnex.apk` e le risorse accanto (`_internal/`), più uno zip `DroidSnex-<versione>.zip` pronto da distribuire. Serve PyInstaller
(`pip install pyinstaller` nello stesso ambiente della GUI):

```bat
cd pc
python tools\build_exe.py            # la cartella dist\DroidSnex\ (+ zip), con l'APK compilato piu' recente
python tools\build_exe.py --apk      # prima gradlew assembleDebug, poi l'exe con l'APK appena compilato
python tools\build_exe.py --console  # exe con console, per vedere gli errori
```

**L'APK nella release.** Lo script prende il compilato più recente dell'agent fra
`android/app/build/outputs/apk/{release,debug}`, `DroidSnex.apk` nella cartella del progetto e `pc/agent.apk`, e
lo copia accanto all'exe come **`DroidSnex.apk`**: finisce così anche nello zip, e il programma lo trova da solo.

**Compilazione normale, in cartella.** L'opzione `--onefile` non c'è più: la build è sempre quella in cartella.

**Antivirus.** Gli exe a file unico ("onefile") di PyInstaller vengono spesso segnalati per sbaglio ("Il file contiene un
virus o software potenzialmente indesiderato"): il bootloader si auto-estrae in una cartella temporanea e le
euristiche non lo gradiscono, e il verdetto può cambiare da una build all'altra perché cambia l'hash. Per questo
si compila solo in cartella. Lo script inoltre non usa UPX, incorpora le informazioni di versione Windows e
l'icona ed esclude i moduli inutili. Se Windows Security blocca lo stesso: aggiungi un'esclusione per la cartella
(Sicurezza di Windows → Protezione da virus e minacce → Gestisci impostazioni → Esclusioni) e segnala il falso
positivo a Microsoft (<https://www.microsoft.com/wdsi/filesubmission>). Il nome del rilevamento è in Sicurezza
di Windows → Cronologia protezione.

Nella cartella: codice, assets (logo, icona, mappa 1:50m), `DroidSnex.apk`, LICENSE, NOTICE, THIRD_PARTY_NOTICES.md
e LICENSES/. Fuori, e scaricati dal tab Config nella cartella accanto all'exe (`tools/`, `data/`; se la
cartella non è scrivibile, in `%LOCALAPPDATA%\DroidSnex`): adb, scrcpy, database DB-IP, mappa 1:10m, liste di
reputazione e range cloud, che per licenza non vanno ridistribuiti. Anche `config.json`, `trusted.json`,
`sessions/` e `captures/` stanno accanto all'exe e **non entrano mai nella release** né nel repository
(`.gitignore`): `config.json` contiene le chiavi API (VirusTotal ecc.) e la posizione di casa. Il guardiano (crash del programma) viene lanciato
dall'exe stesso con `--guard`. I percorsi sono in `droidsnex/paths.py` (`BUNDLE_DIR` = risorse incluse,
`HOME_DIR` = file di lavoro).

## Usare il programma PC

Flusso completo (verifica adb e device, installa l'APK, concede i permessi, avvia la VPN, `adb forward`, tabella live):
```bash
cd pc
python run.py                      # equivale a: python run.py run
python run.py --apk ../percorso/app-debug.apk
python run.py -s <seriale>         # se hai più device collegati
```

Cosa fa, passo per passo:
1. `adb devices` — controlla che adb ci sia e che il device sia collegato e **autorizzato**.
2. `adb install -r -g agent.apk` — installa o aggiorna l'agent concedendo i permessi runtime.
3. Permessi: `appops set com.droidsnex.agent ACTIVATE_VPN allow` pre-autorizza la VPN (di solito il
   dialog "Richiesta di connessione" non compare nemmeno), `pm grant ... POST_NOTIFICATIONS`,
   esclusione dall'ottimizzazione batteria (`dumpsys deviceidle whitelist`).
4. `adb shell am start -n com.droidsnex.agent/.MainActivity -a com.droidsnex.agent.START` — avvia la cattura.
   Se il telefono mostra comunque il dialog VPN, sblocca lo schermo e tocca **OK**: il programma attende.
5. `adb forward tcp:8888 tcp:8888` — la porta 8888 del PC viene collegata, attraverso il cavo USB,
   alla porta 8888 del loopback del telefono, dove l'agent trasmette gli eventi.
6. Connessione a `127.0.0.1:8888`, lettura dello stream e tabella live.

Altri comandi:
```bash
python run.py install [--apk FILE]   # solo installazione + permessi
python run.py start | stop           # avvia / ferma la VPN sul telefono
python run.py monitor                # agent già avviato: solo forward + tabella
python run.py devices                # elenca i device adb
python run.py uninstall
python run.py --duration 60          # raccoglie per 60 s, esporta ed esce (senza TUI)
python run.py --hide-dns --no-rdns --plain --export-on-exit
python run.py --keep-agent           # all'uscita lascia l'agent installato e attivo
```

### Interfaccia grafica

```bash
cd pc
pip install -r ../requirements.txt      # tutto il necessario (customtkinter, pillow; su Windows anche windows-curses)
python tools/make_logo.py               # facoltativo: rigenera logo e icona (serve Panchang installato)
python gui.py                           # usa adb e il telefono collegato
python gui.py --demo 127.0.0.1:8899     # prova senza telefono (con tools/fake_agent.py avviato)
```
Stesso stile di AndrOsint (tema scuro Seity, accento `#7b95dd`, logo bicolore in Panchang Semibold,
finestra senza barra del titolo su Windows): intestazione con logo, scelta del dispositivo e stato;
colonna dei comandi (un solo pulsante *Start monitor* che a monitor attivo diventa *Stop monitor*, *Esporta*, opzioni, stato ADB/device/VPN/stream);
contatori (con il traffico al secondo in uscita ↑ e in entrata ↓), pannello dettagli e log.
Al centro le schede: **Config**, **Untrusted**, **Trusted**, **Mappa**, **Grafo**, **Timeline**, **DNS**,
**Alert**, **Sessioni**. Ogni pannello si può staccare in una finestra a parte (pulsante ⧉, anch'essa senza
barra del titolo) e riagganciare.

### Ciclo di vita dell'agent (Start / Stop / watchdog)

- **Start** (GUI) o `python run.py`: installa l'APK, concede i permessi, avvia la VPN, fa `adb forward`
  e mostra le connessioni live.
- **Stop**, chiusura della finestra, uscita del programma (anche per errore o Ctrl+C): il PC ferma la VPN,
  rimuove il forward e **disinstalla l'agent** con `adb uninstall`.
- **Crash del programma PC** (chiusura brutale, kill, errore fatale): allo Start il PC avvia anche un
  **guardiano**, un piccolo processo a parte (`droidsnex/guard.py`) collegato al programma da un tubo. Se il
  programma muore, il tubo si chiude e il guardiano ferma la cattura, toglie il forward e **disinstalla
  l'agent** via adb (insiste per 2 minuti se il telefono non risponde subito; registro in
  `pc/captures/guard.log`). Con Stop o chiusura regolare il guardiano riceve "bye" ed esce senza fare nulla.
- **Cavo staccato (o telefono irraggiungibile)**: il programma PC, collegandosi, arma un *watchdog*
  sull'agent. Se per 20 secondi non c'è più nessun PC collegato, l'agent ferma la VPN da solo e mostra la
  richiesta di disinstallazione (una notifica "DroidSnex fermato – tocca per disinstallare"). Senza root
  un'app non può disinstallarsi in silenzio: serve un tocco di conferma. Al successivo Start il PC
  reinstalla comunque l'agent (e allo Stop lo rimuove).

### Pulisci tutto e schermo del telefono

Nella colonna dei comandi, a monitor fermo, compare **Pulisci tutto** (con conferma): svuota connessioni,
query DNS, alert, mappa, grafo e timeline della sessione corrente; le sessioni salvate e l'elenco delle fidate
restano. **Schermo del telefono** apre lo schermo del telefono con **scrcpy** (Genymobile, Apache 2.0), esattamente come
AndrOsint: scrcpy nella sua finestra (risoluzione max 1024, 4 Mbps, 30 fps, senza audio, telefono sveglio);
mouse e tastiera dentro la finestra vanno al telefono (tocco, scorrimento, testo); l'orientamento resta
verticale anche se il telefono viene ruotato; la finestra parte a metà della dimensione del video (si può
ridimensionare); su Windows la finestra è "posseduta" da quella di DroidSnex, quindi
resta sopra il programma (mai sotto) ma non sopra le altre applicazioni; il pulsante diventa *Chiudi schermo*
finché la finestra è aperta. scrcpy va scaricato una volta dalla scheda Config (*Scarica / aggiorna da
GitHub*, release ufficiale per Windows in `pc/tools/scrcpy`, mai in automatico e mai quello del sistema); usa
l'adb della cartella tools.

**Finestre staccate**: Mappa, Grafo, Dettagli e App sulla mappa, una volta staccate, su Windows sono
senza barra del titolo come la finestra principale: intestazione con il logo (trascinabile, doppio clic
massimizza), pulsante **⇲ Riaggancia** e riduci / massimizza / chiudi (anche la X riaggancia).

### Untrusted / Trusted

Le destinazioni live (dominio, IP risolti, porte, app, connessioni, traffico, prima/ultima vista, ASN) sono
divise in due schede: **Untrusted** e **Trusted, in verde**; accanto al nome della scheda c'è il conteggio.
Le righe non fidate sono colorate secondo una **scala di pericolosità** da 0 a 5 (`pc/droidsnex/risk.py`):
**bianco → giallo → arancio → rosso → fucsia → viola**, più la riga va verso il viola più il collegamento è
sospetto. Si sommano punti per ogni segnale: solo IP senza nome (+1), organizzazione sconosciuta (+1), paese
diverso dal tuo (+1, serve la tua posizione in Config), resolver DNS cifrato (+1), porta
insolita (+2), provider VPN (+3), tracker/pubblicità (+4), nodo di uscita Tor (+4), malware in lista (+5). I
segnali generici arrivano al massimo al rosso: fucsia e viola sono riservati a chi compare nelle liste di
reputazione. Il pannello Dettagli mostra livello e motivi; la stessa scala colora le linee della mappa e i
nodi/collegamenti del grafo (legenda in basso), con *✕ Untrust tutti* (con conferma) nella scheda Trusted. Il clic su `✓ TRUST` sposta una destinazione tra le fidate, il clic su `✕ UNTRUST` la riporta
tra le non fidate. L'elenco viene salvato in `pc/trusted.json` e resta valido tra una sessione e l'altra.
Un clic sul titolo di una colonna ordina la lista per quella colonna (A-Z, dal più piccolo al più grande);
un secondo clic inverte l'ordine (Z-A). La freccia ▲/▼ nel titolo indica la colonna attiva; il menu
*Ordina* torna agli ordinamenti predefiniti.

### Mappa

**Pannelli staccabili**: Mappa, Dettagli e App sulla mappa hanno in alto a destra il pulsante `⧉` che li
stacca in una finestra a parte (spostabile, ridimensionabile, anche su un secondo monitor); `⇲` o la chiusura
della finestra li riaggancia. Il pannello Dettagli mantiene la posizione di scorrimento durante l'aggiornamento live.

Un piccolo smartphone nella tua posizione e una linea sottile verso la città di ogni destinazione:
**verde se fidata, rossa se non fidata**, con il punto della destinazione dello stesso colore.
L'agent invia ogni secondo i byte delle connessioni aperte: sulle linee scorrono dei puntini
(colorati = dati in uscita verso la destinazione, bianchi = dati in entrata verso il telefono)
e **lo spessore della linea cresce con i byte al secondo** (scala logaritmica, da 1 a 5 px); le linee
senza traffico restano sottili e più scure. Rotella o doppio clic = zoom, trascina = sposta, `⌂` = centra
sul telefono, `◯` = mondo intero; passa sopra un punto per il riepilogo, cliccalo per i dettagli.
C'è **una linea per ogni IP** di destinazione: le linee verso la stessa città si aprono a ventaglio
(prima le fidate, poi le non fidate) lungo il percorso e arrivano tutte nello stesso punto della città
(rosso se c'è almeno una non fidata, con il bordo verde se ci sono anche fidate), così si vedono e si cliccano una per una. Anche le **linee sono cliccabili**: passandoci sopra compare il riepilogo, il clic seleziona la linea
(evidenziata) e il pannello Dettagli mostra città, app, destinazioni e l'elenco delle connessioni su quella
linea (ora, protocollo, IP:porta, stato, byte in uscita/entrata). Il filtro di ricerca vale anche per la mappa. A destra della mappa c'è l'elenco delle **app** che
generano i collegamenti (con il numero di connessioni): spunta una o più app per vedere solo le loro
linee, oppure usa *Mostra tutte* / *Nascondi tutte*. Dopo *Nascondi tutte* anche le app nuove restano
nascoste finché non le spunti. *Solo connessioni nuove* nasconde tutte le linee presenti in quel momento
e da lì in poi mostra solo le connessioni nuove; un secondo clic le rimostra tutte. Sopra l'elenco, *Tutte* / *Fidate* / *Non fidate* mostra tutte le linee
oppure solo quelle verdi o solo quelle rosse (si combina con il filtro per app). Le destinazioni con IP privati (LAN, DNS del router) o non
presenti nel database vengono contate a parte.

**Animazioni e lettura a colpo d'occhio** (`gui/mapview.py`):
- gli **impulsi** sulle linee hanno una scia e sono tanti e grandi quanto il traffico; le linee con traffico in
  corso hanno un alone;
- una **connessione nuova** si annuncia con una scintilla che parte dal telefono e due anelli che si allargano
  sulla destinazione (anche durante il replay di una sessione); le città con connessioni aperte e il telefono
  **pulsano**;
- lo **zoom è progressivo** (pochi fotogrammi, il punto sotto il cursore resta fermo) e il trascinamento
  **continua per inerzia** e rallenta; durante il trascinamento la mappa viene ridisegnata, senza bordi vuoti;
- a zoom bassi le **destinazioni vicine sono raggruppate** in una pallina con dentro il **numero di IP**
  (anche quando stanno tutti nella stessa città): passandoci sopra compare l'elenco, il clic ingrandisce lì;
- ingrandendo, gli **IP che il database colloca nello stesso punto si aprono** in puntini distinti attorno
  alla città (dallo zoom 4, sempre più distanziati man mano che si ingrandisce), ognuno con la sua linea, il
  suo colore e il suo dettaglio al passaggio del mouse e al clic;
- gli **stati si colorano in base al traffico** scambiato (più chiaro = più byte, cinque livelli; fino allo
  zoom 5, con i contorni semplici 1:110m di `assets/world.json`). Il pulsante `◐` accanto alla mappa lo accende
  e lo spegne (`map_heat` in `config.json`).

### Grafo

Lo stesso tipo di grafo di OsintGraph (cerchi bianchi con bordo colorato, icona dell'app dentro, etichette in
grassetto, collegamenti curvi, disposizione a forze): **telefono → app → organizzazione/ASN → destinazione**.
Clic = evidenzia il nodo e i vicini (e mostra i dettagli), doppio clic su app/organizzazione = richiude il
ramo, doppio clic su un'app nell'elenco a destra = **profilo dell'app** (etichetta, icona, versione, permessi
con quelli sensibili in giallo, destinazioni). Le destinazioni non fidate hanno il colore della scala di
pericolosità. Serve il database ASN (scheda Config); senza, tutte le destinazioni finiscono sotto
"organizzazione sconosciuta". Filtri dell'elenco app, Fidate/Non fidate e *Solo connessioni nuove* valgono
anche qui.

Riquadro **LAYOUT** in basso a sinistra, come in OsintGraph: **Gerarchico** (predefinito all'apertura, evidenziato
in verde: albero telefono → app → organizzazione → destinazione, padri centrati sui figli), **Organico** (a forze),
**Circolare** (tutti i nodi su un cerchio, in ordine di ramo), **Griglia**, e **Riduci incroci**: ripete la disposizione
organica con semi diversi per qualche secondo e tiene quella con meno collegamenti che si intersecano (il
risultato, es. "5 incroci dopo 12 tentativi", compare sotto la legenda). Nei layout statici i nodi nuovi che
arrivano dal vivo vengono ridisposti con lo stesso schema; ⟳ ridispone con il layout scelto. Le icone dei nodi
(telefono, organizzazione, globo delle destinazioni) sono disegnate a linee sottili sul canvas, le icone delle
app ritagliate in un cerchio; i collegamenti sono linee fini (spessore in scala logaritmica con i byte).
Le **etichette non si sovrappongono**: vengono scritte prima quelle più importanti (telefono, nodo selezionato,
app, organizzazioni, poi le destinazioni con più collegamenti); una che finirebbe sopra un'altra viene abbreviata
e, se non basta, nascosta. Passando con il mouse sopra un nodo compare sempre il **nome completo**.

Il **traffico è animato come sulla mappa**: su ogni collegamento (telefono → app → organizzazione → destinazione)
scorrono gli stessi impulsi con la scia, colorati in uscita e chiari in entrata, tanti più quanti sono i byte al
secondo che passano di lì; le destinazioni con connessioni ancora aperte hanno un anello che pulsa. Con un nodo
selezionato si animano solo i suoi collegamenti.

### Timeline

Traffico per app nel tempo: aree impilate, in uscita sopra e in entrata sotto, finestra 2/5/15/30 minuti,
clic sulla legenda per nascondere un'app, cursore con i valori al passaggio del mouse.

### DNS

Query e risposte DNS viste dall'agent (ora, app, dominio, tipo, risposte, esito, server, tempo di risposta),
con i domini risolti ma mai contattati. Se un'app parla direttamente con un resolver DoH/DoT (`dns.google`,
`1.1.1.1`…) viene segnalato: quelle query non passano dal DNS di sistema e qui non compaiono.

### Alert

Eventi che meritano uno sguardo, ciascuno una volta: nuova destinazione non fidata, nuovo paese, porta
insolita, dominio/IP in una lista di reputazione (tracker, malware, nodo di uscita Tor), VPN (dal nome
dell'organizzazione nel db ASN, indicativo), DNS cifrato. Clic su un alert = dettagli della destinazione.

### Sessioni

Ogni Start registra una sessione (connessioni, DNS, app, alert) in `pc/sessions/<telefono>/<data>.json.gz`,
salvata ogni minuto e alla chiusura. Il telefono è riconosciuto da IMEI e MAC Wi-Fi se leggibili, altrimenti
(Android 10+ senza root, cioè quasi sempre) da **numero di serie + Android ID**. Seleziona due sessioni dello
stesso telefono (Ctrl+clic) e premi *Confronta*: destinazioni nuove/scomparse/cambiate, nuove app,
organizzazioni e paesi.

**Registrazione e replay.** La registrazione è sempre attiva: oltre allo stato finale, ogni sessione salva tutti
gli eventi ricevuti dal telefono con l'istante di arrivo (nuova connessione, nome scoperto dopo, chiusura,
contatori dei byte, query DNS con risposta, scheda app). Durante il monitor il pulsante **Segnalibro** nella
barra laterale salva nella sessione una nota ("ho aperto Instagram") con l'orario e, se c'è il telefono, uno
screenshot via `adb exec-out screencap` (`pc/sessions/<telefono>/<sessione>-mark-N.png`). Nel tab Sessioni
**Rivedi** apre la sessione nel replay: in basso compare la barra con play/pausa, ⏮, velocità 1x/10x/60x, il
cursore trascinabile con l'orario e i marcatori verdi dei segnalibri (clic = salto all'istante e nota nei
Dettagli, tasto destro = apre lo screenshot). Liste, mappa, grafo, timeline, DNS e alert mostrano solo ciò che
esisteva all'istante scelto, con le connessioni che compaiono nell'ordine reale: gli eventi vengono rimandati a
un monitor dedicato, e tornare indietro vuol dire ripartire dall'inizio fino al nuovo istante (pochi
millisecondi). Durante il replay il monitor dal vivo è fermo (per rivedere una sessione bisogna prima premere
Stop); *Esci dal replay* o *Start* riportano alla modalità dal vivo. Le sessioni salvate da versioni precedenti
(senza eventi) si aprono e si confrontano ma non si possono rivedere (colonna *Replay* = —).

Nel menu di sinistra, sezione **Aiuto**, il pulsante **📖 Manuale** apre `pc/docs/manual/<lingua>/MANUAL.md`
nella lingua impostata (inglese se manca, poi italiano) **formattato in una finestra del programma**, senza
barra del titolo come le altre (`gui/manual.py`, interprete Markdown interno, nessuna libreria esterna): indice
dei capitoli a sinistra, titoli, grassetto/corsivo/codice, elenchi annidati, tabelle, immagini adattate alla
larghezza (clic = immagine intera), link interni che saltano al capitolo ed esterni nel browser. Se non c'è
nessun manuale lo dice nel registro. La cartella `docs/` viene inclusa nella build in cartella.
In alto a sinistra c'è la **ricerca** (`Ctrl+F`): evidenzia tutte le occorrenze nel testo e nelle tabelle, mostra
"3 / 12", `Invio` o `F3` = successiva, `Maiusc+Invio` = precedente, `Esc` svuota la ricerca (un secondo `Esc`
chiude la finestra).

### Config

- **Agent Android · APK**: quale file .apk Start installa e avvia sul telefono. Vuoto = predefinito
  (`pc/agent.apk` oppure l'ultima build in `android/app/build/outputs/apk`); *Sfoglia…* sceglie un altro file
  (salvato in `pc/config.json`, voce `agent_apk`). Il riquadro legge dal file package, versione e dimensione
  (senza strumenti esterni) e avvisa se non è l'agent DroidSnex. Da qui non si installa niente: l'installazione
  avviene allo Start e la rimozione allo Stop (o alla chiusura/crash, vedi sopra).
- **Percorsi relativi in `config.json`**: il database città e l'APK scelti vengono salvati relativi alla cartella
  del programma (`pc/` da sorgente, la cartella di `DroidSnex.exe` impacchettato) quando stanno lì dentro, es.
  `data/dbip-city-lite.mmdb` o `agent.apk`: la cartella si può spostare o copiare altrove senza toccare la
  configurazione. Un file fuori dalla cartella resta con il percorso assoluto. Un `config.json` vecchio con
  percorsi assoluti viene convertito al primo salvataggio.
- **La tua posizione**: latitudine e longitudine del telefono (il punto da cui partono le linee). Quattro modi,
  dal più preciso al meno:
  - *Dal telefono (GPS)*: legge dal telefono collegato l'ultima posizione nota (GPS, fused o rete) con
    `adb shell dumpsys location` (`droidsnex/phoneloc.py`). Precisione di metri, niente internet, nessun
    permesso in più per l'agent. Sceglie la più recente e precisa e mostra sorgente, precisione ed età
    (es. `GPS · ±6 m · 1 min fa`). Serve la localizzazione accesa e che un'app l'abbia usata di recente:
    altrimenti lo dice e resta la posizione di prima.
  - **clic destro sulla mappa** → *Imposta qui la mia posizione*.
  - a mano, scrivendo latitudine e longitudine e premendo *Salva posizione*.
  - *Rileva dal mio IP pubblico*: il programma chiede l'IP ad `api.ipify.org` e lo cerca nel database locale.
    È solo indicativo: l'IP indica dove sta il provider e può sbagliare di decine di chilometri.

  Con i primi due il nome è quello della città più vicina sulla mappa e lo stato (usato dalla scala di
  rischio per "stato diverso dal tuo") viene ricavato dai contorni degli stati.
- **Database città · DB-IP City Lite**: *Scarica / aggiorna* scarica da db-ip.com il file del mese
  (`dbip-city-lite-AAAA-MM.mmdb.gz`, ~60 MB, licenza CC BY 4.0) e lo salva come
  `pc/data/dbip-city-lite.mmdb`. Con *Scegli file .mmdb…* puoi usare anche un `GeoLite2-City.mmdb`.
  Il formato .mmdb è letto da DroidSnex stesso, senza moduli in più.
- **Mappa vettoriale · livello città** (l'unico tipo di mappa): disegnata dal programma con i dati di Natural
  Earth (pubblico dominio), quindi nitida a ogni zoom: terre, coste, laghi, fiumi, confini di stato e di
  regione, nomi delle città. *Scarica mappa* scarica una volta il livello città 1:10m (~60 MB di GeoJSON da
  GitHub `nvkelso/natural-earth-vector`, convertiti in `pc/data/vector-10m.json.gz`, ~8 MB, fino allo zoom 11);
  poi funziona senza rete. Finché non è scaricata si vede la versione base inclusa 1:50m
  (`pc/droidsnex/gui/assets/vector-50m.json.gz`, ~0,9 MB, stati e grandi città). Le tile sono disegnate in un
  thread a parte a risoluzione doppia e poi ridotte. *Mappa scura* usa i colori dell'interfaccia.
  La vecchia cartella `pc/data/tiles/` (tile OSM/CARTO delle versioni precedenti) non serve più e si può cancellare.
- **Organizzazioni degli IP · DB-IP ASN Lite**: *Scarica / aggiorna* scarica il database ASN del mese
  (`dbip-asn-lite-AAAA-MM.mmdb.gz`, ~8 MB, CC BY 4.0) in `pc/data/dbip-asn-lite.mmdb`. Serve per la colonna
  ORG, per il grafo e per riconoscere le VPN. Va bene anche `GeoLite2-ASN.mmdb` o `ip2asn-combined.tsv.gz`.
- **Liste di reputazione**: *Scarica / aggiorna liste* scarica (solo da qui, mai in automatico) in
  `pc/data/reputation/` le liste StevenBlack hosts (pubblicità e tracker, MIT), URLhaus di abuse.ch (domini
  malware, CC0) e l'elenco dei nodi di uscita Tor (check.torproject.org). Le destinazioni in lista hanno il
  badge nella colonna REP., un colore della scala di pericolosità e un alert.
- **Lingua**: italiano, inglese, tedesco, francese, spagnolo, olandese, polacco, greco o albanese. Il
  cambio è immediato (l'interfaccia si ricostruisce senza fermare il monitor). La stessa lingua viene
  passata all'app sul telefono a ogni Start (`am start ... --es lang <codice>`): l'app la salva e la usa
  anche per le notifiche. I testi del PC sono in `pc/droidsnex/i18n_strings.py` (chiave = testo italiano,
  una colonna per lingua), quelli dell'app in `android/.../Strings.kt`.

- **Aggiornamenti**: *Controlla aggiornamenti* legge l'indirizzo scritto nel campo (`update_url` in
  `config.json`) e dice se c'è una versione più nuova di quella installata, con il collegamento alla pagina.
  Parte **solo dal pulsante**, non scarica e non installa niente (`droidsnex/updates.py`). L'indirizzo predefinito è
  `https://github.com/tingon11/DroidSnex` (vengono lette le sue release: serve almeno una release pubblicata con
  il numero di versione nel tag, es. `v1.0.1`); può essere un altro progetto GitHub oppure un
  file JSON proprio: `{"version": "1.2.0", "url": "https://…", "notes": "…"}`. Solo `https://`.

Impostazioni in `pc/config.json`. Attribuzioni mostrate sulla mappa: © OpenStreetMap contributors (ODbL),
IP Geolocation by DB-IP (CC BY 4.0).

### Tabella live

```
DroidSnex — Pixel 7 — VPN attiva — 412 connessioni — stato: collegato (eventi recuperati: 0)
raggruppa: dest+app | ordina: ultima vista | DNS: visibili
 DESTINAZIONE               PORTE       APP                       CONN  PRIMA    ULTIMA    TRAFF ORG
●graph.facebook.com         443         com.whatsapp                12  16:02:11 16:07:40   212K AS32934 FACEBOOK (US)
 i.instagram.com            443         com.instagram.android       31  16:01:58 16:07:39     3M AS32934 FACEBOOK (US)
 r3---sn-x.googlevideo.com  443         com.google.android.youtube   4  16:05:02 16:07:12    48M AS15169 GOOGLE (US)
```
`●` indica connessioni ancora aperte. Tasti: `q` esci, `e` esporta, `s` cambia ordinamento, `g` cambia
raggruppamento (destinazione+app / destinazione / app), `d` mostra/nasconde il DNS, `/` filtro, frecce e PgUp/PgDn per scorrere.
In modalità `--plain` (o senza curses) i comandi si digitano seguiti da Invio.

### Da dove arriva il nome della destinazione

In ordine di priorità: **SNI** del ClientHello TLS → header **Host** HTTP → **cache DNS** del telefono
(le risposte DNS passano dalla VPN, quindi l'agent sa quale dominio corrisponde a ogni IP) →
**reverse DNS** fatto dal PC → IP nudo. La colonna `host_src` nell'export dice quale fonte è stata usata.

### ASN / organizzazione (facoltativo)

Il modo più semplice è il pulsante nella scheda Config (DB-IP ASN Lite). In alternativa scarica
`ip2asn-combined.tsv.gz` da <https://iptoasn.com> e mettilo in `pc/` o `pc/data/` (viene trovato da solo),
oppure usa `--asn-db FILE` (anche `GeoLite2-ASN.mmdb`). Senza db la colonna ORG resta vuota e tutto il resto
funziona.

### Export

Con `e` (o `--export-on-exit` / `--duration`) vengono creati in `pc/captures/`:
- `droidsnex-AAAAMMGG-hhmmss.csv` — una riga per connessione (timestamp, app, UID, protocollo, IP/porte, host e fonte, ASN, byte, errori);
- `.json` — gli stessi dati;
- `.pcapng` — apribile con **Wireshark**. Contiene, per ogni connessione, il pacchetto di apertura
  ricostruito (SYN TCP o datagramma UDP; per il DNS la query con il nome) con i veri IP/porte/orari,
  un commento con app, UID, host e byte (`pkt_comment` / *Commenti pacchetto*), e un blocco di risoluzione
  nomi IP → dominio. È un file **sintetico**: l'agent invia solo metadati, non il traffico.
  Filtro utile in Wireshark: `frame.comment contains "com.whatsapp"`.

**Report HTML** (pulsante nel menu di sinistra, sezione Dati, oppure *Report* nella scheda Sessioni per una
sessione salvata): `pc/captures/droidsnex-report-<sessione>.html`, un file solo, senza collegamenti esterni,
aperto subito nel browser. Contiene riepilogo, dati del telefono, mappa (stati colorati per traffico e linee
verso le città), destinazioni non fidate in ordine di pericolosità con i motivi, destinazioni fidate, traffico
per app e per stato, alert e segnalibri con gli screenshot incorporati. È nella lingua dell'interfaccia; per
il **PDF** si usa *Stampa → Salva come PDF* del browser (in stampa passa da solo ai colori chiari). Il report
riguarda la sessione in corso, quella in replay oppure quella scelta nell'elenco (`droidsnex/report.py`).

Inoltre lo stream grezzo viene sempre salvato in `pc/captures/stream-*.jsonl` (disattivabile con `--no-log`).

## Protocollo dello stream

JSON-lines su `127.0.0.1:8888` del telefono. Appena connesso, il client può inviare
`{"cmd":"since","seq":N}` per ricevere gli eventi con numero di sequenza maggiore di N
(l'agent conserva gli ultimi 20.000). Eventi:

```json
{"ev":"hello","agent":"droidsnex","version":1,"instance":"3fa1c2d0","last_seq":120,"replay":120,"vpn":true}
{"ev":"conn","seq":121,"id":57,"ts":1699999999,"ts_ms":1699999999123,"app":"com.whatsapp","uid":10187,"proto":"TCP","ipver":4,"src_ip":"10.215.173.1","src_port":41234,"dst_ip":"157.240.1.1","dst_port":443,"host":"graph.facebook.com","host_src":"dns"}
{"ev":"update","seq":122,"id":57,"ts":1699999999,"host":"graph.facebook.com","host_src":"sni"}
{"ev":"close","seq":160,"id":57,"ts":1700000030,"bytes_out":2311,"bytes_in":18734,"duration_ms":31022}
{"ev":"bytes","seq":158,"ts":1700000029,"flows":[[57,2100,17950],[58,640,1200]]}
{"ev":"status","seq":1,"vpn":true,"ipv6":false,"dns_upstream":"192.168.1.1","ts":1699999990}
{"ev":"ping","ts":1700000035,"vpn":true}
{"ev":"dns","seq":130,"ts":1700000001,"app":"com.whatsapp","uid":10187,"qname":"graph.facebook.com","qtype":"A","rcode":"NOERROR","answers":["157.240.1.1"],"cnames":[],"server":"192.168.1.1","rtt_ms":18,"ttl":60,"conn":57}
{"ev":"app","pkg":"com.whatsapp","uid":10187,"label":"WhatsApp","version":"2.24.1","system":false,"installed":1690000000,"updated":1699000000,"target_sdk":34,"perms":[{"name":"android.permission.CAMERA","granted":true}],"icon":"<PNG 64px in base64>"}
```
`dns` (query e risposta) e `app` (scheda dell'app, una volta per app) sono stati aggiunti con le schede DNS,
Grafo e il profilo dell'app: **l'APK va ricompilato** perché un agent più vecchio non li manda (il PC
funziona lo stesso, senza quelle informazioni).
`bytes` arriva ogni secondo con i contatori (id, byte in uscita, byte in entrata) delle connessioni aperte
che sono cambiati; non viene conservato nel buffer di ripresa. Puoi leggerlo anche a mano: `adb forward tcp:8888 tcp:8888` e poi `nc 127.0.0.1 8888`.

## Disconnessione del cavo

- Sul telefono la cattura continua anche senza PC; gli eventi restano nel buffer.
- Il PC se ne accorge (socket chiuso o nessun dato/ping per 15 s), aspetta che il device ricompaia
  in `adb devices`, rifà `adb forward` (adb lo perde a ogni disconnessione) e si ricollega chiedendo
  gli eventi persi. Se l'agent non risponde, rilancia la cattura sul telefono.
- Se l'agent è stato riavviato (nuovo `instance`), il PC si risincronizza da zero senza duplicati.

## Come funziona (in breve)

1. **VpnService** crea un'interfaccia TUN con route `0.0.0.0/0` (e `::/0` se la rete ha IPv6) e un
   DNS virtuale `10.215.173.2`: il sistema invia lì tutti i pacchetti IP delle app. L'agent stesso
   è escluso dalla VPN (`addDisallowedApplication`) e i suoi socket sono `protect()`-ati, quindi non c'è loop.
2. Il thread lettore prende i pacchetti dal TUN; **Forwarder** li analizza: per ogni SYN TCP apre un
   `SocketChannel` reale verso la destinazione e "recita" la parte del server verso l'app (SYN-ACK,
   numeri di sequenza, finestre, ritrasmissione, FIN/RST); per l'UDP apre un `DatagramChannel` per flusso.
   Le query al DNS virtuale vanno al DNS reale della rete. Le risposte vengono reimpacchettate in IP e
   scritte nel TUN. **La rete del telefono continua a funzionare normalmente.**
3. Durante il passaggio si leggono solo header e primi byte: risposte DNS, SNI del ClientHello, Host HTTP.
4. L'UID dell'app viene da `ConnectivityManager.getConnectionOwnerUid()` (Android 10+, consentito alla VPN attiva)
   o da `/proc/net/*` (Android 7-9), e viene tradotto in nome pacchetto.

## Troubleshooting

**"Device non autorizzato" / `unauthorized` in `adb devices`**
Sblocca il telefono e accetta il popup del debug USB. Se non compare: *Opzioni sviluppatore >
Revoca autorizzazioni debug USB*, stacca e riattacca il cavo, `adb kill-server && adb start-server`.
Usa un cavo dati (non solo ricarica) e imposta la modalità USB su *Trasferimento file*.

**Il dialog "Richiesta di connessione" VPN compare ogni volta o la VPN non parte**
- Il programma esegue `adb shell appops set com.droidsnex.agent ACTIVATE_VPN allow`; alcuni produttori lo
  ignorano: in quel caso tocca **OK** sul telefono (serve una volta sola finché non revochi).
- Verifica a mano: `adb shell appops get com.droidsnex.agent ACTIVATE_VPN` deve dire `allow`.
- *Impostazioni > Rete e Internet > VPN*: se un'altra app è impostata come **VPN sempre attiva** con
  *Blocca connessioni senza VPN*, disattivala, altrimenti DroidSnex non può subentrare.
  Android consente una sola VPN attiva: avviare DroidSnex disconnette le altre.
- Profilo di lavoro / dispositivo aziendale: la policy può vietare VPN di terze parti.
- Se l'app risulta "Consenso VPN rifiutato", aprila sul telefono e tocca *Avvia*.

**La VPN si ferma da sola dopo un po'**
Batteria: *Impostazioni > App > DroidSnex > Batteria > Senza restrizioni* (il programma prova già con
`dumpsys deviceidle whitelist`). Su MIUI/EMUI/OneUI abilita anche l'avvio automatico/attività in background.

**Notifica assente o servizio terminato su Android 13+**
`adb shell pm grant com.droidsnex.agent android.permission.POST_NOTIFICATIONS`.

**"l'agent sul telefono non risponde"**
La cattura è ferma: `python run.py start`, oppure apri l'app e tocca *Avvia*. Controlla che nessun altro
programma sul PC usi la porta 8888 (in alternativa `--port 9999`, il forward diventa `tcp:9999 tcp:8888`).

**Molte destinazioni senza nome**
- *DNS privato* (Impostazioni > Rete > DNS privato) impostato su un provider specifico: le query DNS sono
  cifrate (DoT) e la cache non si riempie. Impostalo su *Automatico* o *Disattivato* durante l'analisi.
- Chrome e altre app possono usare DNS-over-HTTPS o QUIC (HTTP/3 su UDP 443): per il QUIC lo SNI non viene
  estratto, il nome arriva dalla cache DNS o dal reverse DNS del PC.
- Con Encrypted Client Hello (ECH) lo SNI visibile è quello pubblico del CDN.

**App mostrata come `unknown` o `uid:NNNNN`**
Su Android 7-9 l'attribuzione via `/proc` può fallire per connessioni brevissime. `android.dns` indica il
resolver di sistema (le query DNS le fa il sistema per conto delle app).

**Limiti noti**
ICMP (ping) non viene inoltrato; IPv6 viene catturato solo se la rete ne è dotata; i pacchetti IP
frammentati vengono scartati; il traffico va un po' più lento rispetto a senza VPN.

## Privacy e sicurezza

- L'agent ascolta solo su `127.0.0.1` del telefono: dal Wi-Fi non è raggiungibile. Il PC lo raggiunge solo
  via adb, cioè con il debug USB autorizzato. Nota: le altre app sullo stesso telefono potrebbero in teoria
  collegarsi alla porta locale: ferma la cattura quando non ti serve (`python run.py stop`).
- Nessun dato viene inviato altrove: i log restano in `pc/captures/` sul tuo PC. Le uniche richieste
  verso Internet del programma PC sono quelle che avvii tu dal tab Config (download del database DB-IP,
  della mappa Natural Earth, di adb da Google, richiesta dell'IP pubblico ad api.ipify.org) e il reverse DNS degli IP, disattivabile.
- Usalo sui dispositivi di cui sei proprietario o che sei autorizzato ad analizzare.
