"""Tests for scripts/build_names_dict.py and the committed data/names_dict.csv.

The generator is tested on small hand-made member lists; fetching is tested with a
fake HTTP client. No test touches sansad.in or Wikidata.
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

from ingest.canonical.names import canonicalize_name, load_names_dict

_APP = Path(__file__).parent.parent
_SCRIPT = _APP / "scripts" / "build_names_dict.py"
_CSV = _APP / "data" / "names_dict.csv"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_names_dict", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod   # dataclasses look their module up while the class is built
    spec.loader.exec_module(mod)
    return mod


bnd = _load_module()
Member = bnd.Member


def _rows(*members) -> dict[str, str]:
    """variant (lowercased) → canonical, for the built rows."""
    return {v.lower(): c for v, c in bnd.build_rows(members).rows}


# ── Cleaning ──────────────────────────────────────────────────────────────────

class TestCleanNamePart:
    @pytest.mark.parametrize("raw,expected", [
        ("Sumitra Mahajan (Tai)", "Sumitra Mahajan"),
        ("Jha, `Suman`", "Jha"),
        ("O`brien", "O'brien"),
        ('Vinay Kumar "Vinnu"', "Vinay Kumar"),
        ("Bhuwan Chandra AVSM (Retd.)", "Bhuwan Chandra"),
        ("A.T. (Nana)", "A. T."),
        ("M.H..S. Nihal", "M. H. S. Nihal"),
        ("ADHIR RANJAN", "Adhir Ranjan"),
        ("Sarojini bindurao", "Sarojini Bindurao"),
        ("Erasmo de", "Erasmo de"),
        ("Mohan S.", "Mohan S."),
        ("Prasad.", "Prasad"),
        ("", ""),
        (None, ""),
    ])
    def test_clean(self, raw, expected):
        assert bnd.clean_name_part(raw) == expected


class TestSplitDirectoryName:
    def test_plain(self):
        assert bnd.split_directory_name("Hari Vishnu", "Kamath") == ("Hari Vishnu", "Kamath", "")

    def test_surname_comma_given_in_last_name_field(self):
        assert bnd.split_directory_name("", "Delkar, Shri Mohan S. ") == ("Mohan S.", "Delkar", "")

    def test_title_inside_first_name_moves_out(self):
        assert bnd.split_directory_name("Sardar Hukam", "Singh") == ("Hukam", "Singh", "Sardar")

    def test_one_field_name_that_starts_like_a_title_is_kept(self):
        assert bnd.split_directory_name(" ", "Sardar Singh") == ("", "Sardar Singh", "")


def test_initials_forms():
    assert bnd.initials_forms(["Hari", "Vishnu"], ["Kamath"]) == [
        "H. Vishnu Kamath", "H. V. Kamath", "H.V. Kamath",
    ]
    # Given names that are already initials are not re-emitted one by one.
    assert bnd.initials_forms(["A.", "C."], ["George"]) == ["A. C. George", "A.C. George"]


def test_lookup_key_matches_canonicalize_name_lookup():
    assert bnd.lookup_key("Shri A.C.  George") == "a. c. george"


# ── Build ─────────────────────────────────────────────────────────────────────

class TestBuildRows:
    def test_full_initials_and_unique_surname(self):
        rows = _rows(Member("ls", "776", "Hari Vishnu", "Kamath", "Shri"))
        for v in ["hari vishnu kamath", "h. v. kamath", "h.v. kamath", "h. vishnu kamath", "kamath"]:
            assert rows[v] == "Hari Vishnu Kamath"
        assert not any(v.startswith("shri ") for v in rows)   # stripped at lookup anyway

    def test_shared_surname_is_left_out(self):
        rows = _rows(
            Member("ls", "1082", "Mahavir", "Tyagi"),
            Member("rs", "9", "K. C.", "Tyagi"),
        )
        assert "tyagi" not in rows
        assert rows["mahavir tyagi"] == "Mahavir Tyagi"
        assert rows["k. c. tyagi"] == "K. C. Tyagi"

    def test_surname_shared_with_a_one_field_name_is_left_out(self):
        rows = _rows(Member("ls", "1", "Harish", "Rawat"), Member("rs", "2", "", "Rawat"))
        assert "rawat" not in rows

    def test_unique_one_word_name_is_kept(self):
        assert _rows(Member("rs", "1", "", "Mayawati"))["mayawati"] == "Mayawati"

    def test_exact_name_beats_another_members_initials(self):
        rows = _rows(Member("ls", "1", "Ajay", "Kumar"), Member("rs", "2", "A.", "Kumar"))
        assert rows["a. kumar"] == "A. Kumar"
        assert rows["ajay kumar"] == "Ajay Kumar"

    def test_initials_shared_by_two_members_are_left_out(self):
        rows = _rows(
            Member("ls", "1", "Ram Surat", "Prasad"),
            Member("ls", "2", "Ravi Shankar", "Prasad"),
        )
        assert "r. s. prasad" not in rows
        assert rows["ram surat prasad"] == "Ram Surat Prasad"

    def test_kept_title_gets_prefixed_variants(self):
        rows = _rows(Member("ls", "803", "J. B.", "Kripalani", "Acharya"))
        assert rows["acharya j. b. kripalani"] == "J. B. Kripalani"
        assert rows["acharya kripalani"] == "J. B. Kripalani"

    def test_same_name_in_two_houses_is_one_person(self):
        rows = _rows(Member("ls", "1", "Mahavir", "Tyagi"), Member("rs", "2", "Mahavir", "Tyagi"))
        assert rows["tyagi"] == "Mahavir Tyagi"

    def test_ca_member_linked_through_wikidata_alias(self):
        rows = _rows(
            Member("ls", "776", "Hari Vishnu", "Kamath", early=True),
            Member("ca", "Q61944025", "Hari Vishnu", "Kamath", aliases=("H. V. Kamath",)),
            Member("ca", "Q1", "H. V.", "Kamath", aliases=("Hari Vishnu Kamath",)),
        )
        assert {c for c in rows.values()} == {"Hari Vishnu Kamath"}

    def test_ca_member_linked_through_initials_only_to_early_members(self):
        ca = Member("ca", "Q2", "Ganesh Vasudev", "Mavalankar")
        early = Member("ls", "1", "Ganesh Vasudeo", "Mavalankar", early=True)
        late = Member("ls", "1", "Ganesh Vasudeo", "Mavalankar", early=False)
        assert _rows(early, ca)["ganesh vasudev mavalankar"] == "Ganesh Vasudeo Mavalankar"
        assert _rows(late, ca)["ganesh vasudev mavalankar"] == "Ganesh Vasudev Mavalankar"

    def test_epithet_aliases_are_dropped(self):
        rows = _rows(Member("ca", "Q3", "Omeo Kumar", "Das", aliases=("Lok Nayak", "Babuji")))
        assert "lok nayak" not in rows and "babuji" not in rows

    def test_rows_resolve_through_names_module(self, tmp_path):
        result = bnd.build_rows([Member("ls", "776", "Hari Vishnu", "Kamath", "Shri")])
        path = tmp_path / "names_dict.csv"
        bnd.write_csv(result.rows, path)
        d = load_names_dict(path)
        assert canonicalize_name("Shri H.V. Kamath", d) == ("Hari Vishnu Kamath", False)
        assert canonicalize_name("Shri Kamath", d) == ("Hari Vishnu Kamath", False)


# ── Source parsing and fetching ───────────────────────────────────────────────

def _ls(mpsno, initial, first, last):
    return {"mpsno": mpsno, "initial": initial, "firstName": first, "lastName": last}


def test_parse_ls_members_dedupes_across_terms_and_marks_early():
    pages = {
        1: [_ls(776, "Shri", "Hari Vishnu", "Kamath")],
        3: [_ls(776, "Shri", "Hari Vishnu", "Kamath"), _ls(97, "Shri", "Adhir Ranjan", "Chowdhury")],
    }
    members = {m.source_id: m for m in bnd.parse_ls_members(pages)}
    assert members["776"].early and not members["97"].early
    assert members["97"] == Member("ls", "97", "Adhir Ranjan", "Chowdhury", "Shri")


def test_parse_rs_members():
    records = [
        {"mpsno": 5, "initial": "Shri ", "firstName": "B.R.", "lastName": "Ambedkar ", "term": "1952-1956"},
        {"mpsno": 6, "initial": "Shri", "firstName": "K.C.", "lastName": "Tyagi", "term": "2013-2016"},
    ]
    a, t = bnd.parse_rs_members(records)
    assert (a.given, a.surname, a.early) == ("B. R.", "Ambedkar", True)
    assert not t.early


def test_parse_wikidata_members():
    bindings = [{
        "item": {"value": "http://www.wikidata.org/entity/Q6733578"},
        "label": {"value": "Begum Aizaz Rasul"},
        "aliases": {"value": "Begum Qudsia Aizaz Rasul|Qudsia Rasul"},
    }]
    (m,) = bnd.parse_wikidata_members(bindings)
    assert (m.source_id, m.given, m.surname, m.honorific) == ("Q6733578", "Aizaz", "Rasul", "Begum")
    assert m.aliases == ("Begum Qudsia Aizaz Rasul", "Qudsia Rasul")


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        if url == bnd.LS_URL:
            records = [_ls(776, "Shri", "Hari Vishnu", "Kamath")] if params["loksabha"] <= 2 else []
            return _FakeResponse({"membersDtoList": records})
        if url == bnd.RS_URL:
            return _FakeResponse({
                "records": [{"mpsno": 6, "initial": "Shri", "firstName": "K.C.",
                             "lastName": "Tyagi", "term": "2013-2016"}],
                "_metadata": {"totalPages": 1},
            })
        if url == bnd.WIKIDATA_URL:
            return _FakeResponse({"results": {"bindings": []}})
        raise AssertionError(url)


def test_fetch_members_stops_at_first_empty_lok_sabha():
    client = _FakeClient()
    members = bnd.fetch_members(client, delay=0)
    ls_calls = [p["loksabha"] for u, p in client.calls if u == bnd.LS_URL]
    assert ls_calls == [1, 2, 3]
    assert [(m.source, m.source_id) for m in members] == [("ls", "776"), ("rs", "6")]


# ── The committed CSV ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def committed():
    with _CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)
    return header, rows


def test_committed_csv_shape(committed):
    header, rows = committed
    assert header == ["variant", "canonical_name"]
    assert len(rows) > 3000
    assert all(v.strip() and c.strip() for v, c in rows)


def test_committed_csv_has_one_canonical_per_lookup_key(committed):
    _, rows = committed
    seen: dict[str, str] = {}
    for variant, canonical in rows:
        key = bnd.lookup_key(variant)
        assert seen.setdefault(key, canonical) == canonical, variant


def test_committed_csv_keys_match_normalize_name_form(committed):
    """Once names.py normalizes name forms, its lookup key must equal ours."""
    names = pytest.importorskip("ingest.canonical.names")
    if not hasattr(names, "normalize_name_form"):
        pytest.skip("normalize_name_form not in this checkout")
    _, rows = committed
    for variant, _ in rows:
        expected = names._normalize_for_lookup(names.normalize_name_form(names.strip_honorifics(variant)))
        assert bnd.lookup_key(variant) == expected, variant


@pytest.mark.parametrize("raw,expected", [
    ("Shri H. V. Kamath", ("Hari Vishnu Kamath", False)),
    ("Shri Kamath", ("Hari Vishnu Kamath", False)),
    ("SHRI ADHIR RANJAN CHOWDHURY", ("Adhir Ranjan Chowdhury", False)),
    ("Acharya Kripalani", ("J. B. Kripalani", False)),
    ("Dr. B. R. Ambedkar", ("B. R. Ambedkar", False)),
    ("Shri K. C. Tyagi", ("K. C. Tyagi", False)),
    ("Shri Tyagi", ("Tyagi", True)),          # several members named Tyagi
])
def test_committed_csv_known_variants(raw, expected):
    assert canonicalize_name(raw, load_names_dict(_CSV)) == expected
