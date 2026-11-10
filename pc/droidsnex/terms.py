# DroidSnex — termini d'uso ed esclusione di responsabilità.  Copyright (C) 2026 Andrea Cumini <andrea@osintinfo.net>
"""Termini d'uso e disclaimer completo (programma PC e app Android), in 9 lingue.

Vengono mostrati alla prima apertura (gui/welcome.py) e l'accettazione viene salvata in config.json
con la versione del testo (TERMS_VERSION) e la data: se la versione cambia, vengono richiesti di nuovo.
Lo stesso testo e' nella finestra "Informazioni e licenze" e nel file TERMS.md del progetto
(generato da questo modulo: python -m droidsnex.terms > ../TERMS.md).

    text(lang)   -> testo completo nella lingua (it se manca)
"""
from __future__ import annotations

TERMS_VERSION = "1.0"            # da aumentare quando il testo cambia in modo sostanziale
TERMS_DATE = "2026-11-07"

_IT = """\
TERMINI D'USO ED ESCLUSIONE DI RESPONSABILITÀ — DroidSnex (programma PC e app Android)
Versione {v} del {d}

Leggi con attenzione. Premendo "Accetto" dichiari di aver letto, compreso e accettato integralmente questi termini. Se non li accetti, premi "Rifiuto": il programma si chiude e non puoi usarlo.

1. CHE COS'È DROIDSNEX
DroidSnex è uno strumento di analisi del traffico di rete composto da un programma per PC ("Programma") e da un'app per Android ("Agent") che il Programma installa sul telefono collegato via USB. L'Agent usa il servizio VPN locale di Android per osservare le connessioni di rete del dispositivo e le invia al Programma, che le mostra, le classifica, le confronta con liste di reputazione e database di geolocalizzazione e, se lo chiedi, le invia a servizi di terze parti (VirusTotal, AbuseIPDB, Shodan, ipinfo e simili) tramite le chiavi API che inserisci tu.

2. USO CONSENTITO E RESPONSABILITÀ DELL'UTENTE
Il software è destinato esclusivamente all'analisi, alla diagnostica e alla sicurezza di dispositivi che ti appartengono oppure per i quali hai un'autorizzazione esplicita, documentata e attuale del legittimo proprietario o dell'interessato. Sei l'unico responsabile di: (a) verificare che l'uso che ne fai sia lecito nel tuo paese e in quello in cui si trova il dispositivo analizzato; (b) ottenere ogni consenso o autorizzazione richiesti dalla legge, inclusi quelli in materia di protezione dei dati personali, segretezza delle comunicazioni, diritto del lavoro e informatica; (c) custodire e usare correttamente i dati raccolti, le sessioni salvate, gli screenshot e le esportazioni, che possono contenere dati personali, credenziali o informazioni riservate. È vietato usare il software per intercettare, sorvegliare o spiare comunicazioni di terzi senza il loro consenso, per aggirare misure di sicurezza, per violare diritti altrui o per qualunque scopo illecito. L'autore non controlla e non può controllare l'uso che ne fai.

3. NESSUNA GARANZIA ("AS IS")
NEI LIMITI MASSIMI CONSENTITI DALLA LEGGE APPLICABILE, IL PROGRAMMA E L'AGENT SONO FORNITI "COSÌ COME SONO" E "COME DISPONIBILI", SENZA GARANZIA DI ALCUN TIPO, ESPRESSA O IMPLICITA, INCLUSE, A TITOLO ESEMPLIFICATIVO E NON ESAUSTIVO, LE GARANZIE IMPLICITE DI COMMERCIABILITÀ, IDONEITÀ A UNO SCOPO PARTICOLARE, NON VIOLAZIONE DI DIRITTI DI TERZI, ACCURATEZZA, DISPONIBILITÀ E ASSENZA DI ERRORI. L'INTERO RISCHIO RELATIVO ALLA QUALITÀ E ALLE PRESTAZIONI DEL SOFTWARE È A TUO CARICO. SE IL SOFTWARE RISULTA DIFETTOSO, TI ASSUMI IL COSTO DI OGNI ASSISTENZA, RIPARAZIONE O CORREZIONE. In particolare non si garantisce che: le connessioni mostrate siano complete o esatte; le classificazioni "fidata"/"non fidata", i livelli di rischio, le geolocalizzazioni, i nomi delle organizzazioni (ASN), le risoluzioni DNS inverse e i risultati dei servizi di reputazione siano corretti, aggiornati o adatti a prendere decisioni; l'Agent non interferisca con altre app, con altre VPN o con la connettività del telefono; il software sia privo di vulnerabilità.

4. ESCLUSIONE DI RESPONSABILITÀ
IN NESSUN CASO, SALVO QUANTO IMPOSTO INDEROGABILMENTE DALLA LEGGE, L'AUTORE, I COLLABORATORI O I DISTRIBUTORI DEL SOFTWARE POTRANNO ESSERE RITENUTI RESPONSABILI VERSO DI TE O VERSO TERZI PER QUALSIASI DANNO DIRETTO, INDIRETTO, INCIDENTALE, SPECIALE, ESEMPLARE, PUNITIVO O CONSEQUENZIALE (INCLUSI, SENZA LIMITAZIONE, PERDITA O CORRUZIONE DI DATI, PERDITA DI PROFITTI, DI AVVIAMENTO O DI OPPORTUNITÀ, INTERRUZIONE DI ATTIVITÀ, GUASTI O MALFUNZIONAMENTI DEL TELEFONO O DEL PC, PERDITA DI CONNETTIVITÀ, COSTI DI SERVIZI SOSTITUTIVI, SANZIONI, PRETESE DI TERZI) DERIVANTI DALL'USO O DALL'IMPOSSIBILITÀ DI USARE IL SOFTWARE, DA DECISIONI PRESE SULLA BASE DELLE SUE INDICAZIONI, DALL'INSTALLAZIONE O RIMOZIONE DELL'AGENT, DALL'USO DI STRUMENTI DI TERZE PARTI SCARICATI O AVVIATI DAL PROGRAMMA (adb, scrcpy, database, liste) O DALL'INVIO DI DATI A SERVIZI ESTERNI, ANCHE SE AVVISATI DELLA POSSIBILITÀ DI TALI DANNI E QUALUNQUE SIA IL TITOLO DELLA PRETESA (CONTRATTO, ILLECITO, RESPONSABILITÀ OGGETTIVA O ALTRO). Nei paesi che non ammettono l'esclusione totale, la responsabilità è limitata nella misura massima consentita.

5. DATI, PRIVACY E SERVIZI DI TERZE PARTI
Il software funziona in locale e non invia dati all'autore. Le funzioni opzionali che interrogano servizi esterni (database DB-IP, liste di reputazione, VirusTotal, AbuseIPDB, Shodan, ipinfo, interrogazione del tuo IP pubblico, download di adb/scrcpy/mappe) trasmettono a quei servizi indirizzi IP, nomi di dominio o altre informazioni della tua analisi, e sono soggette ai termini e alle informative sulla privacy di ciascun servizio, che accetti usandole con le tue chiavi. L'autore non è responsabile per la condotta di tali servizi, per i loro costi, limiti o interruzioni, né per l'esattezza dei dati che restituiscono. L'Agent installato sul telefono raccoglie metadati delle connessioni (indirizzi, porte, byte, app, query DNS) e, a tua richiesta, screenshot; rimuovilo quando non ti serve (il Programma lo fa allo Stop e alla chiusura).

6. LICENZE E COMPONENTI DI TERZE PARTI
Il software è distribuito sotto licenza GNU GPL v3 o successiva (file LICENSE); le attribuzioni obbligatorie e le licenze delle componenti e dei dati di terze parti (DB-IP CC BY 4.0, Natural Earth, Android Platform-Tools con i termini dell'Android SDK, scrcpy, CustomTkinter, Pillow, Kotlin e altri) sono in NOTICE e THIRD_PARTY_NOTICES.md. Sei tenuto a rispettarle, in particolare i termini di Google per i Platform-Tools e il divieto di ridistribuire i database e gli strumenti scaricati. Questi termini si aggiungono alla GPL e non ne limitano i diritti di copia, modifica e ridistribuzione del codice; le clausole 3 e 4 riproducono e integrano le sezioni 15 e 16 della GPL v3.

7. MODIFICHE, LEGGE APPLICABILE E CLAUSOLE FINALI
Questi termini possono essere aggiornati nelle versioni successive del software; alla prima apertura di una versione con termini nuovi ti verranno riproposti. Se una clausola fosse invalida, le altre restano efficaci. Salvo norme inderogabili a tua tutela, si applica la legge italiana. Il software non è destinato a minori né a usi in cui un malfunzionamento potrebbe causare danni a persone o cose.

Premendo "Accetto" confermi di avere letto e accettato tutti i punti precedenti, di usare DroidSnex solo su dispositivi tuoi o con autorizzazione, e di assumerti ogni responsabilità per l'uso che ne fai.
"""

