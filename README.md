# DroidSnex

**English** · [Italiano](README.it.md)

> 📖 **User manual** in 9 languages, with screenshots: [MANUAL.md](MANUAL.md) · [English manual](pc/docs/manual/en/MANUAL.md)

Network connection monitor for an Android phone, viewed from the PC over a USB cable.
It shows in real time **which destinations (IP, domain, port) every app connects to**.
No root is needed, certificates are not intercepted and content is not decrypted:
only destination metadata is collected. It is meant for analysing **your own devices**.

The approach (local VPN + user-space TCP/UDP stack) is the same as tools like PCAPdroid;
the code in this repository is written from scratch.

```
 ┌──────────────── Phone ───────────────────┐            ┌────────────── PC ──────────────┐
 │  App ──► TUN (VpnService) ──► agent      │            │                                │
 │                │  reads the headers      │            │  droidsnex (Python)            │
 │                │  DNS / SNI / Host       │   USB      │   ├─ adb install / appops      │
 │                ▼                         │  (adb      │   ├─ adb forward tcp:8888      │
 │       "protected" sockets ──► Internet   │  forward)  │   ├─ live table                │
 │                                          │◄──────────►│   ├─ reverse DNS, ASN          │
 │  server 127.0.0.1:8888 (JSON-lines) ─────┼────────────┼──►└─ export CSV/JSON/pcapng     │
 └──────────────────────────────────────────┘            └────────────────────────────────┘
```

## Layout

```
android/                 Android "agent" app (Kotlin, no external dependencies)
  app/src/main/java/com/droidsnex/agent/
    CaptureService.kt    VpnService: sets up the TUN, reader thread, JSON events
    net/Forwarder.kt     user-space TCP/UDP stack (pass-through to protected sockets)
    net/Packet.kt        parsing and building of IPv4/IPv6, TCP, UDP packets, checksums
    inspect/Dns.kt       DNS query/response parsing (IP -> domain cache, "dns" events to the PC)
    AppInfoReporter.kt   app card (label, icon, version, permissions) -> "app" event to the PC
    inspect/HostSniffer.kt  SNI from the TLS ClientHello, HTTP Host header
    AppResolver.kt       connection -> UID -> package name
    EventServer.kt       TCP server 127.0.0.1:8888, buffer for resuming after a disconnect
    MainActivity.kt      minimal UI: status, counter, start/stop
  app/src/test/...       JVM tests of the network stack
pc/                      PC program (Python 3.9+, standard library only)
  run.py                 entry point (command line)
  gui.py                 CustomTkinter graphical interface (droidsnex/gui/, assets in droidsnex/gui/assets/)
  droidsnex/             adb, stream, aggregation, resolution, TUI, export
    geo.py               .mmdb reader (DB-IP City Lite / GeoLite2) and database download
    platform_tools.py    download of adb (Android Platform Tools) into the pc/tools folder
    scrcpy.py            download of scrcpy (official release) into pc/tools/scrcpy and mirroring launch
    ipinfo.py            IP detail: PTR, RDAP, cloud ranges, TLS certificate, services with an API key
    gui/ipdetail.py      "IP detail" window and saving of link + IP
    vector.py            Natural Earth vector map: conversion, 1:10m download, tile drawing
    gui/mapview.py       world map with animated connections
    gui/graphview.py     OsintGraph-style force graph (phone, apps, organisations, destinations)
    gui/timeline.py      per-app traffic over time
    gui/analysis.py      Graph, Timeline, DNS, Alerts, Sessions tabs and app profile
    gui/welcome.py       blocking start window: language choice and acceptance of the terms
    gui/manual.py        manual window: formatted Markdown, table of contents, images, links
    risk.py              danger scale (white -> purple) of untrusted destinations
    alerts.py            alert rules
    reputation.py        reputation lists (trackers, malware, Tor) and VPN detection
    sessions.py          saved sessions (with events and bookmarks) and comparison
    apkinfo.py           package and version of an APK file (binary manifest), for the Android agent box
    guard.py             guardian: separate process that uninstalls the agent if the PC program crashes
    paths.py             folders: resources bundled in the exe (BUNDLE_DIR) and working files (HOME_DIR)
    terms.py             terms of use and disclaimer in 9 languages (start window, TERMS.md)
    proc.py              external processes (adb, scrcpy, guardian) without console windows on Windows
    replay.py            session replay: events re-sent to a dedicated monitor, timeline recomputed
    report.py            HTML session report (a single file, printable to PDF from the browser)
    updates.py           check for a new version, only from the button in Config
  docs/manual/<lang>/    user manual (MANUAL.md + screenshots) in 9 languages, see MANUAL.md
  data/                  (created by Config) city and ASN databases, map, reputation lists
  sessions/              (created by Start) recorded sessions, one folder per phone
  tools/make_world.py    regenerates country outlines with ISO codes (simple background, coloured countries, report)
  tools/make_vector.py   regenerates the bundled 1:50m vector map
  tools/fake_agent.py    simulated agent to try the PC side without a phone
  tools/build_exe.py     DroidSnex.exe in a folder (PyInstaller), with --apk it rebuilds the agent
.github/workflows/       automatic APK build on GitHub Actions
```

## Requirements

