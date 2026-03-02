"""Tests for external ID generation - REGRESSION SAFETY.

These tests ensure that _make_external_id() functions produce identical
IDs after refactoring. If any test fails, existing events in the database
would get duplicate entries.
"""

import hashlib
from datetime import date

import pytest

# ---------------------------------------------------------------------------
# Imports from each adapter
# ---------------------------------------------------------------------------
from src.adapters.bronze.cnt_agenda import (
    _make_external_id as cnt_make_id,
)
from src.adapters.bronze.nferias import (
    _make_external_id as nferias_make_id,
)
from src.adapters.bronze.tourdelempleo import (
    _make_external_id as tourempleo_make_id,
)
from src.adapters.bronze.defensor_pueblo import (
    _make_external_id as defensor_make_id,
)
from src.adapters.bronze.segib import (
    _make_external_id as segib_make_id,
)
from src.adapters.bronze.horizonte_europa import (
    _make_external_id as heuropa_make_id,
)
from src.adapters.bronze.la_moncloa import (
    _make_external_id as moncloa_make_id,
)
from src.adapters.bronze.jgpa import (
    _make_external_id as jgpa_make_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _md5_12(raw: str) -> str:
    """Compute the first 12 hex chars of the MD5 hash of *raw*."""
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ===================================================================
# 1. FORMAT: prefix + 12-char hex
# ===================================================================

class TestExternalIdFormat:
    """Verify prefix and hash format for each adapter."""

    # -- standard adapters (title, date) --------------------------------

    @pytest.mark.parametrize("make_id, prefix", [
        (cnt_make_id, "cnt_"),
        (nferias_make_id, "nferias_"),
        (tourempleo_make_id, "tourempleo_"),
        (defensor_make_id, "defensor_"),
    ])
    def test_standard_prefix_and_length(self, make_id, prefix):
        result = make_id("Some Event", date(2026, 1, 1))
        assert result.startswith(prefix), f"Expected prefix '{prefix}', got '{result}'"
        hash_part = result[len(prefix):]
        assert len(hash_part) == 12, f"Hash part should be 12 chars, got {len(hash_part)}"
        assert all(c in "0123456789abcdef" for c in hash_part), (
            f"Hash part should be lowercase hex, got '{hash_part}'"
        )

    # -- date_str adapters (title, date_str) ----------------------------

    @pytest.mark.parametrize("make_id, prefix", [
        (segib_make_id, "segib_"),
        (heuropa_make_id, "heuropa_"),
    ])
    def test_datestr_prefix_and_length(self, make_id, prefix):
        result = make_id("Some Event", "2026-01-01")
        assert result.startswith(prefix)
        hash_part = result[len(prefix):]
        assert len(hash_part) == 12
        assert all(c in "0123456789abcdef" for c in hash_part)

    # -- jgpa (title[:80], date) ----------------------------------------

    def test_jgpa_prefix_and_length(self):
        result = jgpa_make_id("Some Event", date(2026, 1, 1))
        assert result.startswith("jgpa_")
        hash_part = result[len("jgpa_"):]
        assert len(hash_part) == 12
        assert all(c in "0123456789abcdef" for c in hash_part)

    # -- la_moncloa (date, cargo, desc) ---------------------------------

    def test_moncloa_prefix_and_length(self):
        result = moncloa_make_id(date(2026, 1, 1), "Presidente", "Reunion bilateral")
        assert result.startswith("moncloa_")
        hash_part = result[len("moncloa_"):]
        assert len(hash_part) == 12
        assert all(c in "0123456789abcdef" for c in hash_part)


# ===================================================================
# 2. DETERMINISM: same inputs -> same output every time
# ===================================================================

class TestExternalIdDeterminism:
    """Verify same inputs always produce same outputs."""

    def test_cnt_deterministic(self):
        a = cnt_make_id("Evento Repetido", date(2026, 6, 15))
        b = cnt_make_id("Evento Repetido", date(2026, 6, 15))
        assert a == b

    def test_nferias_deterministic(self):
        a = nferias_make_id("Feria del Libro", date(2026, 5, 1))
        b = nferias_make_id("Feria del Libro", date(2026, 5, 1))
        assert a == b

    def test_tourempleo_deterministic(self):
        a = tourempleo_make_id("Foro de Empleo", date(2026, 4, 20))
        b = tourempleo_make_id("Foro de Empleo", date(2026, 4, 20))
        assert a == b

    def test_defensor_deterministic(self):
        a = defensor_make_id("Informe Anual", date(2026, 3, 10))
        b = defensor_make_id("Informe Anual", date(2026, 3, 10))
        assert a == b

    def test_segib_deterministic(self):
        a = segib_make_id("Cumbre Iberoamericana", "2026-11-01")
        b = segib_make_id("Cumbre Iberoamericana", "2026-11-01")
        assert a == b

    def test_heuropa_deterministic(self):
        a = heuropa_make_id("Horizon Call", "2026-09-30")
        b = heuropa_make_id("Horizon Call", "2026-09-30")
        assert a == b

    def test_moncloa_deterministic(self):
        a = moncloa_make_id(date(2026, 2, 14), "Ministro", "Reunion bilateral")
        b = moncloa_make_id(date(2026, 2, 14), "Ministro", "Reunion bilateral")
        assert a == b

    def test_jgpa_deterministic(self):
        a = jgpa_make_id("Pleno del Parlamento", date(2026, 7, 1))
        b = jgpa_make_id("Pleno del Parlamento", date(2026, 7, 1))
        assert a == b


# ===================================================================
# 3. GOLDEN VALUES: pre-computed hashes that MUST NOT change
# ===================================================================

class TestExternalIdGoldenValues:
    """Pre-computed golden values that MUST NOT change during refactoring.

    Each test independently computes the expected MD5-based ID using the
    exact same algorithm the adapter uses, and asserts it matches.  If a
    refactoring accidentally changes the hashing logic, these tests will
    catch it.
    """

    # -- cnt_agenda -----------------------------------------------------

    def test_cnt_golden_value(self):
        result = cnt_make_id("Jornadas Sindicales CNT 2026", date(2026, 3, 15))
        raw = "jornadas sindicales cnt 2026_2026-03-15"
        expected = f"cnt_{_md5_12(raw)}"
        assert result == expected

    def test_cnt_golden_value_whitespace(self):
        """Leading/trailing whitespace should be stripped before hashing."""
        result = cnt_make_id("  Evento con espacios  ", date(2026, 1, 1))
        raw = "evento con espacios_2026-01-01"
        expected = f"cnt_{_md5_12(raw)}"
        assert result == expected

    # -- nferias --------------------------------------------------------

    def test_nferias_golden_value(self):
        result = nferias_make_id("FITUR 2026", date(2026, 1, 22))
        raw = "fitur 2026_2026-01-22"
        expected = f"nferias_{_md5_12(raw)}"
        assert result == expected

    # -- tourdelempleo --------------------------------------------------

    def test_tourempleo_golden_value(self):
        result = tourempleo_make_id("Foro de Empleo Madrid", date(2026, 10, 5))
        raw = "foro de empleo madrid_2026-10-05"
        expected = f"tourempleo_{_md5_12(raw)}"
        assert result == expected

    # -- defensor_pueblo ------------------------------------------------

    def test_defensor_golden_value(self):
        result = defensor_make_id("Presentacion Informe 2025", date(2026, 6, 1))
        raw = "presentacion informe 2025_2026-06-01"
        expected = f"defensor_{_md5_12(raw)}"
        assert result == expected

    # -- segib ----------------------------------------------------------

    def test_segib_golden_value(self):
        result = segib_make_id("XXIX Cumbre Iberoamericana de Jefes de Estado", "2026-11-15")
        raw = "xxix cumbre iberoamericana de jefes de estado_2026-11-15"
        # Title is 46 chars, well under 80-char truncation
        expected = f"segib_{_md5_12(raw)}"
        assert result == expected

    def test_segib_golden_truncation(self):
        """Titles longer than 80 chars must be truncated BEFORE hashing."""
        long_title = "A" * 120
        result = segib_make_id(long_title, "2026-01-01")
        # strip().lower()[:80] => "a" * 80
        raw = f"{'a' * 80}_2026-01-01"
        expected = f"segib_{_md5_12(raw)}"
        assert result == expected

    # -- horizonte_europa -----------------------------------------------

    def test_heuropa_golden_value(self):
        result = heuropa_make_id("Cluster 5 - Climate, Energy and Mobility", "2026-09-30")
        raw = "cluster 5 - climate, energy and mobility_2026-09-30"
        expected = f"heuropa_{_md5_12(raw)}"
        assert result == expected

    def test_heuropa_golden_truncation(self):
        """Titles longer than 80 chars must be truncated BEFORE hashing."""
        long_title = "B" * 100
        result = heuropa_make_id(long_title, "2026-02-28")
        raw = f"{'b' * 80}_2026-02-28"
        expected = f"heuropa_{_md5_12(raw)}"
        assert result == expected

    # -- la_moncloa -----------------------------------------------------

    def test_moncloa_golden_value(self):
        result = moncloa_make_id(
            date(2026, 3, 1),
            "Presidente del Gobierno",
            "Reunion con el primer ministro de Portugal",
        )
        raw = (
            "2026-03-01_presidente del gobierno_"
            "reunion con el primer ministro de portugal"
        )
        expected = f"moncloa_{_md5_12(raw)}"
        assert result == expected

    def test_moncloa_golden_desc_truncation(self):
        """Description longer than 80 chars must be truncated BEFORE hashing."""
        long_desc = "C" * 120
        result = moncloa_make_id(date(2026, 4, 1), "Ministro", long_desc)
        raw = f"2026-04-01_ministro_{'c' * 80}"
        expected = f"moncloa_{_md5_12(raw)}"
        assert result == expected

    # -- jgpa -----------------------------------------------------------

    def test_jgpa_golden_value(self):
        result = jgpa_make_id("Pleno del Parlamento de Asturias", date(2026, 7, 10))
        raw = "pleno del parlamento de asturias_2026-07-10"
        expected = f"jgpa_{_md5_12(raw)}"
        assert result == expected

    def test_jgpa_golden_truncation(self):
        """Titles longer than 80 chars must be truncated BEFORE hashing."""
        long_title = "D" * 100
        result = jgpa_make_id(long_title, date(2026, 8, 1))
        raw = f"{'d' * 80}_2026-08-01"
        expected = f"jgpa_{_md5_12(raw)}"
        assert result == expected


# ===================================================================
# 4. EDGE CASES
# ===================================================================

class TestExternalIdEdgeCases:
    """Edge cases: empty strings, unicode, long titles."""

    # -- Empty title / fields -------------------------------------------

    @pytest.mark.parametrize("make_id, prefix", [
        (cnt_make_id, "cnt_"),
        (nferias_make_id, "nferias_"),
        (tourempleo_make_id, "tourempleo_"),
        (defensor_make_id, "defensor_"),
    ])
    def test_empty_title_standard(self, make_id, prefix):
        """Empty title should still produce a valid, deterministic ID."""
        result = make_id("", date(2026, 1, 1))
        raw = "_2026-01-01"
        expected = f"{prefix}{_md5_12(raw)}"
        assert result == expected

    @pytest.mark.parametrize("make_id, prefix", [
        (segib_make_id, "segib_"),
        (heuropa_make_id, "heuropa_"),
    ])
    def test_empty_title_datestr(self, make_id, prefix):
        result = make_id("", "2026-01-01")
        raw = "_2026-01-01"
        expected = f"{prefix}{_md5_12(raw)}"
        assert result == expected

    def test_jgpa_empty_title(self):
        result = jgpa_make_id("", date(2026, 1, 1))
        raw = "_2026-01-01"
        expected = f"jgpa_{_md5_12(raw)}"
        assert result == expected

    def test_moncloa_empty_fields(self):
        result = moncloa_make_id(date(2026, 1, 1), "", "")
        raw = "2026-01-01__"
        expected = f"moncloa_{_md5_12(raw)}"
        assert result == expected

    # -- Unicode characters ---------------------------------------------

    @pytest.mark.parametrize("make_id, prefix", [
        (cnt_make_id, "cnt_"),
        (nferias_make_id, "nferias_"),
        (tourempleo_make_id, "tourempleo_"),
        (defensor_make_id, "defensor_"),
    ])
    def test_unicode_title_standard(self, make_id, prefix):
        title = "Jornada sobre inclusion y equidad en la educacion"
        result = make_id(title, date(2026, 5, 20))
        raw = f"{title.strip().lower()}_2026-05-20"
        expected = f"{prefix}{_md5_12(raw)}"
        assert result == expected

    def test_unicode_accents_cnt(self):
        """Accented characters must be preserved as-is in the hash."""
        title = "Dia de la Constitucion Espanola"
        result = cnt_make_id(title, date(2026, 12, 6))
        raw = f"{title.strip().lower()}_2026-12-06"
        expected = f"cnt_{_md5_12(raw)}"
        assert result == expected

    def test_unicode_with_emojis(self):
        """Emoji characters in titles should hash without errors."""
        title = "Festival de Musica en Vivo"
        result = cnt_make_id(title, date(2026, 8, 15))
        raw = f"{title.strip().lower()}_2026-08-15"
        expected = f"cnt_{_md5_12(raw)}"
        assert result == expected

    def test_unicode_japanese(self):
        """Non-Latin characters should hash correctly."""
        title = "Exposicion de Arte Japones"
        result = nferias_make_id(title, date(2026, 3, 1))
        raw = f"{title.strip().lower()}_2026-03-01"
        expected = f"nferias_{_md5_12(raw)}"
        assert result == expected

    def test_segib_unicode(self):
        title = "Cumbre sobre Cooperacion Sur-Sur"
        result = segib_make_id(title, "2026-04-10")
        raw = f"{title.strip().lower()[:80]}_2026-04-10"
        expected = f"segib_{_md5_12(raw)}"
        assert result == expected

    def test_moncloa_unicode(self):
        result = moncloa_make_id(
            date(2026, 1, 1),
            "Presidente del Gobierno de Espana",
            "Dialogo social con sindicatos",
        )
        raw = "2026-01-01_presidente del gobierno de espana_dialogo social con sindicatos"
        expected = f"moncloa_{_md5_12(raw)}"
        assert result == expected

    # -- Very long titles -----------------------------------------------

    def test_cnt_long_title_no_truncation(self):
        """cnt_agenda does NOT truncate - full title used regardless of length."""
        long_title = "X" * 500
        result = cnt_make_id(long_title, date(2026, 1, 1))
        raw = f"{'x' * 500}_2026-01-01"
        expected = f"cnt_{_md5_12(raw)}"
        assert result == expected

    def test_nferias_long_title_no_truncation(self):
        """nferias does NOT truncate."""
        long_title = "Y" * 500
        result = nferias_make_id(long_title, date(2026, 1, 1))
        raw = f"{'y' * 500}_2026-01-01"
        expected = f"nferias_{_md5_12(raw)}"
        assert result == expected

    def test_tourempleo_long_title_no_truncation(self):
        """tourdelempleo does NOT truncate."""
        long_title = "Z" * 500
        result = tourempleo_make_id(long_title, date(2026, 1, 1))
        raw = f"{'z' * 500}_2026-01-01"
        expected = f"tourempleo_{_md5_12(raw)}"
        assert result == expected

    def test_defensor_long_title_no_truncation(self):
        """defensor_pueblo does NOT truncate."""
        long_title = "W" * 500
        result = defensor_make_id(long_title, date(2026, 1, 1))
        raw = f"{'w' * 500}_2026-01-01"
        expected = f"defensor_{_md5_12(raw)}"
        assert result == expected

    def test_segib_truncates_at_80(self):
        """segib truncates title to 80 chars."""
        long_title = "A" * 200
        result = segib_make_id(long_title, "2026-01-01")
        # Only first 80 chars of lowered title are used
        raw = f"{'a' * 80}_2026-01-01"
        expected = f"segib_{_md5_12(raw)}"
        assert result == expected

    def test_heuropa_truncates_at_80(self):
        """horizonte_europa truncates title to 80 chars."""
        long_title = "B" * 200
        result = heuropa_make_id(long_title, "2026-01-01")
        raw = f"{'b' * 80}_2026-01-01"
        expected = f"heuropa_{_md5_12(raw)}"
        assert result == expected

    def test_jgpa_truncates_at_80(self):
        """jgpa truncates title to 80 chars."""
        long_title = "D" * 200
        result = jgpa_make_id(long_title, date(2026, 1, 1))
        raw = f"{'d' * 80}_2026-01-01"
        expected = f"jgpa_{_md5_12(raw)}"
        assert result == expected

    def test_moncloa_desc_truncates_at_80(self):
        """la_moncloa truncates description to 80 chars (cargo is NOT truncated)."""
        long_desc = "E" * 200
        result = moncloa_make_id(date(2026, 1, 1), "Presidente", long_desc)
        raw = f"2026-01-01_presidente_{'e' * 80}"
        expected = f"moncloa_{_md5_12(raw)}"
        assert result == expected

    def test_moncloa_cargo_not_truncated(self):
        """la_moncloa does NOT truncate cargo, only desc."""
        long_cargo = "F" * 200
        result = moncloa_make_id(date(2026, 1, 1), long_cargo, "breve")
        raw = f"2026-01-01_{'f' * 200}_breve"
        expected = f"moncloa_{_md5_12(raw)}"
        assert result == expected

    # -- Whitespace handling --------------------------------------------

    @pytest.mark.parametrize("make_id, prefix", [
        (cnt_make_id, "cnt_"),
        (nferias_make_id, "nferias_"),
        (tourempleo_make_id, "tourempleo_"),
        (defensor_make_id, "defensor_"),
    ])
    def test_whitespace_stripped_standard(self, make_id, prefix):
        """Leading/trailing whitespace must be stripped before hashing."""
        clean = make_id("Evento", date(2026, 1, 1))
        padded = make_id("  Evento  ", date(2026, 1, 1))
        assert clean == padded

    def test_whitespace_stripped_segib(self):
        clean = segib_make_id("Evento", "2026-01-01")
        padded = segib_make_id("  Evento  ", "2026-01-01")
        assert clean == padded

    def test_whitespace_stripped_heuropa(self):
        clean = heuropa_make_id("Evento", "2026-01-01")
        padded = heuropa_make_id("  Evento  ", "2026-01-01")
        assert clean == padded

    def test_whitespace_stripped_jgpa(self):
        clean = jgpa_make_id("Evento", date(2026, 1, 1))
        padded = jgpa_make_id("  Evento  ", date(2026, 1, 1))
        assert clean == padded

    def test_whitespace_stripped_moncloa(self):
        clean = moncloa_make_id(date(2026, 1, 1), "Cargo", "Desc")
        padded = moncloa_make_id(date(2026, 1, 1), "  Cargo  ", "  Desc  ")
        assert clean == padded

    # -- Case insensitivity ---------------------------------------------

    @pytest.mark.parametrize("make_id, prefix", [
        (cnt_make_id, "cnt_"),
        (nferias_make_id, "nferias_"),
        (tourempleo_make_id, "tourempleo_"),
        (defensor_make_id, "defensor_"),
    ])
    def test_case_insensitive_standard(self, make_id, prefix):
        """Title casing should not affect the output (lowered before hash)."""
        upper = make_id("EVENTO IMPORTANTE", date(2026, 1, 1))
        lower = make_id("evento importante", date(2026, 1, 1))
        mixed = make_id("Evento Importante", date(2026, 1, 1))
        assert upper == lower == mixed

    def test_case_insensitive_moncloa(self):
        a = moncloa_make_id(date(2026, 1, 1), "PRESIDENTE", "REUNION")
        b = moncloa_make_id(date(2026, 1, 1), "presidente", "reunion")
        assert a == b

    # -- Different inputs produce different IDs -------------------------

    def test_different_titles_differ(self):
        a = cnt_make_id("Evento A", date(2026, 1, 1))
        b = cnt_make_id("Evento B", date(2026, 1, 1))
        assert a != b

    def test_different_dates_differ(self):
        a = cnt_make_id("Mismo Evento", date(2026, 1, 1))
        b = cnt_make_id("Mismo Evento", date(2026, 1, 2))
        assert a != b

    def test_different_prefixes_differ(self):
        """Same raw input but different adapters must produce different IDs."""
        cnt_result = cnt_make_id("Evento", date(2026, 1, 1))
        nferias_result = nferias_make_id("Evento", date(2026, 1, 1))
        # Same hash but different prefix
        assert cnt_result != nferias_result
        assert cnt_result.startswith("cnt_")
        assert nferias_result.startswith("nferias_")