_EN = """\
TERMS OF USE AND DISCLAIMER OF LIABILITY — DroidSnex (PC program and Android app)
Version {v} of {d}

Please read carefully. By pressing "I accept" you declare that you have read, understood and fully accepted these terms. If you do not accept them, press "I decline": the program closes and you may not use it.

1. WHAT DROIDSNEX IS
DroidSnex is a network-traffic analysis tool made of a PC program (the "Program") and an Android app (the "Agent") that the Program installs on the phone connected via USB. The Agent uses Android's local VPN service to observe the device's network connections and sends them to the Program, which displays and classifies them, compares them with reputation lists and geolocation databases and, if you ask, sends them to third-party services (VirusTotal, AbuseIPDB, Shodan, ipinfo and similar) through API keys that you provide.

2. PERMITTED USE AND USER RESPONSIBILITY
The software is intended solely for the analysis, diagnostics and security of devices that you own or for which you hold the explicit, documented and current authorisation of the lawful owner or data subject. You alone are responsible for: (a) verifying that your use is lawful in your country and in the country where the analysed device is located; (b) obtaining every consent or authorisation required by law, including those on personal-data protection, secrecy of communications, labour law and computer-misuse law; (c) safeguarding and using correctly the collected data, saved sessions, screenshots and exports, which may contain personal data, credentials or confidential information. Using the software to intercept, monitor or spy on third parties' communications without their consent, to bypass security measures, to infringe others' rights or for any unlawful purpose is forbidden. The author does not and cannot control how you use it.

3. NO WARRANTY ("AS IS")
TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, THE PROGRAM AND THE AGENT ARE PROVIDED "AS IS" AND "AS AVAILABLE", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, NON-INFRINGEMENT, ACCURACY, AVAILABILITY AND FREEDOM FROM ERRORS. THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE SOFTWARE IS WITH YOU. SHOULD THE SOFTWARE PROVE DEFECTIVE, YOU ASSUME THE COST OF ALL NECESSARY SERVICING, REPAIR OR CORRECTION. In particular there is no guarantee that: the connections shown are complete or exact; the "trusted"/"untrusted" classifications, risk levels, geolocations, organisation names (ASN), reverse DNS results and reputation-service results are correct, up to date or suitable for taking decisions; the Agent does not interfere with other apps, other VPNs or the phone's connectivity; the software is free of vulnerabilities.

4. LIMITATION OF LIABILITY
IN NO EVENT, EXCEPT WHERE MANDATORY LAW PROVIDES OTHERWISE, SHALL THE AUTHOR, CONTRIBUTORS OR DISTRIBUTORS OF THE SOFTWARE BE LIABLE TO YOU OR TO ANY THIRD PARTY FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, PUNITIVE OR CONSEQUENTIAL DAMAGES (INCLUDING, WITHOUT LIMITATION, LOSS OR CORRUPTION OF DATA, LOSS OF PROFITS, GOODWILL OR OPPORTUNITIES, BUSINESS INTERRUPTION, FAILURE OR MALFUNCTION OF THE PHONE OR THE PC, LOSS OF CONNECTIVITY, COST OF SUBSTITUTE SERVICES, FINES, THIRD-PARTY CLAIMS) ARISING OUT OF THE USE OR INABILITY TO USE THE SOFTWARE, DECISIONS TAKEN ON THE BASIS OF ITS OUTPUT, THE INSTALLATION OR REMOVAL OF THE AGENT, THE USE OF THIRD-PARTY TOOLS DOWNLOADED OR LAUNCHED BY THE PROGRAM (adb, scrcpy, databases, lists) OR THE SENDING OF DATA TO EXTERNAL SERVICES, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGES AND WHATEVER THE LEGAL THEORY (CONTRACT, TORT, STRICT LIABILITY OR OTHERWISE). In jurisdictions that do not allow a total exclusion, liability is limited to the maximum extent permitted.

5. DATA, PRIVACY AND THIRD-PARTY SERVICES
The software runs locally and sends no data to the author. The optional features that query external services (DB-IP databases, reputation lists, VirusTotal, AbuseIPDB, Shodan, ipinfo, lookup of your public IP, download of adb/scrcpy/maps) transmit to those services IP addresses, domain names or other information from your analysis, and are subject to each service's terms and privacy policy, which you accept by using them with your keys. The author is not responsible for the conduct of such services, their costs, limits or outages, nor for the accuracy of the data they return. The Agent installed on the phone collects connection metadata (addresses, ports, bytes, apps, DNS queries) and, at your request, screenshots; remove it when you no longer need it (the Program does so on Stop and on exit).

6. LICENCES AND THIRD-PARTY COMPONENTS
The software is distributed under the GNU GPL v3 or later (file LICENSE); the mandatory attributions and the licences of third-party components and data (DB-IP CC BY 4.0, Natural Earth, Android Platform-Tools under the Android SDK terms, scrcpy, CustomTkinter, Pillow, Kotlin and others) are in NOTICE and THIRD_PARTY_NOTICES.md. You must comply with them, in particular Google's terms for the Platform-Tools and the prohibition on redistributing downloaded databases and tools. These terms are in addition to the GPL and do not limit its rights to copy, modify and redistribute the code; clauses 3 and 4 reproduce and supplement sections 15 and 16 of GPL v3.

7. CHANGES, GOVERNING LAW AND FINAL CLAUSES
These terms may be updated in later versions of the software; on first launch of a version with new terms you will be asked again. If any clause is invalid, the others remain in force. Subject to mandatory rules protecting you, Italian law applies. The software is not intended for minors nor for uses in which a malfunction could cause injury to persons or damage to property.

By pressing "I accept" you confirm that you have read and accepted all the points above, that you use DroidSnex only on your own devices or with authorisation, and that you take full responsibility for your use of it.
"""

_DE = """\
NUTZUNGSBEDINGUNGEN UND HAFTUNGSAUSSCHLUSS — DroidSnex (PC-Programm und Android-App)
Version {v} vom {d}

Bitte sorgfältig lesen. Mit "Ich akzeptiere" erklären Sie, diese Bedingungen gelesen, verstanden und vollständig akzeptiert zu haben. Wenn Sie sie nicht akzeptieren, drücken Sie "Ich lehne ab": das Programm wird beendet und Sie dürfen es nicht verwenden.

1. WAS DROIDSNEX IST
DroidSnex ist ein Werkzeug zur Analyse des Netzwerkverkehrs, bestehend aus einem PC-Programm („Programm") und einer Android-App („Agent"), die das Programm auf dem per USB verbundenen Telefon installiert. Der Agent nutzt den lokalen VPN-Dienst von Android, um die Netzwerkverbindungen des Geräts zu beobachten, und sendet sie an das Programm, das sie anzeigt, klassifiziert, mit Reputationslisten und Geolokalisierungsdatenbanken vergleicht und auf Ihren Wunsch an Dienste Dritter (VirusTotal, AbuseIPDB, Shodan, ipinfo u. ä.) über die von Ihnen eingegebenen API-Schlüssel übermittelt.

2. ZULÄSSIGE NUTZUNG UND VERANTWORTUNG DES NUTZERS
Die Software ist ausschließlich für Analyse, Diagnose und Sicherheit von Geräten bestimmt, die Ihnen gehören oder für die Sie eine ausdrückliche, dokumentierte und aktuelle Erlaubnis des rechtmäßigen Eigentümers bzw. der betroffenen Person haben. Sie allein sind verantwortlich dafür: (a) zu prüfen, dass Ihre Nutzung in Ihrem Land und im Land des analysierten Geräts rechtmäßig ist; (b) jede gesetzlich erforderliche Einwilligung oder Genehmigung einzuholen, einschließlich Datenschutz, Fernmeldegeheimnis, Arbeitsrecht und Computerstrafrecht; (c) die erhobenen Daten, gespeicherten Sitzungen, Screenshots und Exporte, die personenbezogene Daten, Zugangsdaten oder vertrauliche Informationen enthalten können, sicher zu verwahren und korrekt zu verwenden. Es ist verboten, die Software zu verwenden, um die Kommunikation Dritter ohne deren Einwilligung abzufangen, zu überwachen oder auszuspähen, Sicherheitsmaßnahmen zu umgehen, Rechte anderer zu verletzen oder für irgendeinen rechtswidrigen Zweck. Der Autor kontrolliert Ihre Nutzung nicht und kann sie nicht kontrollieren.

3. KEINE GEWÄHRLEISTUNG („AS IS")
SOWEIT NACH ANWENDBAREM RECHT ZULÄSSIG, WERDEN DAS PROGRAMM UND DER AGENT „WIE BESEHEN" UND „WIE VERFÜGBAR" OHNE JEGLICHE AUSDRÜCKLICHE ODER STILLSCHWEIGENDE GEWÄHRLEISTUNG BEREITGESTELLT, EINSCHLIESSLICH, ABER NICHT BESCHRÄNKT AUF DIE STILLSCHWEIGENDEN GEWÄHRLEISTUNGEN DER MARKTGÄNGIGKEIT, DER EIGNUNG FÜR EINEN BESTIMMTEN ZWECK, DER NICHTVERLETZUNG VON RECHTEN DRITTER, DER GENAUIGKEIT, DER VERFÜGBARKEIT UND DER FEHLERFREIHEIT. DAS GESAMTE RISIKO HINSICHTLICH QUALITÄT UND LEISTUNG DER SOFTWARE LIEGT BEI IHNEN. SOLLTE SICH DIE SOFTWARE ALS FEHLERHAFT ERWEISEN, TRAGEN SIE DIE KOSTEN ALLER ERFORDERLICHEN WARTUNGS-, REPARATUR- ODER KORREKTURMASSNAHMEN. Insbesondere wird nicht garantiert, dass: die angezeigten Verbindungen vollständig oder exakt sind; die Einstufungen „vertrauenswürdig"/„nicht vertrauenswürdig", Risikostufen, Geolokalisierungen, Organisationsnamen (ASN), Reverse-DNS-Ergebnisse und Ergebnisse der Reputationsdienste korrekt, aktuell oder für Entscheidungen geeignet sind; der Agent nicht mit anderen Apps, anderen VPNs oder der Konnektivität des Telefons interferiert; die Software frei von Schwachstellen ist.

4. HAFTUNGSAUSSCHLUSS
IN KEINEM FALL, SOFERN NICHT ZWINGENDES RECHT ETWAS ANDERES VORSCHREIBT, HAFTEN DER AUTOR, MITWIRKENDE ODER VERTREIBER DER SOFTWARE IHNEN ODER DRITTEN GEGENÜBER FÜR DIREKTE, INDIREKTE, ZUFÄLLIGE, BESONDERE, EXEMPLARISCHE, STRAF- ODER FOLGESCHÄDEN (EINSCHLIESSLICH, OHNE EINSCHRÄNKUNG, DATENVERLUST ODER -BESCHÄDIGUNG, ENTGANGENER GEWINN, VERLUST VON GESCHÄFTSWERT ODER CHANCEN, BETRIEBSUNTERBRECHUNG, AUSFALL ODER FEHLFUNKTION DES TELEFONS ODER DES PCS, VERLUST DER KONNEKTIVITÄT, KOSTEN FÜR ERSATZDIENSTE, BUSSGELDER, ANSPRÜCHE DRITTER), DIE SICH AUS DER NUTZUNG ODER DER UNMÖGLICHKEIT DER NUTZUNG DER SOFTWARE, AUS ENTSCHEIDUNGEN AUF GRUNDLAGE IHRER AUSGABEN, AUS DER INSTALLATION ODER ENTFERNUNG DES AGENTS, AUS DER NUTZUNG VON DURCH DAS PROGRAMM HERUNTERGELADENEN ODER GESTARTETEN WERKZEUGEN DRITTER (adb, scrcpy, Datenbanken, Listen) ODER AUS DER ÜBERMITTLUNG VON DATEN AN EXTERNE DIENSTE ERGEBEN, SELBST WENN AUF DIE MÖGLICHKEIT SOLCHER SCHÄDEN HINGEWIESEN WURDE UND UNABHÄNGIG VON DER RECHTSGRUNDLAGE (VERTRAG, UNERLAUBTE HANDLUNG, GEFÄHRDUNGSHAFTUNG ODER SONSTIGES). In Rechtsordnungen, die einen vollständigen Ausschluss nicht zulassen, ist die Haftung im größtmöglichen zulässigen Umfang beschränkt.

5. DATEN, DATENSCHUTZ UND DIENSTE DRITTER
Die Software läuft lokal und sendet keine Daten an den Autor. Die optionalen Funktionen, die externe Dienste abfragen (DB-IP-Datenbanken, Reputationslisten, VirusTotal, AbuseIPDB, Shodan, ipinfo, Abfrage Ihrer öffentlichen IP, Download von adb/scrcpy/Karten), übermitteln an diese Dienste IP-Adressen, Domainnamen oder andere Informationen Ihrer Analyse und unterliegen den Bedingungen und Datenschutzerklärungen des jeweiligen Dienstes, die Sie durch die Nutzung mit Ihren Schlüsseln akzeptieren. Der Autor ist nicht verantwortlich für das Verhalten dieser Dienste, deren Kosten, Limits oder Ausfälle noch für die Richtigkeit der zurückgegebenen Daten. Der auf dem Telefon installierte Agent erfasst Verbindungsmetadaten (Adressen, Ports, Bytes, Apps, DNS-Abfragen) und auf Ihren Wunsch Screenshots; entfernen Sie ihn, wenn Sie ihn nicht mehr benötigen (das Programm tut dies bei Stop und beim Beenden).

6. LIZENZEN UND KOMPONENTEN DRITTER
Die Software wird unter der GNU GPL v3 oder später (Datei LICENSE) vertrieben; die Pflichtangaben und Lizenzen der Komponenten und Daten Dritter (DB-IP CC BY 4.0, Natural Earth, Android Platform-Tools unter den Bedingungen des Android SDK, scrcpy, CustomTkinter, Pillow, Kotlin und andere) stehen in NOTICE und THIRD_PARTY_NOTICES.md. Sie sind verpflichtet, diese einzuhalten, insbesondere die Bedingungen von Google für die Platform-Tools und das Verbot der Weiterverbreitung heruntergeladener Datenbanken und Werkzeuge. Diese Bedingungen ergänzen die GPL und schränken deren Rechte zum Kopieren, Ändern und Weiterverbreiten des Codes nicht ein; die Klauseln 3 und 4 geben die Abschnitte 15 und 16 der GPL v3 wieder und ergänzen sie.

7. ÄNDERUNGEN, ANWENDBARES RECHT UND SCHLUSSBESTIMMUNGEN
Diese Bedingungen können in späteren Versionen der Software aktualisiert werden; beim ersten Start einer Version mit neuen Bedingungen werden sie erneut vorgelegt. Sollte eine Klausel unwirksam sein, bleiben die übrigen wirksam. Vorbehaltlich zwingender Vorschriften zu Ihrem Schutz gilt italienisches Recht. Die Software ist nicht für Minderjährige und nicht für Anwendungen bestimmt, bei denen eine Fehlfunktion Personen- oder Sachschäden verursachen könnte.

Mit "Ich akzeptiere" bestätigen Sie, alle vorstehenden Punkte gelesen und akzeptiert zu haben, DroidSnex nur auf eigenen Geräten oder mit Erlaubnis zu verwenden und die volle Verantwortung für Ihre Nutzung zu übernehmen.
"""

