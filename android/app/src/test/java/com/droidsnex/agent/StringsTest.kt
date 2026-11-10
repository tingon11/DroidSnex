package com.droidsnex.agent

import org.junit.Assert.assertEquals
import org.junit.Test

class StringsTest {
    private val ph = Regex("\\{\\d+\\}")

    @Test fun everyTextHasAllLanguagesAndSamePlaceholders() {
        for ((key, row) in Strings.TEXT) {
            assertEquals("lingue per $key", Strings.LANGS.size, row.size)
            val base = ph.findAll(row[0]).map { it.value }.sorted().toList()
            row.forEachIndexed { i, s ->
                assertEquals("segnaposto $key/${Strings.LANGS[i]}", base, ph.findAll(s).map { it.value }.sorted().toList())
                assert(s.isNotBlank()) { "vuoto: $key/${Strings.LANGS[i]}" }
            }
        }
    }

    @Test fun formatsPlaceholders() {
        assertEquals("aperte ora: 3", Strings.t("open_now", 3))
    }
}
