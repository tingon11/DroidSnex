package com.droidsnex.agent

import android.content.Context

/**
 * Testi dell'app nelle stesse 9 lingue del programma PC.
 *
 * La lingua la sceglie il PC: in Config del programma PC, poi passata a ogni
 * Start con `am start ... --es lang <codice>`. Viene salvata nelle
 * SharedPreferences così la usa anche il servizio (notifiche) e resta dopo
 * un riavvio dell'app. Senza indicazioni si usa l'italiano.
 *
 * Ogni riga: it, en, de, fr, es, nl, pl, el, sq. "{0}" è un segnaposto.
 */
object Strings {
    val LANGS = listOf("it", "en", "de", "fr", "es", "nl", "pl", "el", "sq")
    private const val PREFS = "droidsnex"
    private const val KEY = "lang"

    @Volatile var lang = "it"
        private set

    /** Legge la lingua salvata (chiamato all'avvio di activity e servizio). */
    fun load(ctx: Context) {
        val saved = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, null)
        if (saved != null && saved in LANGS) lang = saved
    }

    /** Imposta e salva la lingua ricevuta dal PC. Ritorna true se è cambiata. */
    fun set(ctx: Context, code: String?): Boolean {
        if (code == null || code !in LANGS || code == lang) return false
        lang = code
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY, code).apply()
        return true
    }

    fun t(key: String, vararg args: Any): String {
        val row = TEXT[key] ?: return key
        var s = row[LANGS.indexOf(lang).coerceAtLeast(0)]
        args.forEachIndexed { i, a -> s = s.replace("{$i}", a.toString()) }
        return s
    }

    val TEXT: Map<String, Array<String>> = mapOf(
        "subtitle" to arrayOf("network monitor", "network monitor", "Netzwerkmonitor", "moniteur réseau", "monitor de red",
            "netwerkmonitor", "monitor sieci", "παρακολούθηση δικτύου", "monitor rrjeti"),
        "status" to arrayOf("Stato", "Status", "Status", "État", "Estado", "Status", "Stan", "Κατάσταση", "Gjendja"),
        "connections" to arrayOf("Connessioni", "Connections", "Verbindungen", "Connexions", "Conexiones", "Verbindingen",
            "Połączenia", "Συνδέσεις", "Lidhjet"),
        "running" to arrayOf("Cattura attiva", "Capture active", "Aufzeichnung aktiv", "Capture active", "Captura activa",
            "Opname actief", "Przechwytywanie aktywne", "Καταγραφή ενεργή", "Kapja aktive"),
        "stopped" to arrayOf("Cattura ferma", "Capture stopped", "Aufzeichnung gestoppt", "Capture arrêtée", "Captura detenida",
            "Opname gestopt", "Przechwytywanie zatrzymane", "Καταγραφή σε παύση", "Kapja e ndalur"),
        "open_now" to arrayOf("aperte ora: {0}", "open now: {0}", "jetzt offen: {0}", "ouvertes : {0}", "abiertas ahora: {0}",
            "nu open: {0}", "otwarte teraz: {0}", "ανοιχτές τώρα: {0}", "të hapura tani: {0}"),
        "pc_on" to arrayOf("PC collegato", "PC connected", "PC verbunden", "PC connecté", "PC conectado", "pc verbonden",
            "PC połączony", "PC συνδεδεμένο", "PC i lidhur"),
        "pc_off" to arrayOf("PC non collegato", "PC not connected", "PC nicht verbunden", "PC non connecté", "PC no conectado",
            "pc niet verbonden", "PC niepołączony", "PC μη συνδεδεμένο", "PC i palidhur"),
        "start" to arrayOf("Avvia cattura", "Start capture", "Aufzeichnung starten", "Démarrer la capture", "Iniciar captura",
            "Opname starten", "Rozpocznij przechwytywanie", "Έναρξη καταγραφής", "Nis kapjen"),
        "stop" to arrayOf("Ferma cattura", "Stop capture", "Aufzeichnung stoppen", "Arrêter la capture", "Detener captura",
            "Opname stoppen", "Zatrzymaj przechwytywanie", "Διακοπή καταγραφής", "Ndalo kapjen"),
        "info" to arrayOf(
            "VPN solo locale: il traffico esce normalmente dalla rete del telefono. Si registrano solo i metadati di destinazione (IP, porta, dominio, app), inviati al PC via USB. Se il programma PC si chiude o si scollega, la cattura si ferma da sola.",
            "Local-only VPN: traffic leaves through the phone's network as usual. Only destination metadata (IP, port, domain, app) is recorded and sent to the PC over USB. If the PC program closes or disconnects, capture stops by itself.",
            "Nur lokales VPN: der Datenverkehr geht wie gewohnt über das Netz des Telefons. Es werden nur Zielmetadaten (IP, Port, Domain, App) erfasst und per USB an den PC gesendet. Wird das PC-Programm geschlossen oder getrennt, stoppt die Aufzeichnung von selbst.",
            "VPN uniquement local : le trafic sort normalement par le réseau du téléphone. Seules les métadonnées de destination (IP, port, domaine, app) sont enregistrées et envoyées au PC par USB. Si le programme PC se ferme ou se déconnecte, la capture s'arrête toute seule.",
            "VPN solo local: el tráfico sale normalmente por la red del teléfono. Solo se registran los metadatos de destino (IP, puerto, dominio, app), enviados al PC por USB. Si el programa del PC se cierra o se desconecta, la captura se detiene sola.",
            "Alleen lokale VPN: het verkeer gaat gewoon via het netwerk van de telefoon. Alleen bestemmingsmetadata (IP, poort, domein, app) worden vastgelegd en via USB naar de pc gestuurd. Als het pc-programma sluit of de verbinding verbreekt, stopt de opname vanzelf.",
            "VPN tylko lokalny: ruch wychodzi normalnie przez sieć telefonu. Rejestrowane są tylko metadane celu (IP, port, domena, aplikacja), wysyłane do PC przez USB. Jeśli program na PC zostanie zamknięty lub odłączony, przechwytywanie zatrzyma się samo.",
            "Μόνο τοπικό VPN: η κίνηση βγαίνει κανονικά από το δίκτυο του τηλεφώνου. Καταγράφονται μόνο τα μεταδεδομένα προορισμού (IP, θύρα, τομέας, εφαρμογή) και αποστέλλονται στο PC μέσω USB. Αν το πρόγραμμα του PC κλείσει ή αποσυνδεθεί, η καταγραφή σταματά μόνη της.",
            "VPN vetëm lokale: trafiku del normalisht nga rrjeti i telefonit. Regjistrohen vetëm metadatat e destinacionit (IP, porta, domeni, aplikacioni), të dërguara te PC me USB. Nëse programi në PC mbyllet ose shkëputet, kapja ndalet vetë."),
        "err_consent_show" to arrayOf("Impossibile mostrare il consenso VPN: {0}", "Cannot show the VPN consent: {0}",
            "VPN-Zustimmung kann nicht angezeigt werden: {0}", "Impossible d'afficher le consentement VPN : {0}",
            "No se puede mostrar el consentimiento VPN: {0}", "Kan de VPN-toestemming niet tonen: {0}",
            "Nie można wyświetlić zgody VPN: {0}", "Αδύνατη η εμφάνιση της συναίνεσης VPN: {0}",
            "Pëlqimi VPN nuk mund të shfaqet: {0}"),
        "err_consent_denied" to arrayOf("Consenso VPN rifiutato", "VPN consent denied", "VPN-Zustimmung abgelehnt",
            "Consentement VPN refusé", "Consentimiento VPN rechazado", "VPN-toestemming geweigerd", "Odmówiono zgody VPN",
            "Η συναίνεση VPN απορρίφθηκε", "Pëlqimi VPN u refuzua"),
        "err_no_permission" to arrayOf("Permesso VPN non concesso", "VPN permission not granted", "VPN-Berechtigung nicht erteilt",
            "Autorisation VPN non accordée", "Permiso VPN no concedido", "VPN-machtiging niet verleend", "Nie przyznano uprawnienia VPN",
            "Δεν δόθηκε άδεια VPN", "Leja VPN nuk u dha"),
        "err_pc_lost" to arrayOf("PC scollegato: cattura fermata", "PC disconnected: capture stopped", "PC getrennt: Aufzeichnung gestoppt",
            "PC déconnecté : capture arrêtée", "PC desconectado: captura detenida", "pc losgekoppeld: opname gestopt",
            "PC odłączony: przechwytywanie zatrzymane", "Το PC αποσυνδέθηκε: η καταγραφή σταμάτησε", "PC u shkëput: kapja u ndal"),
        "notif_channel" to arrayOf("Cattura attiva", "Capture active", "Aufzeichnung aktiv", "Capture active", "Captura activa",
            "Opname actief", "Przechwytywanie aktywne", "Καταγραφή ενεργή", "Kapja aktive"),
        "notif_title" to arrayOf("DroidSnex attivo", "DroidSnex active", "DroidSnex aktiv", "DroidSnex actif", "DroidSnex activo",
            "DroidSnex actief", "DroidSnex aktywny", "DroidSnex ενεργό", "DroidSnex aktiv"),
        "notif_text" to arrayOf("Monitoraggio delle connessioni in corso (porta {0})", "Monitoring connections (port {0})",
            "Verbindungen werden überwacht (Port {0})", "Surveillance des connexions en cours (port {0})",
            "Monitorizando conexiones (puerto {0})", "Verbindingen worden bewaakt (poort {0})",
            "Monitorowanie połączeń (port {0})", "Παρακολούθηση συνδέσεων (θύρα {0})", "Po monitorohen lidhjet (porta {0})"),
        "notif_stopped_title" to arrayOf("DroidSnex fermato", "DroidSnex stopped", "DroidSnex gestoppt", "DroidSnex arrêté",
            "DroidSnex detenido", "DroidSnex gestopt", "DroidSnex zatrzymany", "Το DroidSnex σταμάτησε", "DroidSnex u ndal"),
        "notif_stopped_text" to arrayOf("Il PC si è scollegato. Tocca per disinstallare l'app.",
            "The PC disconnected. Tap to uninstall the app.", "Der PC wurde getrennt. Tippen, um die App zu deinstallieren.",
            "Le PC s'est déconnecté. Touchez pour désinstaller l'app.", "El PC se ha desconectado. Toca para desinstalar la app.",
            "De pc is losgekoppeld. Tik om de app te verwijderen.", "PC został odłączony. Dotknij, aby odinstalować aplikację.",
            "Το PC αποσυνδέθηκε. Πατήστε για απεγκατάσταση της εφαρμογής.", "PC u shkëput. Prek për të çinstaluar aplikacionin."),
    )
}