_FR = """\
CONDITIONS D'UTILISATION ET EXCLUSION DE RESPONSABILITÉ — DroidSnex (programme PC et application Android)
Version {v} du {d}

Lisez attentivement. En appuyant sur « J'accepte », vous déclarez avoir lu, compris et accepté intégralement ces conditions. Si vous ne les acceptez pas, appuyez sur « Je refuse » : le programme se ferme et vous ne pouvez pas l'utiliser.

1. CE QU'EST DROIDSNEX
DroidSnex est un outil d'analyse du trafic réseau composé d'un programme pour PC (le « Programme ») et d'une application Android (l'« Agent ») que le Programme installe sur le téléphone connecté par USB. L'Agent utilise le service VPN local d'Android pour observer les connexions réseau de l'appareil et les envoie au Programme, qui les affiche, les classe, les compare à des listes de réputation et à des bases de géolocalisation et, à votre demande, les transmet à des services tiers (VirusTotal, AbuseIPDB, Shodan, ipinfo et similaires) via les clés API que vous saisissez.

2. USAGE AUTORISÉ ET RESPONSABILITÉ DE L'UTILISATEUR
Le logiciel est destiné exclusivement à l'analyse, au diagnostic et à la sécurité d'appareils qui vous appartiennent ou pour lesquels vous disposez d'une autorisation explicite, documentée et en cours de validité du propriétaire légitime ou de la personne concernée. Vous êtes seul responsable : (a) de vérifier que votre usage est licite dans votre pays et dans celui où se trouve l'appareil analysé ; (b) d'obtenir tout consentement ou autorisation exigés par la loi, y compris en matière de protection des données personnelles, de secret des communications, de droit du travail et de criminalité informatique ; (c) de conserver et d'utiliser correctement les données collectées, les sessions enregistrées, les captures d'écran et les exports, qui peuvent contenir des données personnelles, des identifiants ou des informations confidentielles. Il est interdit d'utiliser le logiciel pour intercepter, surveiller ou espionner les communications de tiers sans leur consentement, pour contourner des mesures de sécurité, pour porter atteinte aux droits d'autrui ou à toute fin illicite. L'auteur ne contrôle pas et ne peut pas contrôler l'usage que vous en faites.

3. ABSENCE DE GARANTIE (« EN L'ÉTAT »)
DANS TOUTE LA MESURE PERMISE PAR LA LOI APPLICABLE, LE PROGRAMME ET L'AGENT SONT FOURNIS « EN L'ÉTAT » ET « SELON DISPONIBILITÉ », SANS GARANTIE D'AUCUNE SORTE, EXPRESSE OU IMPLICITE, Y COMPRIS, SANS S'Y LIMITER, LES GARANTIES IMPLICITES DE QUALITÉ MARCHANDE, D'ADÉQUATION À UN USAGE PARTICULIER, D'ABSENCE DE CONTREFAÇON, D'EXACTITUDE, DE DISPONIBILITÉ ET D'ABSENCE D'ERREURS. VOUS ASSUMEZ L'INTÉGRALITÉ DU RISQUE QUANT À LA QUALITÉ ET AUX PERFORMANCES DU LOGICIEL. SI LE LOGICIEL S'AVÈRE DÉFECTUEUX, VOUS ASSUMEZ LE COÛT DE TOUTE ASSISTANCE, RÉPARATION OU CORRECTION. En particulier, il n'est pas garanti que : les connexions affichées soient complètes ou exactes ; les classifications « de confiance »/« non fiable », les niveaux de risque, les géolocalisations, les noms d'organisations (ASN), les résolutions DNS inverses et les résultats des services de réputation soient corrects, à jour ou adaptés à la prise de décisions ; l'Agent n'interfère pas avec d'autres applications, d'autres VPN ou la connectivité du téléphone ; le logiciel soit exempt de vulnérabilités.

4. EXCLUSION DE RESPONSABILITÉ
EN AUCUN CAS, SAUF DISPOSITION LÉGALE IMPÉRATIVE CONTRAIRE, L'AUTEUR, LES CONTRIBUTEURS OU LES DISTRIBUTEURS DU LOGICIEL NE POURRONT ÊTRE TENUS RESPONSABLES ENVERS VOUS OU ENVERS DES TIERS DE TOUT DOMMAGE DIRECT, INDIRECT, ACCESSOIRE, SPÉCIAL, EXEMPLAIRE, PUNITIF OU CONSÉCUTIF (Y COMPRIS, SANS LIMITATION, LA PERTE OU LA CORRUPTION DE DONNÉES, LA PERTE DE PROFITS, DE CLIENTÈLE OU D'OPPORTUNITÉS, L'INTERRUPTION D'ACTIVITÉ, LA PANNE OU LE DYSFONCTIONNEMENT DU TÉLÉPHONE OU DU PC, LA PERTE DE CONNECTIVITÉ, LE COÛT DE SERVICES DE SUBSTITUTION, LES SANCTIONS, LES RÉCLAMATIONS DE TIERS) DÉCOULANT DE L'UTILISATION OU DE L'IMPOSSIBILITÉ D'UTILISER LE LOGICIEL, DE DÉCISIONS PRISES SUR LA BASE DE SES INDICATIONS, DE L'INSTALLATION OU DU RETRAIT DE L'AGENT, DE L'UTILISATION D'OUTILS TIERS TÉLÉCHARGÉS OU LANCÉS PAR LE PROGRAMME (adb, scrcpy, bases de données, listes) OU DE L'ENVOI DE DONNÉES À DES SERVICES EXTERNES, MÊME S'ILS ONT ÉTÉ INFORMÉS DE LA POSSIBILITÉ DE TELS DOMMAGES ET QUEL QUE SOIT LE FONDEMENT INVOQUÉ (CONTRAT, DÉLIT, RESPONSABILITÉ OBJECTIVE OU AUTRE). Dans les pays qui n'admettent pas une exclusion totale, la responsabilité est limitée dans la mesure maximale permise.

5. DONNÉES, VIE PRIVÉE ET SERVICES TIERS
Le logiciel fonctionne en local et n'envoie aucune donnée à l'auteur. Les fonctions facultatives qui interrogent des services externes (bases DB-IP, listes de réputation, VirusTotal, AbuseIPDB, Shodan, ipinfo, interrogation de votre IP publique, téléchargement d'adb/scrcpy/cartes) transmettent à ces services des adresses IP, des noms de domaine ou d'autres informations de votre analyse, et sont soumises aux conditions et politiques de confidentialité de chaque service, que vous acceptez en les utilisant avec vos clés. L'auteur n'est pas responsable de la conduite de ces services, de leurs coûts, limites ou interruptions, ni de l'exactitude des données qu'ils renvoient. L'Agent installé sur le téléphone collecte des métadonnées de connexion (adresses, ports, octets, applications, requêtes DNS) et, à votre demande, des captures d'écran ; retirez-le quand vous n'en avez plus besoin (le Programme le fait à l'arrêt et à la fermeture).

6. LICENCES ET COMPOSANTS TIERS
Le logiciel est distribué sous licence GNU GPL v3 ou ultérieure (fichier LICENSE) ; les attributions obligatoires et les licences des composants et données tiers (DB-IP CC BY 4.0, Natural Earth, Android Platform-Tools selon les conditions de l'Android SDK, scrcpy, CustomTkinter, Pillow, Kotlin et autres) figurent dans NOTICE et THIRD_PARTY_NOTICES.md. Vous êtes tenu de les respecter, en particulier les conditions de Google pour les Platform-Tools et l'interdiction de redistribuer les bases de données et outils téléchargés. Ces conditions s'ajoutent à la GPL et ne limitent pas ses droits de copie, de modification et de redistribution du code ; les clauses 3 et 4 reproduisent et complètent les sections 15 et 16 de la GPL v3.

7. MODIFICATIONS, LOI APPLICABLE ET CLAUSES FINALES
Ces conditions peuvent être mises à jour dans les versions ultérieures du logiciel ; à la première ouverture d'une version comportant de nouvelles conditions, elles vous seront soumises de nouveau. Si une clause est invalide, les autres restent en vigueur. Sous réserve des règles impératives vous protégeant, la loi italienne s'applique. Le logiciel n'est pas destiné aux mineurs ni aux usages dans lesquels un dysfonctionnement pourrait causer des dommages aux personnes ou aux biens.

En appuyant sur « J'accepte », vous confirmez avoir lu et accepté tous les points précédents, utiliser DroidSnex uniquement sur vos propres appareils ou avec autorisation, et assumer l'entière responsabilité de l'usage que vous en faites.
"""