**Phone**
- Android 7.0 or later (Android 10+ recommended: attributing connections to apps is more reliable).
- Developer options enabled: *Settings > About phone > tap "Build number" 7 times*.
- *USB debugging* enabled (*Settings > System > Developer options > USB debugging*).
- On the first connection accept the **"Allow USB debugging?"** popup, ticking *Always allow from this computer*.
- On Xiaomi/MIUI/HyperOS also enable *Install via USB* and *USB debugging (Security settings)*.

**PC**
- `adb` (Android Platform Tools), **only the one in the program folder**: DroidSnex never uses the system adb
  (`PATH`) or the Android SDK one, and never downloads it by itself. On first launch open the GUI and press
  **Config > ADB · Android Platform Tools > Download / update from Google**: the program downloads the official
  zip (`dl.google.com/android/repository/platform-tools-latest-<os>.zip`) and extracts it into
  `pc/tools/platform-tools/`, without installing anything on the system and without touching `PATH`. Until it is
  there, the GUI shows a warning and the command line stops with the same message.
- Python 3.9 or later. No mandatory packages.
  Optional: `pip install windows-curses` on Windows for the full-screen table.
- To build the APK: JDK 17 or 21 and the Android SDK (installed by Android Studio), or GitHub Actions (see below).

Check:
```bash
pc/tools/platform-tools/adb version     # Windows: pc\tools\platform-tools\adb.exe
pc/tools/platform-tools/adb devices     # the serial must appear with state "device"
```

## Building the APK

The Android agent is a Gradle project in the `android/` folder (Kotlin, no runtime dependencies).

| Component | Version |
|---|---|
| Gradle | 8.14.3, through the bundled wrapper (`gradlew` / `gradlew.bat`): it downloads itself on first run |
| Android Gradle Plugin | 8.7.3 |
| Kotlin | 2.0.21 |
| JDK | **17 or 21** (Temurin, or a JetBrains Runtime 21). Java 25, bundled with recent Android Studio versions, does **not** work with Kotlin 2.0.21 |
| Android SDK | `compileSdk 35` (SDK Platform 35 + Build-Tools), `minSdk 24` (Android 7.0), `targetSdk 34` |
| Package | `com.droidsnex.agent` |

**Prerequisites**: JDK 17 or 21 with `JAVA_HOME` set (or `java` on the `PATH`) and the Android SDK. The easiest way is
to install Android Studio, which brings the SDK (if its bundled JDK is Java 25, pick a JDK 17/21 in *Settings > Build, Execution, Deployment > Build Tools > Gradle > Gradle JDK*, or set `JAVA_HOME` for the command line). Gradle needs to know where the SDK is: set the
`ANDROID_HOME` variable or create `android/local.properties` (it is in `.gitignore`, never commit it) with one line:

```properties
# Windows
sdk.dir=C\:\\Users\\<user>\\AppData\\Local\\Android\\Sdk
# Linux / macOS
sdk.dir=/home/<user>/Android/Sdk
```

Without Android Studio the SDK *command-line tools* are enough:
`sdkmanager "platforms;android-35" "build-tools;35.0.0" "platform-tools"`.

**From the command line**:
```bash
cd android
./gradlew assembleDebug          # Windows: gradlew.bat assembleDebug
./gradlew assembleRelease        # optional: release build (signed with the debug key, for sideloading)
./gradlew testDebugUnitTest      # optional: JVM tests of the network stack
```
The APKs end up in `android/app/build/outputs/apk/debug/app-debug.apk` and
`android/app/build/outputs/apk/release/app-release.apk`: the PC program finds them there automatically (it takes
the most recent one). Otherwise copy it to `pc/agent.apk`, pass it with `--apk` or pick it in *Config > Android agent*.
In `pc/`, `python tools/build_exe.py --apk` runs `gradlew assembleDebug` and puts the APK next to the exe as
`DroidSnex.apk`.

**With Android Studio**: *File > Open* on the `android/` folder, wait for the Gradle sync, then
*Build > Build App Bundle(s)/APK(s) > Build APK(s)*.

**Without installing anything**: push the repository to GitHub; the workflow
[`.github/workflows/android.yml`](.github/workflows/android.yml) runs the tests, builds the debug APK and
publishes it as the `droidsnex-agent-apk` artifact on the run page (*Actions* tab). It can also be started by
hand from *Actions > Android agent APK > Run workflow*.

## First launch: language and terms of use

On first launch (or when the terms change version) a window appears on top, with no title bar, blocking the rest
of the program: if the language is not yet in `config.json` you choose one of the 9 available, then the full
**terms of use and disclaimer** are shown in the chosen language, for the PC program and for the Android app (use
only on your own or authorised devices, no warranty "AS IS", limitation of liability, data sent to third-party
services through APIs, component licences, governing law). *Accept* becomes active after scrolling the text to
the end: it saves the accepted version and the date in `config.json` (`terms_accepted`, `terms_accepted_at`) and
the program starts. *Decline* closes the program. The text is in `pc/droidsnex/terms.py` (9 languages), in the
`TERMS.md` file (generated with `cd pc && python -m droidsnex.terms > ../TERMS.md`) and in the *Info and
licenses* window (*Terms of use* button).

## Windows executable

`pc/tools/build_exe.py` creates the `pc/dist/DroidSnex/` folder with `DroidSnex.exe`, the agent `DroidSnex.apk`
and the resources next to it (`_internal/`), plus a `DroidSnex-<version>.zip` ready to distribute. It needs
PyInstaller (`pip install pyinstaller` in the same environment as the GUI):