_ES = """\
TÉRMINOS DE USO Y EXCLUSIÓN DE RESPONSABILIDAD — DroidSnex (programa para PC y aplicación Android)
Versión {v} de {d}

Lea con atención. Al pulsar «Acepto» declara haber leído, comprendido y aceptado íntegramente estos términos. Si no los acepta, pulse «Rechazo»: el programa se cierra y no puede usarlo.

1. QUÉ ES DROIDSNEX
DroidSnex es una herramienta de análisis del tráfico de red compuesta por un programa para PC (el «Programa») y una aplicación para Android (el «Agente») que el Programa instala en el teléfono conectado por USB. El Agente usa el servicio VPN local de Android para observar las conexiones de red del dispositivo y las envía al Programa, que las muestra, las clasifica, las compara con listas de reputación y bases de datos de geolocalización y, si usted lo pide, las envía a servicios de terceros (VirusTotal, AbuseIPDB, Shodan, ipinfo y similares) mediante las claves API que usted introduce.

2. USO PERMITIDO Y RESPONSABILIDAD DEL USUARIO
El software está destinado exclusivamente al análisis, el diagnóstico y la seguridad de dispositivos que le pertenecen o para los que dispone de una autorización explícita, documentada y vigente del propietario legítimo o del interesado. Usted es el único responsable de: (a) comprobar que el uso que hace es lícito en su país y en el país donde se encuentra el dispositivo analizado; (b) obtener todo consentimiento o autorización exigidos por la ley, incluidos los relativos a protección de datos personales, secreto de las comunicaciones, derecho laboral y delitos informáticos; (c) custodiar y usar correctamente los datos recogidos, las sesiones guardadas, las capturas de pantalla y las exportaciones, que pueden contener datos personales, credenciales o información confidencial. Está prohibido usar el software para interceptar, vigilar o espiar comunicaciones de terceros sin su consentimiento, para eludir medidas de seguridad, para violar derechos ajenos o para cualquier fin ilícito. El autor no controla ni puede controlar el uso que usted hace.

3. SIN GARANTÍA («TAL CUAL»)
EN LA MÁXIMA MEDIDA PERMITIDA POR LA LEY APLICABLE, EL PROGRAMA Y EL AGENTE SE SUMINISTRAN «TAL CUAL» Y «SEGÚN DISPONIBILIDAD», SIN GARANTÍA DE NINGÚN TIPO, EXPRESA O IMPLÍCITA, INCLUIDAS, A TÍTULO ENUNCIATIVO Y NO LIMITATIVO, LAS GARANTÍAS IMPLÍCITAS DE COMERCIABILIDAD, IDONEIDAD PARA UN FIN DETERMINADO, NO INFRACCIÓN, EXACTITUD, DISPONIBILIDAD Y AUSENCIA DE ERRORES. TODO EL RIESGO EN CUANTO A LA CALIDAD Y EL RENDIMIENTO DEL SOFTWARE ES SUYO. SI EL SOFTWARE RESULTA DEFECTUOSO, USTED ASUME EL COSTE DE TODA ASISTENCIA, REPARACIÓN O CORRECCIÓN. En particular no se garantiza que: las conexiones mostradas sean completas o exactas; las clasificaciones «de confianza»/«no fiable», los niveles de riesgo, las geolocalizaciones, los nombres de las organizaciones (ASN), las resoluciones DNS inversas y los resultados de los servicios de reputación sean correctos, actuales o adecuados para tomar decisiones; el Agente no interfiera con otras aplicaciones, otras VPN o la conectividad del teléfono; el software esté libre de vulnerabilidades.

4. EXCLUSIÓN DE RESPONSABILIDAD
EN NINGÚN CASO, SALVO QUE LA LEY IMPERATIVA DISPONGA OTRA COSA, EL AUTOR, LOS COLABORADORES O LOS DISTRIBUIDORES DEL SOFTWARE SERÁN RESPONSABLES ANTE USTED O ANTE TERCEROS DE NINGÚN DAÑO DIRECTO, INDIRECTO, INCIDENTAL, ESPECIAL, EJEMPLAR, PUNITIVO O CONSECUENTE (INCLUIDOS, SIN LIMITACIÓN, PÉRDIDA O CORRUPCIÓN DE DATOS, PÉRDIDA DE BENEFICIOS, DE FONDO DE COMERCIO O DE OPORTUNIDADES, INTERRUPCIÓN DE LA ACTIVIDAD, AVERÍA O MAL FUNCIONAMIENTO DEL TELÉFONO O DEL PC, PÉRDIDA DE CONECTIVIDAD, COSTE DE SERVICIOS SUSTITUTIVOS, SANCIONES, RECLAMACIONES DE TERCEROS) DERIVADO DEL USO O DE LA IMPOSIBILIDAD DE USAR EL SOFTWARE, DE DECISIONES TOMADAS SOBRE LA BASE DE SUS INDICACIONES, DE LA INSTALACIÓN O RETIRADA DEL AGENTE, DEL USO DE HERRAMIENTAS DE TERCEROS DESCARGADAS O LANZADAS POR EL PROGRAMA (adb, scrcpy, bases de datos, listas) O DEL ENVÍO DE DATOS A SERVICIOS EXTERNOS, AUNQUE SE HAYA ADVERTIDO DE LA POSIBILIDAD DE TALES DAÑOS Y CUALQUIERA QUE SEA EL FUNDAMENTO (CONTRATO, RESPONSABILIDAD EXTRACONTRACTUAL, OBJETIVA U OTRO). En los países que no admiten la exclusión total, la responsabilidad queda limitada en la máxima medida permitida.

5. DATOS, PRIVACIDAD Y SERVICIOS DE TERCEROS
El software funciona en local y no envía datos al autor. Las funciones opcionales que consultan servicios externos (bases DB-IP, listas de reputación, VirusTotal, AbuseIPDB, Shodan, ipinfo, consulta de su IP pública, descarga de adb/scrcpy/mapas) transmiten a esos servicios direcciones IP, nombres de dominio u otra información de su análisis, y están sujetas a los términos y políticas de privacidad de cada servicio, que usted acepta al usarlos con sus claves. El autor no es responsable de la conducta de dichos servicios, de sus costes, límites o interrupciones, ni de la exactitud de los datos que devuelven. El Agente instalado en el teléfono recoge metadatos de las conexiones (direcciones, puertos, bytes, aplicaciones, consultas DNS) y, a petición suya, capturas de pantalla; desinstálelo cuando no lo necesite (el Programa lo hace al pulsar Stop y al cerrarse).

6. LICENCIAS Y COMPONENTES DE TERCEROS
El software se distribuye bajo licencia GNU GPL v3 o posterior (archivo LICENSE); las atribuciones obligatorias y las licencias de los componentes y datos de terceros (DB-IP CC BY 4.0, Natural Earth, Android Platform-Tools con los términos del Android SDK, scrcpy, CustomTkinter, Pillow, Kotlin y otros) están en NOTICE y THIRD_PARTY_NOTICES.md. Está obligado a respetarlas, en particular los términos de Google para los Platform-Tools y la prohibición de redistribuir las bases de datos y herramientas descargadas. Estos términos se añaden a la GPL y no limitan sus derechos de copia, modificación y redistribución del código; las cláusulas 3 y 4 reproducen y complementan las secciones 15 y 16 de la GPL v3.

7. MODIFICACIONES, LEY APLICABLE Y CLÁUSULAS FINALES
Estos términos pueden actualizarse en versiones posteriores del software; en la primera apertura de una versión con términos nuevos se le volverán a presentar. Si alguna cláusula fuera inválida, las demás seguirán vigentes. Salvo normas imperativas que le protejan, se aplica la ley italiana. El software no está destinado a menores ni a usos en los que un mal funcionamiento pudiera causar daños a personas o bienes.

Al pulsar «Acepto» confirma haber leído y aceptado todos los puntos anteriores, usar DroidSnex solo en dispositivos propios o con autorización, y asumir toda la responsabilidad por el uso que haga de él.
"""

_NL = """\
GEBRUIKSVOORWAARDEN EN UITSLUITING VAN AANSPRAKELIJKHEID — DroidSnex (pc-programma en Android-app)
Versie {v} van {d}

Lees dit zorgvuldig. Door op "Ik accepteer" te drukken verklaart u deze voorwaarden te hebben gelezen, begrepen en volledig te aanvaarden. Accepteert u ze niet, druk dan op "Ik weiger": het programma sluit af en u mag het niet gebruiken.

1. WAT DROIDSNEX IS
DroidSnex is een hulpmiddel voor netwerkverkeersanalyse, bestaande uit een pc-programma (het "Programma") en een Android-app (de "Agent") die het Programma installeert op de via USB aangesloten telefoon. De Agent gebruikt de lokale VPN-dienst van Android om de netwerkverbindingen van het apparaat te observeren en stuurt ze naar het Programma, dat ze toont, classificeert, vergelijkt met reputatielijsten en geolocatiedatabases en, als u daarom vraagt, doorstuurt naar diensten van derden (VirusTotal, AbuseIPDB, Shodan, ipinfo en dergelijke) via de API-sleutels die u invoert.

2. TOEGESTAAN GEBRUIK EN VERANTWOORDELIJKHEID VAN DE GEBRUIKER
De software is uitsluitend bedoeld voor analyse, diagnose en beveiliging van apparaten die van u zijn of waarvoor u een uitdrukkelijke, gedocumenteerde en actuele toestemming van de rechtmatige eigenaar of betrokkene hebt. U alleen bent verantwoordelijk voor: (a) het nagaan of uw gebruik rechtmatig is in uw land en in het land waar het geanalyseerde apparaat zich bevindt; (b) het verkrijgen van elke wettelijk vereiste toestemming of machtiging, waaronder die inzake bescherming van persoonsgegevens, communicatiegeheim, arbeidsrecht en computercriminaliteit; (c) het veilig bewaren en correct gebruiken van de verzamelde gegevens, opgeslagen sessies, schermafbeeldingen en exports, die persoonsgegevens, inloggegevens of vertrouwelijke informatie kunnen bevatten. Het is verboden de software te gebruiken om communicatie van derden zonder hun toestemming te onderscheppen, te volgen of te bespioneren, om beveiligingsmaatregelen te omzeilen, om rechten van anderen te schenden of voor enig onrechtmatig doel. De auteur controleert uw gebruik niet en kan dat ook niet.

3. GEEN GARANTIE ("AS IS")
VOOR ZOVER TOEGESTAAN DOOR HET TOEPASSELIJKE RECHT WORDEN HET PROGRAMMA EN DE AGENT GELEVERD "ZOALS ZE ZIJN" EN "ZOALS BESCHIKBAAR", ZONDER ENIGE GARANTIE, UITDRUKKELIJK OF STILZWIJGEND, MET INBEGRIP VAN MAAR NIET BEPERKT TOT DE STILZWIJGENDE GARANTIES VAN VERKOOPBAARHEID, GESCHIKTHEID VOOR EEN BEPAALD DOEL, NIET-INBREUK, NAUWKEURIGHEID, BESCHIKBAARHEID EN AFWEZIGHEID VAN FOUTEN. HET VOLLEDIGE RISICO VOOR DE KWALITEIT EN PRESTATIES VAN DE SOFTWARE LIGT BIJ U. BLIJKT DE SOFTWARE GEBREKKIG, DAN DRAAGT U DE KOSTEN VAN ALLE NODIGE ONDERHOUD, REPARATIE OF CORRECTIE. In het bijzonder wordt niet gegarandeerd dat: de getoonde verbindingen volledig of exact zijn; de classificaties "vertrouwd"/"niet vertrouwd", risiconiveaus, geolocaties, organisatienamen (ASN), reverse-DNS-resultaten en resultaten van reputatiediensten juist, actueel of geschikt voor besluitvorming zijn; de Agent niet interfereert met andere apps, andere VPN's of de connectiviteit van de telefoon; de software vrij is van kwetsbaarheden.

4. UITSLUITING VAN AANSPRAKELIJKHEID
IN GEEN GEVAL, BEHOUDENS DWINGEND RECHT, ZIJN DE AUTEUR, MEDEWERKERS OF DISTRIBUTEURS VAN DE SOFTWARE JEGENS U OF DERDEN AANSPRAKELIJK VOOR ENIGE DIRECTE, INDIRECTE, INCIDENTELE, BIJZONDERE, EXEMPLAIRE, PUNITIEVE OF GEVOLGSCHADE (MET INBEGRIP VAN, ZONDER BEPERKING, VERLIES OF BESCHADIGING VAN GEGEVENS, WINSTDERVING, VERLIES VAN GOODWILL OF KANSEN, BEDRIJFSONDERBREKING, STORING OF DEFECT VAN DE TELEFOON OF DE PC, VERLIES VAN CONNECTIVITEIT, KOSTEN VAN VERVANGENDE DIENSTEN, BOETES, AANSPRAKEN VAN DERDEN) VOORTVLOEIEND UIT HET GEBRUIK OF DE ONMOGELIJKHEID VAN GEBRUIK VAN DE SOFTWARE, UIT BESLISSINGEN GENOMEN OP BASIS VAN DE UITKOMSTEN ERVAN, UIT DE INSTALLATIE OF VERWIJDERING VAN DE AGENT, UIT HET GEBRUIK VAN DOOR HET PROGRAMMA GEDOWNLOADE OF GESTARTE HULPMIDDELEN VAN DERDEN (adb, scrcpy, databases, lijsten) OF UIT HET VERZENDEN VAN GEGEVENS NAAR EXTERNE DIENSTEN, ZELFS INDIEN GEWEZEN OP DE MOGELIJKHEID VAN DERGELIJKE SCHADE EN ONGEACHT DE RECHTSGROND (OVEREENKOMST, ONRECHTMATIGE DAAD, RISICOAANSPRAKELIJKHEID OF ANDERSZINS). In rechtsgebieden die een volledige uitsluiting niet toestaan, is de aansprakelijkheid beperkt tot het maximaal toegestane.

5. GEGEVENS, PRIVACY EN DIENSTEN VAN DERDEN
De software werkt lokaal en stuurt geen gegevens naar de auteur. De optionele functies die externe diensten raadplegen (DB-IP-databases, reputatielijsten, VirusTotal, AbuseIPDB, Shodan, ipinfo, opvragen van uw publieke IP, downloaden van adb/scrcpy/kaarten) sturen IP-adressen, domeinnamen of andere informatie uit uw analyse naar die diensten en vallen onder de voorwaarden en het privacybeleid van elke dienst, die u aanvaardt door ze met uw sleutels te gebruiken. De auteur is niet verantwoordelijk voor het gedrag van die diensten, hun kosten, limieten of storingen, noch voor de juistheid van de gegevens die ze teruggeven. De op de telefoon geïnstalleerde Agent verzamelt verbindingsmetadata (adressen, poorten, bytes, apps, DNS-query's) en, op uw verzoek, schermafbeeldingen; verwijder hem wanneer u hem niet meer nodig hebt (het Programma doet dit bij Stop en bij afsluiten).

6. LICENTIES EN COMPONENTEN VAN DERDEN
De software wordt verspreid onder de GNU GPL v3 of later (bestand LICENSE); de verplichte naamsvermeldingen en de licenties van componenten en gegevens van derden (DB-IP CC BY 4.0, Natural Earth, Android Platform-Tools onder de Android SDK-voorwaarden, scrcpy, CustomTkinter, Pillow, Kotlin en andere) staan in NOTICE en THIRD_PARTY_NOTICES.md. U bent verplicht deze na te leven, in het bijzonder de voorwaarden van Google voor de Platform-Tools en het verbod op herdistributie van gedownloade databases en hulpmiddelen. Deze voorwaarden komen bovenop de GPL en beperken de rechten daarvan om de code te kopiëren, te wijzigen en te herdistribueren niet; de clausules 3 en 4 geven de secties 15 en 16 van GPL v3 weer en vullen ze aan.

7. WIJZIGINGEN, TOEPASSELIJK RECHT EN SLOTBEPALINGEN
Deze voorwaarden kunnen in latere versies van de software worden bijgewerkt; bij de eerste start van een versie met nieuwe voorwaarden worden ze opnieuw voorgelegd. Is een clausule ongeldig, dan blijven de overige van kracht. Behoudens dwingende regels ter bescherming van u is Italiaans recht van toepassing. De software is niet bedoeld voor minderjarigen, noch voor toepassingen waarbij een storing letsel aan personen of schade aan zaken zou kunnen veroorzaken.

Door op "Ik accepteer" te drukken bevestigt u alle bovenstaande punten te hebben gelezen en aanvaard, DroidSnex alleen op eigen apparaten of met toestemming te gebruiken en de volledige verantwoordelijkheid voor uw gebruik te dragen.
"""

_PL = """\
WARUNKI UŻYTKOWANIA I WYŁĄCZENIE ODPOWIEDZIALNOŚCI — DroidSnex (program na PC i aplikacja Android)
Wersja {v} z dnia {d}

Przeczytaj uważnie. Naciskając „Akceptuję", oświadczasz, że przeczytałeś(-aś), zrozumiałeś(-aś) i w pełni akceptujesz niniejsze warunki. Jeśli ich nie akceptujesz, naciśnij „Odrzucam": program zostanie zamknięty i nie możesz z niego korzystać.

1. CZYM JEST DROIDSNEX
DroidSnex to narzędzie do analizy ruchu sieciowego złożone z programu na PC („Program") oraz aplikacji na Androida („Agent"), którą Program instaluje na telefonie podłączonym przez USB. Agent korzysta z lokalnej usługi VPN Androida, aby obserwować połączenia sieciowe urządzenia, i przesyła je do Programu, który je wyświetla, klasyfikuje, porównuje z listami reputacji i bazami geolokalizacji oraz, na Twoje żądanie, wysyła do usług zewnętrznych (VirusTotal, AbuseIPDB, Shodan, ipinfo i podobnych) za pomocą kluczy API, które wprowadzasz.

2. DOZWOLONE UŻYCIE I ODPOWIEDZIALNOŚĆ UŻYTKOWNIKA
Oprogramowanie jest przeznaczone wyłącznie do analizy, diagnostyki i zabezpieczania urządzeń, które należą do Ciebie lub co do których posiadasz wyraźne, udokumentowane i aktualne upoważnienie prawowitego właściciela lub osoby, której dane dotyczą. Wyłącznie Ty odpowiadasz za: (a) sprawdzenie, czy Twoje użycie jest zgodne z prawem w Twoim kraju i w kraju, w którym znajduje się analizowane urządzenie; (b) uzyskanie wszelkich zgód lub zezwoleń wymaganych prawem, w tym dotyczących ochrony danych osobowych, tajemnicy komunikacji, prawa pracy i przestępstw komputerowych; (c) bezpieczne przechowywanie i prawidłowe wykorzystanie zebranych danych, zapisanych sesji, zrzutów ekranu i eksportów, które mogą zawierać dane osobowe, dane uwierzytelniające lub informacje poufne. Zabronione jest używanie oprogramowania do przechwytywania, monitorowania lub szpiegowania komunikacji osób trzecich bez ich zgody, do obchodzenia zabezpieczeń, do naruszania praw innych osób lub w jakimkolwiek niezgodnym z prawem celu. Autor nie kontroluje i nie może kontrolować sposobu, w jaki z niego korzystasz.

3. BRAK GWARANCJI („TAK JAK JEST")
W MAKSYMALNYM ZAKRESIE DOZWOLONYM PRZEZ OBOWIĄZUJĄCE PRAWO PROGRAM I AGENT SĄ DOSTARCZANE „TAK JAK SĄ" I „W MIARĘ DOSTĘPNOŚCI", BEZ JAKIEJKOLWIEK GWARANCJI, WYRAŹNEJ LUB DOROZUMIANEJ, W TYM MIĘDZY INNYMI DOROZUMIANYCH GWARANCJI PRZYDATNOŚCI HANDLOWEJ, PRZYDATNOŚCI DO OKREŚLONEGO CELU, NIENARUSZANIA PRAW OSÓB TRZECICH, DOKŁADNOŚCI, DOSTĘPNOŚCI I BRAKU BŁĘDÓW. CAŁE RYZYKO CO DO JAKOŚCI I DZIAŁANIA OPROGRAMOWANIA PONOSISZ TY. JEŚLI OPROGRAMOWANIE OKAŻE SIĘ WADLIWE, PONOSISZ KOSZTY WSZELKIEJ NIEZBĘDNEJ OBSŁUGI, NAPRAWY LUB KOREKTY. W szczególności nie gwarantuje się, że: pokazywane połączenia są kompletne lub dokładne; klasyfikacje „zaufane"/„niezaufane", poziomy ryzyka, geolokalizacje, nazwy organizacji (ASN), wyniki odwrotnego DNS i wyniki usług reputacji są poprawne, aktualne lub nadają się do podejmowania decyzji; Agent nie zakłóca działania innych aplikacji, innych VPN ani łączności telefonu; oprogramowanie jest wolne od podatności.

4. WYŁĄCZENIE ODPOWIEDZIALNOŚCI
W ŻADNYM WYPADKU, O ILE BEZWZGLĘDNIE OBOWIĄZUJĄCE PRZEPISY NIE STANOWIĄ INACZEJ, AUTOR, WSPÓŁTWÓRCY ANI DYSTRYBUTORZY OPROGRAMOWANIA NIE PONOSZĄ ODPOWIEDZIALNOŚCI WOBEC CIEBIE ANI OSÓB TRZECICH ZA JAKIEKOLWIEK SZKODY BEZPOŚREDNIE, POŚREDNIE, PRZYPADKOWE, SZCZEGÓLNE, PRZYKŁADOWE, KARNE LUB WTÓRNE (W TYM BEZ OGRANICZEŃ UTRATĘ LUB USZKODZENIE DANYCH, UTRATĘ ZYSKÓW, RENOMY LUB SZANS, PRZERWĘ W DZIAŁALNOŚCI, AWARIĘ LUB NIEPRAWIDŁOWE DZIAŁANIE TELEFONU LUB PC, UTRATĘ ŁĄCZNOŚCI, KOSZTY USŁUG ZASTĘPCZYCH, KARY, ROSZCZENIA OSÓB TRZECICH) WYNIKAJĄCE Z UŻYCIA LUB NIEMOŻNOŚCI UŻYCIA OPROGRAMOWANIA, Z DECYZJI PODJĘTYCH NA PODSTAWIE JEGO WSKAZAŃ, Z INSTALACJI LUB USUNIĘCIA AGENTA, Z UŻYCIA NARZĘDZI OSÓB TRZECICH POBRANYCH LUB URUCHOMIONYCH PRZEZ PROGRAM (adb, scrcpy, bazy danych, listy) LUB Z WYSYŁANIA DANYCH DO USŁUG ZEWNĘTRZNYCH, NAWET JEŚLI POINFORMOWANO O MOŻLIWOŚCI WYSTĄPIENIA TAKICH SZKÓD I NIEZALEŻNIE OD PODSTAWY PRAWNEJ (UMOWA, CZYN NIEDOZWOLONY, ODPOWIEDZIALNOŚĆ NA ZASADZIE RYZYKA LUB INNA). W krajach, które nie dopuszczają całkowitego wyłączenia, odpowiedzialność jest ograniczona w maksymalnym dozwolonym zakresie.

5. DANE, PRYWATNOŚĆ I USŁUGI OSÓB TRZECICH
Oprogramowanie działa lokalnie i nie wysyła danych do autora. Opcjonalne funkcje odpytujące usługi zewnętrzne (bazy DB-IP, listy reputacji, VirusTotal, AbuseIPDB, Shodan, ipinfo, sprawdzenie Twojego publicznego IP, pobieranie adb/scrcpy/map) przekazują tym usługom adresy IP, nazwy domen lub inne informacje z Twojej analizy i podlegają warunkom oraz politykom prywatności każdej usługi, które akceptujesz, korzystając z nich ze swoimi kluczami. Autor nie odpowiada za działanie tych usług, ich koszty, limity lub przerwy ani za dokładność zwracanych przez nie danych. Agent zainstalowany na telefonie zbiera metadane połączeń (adresy, porty, bajty, aplikacje, zapytania DNS) oraz, na Twoje żądanie, zrzuty ekranu; usuń go, gdy nie jest już potrzebny (Program robi to przy Stop i przy zamknięciu).

6. LICENCJE I KOMPONENTY OSÓB TRZECICH
Oprogramowanie jest rozpowszechniane na licencji GNU GPL v3 lub nowszej (plik LICENSE); obowiązkowe informacje o autorstwie i licencje komponentów oraz danych osób trzecich (DB-IP CC BY 4.0, Natural Earth, Android Platform-Tools na warunkach Android SDK, scrcpy, CustomTkinter, Pillow, Kotlin i inne) znajdują się w NOTICE i THIRD_PARTY_NOTICES.md. Masz obowiązek ich przestrzegać, w szczególności warunków Google dotyczących Platform-Tools oraz zakazu redystrybucji pobranych baz danych i narzędzi. Niniejsze warunki uzupełniają GPL i nie ograniczają wynikających z niej praw do kopiowania, modyfikowania i redystrybucji kodu; punkty 3 i 4 odtwarzają i uzupełniają sekcje 15 i 16 GPL v3.

7. ZMIANY, PRAWO WŁAŚCIWE I POSTANOWIENIA KOŃCOWE
Niniejsze warunki mogą być aktualizowane w kolejnych wersjach oprogramowania; przy pierwszym uruchomieniu wersji z nowymi warunkami zostaną one przedstawione ponownie. Jeśli którekolwiek postanowienie jest nieważne, pozostałe zachowują moc. Z zastrzeżeniem bezwzględnie obowiązujących przepisów chroniących Ciebie, stosuje się prawo włoskie. Oprogramowanie nie jest przeznaczone dla osób niepełnoletnich ani do zastosowań, w których awaria mogłaby spowodować obrażenia osób lub szkody w mieniu.

Naciskając „Akceptuję", potwierdzasz, że przeczytałeś(-aś) i akceptujesz wszystkie powyższe punkty, że używasz DroidSnex wyłącznie na własnych urządzeniach lub za upoważnieniem oraz że bierzesz pełną odpowiedzialność za sposób, w jaki z niego korzystasz.
"""