```bat
cd pc
python tools\build_exe.py            # the dist\DroidSnex\ folder (+ zip), with the most recently built APK
python tools\build_exe.py --apk      # first gradlew assembleDebug, then the exe with the freshly built APK
python tools\build_exe.py --console  # exe with a console, to see errors
```

**The APK in the release.** The script takes the most recent agent build among
`android/app/build/outputs/apk/{release,debug}`, `DroidSnex.apk` in the project folder and `pc/agent.apk`, and
copies it next to the exe as **`DroidSnex.apk`**: that way it also ends up in the zip, and the program finds it
by itself.

**Normal build, in a folder.** The `--onefile` option is gone: the build is always the folder one.

**Antivirus.** PyInstaller single-file ("onefile") executables are often flagged by mistake ("The file contains
a virus or potentially unwanted software"): the bootloader extracts itself into a temporary folder and the
heuristics don't like it, and the verdict can change from one build to the next because the hash changes. That is
why only the folder build is made. The script also does not use UPX, embeds the Windows version information and
the icon and excludes unneeded modules. If Windows Security blocks it anyway: add an exclusion for the folder
(Windows Security → Virus & threat protection → Manage settings → Exclusions) and report the false positive to
Microsoft (<https://www.microsoft.com/wdsi/filesubmission>). The detection name is in Windows Security →
Protection history.

In the folder: code, assets (logo, icon, 1:50m map), `DroidSnex.apk`, LICENSE, NOTICE, THIRD_PARTY_NOTICES.md
and LICENSES/. Outside it, and downloaded from the Config tab into the folder next to the exe (`tools/`, `data/`;
if the folder is not writable, into `%LOCALAPPDATA%\DroidSnex`): adb, scrcpy, DB-IP databases, 1:10m map,
reputation lists and cloud ranges, which by licence must not be redistributed. `config.json`, `trusted.json`,
`sessions/` and `captures/` also live next to the exe and **never go into the release** or the repository
(`.gitignore`): `config.json` holds the API keys (VirusTotal etc.) and the home position. The guardian (program
crash) is launched by the exe itself with `--guard`. The paths are in `droidsnex/paths.py` (`BUNDLE_DIR` =
bundled resources, `HOME_DIR` = working files).

## Using the PC program

Full flow (checks adb and the device, installs the APK, grants permissions, starts the VPN, `adb forward`, live table):
```bash
cd pc
python run.py                      # same as: python run.py run
python run.py --apk ../path/app-debug.apk
python run.py -s <serial>          # if you have several devices connected
```

What it does, step by step:
1. `adb devices` — checks that adb is there and the device is connected and **authorised**.
2. `adb install -r -g agent.apk` — installs or updates the agent, granting runtime permissions.
3. Permissions: `appops set com.droidsnex.agent ACTIVATE_VPN allow` pre-authorises the VPN (usually the
   "Connection request" dialog doesn't even show up), `pm grant ... POST_NOTIFICATIONS`,
   exclusion from battery optimisation (`dumpsys deviceidle whitelist`).
4. `adb shell am start -n com.droidsnex.agent/.MainActivity -a com.droidsnex.agent.START` — starts the capture.
   If the phone still shows the VPN dialog, unlock the screen and tap **OK**: the program waits.
5. `adb forward tcp:8888 tcp:8888` — port 8888 on the PC is connected, through the USB cable,
   to port 8888 on the phone's loopback, where the agent streams the events.
6. Connection to `127.0.0.1:8888`, reading of the stream and live table.

Other commands:
```bash
python run.py install [--apk FILE]   # install + permissions only
python run.py start | stop           # start / stop the VPN on the phone
python run.py monitor                # agent already running: forward + table only
python run.py devices                # list adb devices
python run.py uninstall
python run.py --duration 60          # collects for 60 s, exports and exits (no TUI)
python run.py --hide-dns --no-rdns --plain --export-on-exit
python run.py --keep-agent           # on exit leave the agent installed and running
```

### Graphical interface

```bash
cd pc
pip install -r ../requirements.txt      # everything needed (customtkinter, pillow; on Windows also windows-curses)
python tools/make_logo.py               # optional: regenerates logo and icon (needs Panchang installed)
python gui.py                           # uses adb and the connected phone
python gui.py --demo 127.0.0.1:8899     # try it without a phone (with tools/fake_agent.py running)
```
Same style as AndrOsint (Seity dark theme, `#7b95dd` accent, two-tone logo in Panchang Semibold,
window without a title bar on Windows): header with logo, device choice and status;
command column (a single *Start monitor* button that becomes *Stop monitor* while monitoring, *Export*, options,
ADB/device/VPN/stream status); counters (with outgoing ↑ and incoming ↓ traffic per second), details panel and log.
In the centre the tabs: **Config**, **Untrusted**, **Trusted**, **Map**, **Graph**, **Timeline**, **DNS**,
**Alerts**, **Sessions**. Every panel can be detached into a separate window (⧉ button, also without a title
bar) and docked back.

### Agent life cycle (Start / Stop / watchdog)

- **Start** (GUI) or `python run.py`: installs the APK, grants permissions, starts the VPN, runs `adb forward`
  and shows live connections.
- **Stop**, closing the window, exiting the program (also on error or Ctrl+C): the PC stops the VPN,
  removes the forward and **uninstalls the agent** with `adb uninstall`.
- **PC program crash** (hard close, kill, fatal error): on Start the PC also launches a **guardian**, a small
  separate process (`droidsnex/guard.py`) connected to the program through a pipe. If the program dies, the pipe
  closes and the guardian stops the capture, removes the forward and **uninstalls the agent** via adb (it keeps
  trying for 2 minutes if the phone doesn't answer right away; log in `pc/captures/guard.log`). On Stop or a
  regular close the guardian receives "bye" and exits without doing anything.
- **Cable unplugged (or phone unreachable)**: when connecting, the PC program arms a *watchdog* on the agent. If
  for 20 seconds no PC is connected any more, the agent stops the VPN by itself and shows the uninstall request
  (a "DroidSnex stopped – tap to uninstall" notification). Without root an app cannot uninstall itself silently:
  a confirmation tap is needed. On the next Start the PC reinstalls the agent anyway (and removes it on Stop).

### Clear everything and phone screen

In the command column, while the monitor is stopped, **Clear everything** appears (with confirmation): it empties
the connections, DNS queries, alerts, map, graph and timeline of the current session; saved sessions and the
trusted list are kept. **Phone screen** opens the phone's screen with **scrcpy** (Genymobile, Apache 2.0), exactly
like AndrOsint: scrcpy in its own window (max resolution 1024, 4 Mbps, 30 fps, no audio, phone kept awake); mouse
and keyboard inside the window go to the phone (tap, scroll, text); the orientation stays portrait even if the
phone is rotated; the window starts at half the video size (it can be resized); on Windows the window is "owned"
by the DroidSnex one, so it stays above the program (never below) but not above other applications; the button
becomes *Close screen* while the window is open. scrcpy must be downloaded once from the Config tab
(*Download / update from GitHub*, official Windows release into `pc/tools/scrcpy`, never automatically and never
the system one); it uses the adb in the tools folder.

**Detached windows**: Map, Graph, Details and Apps on the map, once detached, have no title bar on Windows, like
the main window: header with the logo (draggable, double click maximises), **⇲ Dock** button and minimise /
maximise / close (the X docks it too).

### Untrusted / Trusted

Live destinations (domain, resolved IPs, ports, app, connections, traffic, first/last seen, ASN) are split into
two tabs: **Untrusted** and **Trusted, in green**; the count is shown next to the tab name.
Untrusted rows are coloured according to a **danger scale** from 0 to 5 (`pc/droidsnex/risk.py`):
**white → yellow → orange → red → fuchsia → purple**, the closer the row gets to purple the more suspicious the
connection. Points are added for every signal: IP only with no name (+1), unknown organisation (+1), country
different from yours (+1, needs your position in Config), encrypted DNS resolver (+1), unusual port (+2), VPN
provider (+3), tracker/advertising (+4), Tor exit node (+4), listed malware (+5). Generic signals reach red at
most: fuchsia and purple are reserved for entries in the reputation lists. The Details panel shows level and
reasons; the same scale colours the map lines and the graph nodes/links (legend at the bottom), with *✕ Untrust
all* (with confirmation) in the Trusted tab. Clicking `✓ TRUST` moves a destination to the trusted ones, clicking
`✕ UNTRUST` moves it back to the untrusted ones. The list is saved in `pc/trusted.json` and stays valid from one
session to the next. Clicking a column title sorts the list by that column (A-Z, smallest to largest); a second
click reverses the order (Z-A). The ▲/▼ arrow in the title shows the active column; the *Sort* menu goes back to
the default orderings.

### Map

**Detachable panels**: Map, Details and Apps on the map have the `⧉` button at the top right that detaches them
into a separate window (movable, resizable, even on a second monitor); `⇲` or closing the window docks them back.
The Details panel keeps its scroll position during live updates.

A small smartphone at your position and a thin line towards the city of every destination:
**green if trusted, red if untrusted**, with the destination dot in the same colour.
Every second the agent sends the bytes of the open connections: dots run along the lines
(coloured = data going out to the destination, white = data coming in to the phone)
and **the line thickness grows with the bytes per second** (logarithmic scale, from 1 to 5 px); lines
with no traffic stay thin and darker. Wheel or double click = zoom, drag = pan, `⌂` = centre on the phone,
`◯` = whole world; hover a dot for the summary, click it for the details.
There is **one line per destination IP**: lines towards the same city fan out (trusted first, then untrusted)
along the way and all arrive at the same point in the city (red if there is at least one untrusted, with a green
border if there are trusted ones too), so they can be seen and clicked one by one. **Lines are clickable** too:
hovering shows the summary, clicking selects the line (highlighted) and the Details panel shows city, apps,
destinations and the list of connections on that line (time, protocol, IP:port, state, bytes out/in). The search
filter applies to the map too. On the right of the map there is the list of the **apps** generating the links
(with the number of connections): tick one or more apps to see only their lines, or use *Show all* / *Hide all*.
After *Hide all* new apps stay hidden too until you tick them. *New connections only* hides all lines present at
that moment and from then on shows only new connections; a second click shows them all again. Above the list,
*All* / *Trusted* / *Untrusted* shows all lines or only the green or only the red ones (combined with the app
filter). Destinations with private IPs (LAN, router DNS) or not in the database are counted separately.

**Animations and reading at a glance** (`gui/mapview.py`):
- the **pulses** on the lines have a trail and are as many and as large as the traffic; lines with ongoing
  traffic have a glow;
- a **new connection** announces itself with a spark leaving the phone and two rings widening on the destination
  (also during a session replay); cities with open connections and the phone **pulse**;
- **zoom is progressive** (a few frames, the point under the cursor stays put) and dragging **continues with
  inertia** and slows down; while dragging the map is redrawn, with no empty edges;
- at low zoom **nearby destinations are grouped** into a ball containing the **number of IPs** (even when they
  are all in the same city): hovering shows the list, clicking zooms in there;
- when zooming in, **IPs the database places at the same point open up** into separate dots around the city
  (from zoom 4, more and more spread out as you zoom in), each with its own line, colour and detail on hover and
  click;
- **countries are coloured by the traffic** exchanged (lighter = more bytes, five levels; up to zoom 5, with the
  simple 1:110m outlines of `assets/world.json`). The `◐` button next to the map turns it on and off (`map_heat`
  in `config.json`).

### Graph

The same kind of graph as OsintGraph (white circles with a coloured border, app icon inside, bold labels, curved
links, force layout): **phone → app → organisation/ASN → destination**.
Click = highlights the node and its neighbours (and shows the details), double click on an app/organisation =
collapses the branch, double click on an app in the list on the right = **app profile** (label, icon, version,
permissions with the sensitive ones in yellow, destinations). Untrusted destinations have the danger-scale colour.
It needs the ASN database (Config tab); without it, all destinations end up under "unknown organisation". App list
filters, Trusted/Untrusted and *New connections only* apply here too.

**LAYOUT** box at the bottom left, as in OsintGraph: **Hierarchical** (default on opening, highlighted in green:
phone → app → organisation → destination tree, parents centred on their children), **Organic** (force-based),
**Circular** (all nodes on a circle, in branch order), **Grid**, and **Reduce crossings**: repeats the organic
layout with different seeds for a few seconds and keeps the one with the fewest intersecting links (the result,
e.g. "5 crossings after 12 attempts", appears under the legend). In static layouts new nodes arriving live are
placed with the same scheme; ⟳ re-lays out with the chosen layout. The node icons (phone, organisation,
destination globe) are drawn with thin lines on the canvas, app icons cropped into a circle; links are fine lines
(thickness on a logarithmic scale with the bytes).
**Labels don't overlap**: the most important ones are written first (phone, selected node, apps, organisations,
then the destinations with the most links); one that would land on top of another is shortened and, if that is
not enough, hidden. Hovering a node always shows the **full name**.

**Traffic is animated as on the map**: on every link (phone → app → organisation → destination) the same pulses
with a trail run, coloured outgoing and light incoming, as many as the bytes per second passing there;
destinations with connections still open have a pulsing ring. With a node selected only its links are animated.

### Timeline

Per-app traffic over time: stacked areas, outgoing above and incoming below, 2/5/15/30-minute window, click on the
legend to hide an app, cursor with the values on hover.

### DNS

DNS queries and responses seen by the agent (time, app, domain, type, answers, result, server, response time),
with domains resolved but never contacted. If an app talks directly to a DoH/DoT resolver (`dns.google`,
`1.1.1.1`…) it is flagged: those queries don't go through the system DNS and don't show up here.

### Alerts

Events worth a look, each one once: new untrusted destination, new country, unusual port, domain/IP in a
reputation list (tracker, malware, Tor exit node), VPN (from the organisation name in the ASN db, indicative),
encrypted DNS. Click on an alert = details of the destination.

### Sessions

Every Start records a session (connections, DNS, apps, alerts) in `pc/sessions/<phone>/<date>.json.gz`, saved
every minute and on close. The phone is recognised by IMEI and Wi-Fi MAC if readable, otherwise (Android 10+
without root, i.e. almost always) by **serial number + Android ID**. Select two sessions of the same phone
(Ctrl+click) and press *Compare*: new/disappeared/changed destinations, new apps, organisations and countries.

**Recording and replay.** Recording is always on: besides the final state, every session saves all events
received from the phone with their arrival time (new connection, name discovered later, close, byte counters, DNS
queries with responses, app card). While monitoring, the **Bookmark** button in the sidebar saves a note in the
session ("I opened Instagram") with the time and, if the phone is there, a screenshot via `adb exec-out
screencap` (`pc/sessions/<phone>/<session>-mark-N.png`). In the Sessions tab **Review** opens the session in
replay: at the bottom the bar appears with play/pause, ⏮, speed 1x/10x/60x, the draggable slider with the time and
the green bookmark markers (click = jump to that moment and note in Details, right click = opens the screenshot).
Lists, map, graph, timeline, DNS and alerts show only what existed at the chosen moment, with connections
appearing in their real order: events are re-sent to a dedicated monitor, and going back means starting again
from the beginning up to the new moment (a few milliseconds). During replay the live monitor is stopped (to review
a session you first have to press Stop); *Exit replay* or *Start* go back to live mode. Sessions saved by earlier
versions (without events) can be opened and compared but not reviewed (*Replay* column = —).

In the left-hand menu, **Help** section, the **📖 Manual** button opens `pc/docs/manual/<language>/MANUAL.md` in the
configured language (English if missing, then Italian; all languages are listed in [MANUAL.md](MANUAL.md))
**formatted in a program window**, without a title bar like the others (`gui/manual.py`, built-in Markdown
renderer, no external library): chapter index on the left, headings, bold/italic/code, nested lists, tables,
images fitted to the width (click = full image), internal links that jump to the chapter and external ones in the
browser. If there is no manual it says so in the log. The `docs/` folder is included in the folder build.
At the top left there is the **search** (`Ctrl+F`): it highlights all occurrences in the text and tables, shows
"3 / 12", `Enter` or `F3` = next, `Shift+Enter` = previous, `Esc` clears the search (a second `Esc` closes the
window).

### Config

- **Android agent · APK**: which .apk file Start installs and launches on the phone. Empty = default
  (`pc/agent.apk` or the latest build in `android/app/build/outputs/apk`); *Browse…* picks another file (saved in
  `pc/config.json`, key `agent_apk`). The box reads package, version and size from the file (without external
  tools) and warns if it is not the DroidSnex agent. Nothing is installed from here: installation happens on
  Start and removal on Stop (or on close/crash, see above).
- **Relative paths in `config.json`**: the chosen city database and APK are saved relative to the program folder
  (`pc/` from source, the folder of the packaged `DroidSnex.exe`) when they are inside it, e.g.
  `data/dbip-city-lite.mmdb` or `agent.apk`: the folder can be moved or copied elsewhere without touching the
  configuration. A file outside the folder keeps its absolute path. An old `config.json` with absolute paths is
  converted on the first save.
- **Your position**: latitude and longitude of the phone (the point the lines start from). Four ways, from the
  most to the least precise:
  - *From the phone (GPS)*: reads the last known position (GPS, fused or network) from the connected phone with
    `adb shell dumpsys location` (`droidsnex/phoneloc.py`). Metre precision, no internet, no extra permission for
    the agent. It picks the most recent and precise one and shows source, accuracy and age
    (e.g. `GPS · ±6 m · 1 min ago`). Location must be on and an app must have used it recently: otherwise it says
    so and the previous position is kept.
  - **right click on the map** → *Set my position here*.
  - by hand, typing latitude and longitude and pressing *Save position*.
  - *Detect from my public IP*: the program asks `api.ipify.org` for the IP and looks it up in the local database.
    It is only indicative: the IP shows where the provider is and can be tens of kilometres off.

  With the first two the name is that of the nearest city on the map and the country (used by the risk scale for
  "country different from yours") is derived from the country outlines.
- **City database · DB-IP City Lite**: *Download / update* downloads the monthly file from db-ip.com
  (`dbip-city-lite-YYYY-MM.mmdb.gz`, ~60 MB, CC BY 4.0 licence) and saves it as `pc/data/dbip-city-lite.mmdb`.
  With *Choose .mmdb file…* you can also use a `GeoLite2-City.mmdb`. The .mmdb format is read by DroidSnex
  itself, with no extra modules.
- **Vector map · city level** (the only map type): drawn by the program from Natural Earth data (public domain),
  so it is sharp at every zoom: land, coasts, lakes, rivers, country and region borders, city names. *Download map*
  downloads the 1:10m city level once (~60 MB of GeoJSON from GitHub `nvkelso/natural-earth-vector`, converted
  into `pc/data/vector-10m.json.gz`, ~8 MB, up to zoom 11); after that it works offline. Until it is downloaded the
  bundled 1:50m base version is shown (`pc/droidsnex/gui/assets/vector-50m.json.gz`, ~0.9 MB, countries and large
  cities). Tiles are drawn in a separate thread at double resolution and then scaled down. *Dark map* uses the
  interface colours. The old `pc/data/tiles/` folder (OSM/CARTO tiles from earlier versions) is no longer needed
  and can be deleted.
- **IP organisations · DB-IP ASN Lite**: *Download / update* downloads the monthly ASN database
  (`dbip-asn-lite-YYYY-MM.mmdb.gz`, ~8 MB, CC BY 4.0) into `pc/data/dbip-asn-lite.mmdb`. It is needed for the ORG
  column, for the graph and to recognise VPNs. `GeoLite2-ASN.mmdb` or `ip2asn-combined.tsv.gz` work too.
- **Reputation lists**: *Download / update lists* downloads (only from here, never automatically) into
  `pc/data/reputation/` the StevenBlack hosts lists (ads and trackers, MIT), abuse.ch URLhaus (malware domains,
  CC0) and the list of Tor exit nodes (check.torproject.org). Listed destinations get the badge in the REP. column,
  a danger-scale colour and an alert.
- **Language**: Italian, English, German, French, Spanish, Dutch, Polish, Greek or Albanian. The change is
  immediate (the interface rebuilds itself without stopping the monitor). The same language is passed to the app
  on the phone at every Start (`am start ... --es lang <code>`): the app saves it and also uses it for
  notifications. The PC texts are in `pc/droidsnex/i18n_strings.py` (key = Italian text, one column per
  language), the app ones in `android/.../Strings.kt`.

- **Updates**: *Check for updates* reads the address written in the field (`update_url` in `config.json`) and
  says whether there is a newer version than the installed one, with the link to the page. It runs **only from the
  button**, and downloads and installs nothing (`droidsnex/updates.py`). The default address is
  `https://github.com/tingon11/DroidSnex` (its releases are read: at least one published release with the version
  number in the tag is needed, e.g. `v1.0.1`); it can be another GitHub project or your own JSON file:
  `{"version": "1.2.0", "url": "https://…", "notes": "…"}`. `https://` only.

Settings in `pc/config.json`. Attributions shown on the map: © OpenStreetMap contributors (ODbL),
IP Geolocation by DB-IP (CC BY 4.0).

### Live table

```
DroidSnex — Pixel 7 — VPN active — 412 connections — state: connected (events recovered: 0)
group: dest+app | sort: last seen | DNS: visible
 DESTINATION                PORTS       APP                       CONN  FIRST    LAST      TRAFF ORG
●graph.facebook.com         443         com.whatsapp                12  16:02:11 16:07:40   212K AS32934 FACEBOOK (US)
 i.instagram.com            443         com.instagram.android       31  16:01:58 16:07:39     3M AS32934 FACEBOOK (US)
 r3---sn-x.googlevideo.com  443         com.google.android.youtube   4  16:05:02 16:07:12    48M AS15169 GOOGLE (US)
```
`●` marks connections that are still open. Keys: `q` quit, `e` export, `s` change sort order, `g` change grouping
(destination+app / destination / app), `d` show/hide DNS, `/` filter, arrows and PgUp/PgDn to scroll.
In `--plain` mode (or without curses) commands are typed followed by Enter.

### Where the destination name comes from

In order of priority: **SNI** from the TLS ClientHello → HTTP **Host** header → the phone's **DNS cache**
(DNS responses go through the VPN, so the agent knows which domain matches each IP) →
**reverse DNS** done by the PC → bare IP. The `host_src` column in the export tells which source was used.

### ASN / organisation (optional)

The simplest way is the button in the Config tab (DB-IP ASN Lite). Alternatively download
`ip2asn-combined.tsv.gz` from <https://iptoasn.com> and put it in `pc/` or `pc/data/` (it is found automatically),
or use `--asn-db FILE` (also `GeoLite2-ASN.mmdb`). Without a db the ORG column stays empty and everything else
works.

### Export

With `e` (or `--export-on-exit` / `--duration`) these are created in `pc/captures/`:
- `droidsnex-YYYYMMDD-hhmmss.csv` — one row per connection (timestamp, app, UID, protocol, IP/ports, host and source, ASN, bytes, errors);
- `.json` — the same data;
- `.pcapng` — opens in **Wireshark**. For every connection it contains the rebuilt opening packet (TCP SYN or UDP
  datagram; for DNS the query with the name) with the real IPs/ports/times, a comment with app, UID, host and
  bytes (`pkt_comment` / *Packet comments*), and an IP → domain name resolution block. It is a **synthetic** file:
  the agent sends only metadata, not the traffic.
  Useful Wireshark filter: `frame.comment contains "com.whatsapp"`.

**HTML report** (button in the left-hand menu, Data section, or *Report* in the Sessions tab for a saved session):
`pc/captures/droidsnex-report-<session>.html`, a single file, with no external links, opened right away in the
browser. It contains a summary, phone data, map (countries coloured by traffic and lines to the cities),
untrusted destinations in order of danger with the reasons, trusted destinations, traffic per app and per
country, alerts and bookmarks with the embedded screenshots. It is in the interface language; for a **PDF** use the
browser's *Print → Save as PDF* (when printing it switches to light colours by itself). The report covers the
current session, the one being replayed or the one chosen in the list (`droidsnex/report.py`).

The raw stream is also always saved in `pc/captures/stream-*.jsonl` (can be turned off with `--no-log`).

## Stream protocol

JSON-lines on the phone's `127.0.0.1:8888`. As soon as it connects, the client can send
`{"cmd":"since","seq":N}` to receive the events with a sequence number greater than N
(the agent keeps the last 20,000). Events:

```json
{"ev":"hello","agent":"droidsnex","version":1,"instance":"3fa1c2d0","last_seq":120,"replay":120,"vpn":true}
{"ev":"conn","seq":121,"id":57,"ts":1699999999,"ts_ms":1699999999123,"app":"com.whatsapp","uid":10187,"proto":"TCP","ipver":4,"src_ip":"10.215.173.1","src_port":41234,"dst_ip":"157.240.1.1","dst_port":443,"host":"graph.facebook.com","host_src":"dns"}
{"ev":"update","seq":122,"id":57,"ts":1699999999,"host":"graph.facebook.com","host_src":"sni"}
{"ev":"close","seq":160,"id":57,"ts":1700000030,"bytes_out":2311,"bytes_in":18734,"duration_ms":31022}
{"ev":"bytes","seq":158,"ts":1700000029,"flows":[[57,2100,17950],[58,640,1200]]}
{"ev":"status","seq":1,"vpn":true,"ipv6":false,"dns_upstream":"192.168.1.1","ts":1699999990}
{"ev":"ping","ts":1700000035,"vpn":true}
{"ev":"dns","seq":130,"ts":1700000001,"app":"com.whatsapp","uid":10187,"qname":"graph.facebook.com","qtype":"A","rcode":"NOERROR","answers":["157.240.1.1"],"cnames":[],"server":"192.168.1.1","rtt_ms":18,"ttl":60,"conn":57}
{"ev":"app","pkg":"com.whatsapp","uid":10187,"label":"WhatsApp","version":"2.24.1","system":false,"installed":1690000000,"updated":1699000000,"target_sdk":34,"perms":[{"name":"android.permission.CAMERA","granted":true}],"icon":"<64px PNG in base64>"}
```
`dns` (query and response) and `app` (app card, once per app) were added with the DNS and Graph tabs and the app
profile: **the APK must be rebuilt** because an older agent doesn't send them (the PC still works, without that
information).
`bytes` arrives every second with the counters (id, bytes out, bytes in) of the open connections that changed; it
is not kept in the resume buffer. You can also read it by hand: `adb forward tcp:8888 tcp:8888` and then
`nc 127.0.0.1 8888`.

## Cable disconnection

- On the phone the capture goes on even without a PC; events stay in the buffer.
- The PC notices (socket closed or no data/ping for 15 s), waits for the device to reappear in `adb devices`,
  redoes `adb forward` (adb loses it on every disconnection) and reconnects asking for the missed events. If the
  agent doesn't answer, it restarts the capture on the phone.
- If the agent was restarted (new `instance`), the PC resynchronises from scratch without duplicates.

## How it works (in short)

1. **VpnService** creates a TUN interface with route `0.0.0.0/0` (and `::/0` if the network has IPv6) and a
   virtual DNS `10.215.173.2`: the system sends all the apps' IP packets there. The agent itself is excluded from
   the VPN (`addDisallowedApplication`) and its sockets are `protect()`-ed, so there is no loop.
2. The reader thread takes the packets from the TUN; **Forwarder** analyses them: for every TCP SYN it opens a real
   `SocketChannel` to the destination and "plays" the server's part towards the app (SYN-ACK, sequence numbers,
   windows, retransmission, FIN/RST); for UDP it opens a `DatagramChannel` per flow. Queries to the virtual DNS go
   to the network's real DNS. The responses are repacked into IP and written to the TUN. **The phone's network
   keeps working normally.**
3. Along the way only headers and the first bytes are read: DNS responses, ClientHello SNI, HTTP Host.
4. The app's UID comes from `ConnectivityManager.getConnectionOwnerUid()` (Android 10+, allowed for the active VPN)
   or from `/proc/net/*` (Android 7-9), and is translated into a package name.

## Troubleshooting

**"Device unauthorized" / `unauthorized` in `adb devices`**
Unlock the phone and accept the USB debugging popup. If it doesn't appear: *Developer options > Revoke USB
debugging authorizations*, unplug and replug the cable, `adb kill-server && adb start-server`.
Use a data cable (not charge-only) and set the USB mode to *File transfer*.

**The VPN "Connection request" dialog shows up every time or the VPN doesn't start**
- The program runs `adb shell appops set com.droidsnex.agent ACTIVATE_VPN allow`; some manufacturers ignore it:
  in that case tap **OK** on the phone (needed only once until you revoke it).
- Check by hand: `adb shell appops get com.droidsnex.agent ACTIVATE_VPN` must say `allow`.
- *Settings > Network & internet > VPN*: if another app is set as **Always-on VPN** with *Block connections
  without VPN*, turn it off, otherwise DroidSnex cannot take over. Android allows only one active VPN: starting
  DroidSnex disconnects the others.
- Work profile / company device: the policy may forbid third-party VPNs.
- If the app says "VPN consent denied", open it on the phone and tap *Start*.

**The VPN stops by itself after a while**
Battery: *Settings > Apps > DroidSnex > Battery > Unrestricted* (the program already tries with
`dumpsys deviceidle whitelist`). On MIUI/EMUI/OneUI also enable autostart/background activity.

**Missing notification or service killed on Android 13+**
`adb shell pm grant com.droidsnex.agent android.permission.POST_NOTIFICATIONS`.

**"the agent on the phone is not responding"**
The capture is stopped: `python run.py start`, or open the app and tap *Start*. Check that no other program on the
PC is using port 8888 (alternatively `--port 9999`, the forward becomes `tcp:9999 tcp:8888`).

**Many destinations without a name**
- *Private DNS* (Settings > Network > Private DNS) set to a specific provider: DNS queries are encrypted (DoT) and
  the cache doesn't fill up. Set it to *Automatic* or *Off* during the analysis.
- Chrome and other apps may use DNS-over-HTTPS or QUIC (HTTP/3 over UDP 443): for QUIC the SNI is not extracted,
  the name comes from the DNS cache or the PC's reverse DNS.
- With Encrypted Client Hello (ECH) the visible SNI is the CDN's public one.

**App shown as `unknown` or `uid:NNNNN`**
On Android 7-9 attribution via `/proc` can fail for very short connections. `android.dns` means the system
resolver (the system makes DNS queries on behalf of the apps).

**Known limits**
ICMP (ping) is not forwarded; IPv6 is captured only if the network has it; fragmented IP packets are dropped;
traffic is a little slower than without the VPN.

## Privacy and security

- The agent listens only on the phone's `127.0.0.1`: it is not reachable from Wi-Fi. The PC reaches it only via
  adb, i.e. with authorised USB debugging. Note: other apps on the same phone could in theory connect to the local
  port: stop the capture when you don't need it (`python run.py stop`).
- No data is sent anywhere else: logs stay in `pc/captures/` on your PC. The only Internet requests made by the PC
  program are the ones you start from the Config tab (download of the DB-IP database, the Natural Earth map, adb
  from Google, public IP request to api.ipify.org) and the reverse DNS of the IPs, which can be turned off.
- Use it on devices you own or are authorised to analyse.