_EL = """\
ΟΡΟΙ ΧΡΗΣΗΣ ΚΑΙ ΑΠΟΠΟΙΗΣΗ ΕΥΘΥΝΗΣ — DroidSnex (πρόγραμμα PC και εφαρμογή Android)
Έκδοση {v} της {d}

Διαβάστε προσεκτικά. Πατώντας «Αποδέχομαι» δηλώνετε ότι διαβάσατε, κατανοήσατε και αποδέχεστε πλήρως τους παρόντες όρους. Αν δεν τους αποδέχεστε, πατήστε «Απορρίπτω»: το πρόγραμμα κλείνει και δεν μπορείτε να το χρησιμοποιήσετε.

1. ΤΙ ΕΙΝΑΙ ΤΟ DROIDSNEX
Το DroidSnex είναι εργαλείο ανάλυσης δικτυακής κίνησης που αποτελείται από ένα πρόγραμμα για PC (το «Πρόγραμμα») και μια εφαρμογή Android (ο «Agent») που το Πρόγραμμα εγκαθιστά στο τηλέφωνο που συνδέεται μέσω USB. Ο Agent χρησιμοποιεί την τοπική υπηρεσία VPN του Android για να παρατηρεί τις δικτυακές συνδέσεις της συσκευής και τις στέλνει στο Πρόγραμμα, το οποίο τις εμφανίζει, τις ταξινομεί, τις συγκρίνει με λίστες φήμης και βάσεις γεωεντοπισμού και, αν το ζητήσετε, τις στέλνει σε υπηρεσίες τρίτων (VirusTotal, AbuseIPDB, Shodan, ipinfo και παρόμοιες) μέσω των κλειδιών API που εισάγετε εσείς.

2. ΕΠΙΤΡΕΠΟΜΕΝΗ ΧΡΗΣΗ ΚΑΙ ΕΥΘΥΝΗ ΤΟΥ ΧΡΗΣΤΗ
Το λογισμικό προορίζεται αποκλειστικά για ανάλυση, διάγνωση και ασφάλεια συσκευών που σας ανήκουν ή για τις οποίες έχετε ρητή, τεκμηριωμένη και ισχύουσα εξουσιοδότηση του νόμιμου ιδιοκτήτη ή του υποκειμένου των δεδομένων. Είστε ο μόνος υπεύθυνος για: (α) να ελέγξετε ότι η χρήση σας είναι νόμιμη στη χώρα σας και στη χώρα όπου βρίσκεται η αναλυόμενη συσκευή· (β) να λάβετε κάθε συγκατάθεση ή άδεια που απαιτεί ο νόμος, συμπεριλαμβανομένων εκείνων για την προστασία προσωπικών δεδομένων, το απόρρητο των επικοινωνιών, το εργατικό δίκαιο και τα εγκλήματα πληροφορικής· (γ) να φυλάσσετε και να χρησιμοποιείτε σωστά τα συλλεγόμενα δεδομένα, τις αποθηκευμένες συνεδρίες, τα στιγμιότυπα οθόνης και τις εξαγωγές, που μπορεί να περιέχουν προσωπικά δεδομένα, διαπιστευτήρια ή εμπιστευτικές πληροφορίες. Απαγορεύεται η χρήση του λογισμικού για υποκλοπή, παρακολούθηση ή κατασκοπεία επικοινωνιών τρίτων χωρίς τη συγκατάθεσή τους, για παράκαμψη μέτρων ασφαλείας, για παραβίαση δικαιωμάτων άλλων ή για οποιονδήποτε παράνομο σκοπό. Ο δημιουργός δεν ελέγχει και δεν μπορεί να ελέγξει τη χρήση που κάνετε.

3. ΚΑΜΙΑ ΕΓΓΥΗΣΗ («ΩΣ ΕΧΕΙ»)
ΣΤΟΝ ΜΕΓΙΣΤΟ ΒΑΘΜΟ ΠΟΥ ΕΠΙΤΡΕΠΕΤΑΙ ΑΠΟ ΤΟ ΕΦΑΡΜΟΣΤΕΟ ΔΙΚΑΙΟ, ΤΟ ΠΡΟΓΡΑΜΜΑ ΚΑΙ Ο AGENT ΠΑΡΕΧΟΝΤΑΙ «ΩΣ ΕΧΟΥΝ» ΚΑΙ «ΟΠΩΣ ΔΙΑΤΙΘΕΝΤΑΙ», ΧΩΡΙΣ ΚΑΝΕΝΟΣ ΕΙΔΟΥΣ ΕΓΓΥΗΣΗ, ΡΗΤΗ Ή ΣΙΩΠΗΡΗ, ΣΥΜΠΕΡΙΛΑΜΒΑΝΟΜΕΝΩΝ, ΕΝΔΕΙΚΤΙΚΑ, ΤΩΝ ΣΙΩΠΗΡΩΝ ΕΓΓΥΗΣΕΩΝ ΕΜΠΟΡΕΥΣΙΜΟΤΗΤΑΣ, ΚΑΤΑΛΛΗΛΟΤΗΤΑΣ ΓΙΑ ΣΥΓΚΕΚΡΙΜΕΝΟ ΣΚΟΠΟ, ΜΗ ΠΑΡΑΒΙΑΣΗΣ ΔΙΚΑΙΩΜΑΤΩΝ ΤΡΙΤΩΝ, ΑΚΡΙΒΕΙΑΣ, ΔΙΑΘΕΣΙΜΟΤΗΤΑΣ ΚΑΙ ΑΠΟΥΣΙΑΣ ΣΦΑΛΜΑΤΩΝ. ΟΛΟΣ Ο ΚΙΝΔΥΝΟΣ ΩΣ ΠΡΟΣ ΤΗΝ ΠΟΙΟΤΗΤΑ ΚΑΙ ΤΗΝ ΑΠΟΔΟΣΗ ΤΟΥ ΛΟΓΙΣΜΙΚΟΥ ΒΑΡΥΝΕΙ ΕΣΑΣ. ΑΝ ΤΟ ΛΟΓΙΣΜΙΚΟ ΑΠΟΔΕΙΧΘΕΙ ΕΛΑΤΤΩΜΑΤΙΚΟ, ΑΝΑΛΑΜΒΑΝΕΤΕ ΤΟ ΚΟΣΤΟΣ ΚΑΘΕ ΑΝΑΓΚΑΙΑΣ ΣΥΝΤΗΡΗΣΗΣ, ΕΠΙΣΚΕΥΗΣ Ή ΔΙΟΡΘΩΣΗΣ. Ειδικότερα, δεν παρέχεται εγγύηση ότι: οι εμφανιζόμενες συνδέσεις είναι πλήρεις ή ακριβείς· οι ταξινομήσεις «αξιόπιστο»/«μη αξιόπιστο», τα επίπεδα κινδύνου, οι γεωεντοπισμοί, τα ονόματα οργανισμών (ASN), οι αντίστροφες επιλύσεις DNS και τα αποτελέσματα των υπηρεσιών φήμης είναι σωστά, ενημερωμένα ή κατάλληλα για λήψη αποφάσεων· ο Agent δεν παρεμβαίνει σε άλλες εφαρμογές, άλλα VPN ή στη συνδεσιμότητα του τηλεφώνου· το λογισμικό είναι απαλλαγμένο από ευπάθειες.

4. ΑΠΟΠΟΙΗΣΗ ΕΥΘΥΝΗΣ
ΣΕ ΚΑΜΙΑ ΠΕΡΙΠΤΩΣΗ, ΕΚΤΟΣ ΑΝ ΟΡΙΖΕΤΑΙ ΔΙΑΦΟΡΕΤΙΚΑ ΑΠΟ ΑΝΑΓΚΑΣΤΙΚΟ ΔΙΚΑΙΟ, Ο ΔΗΜΙΟΥΡΓΟΣ, ΟΙ ΣΥΝΕΡΓΑΤΕΣ Ή ΟΙ ΔΙΑΝΟΜΕΙΣ ΤΟΥ ΛΟΓΙΣΜΙΚΟΥ ΔΕΝ ΕΥΘΥΝΟΝΤΑΙ ΑΠΕΝΑΝΤΙ ΣΑΣ Ή ΑΠΕΝΑΝΤΙ ΣΕ ΤΡΙΤΟΥΣ ΓΙΑ ΟΠΟΙΑΔΗΠΟΤΕ ΑΜΕΣΗ, ΕΜΜΕΣΗ, ΤΥΧΑΙΑ, ΕΙΔΙΚΗ, ΠΑΡΑΔΕΙΓΜΑΤΙΚΗ, ΤΙΜΩΡΗΤΙΚΗ Ή ΕΠΑΚΟΛΟΥΘΗ ΖΗΜΙΑ (ΣΥΜΠΕΡΙΛΑΜΒΑΝΟΜΕΝΩΝ, ΧΩΡΙΣ ΠΕΡΙΟΡΙΣΜΟ, ΑΠΩΛΕΙΑΣ Ή ΑΛΛΟΙΩΣΗΣ ΔΕΔΟΜΕΝΩΝ, ΑΠΩΛΕΙΑΣ ΚΕΡΔΩΝ, ΦΗΜΗΣ Ή ΕΥΚΑΙΡΙΩΝ, ΔΙΑΚΟΠΗΣ ΔΡΑΣΤΗΡΙΟΤΗΤΑΣ, ΒΛΑΒΗΣ Ή ΔΥΣΛΕΙΤΟΥΡΓΙΑΣ ΤΟΥ ΤΗΛΕΦΩΝΟΥ Ή ΤΟΥ PC, ΑΠΩΛΕΙΑΣ ΣΥΝΔΕΣΙΜΟΤΗΤΑΣ, ΚΟΣΤΟΥΣ ΥΠΟΚΑΤΑΣΤΑΤΩΝ ΥΠΗΡΕΣΙΩΝ, ΠΡΟΣΤΙΜΩΝ, ΑΞΙΩΣΕΩΝ ΤΡΙΤΩΝ) ΠΟΥ ΠΡΟΚΥΠΤΕΙ ΑΠΟ ΤΗ ΧΡΗΣΗ Ή ΤΗΝ ΑΔΥΝΑΜΙΑ ΧΡΗΣΗΣ ΤΟΥ ΛΟΓΙΣΜΙΚΟΥ, ΑΠΟ ΑΠΟΦΑΣΕΙΣ ΠΟΥ ΛΗΦΘΗΚΑΝ ΜΕ ΒΑΣΗ ΤΙΣ ΕΝΔΕΙΞΕΙΣ ΤΟΥ, ΑΠΟ ΤΗΝ ΕΓΚΑΤΑΣΤΑΣΗ Ή ΑΦΑΙΡΕΣΗ ΤΟΥ AGENT, ΑΠΟ ΤΗ ΧΡΗΣΗ ΕΡΓΑΛΕΙΩΝ ΤΡΙΤΩΝ ΠΟΥ ΚΑΤΕΒΑΣΕ Ή ΕΚΚΙΝΗΣΕ ΤΟ ΠΡΟΓΡΑΜΜΑ (adb, scrcpy, βάσεις δεδομένων, λίστες) Ή ΑΠΟ ΤΗΝ ΑΠΟΣΤΟΛΗ ΔΕΔΟΜΕΝΩΝ ΣΕ ΕΞΩΤΕΡΙΚΕΣ ΥΠΗΡΕΣΙΕΣ, ΑΚΟΜΗ ΚΑΙ ΑΝ ΕΧΟΥΝ ΕΝΗΜΕΡΩΘΕΙ ΓΙΑ ΤΗΝ ΠΙΘΑΝΟΤΗΤΑ ΤΕΤΟΙΩΝ ΖΗΜΙΩΝ ΚΑΙ ΑΝΕΞΑΡΤΗΤΑ ΑΠΟ ΤΗ ΝΟΜΙΚΗ ΒΑΣΗ (ΣΥΜΒΑΣΗ, ΑΔΙΚΟΠΡΑΞΙΑ, ΑΝΤΙΚΕΙΜΕΝΙΚΗ ΕΥΘΥΝΗ Ή ΑΛΛΟ). Στις χώρες που δεν επιτρέπουν πλήρη αποκλεισμό, η ευθύνη περιορίζεται στον μέγιστο επιτρεπόμενο βαθμό.

5. ΔΕΔΟΜΕΝΑ, ΑΠΟΡΡΗΤΟ ΚΑΙ ΥΠΗΡΕΣΙΕΣ ΤΡΙΤΩΝ
Το λογισμικό λειτουργεί τοπικά και δεν στέλνει δεδομένα στον δημιουργό. Οι προαιρετικές λειτουργίες που ρωτούν εξωτερικές υπηρεσίες (βάσεις DB-IP, λίστες φήμης, VirusTotal, AbuseIPDB, Shodan, ipinfo, αναζήτηση της δημόσιας IP σας, λήψη adb/scrcpy/χαρτών) διαβιβάζουν σε αυτές διευθύνσεις IP, ονόματα τομέων ή άλλες πληροφορίες της ανάλυσής σας και υπόκεινται στους όρους και τις πολιτικές απορρήτου κάθε υπηρεσίας, τους οποίους αποδέχεστε χρησιμοποιώντας τες με τα κλειδιά σας. Ο δημιουργός δεν ευθύνεται για τη συμπεριφορά αυτών των υπηρεσιών, το κόστος, τα όρια ή τις διακοπές τους, ούτε για την ακρίβεια των δεδομένων που επιστρέφουν. Ο Agent που εγκαθίσταται στο τηλέφωνο συλλέγει μεταδεδομένα συνδέσεων (διευθύνσεις, θύρες, bytes, εφαρμογές, ερωτήματα DNS) και, κατόπιν αιτήματός σας, στιγμιότυπα οθόνης· αφαιρέστε τον όταν δεν τον χρειάζεστε (το Πρόγραμμα το κάνει στο Stop και στο κλείσιμο).

6. ΑΔΕΙΕΣ ΚΑΙ ΣΤΟΙΧΕΙΑ ΤΡΙΤΩΝ
Το λογισμικό διανέμεται υπό την άδεια GNU GPL v3 ή νεότερη (αρχείο LICENSE)· οι υποχρεωτικές αναφορές και οι άδειες των στοιχείων και δεδομένων τρίτων (DB-IP CC BY 4.0, Natural Earth, Android Platform-Tools με τους όρους του Android SDK, scrcpy, CustomTkinter, Pillow, Kotlin και άλλα) βρίσκονται στα NOTICE και THIRD_PARTY_NOTICES.md. Οφείλετε να τις τηρείτε, ιδίως τους όρους της Google για τα Platform-Tools και την απαγόρευση αναδιανομής των βάσεων δεδομένων και εργαλείων που κατεβάσατε. Οι παρόντες όροι προστίθενται στην GPL και δεν περιορίζουν τα δικαιώματά της αντιγραφής, τροποποίησης και αναδιανομής του κώδικα· οι ρήτρες 3 και 4 αναπαράγουν και συμπληρώνουν τις ενότητες 15 και 16 της GPL v3.

7. ΤΡΟΠΟΠΟΙΗΣΕΙΣ, ΕΦΑΡΜΟΣΤΕΟ ΔΙΚΑΙΟ ΚΑΙ ΤΕΛΙΚΕΣ ΡΗΤΡΕΣ
Οι παρόντες όροι μπορεί να ενημερωθούν σε επόμενες εκδόσεις του λογισμικού· στο πρώτο άνοιγμα έκδοσης με νέους όρους θα σας ζητηθεί ξανά η αποδοχή. Αν κάποια ρήτρα είναι άκυρη, οι υπόλοιπες παραμένουν σε ισχύ. Με την επιφύλαξη αναγκαστικών διατάξεων για την προστασία σας, εφαρμόζεται το ιταλικό δίκαιο. Το λογισμικό δεν προορίζεται για ανηλίκους ούτε για χρήσεις στις οποίες μια δυσλειτουργία θα μπορούσε να προκαλέσει βλάβη σε πρόσωπα ή πράγματα.

Πατώντας «Αποδέχομαι» επιβεβαιώνετε ότι διαβάσατε και αποδέχεστε όλα τα παραπάνω σημεία, ότι χρησιμοποιείτε το DroidSnex μόνο σε δικές σας συσκευές ή με εξουσιοδότηση και ότι αναλαμβάνετε κάθε ευθύνη για τη χρήση που κάνετε.
"""

_SQ = """\
KUSHTET E PËRDORIMIT DHE PËRJASHTIMI I PËRGJEGJËSISË — DroidSnex (programi për PC dhe aplikacioni Android)
Versioni {v} i datës {d}

Lexoni me kujdes. Duke shtypur "Pranoj" deklaroni se i keni lexuar, kuptuar dhe pranuar plotësisht këto kushte. Nëse nuk i pranoni, shtypni "Refuzoj": programi mbyllet dhe nuk mund ta përdorni.

1. ÇFARË ËSHTË DROIDSNEX
DroidSnex është një mjet për analizën e trafikut të rrjetit, i përbërë nga një program për PC ("Programi") dhe një aplikacion Android ("Agjenti") që Programi e instalon në telefonin e lidhur me USB. Agjenti përdor shërbimin lokal VPN të Android për të vëzhguar lidhjet e rrjetit të pajisjes dhe ia dërgon ato Programit, i cili i shfaq, i klasifikon, i krahason me lista reputacioni dhe baza të dhënash gjeolokalizimi dhe, nëse e kërkoni, ia dërgon shërbimeve të palëve të treta (VirusTotal, AbuseIPDB, Shodan, ipinfo e të ngjashme) përmes çelësave API që vendosni ju.

2. PËRDORIMI I LEJUAR DHE PËRGJEGJËSIA E PËRDORUESIT
Softueri është i destinuar ekskluzivisht për analizën, diagnostikimin dhe sigurinë e pajisjeve që ju përkasin ose për të cilat keni një autorizim të shprehur, të dokumentuar dhe të vlefshëm nga pronari i ligjshëm ose personi i interesuar. Ju jeni i vetmi përgjegjës për: (a) të verifikoni që përdorimi juaj është i ligjshëm në vendin tuaj dhe në vendin ku ndodhet pajisja e analizuar; (b) të merrni çdo pëlqim ose autorizim të kërkuar nga ligji, përfshirë ato për mbrojtjen e të dhënave personale, fshehtësinë e komunikimeve, të drejtën e punës dhe krimet kompjuterike; (c) të ruani dhe të përdorni saktë të dhënat e mbledhura, sesionet e ruajtura, pamjet e ekranit dhe eksportimet, që mund të përmbajnë të dhëna personale, kredenciale ose informacione konfidenciale. Ndalohet përdorimi i softuerit për të përgjuar, mbikëqyrur ose spiunuar komunikimet e të tretëve pa pëlqimin e tyre, për të anashkaluar masa sigurie, për të shkelur të drejtat e të tjerëve ose për çfarëdo qëllimi të paligjshëm. Autori nuk e kontrollon dhe nuk mund ta kontrollojë përdorimin që bëni.

3. ASNJË GARANCI ("SIÇ ËSHTË")
NË MASËN MAKSIMALE TË LEJUAR NGA LIGJI I ZBATUESHËM, PROGRAMI DHE AGJENTI OFROHEN "SIÇ JANË" DHE "SIÇ JANË TË DISPONUESHËM", PA ASNJË LLOJ GARANCIE, TË SHPREHUR OSE TË NËNKUPTUAR, PËRFSHIRË, POR PA U KUFIZUAR NË, GARANCITË E NËNKUPTUARA TË TREGTUESHMËRISË, PËRSHTATSHMËRISË PËR NJË QËLLIM TË CAKTUAR, MOSSHKELJES SË TË DREJTAVE TË TË TRETËVE, SAKTËSISË, DISPONUESHMËRISË DHE MUNGESËS SË GABIMEVE. I GJITHË RREZIKU PËR CILËSINË DHE PERFORMANCËN E SOFTUERIT ËSHTË I JUAJI. NËSE SOFTUERI REZULTON ME DEFEKT, JU MERRNI PËRSIPËR KOSTON E ÇDO ASISTENCE, RIPARIMI OSE KORRIGJIMI. Në veçanti nuk garantohet që: lidhjet e shfaqura të jenë të plota ose të sakta; klasifikimet "i besuar"/"i pabesuar", nivelet e rrezikut, gjeolokalizimet, emrat e organizatave (ASN), zgjidhjet e kundërta DNS dhe rezultatet e shërbimeve të reputacionit të jenë të sakta, të përditësuara ose të përshtatshme për marrjen e vendimeve; Agjenti të mos ndërhyjë me aplikacione të tjera, VPN të tjera ose lidhjen e telefonit; softueri të jetë pa dobësi sigurie.

4. PËRJASHTIMI I PËRGJEGJËSISË
NË ASNJË RAST, PËRVEÇ KUR LIGJI I DETYRUESHËM PARASHIKON NDRYSHE, AUTORI, BASHKËPUNËTORËT OSE SHPËRNDARËSIT E SOFTUERIT NUK DO TË JENË PËRGJEGJËS NDAJ JUSH OSE NDAJ TË TRETËVE PËR ASNJË DËM TË DREJTPËRDREJTË, TË TËRTHORTË, TË RASTËSISHËM, TË VEÇANTË, SHEMBULLOR, NDËSHKUES OSE PASOJË (PËRFSHIRË, PA KUFIZIM, HUMBJEN OSE DËMTIMIN E TË DHËNAVE, HUMBJEN E FITIMEVE, TË EMRIT TË MIRË OSE TË MUNDËSIVE, NDËRPRERJEN E VEPRIMTARISË, PRISHJEN OSE MOSFUNKSIONIMIN E TELEFONIT OSE TË PC-SË, HUMBJEN E LIDHJES, KOSTON E SHËRBIMEVE ZËVENDËSUESE, GJOBAT, PRETENDIMET E TË TRETËVE) QË RRJEDHIN NGA PËRDORIMI OSE PAMUNDËSIA E PËRDORIMIT TË SOFTUERIT, NGA VENDIME TË MARRA MBI BAZËN E TREGUESVE TË TIJ, NGA INSTALIMI OSE HEQJA E AGJENTIT, NGA PËRDORIMI I MJETEVE TË PALËVE TË TRETA TË SHKARKUARA OSE TË NISURA NGA PROGRAMI (adb, scrcpy, baza të dhënash, lista) OSE NGA DËRGIMI I TË DHËNAVE TE SHËRBIME TË JASHTME, EDHE NËSE JANË PARALAJMËRUAR PËR MUNDËSINË E DËMEVE TË TILLA DHE PAVARËSISHT NGA BAZA LIGJORE (KONTRATË, DËM JASHTËKONTRAKTOR, PËRGJEGJËSI OBJEKTIVE OSE TJETËR). Në vendet që nuk lejojnë përjashtimin e plotë, përgjegjësia kufizohet në masën maksimale të lejuar.

5. TË DHËNAT, PRIVATËSIA DHE SHËRBIMET E PALËVE TË TRETA
Softueri funksionon lokalisht dhe nuk i dërgon të dhëna autorit. Funksionet opsionale që pyesin shërbime të jashtme (bazat DB-IP, listat e reputacionit, VirusTotal, AbuseIPDB, Shodan, ipinfo, kërkimi i IP-së suaj publike, shkarkimi i adb/scrcpy/hartave) u transmetojnë atyre shërbimeve adresa IP, emra domenesh ose informacione të tjera të analizës suaj dhe u nënshtrohen kushteve dhe politikave të privatësisë së secilit shërbim, që ju i pranoni duke i përdorur me çelësat tuaj. Autori nuk është përgjegjës për sjelljen e këtyre shërbimeve, për kostot, kufijtë ose ndërprerjet e tyre, as për saktësinë e të dhënave që kthejnë. Agjenti i instaluar në telefon mbledh metadata të lidhjeve (adresa, porta, byte, aplikacione, pyetje DNS) dhe, me kërkesën tuaj, pamje ekrani; hiqeni kur nuk ju duhet më (Programi e bën këtë te Stop dhe në mbyllje).

6. LICENCAT DHE KOMPONENTËT E PALËVE TË TRETA
Softueri shpërndahet nën licencën GNU GPL v3 ose më të re (skedari LICENSE); atribuimet e detyrueshme dhe licencat e komponentëve dhe të dhënave të palëve të treta (DB-IP CC BY 4.0, Natural Earth, Android Platform-Tools me kushtet e Android SDK, scrcpy, CustomTkinter, Pillow, Kotlin e të tjera) gjenden në NOTICE dhe THIRD_PARTY_NOTICES.md. Jeni të detyruar t'i respektoni, në veçanti kushtet e Google për Platform-Tools dhe ndalimin e rishpërndarjes së bazave të të dhënave dhe mjeteve të shkarkuara. Këto kushte i shtohen GPL-së dhe nuk i kufizojnë të drejtat e saj për kopjimin, ndryshimin dhe rishpërndarjen e kodit; pikat 3 dhe 4 riprodhojnë dhe plotësojnë seksionet 15 dhe 16 të GPL v3.

7. NDRYSHIMET, LIGJI I ZBATUESHËM DHE DISPOZITAT PËRFUNDIMTARE
Këto kushte mund të përditësohen në versionet e mëvonshme të softuerit; në hapjen e parë të një versioni me kushte të reja do t'ju kërkohen përsëri. Nëse një pikë është e pavlefshme, të tjerat mbeten në fuqi. Me përjashtim të normave të detyrueshme në mbrojtjen tuaj, zbatohet ligji italian. Softueri nuk është i destinuar për të miturit as për përdorime ku një mosfunksionim mund të shkaktojë dëme ndaj personave ose sendeve.

Duke shtypur "Pranoj" konfirmoni se i keni lexuar dhe pranuar të gjitha pikat e mësipërme, se e përdorni DroidSnex vetëm në pajisjet tuaja ose me autorizim, dhe se merrni përsipër çdo përgjegjësi për përdorimin që bëni.
"""

TEXTS = {"it": _IT, "en": _EN, "de": _DE, "fr": _FR, "es": _ES, "nl": _NL, "pl": _PL, "el": _EL, "sq": _SQ}

# etichette dei pulsanti, nella lingua dei termini (non passano da tr: devono seguire la lingua scelta nella finestra)
LABELS = {
    "it": ("Termini d'uso", "Accetto", "Rifiuto", "Scegli la lingua", "Leggi i termini fino in fondo: con Rifiuto il programma si chiude."),
    "en": ("Terms of use", "I accept", "I decline", "Choose your language", "Read the terms to the end: with Decline the program closes."),
    "de": ("Nutzungsbedingungen", "Ich akzeptiere", "Ich lehne ab", "Sprache wählen", "Lesen Sie die Bedingungen bis zum Ende: mit Ablehnen wird das Programm beendet."),
    "fr": ("Conditions d'utilisation", "J'accepte", "Je refuse", "Choisissez la langue", "Lisez les conditions jusqu'au bout : avec Refuser, le programme se ferme."),
    "es": ("Términos de uso", "Acepto", "Rechazo", "Elija el idioma", "Lea los términos hasta el final: con Rechazo el programa se cierra."),
    "nl": ("Gebruiksvoorwaarden", "Ik accepteer", "Ik weiger", "Kies uw taal", "Lees de voorwaarden tot het einde: met Weigeren sluit het programma af."),
    "pl": ("Warunki użytkowania", "Akceptuję", "Odrzucam", "Wybierz język", "Przeczytaj warunki do końca: po Odrzucam program się zamknie."),
    "el": ("Όροι χρήσης", "Αποδέχομαι", "Απορρίπτω", "Επιλέξτε γλώσσα", "Διαβάστε τους όρους μέχρι το τέλος: με Απορρίπτω το πρόγραμμα κλείνει."),
    "sq": ("Kushtet e përdorimit", "Pranoj", "Refuzoj", "Zgjidhni gjuhën", "Lexoni kushtet deri në fund: me Refuzoj programi mbyllet."),
}


def text(lang: str) -> str:
    """Il testo completo dei termini nella lingua (italiano se la lingua non c'e')."""
    return TEXTS.get(lang, _IT).format(v=TERMS_VERSION, d=TERMS_DATE)


def labels(lang: str) -> tuple[str, str, str, str, str]:
    """(titolo, Accetto, Rifiuto, Scegli la lingua, nota) nella lingua."""
    return LABELS.get(lang, LABELS["it"])


def markdown() -> str:
    """TERMS.md: tutte le lingue, una sezione per lingua."""
    from .i18n import LANGUAGES
    out = ["# DroidSnex — Terms of use / Termini d'uso", "",
           f"Version {TERMS_VERSION} ({TERMS_DATE}). Generated from `pc/droidsnex/terms.py` "
           "(`cd pc && python -m droidsnex.terms > ../TERMS.md`). The program shows these terms in the chosen "
           "language on first launch and keeps the acceptance (version and date) in `config.json`; they are "
           "shown again when the version changes. Also available from the *Info e licenze* window.", ""]
    for code in ("it", "en", "de", "fr", "es", "nl", "pl", "el", "sq"):
        out += [f"## {LANGUAGES[code]} ({code})", "", "```text", text(code).rstrip(), "```", ""]
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    sys.stdout.write(markdown())
