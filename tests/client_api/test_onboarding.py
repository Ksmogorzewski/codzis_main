"""Czyste funkcje onboardingu (src/client_api/onboarding.py)."""

from datetime import date

import pytest

from tests.support import CLIENT_API_DIR, DISTRICTS, load_lambda, taxonomy

onboarding = load_lambda(CLIENT_API_DIR, "onboarding")

# Pole preferencji -> wymiar taksonomii taggera (tagger/prompt.py -> DIMENSIONS)
PREF_TO_DIMENSION = {
    "themes": "theme",
    "formats": "format",
    "audience": "audience",
    "occasion": "occasion",
    "activityLevel": "activity_level",
    "cost": "cost",
    "mode": "mode",
    "setting": "setting",
    "registration": "registration",
    "accessibility": "accessibility",
}

VALID_ANSWERS = {
    "who": "solo_friends",
    "vibe": ["art", "chill"],
    "district": "Mokotów",
    "travel": "nearby",
}


def steps():
    return onboarding.build_steps(DISTRICTS)


def fields_by_id():
    return {f["id"]: f for s in steps() for f in s["fields"]}


# --- build_steps / onboarding_version / public_steps ---


def test_build_steps_has_unique_step_and_field_ids():
    built = steps()
    step_ids = [s["id"] for s in built]
    field_ids = [f["id"] for s in built for f in s["fields"]]
    assert len(step_ids) == len(set(step_ids))
    assert len(field_ids) == len(set(field_ids))
    assert step_ids[:4] == ["who", "vibe", "where", "when"]


def test_build_steps_district_options_come_from_argument():
    district = fields_by_id()["district"]
    assert district["type"] == "select"
    assert [o["id"] for o in district["options"]] == DISTRICTS
    assert district["options"][0]["maps"] == {"district": "Mokotów"}


def test_option_short_defaults_to_label():
    who = fields_by_id()["who"]
    assert who["options"][0]["short"] == "Solo / we dwoje"
    mokotow = fields_by_id()["district"]["options"][0]
    assert mokotow["short"] == mokotow["label"] == "Mokotów"


def test_onboarding_version_is_stable_and_short():
    assert onboarding.onboarding_version(steps()) == onboarding.onboarding_version(steps())
    assert len(onboarding.onboarding_version(steps())) == 12


def test_onboarding_version_ignores_labels_but_tracks_mapping():
    base = onboarding.onboarding_version(steps())

    relabeled = steps()
    relabeled[0]["fields"][0]["options"][0]["label"] = "Inna etykieta"
    relabeled[0]["title"] = "Inny tytuł"
    assert onboarding.onboarding_version(relabeled) == base

    remapped = steps()
    remapped[0]["fields"][0]["options"][0]["maps"]["occasion"] = ["Samodzielnie"]
    assert onboarding.onboarding_version(remapped) != base

    assert onboarding.onboarding_version(onboarding.build_steps(["Wola"])) != base


def test_missing_required_lists_only_unanswered_required_fields():
    assert (
        onboarding.missing_required({k: [v] if isinstance(v, str) else v for k, v in VALID_ANSWERS.items()}, steps())
        == []
    )
    assert onboarding.missing_required({}, steps()) == ["who", "vibe", "district", "travel"]
    assert onboarding.missing_required({**VALID_ANSWERS, "vibe": []}, steps()) == ["vibe"]


def test_missing_required_ignores_removed_and_optional_fields():
    answers = {**VALID_ANSWERS, "age": ["30-49"]}  # usunięte pytanie
    assert onboarding.missing_required(answers, steps()) == []
    with_optional = steps()
    with_optional[-1]["fields"].append({"id": "nowe", "type": "multi", "required": False, "options": []})
    assert onboarding.missing_required(answers, with_optional) == []
    with_required = steps()
    with_required[-1]["fields"].append({"id": "nowe", "type": "multi", "required": True, "options": []})
    assert onboarding.missing_required(answers, with_required) == ["nowe"]


def test_bio_field_is_optional():
    assert fields_by_id()["bio"]["required"] is False


def test_public_steps_hides_mappings_and_keeps_shape():
    public = onboarding.public_steps(steps())
    assert [s["id"] for s in public] == [s["id"] for s in steps()]
    for step, original in zip(public, steps(), strict=True):
        assert {k for k in step if k != "fields"} == {k for k in original if k != "fields"}
        for field in step["fields"]:
            for option in field["options"]:
                assert set(option) == {"id", "label", "icon", "short"}
    vibe = next(s for s in public if s["id"] == "vibe")["fields"][0]
    assert vibe["maxSelect"] == 2
    assert vibe["required"] is True
    bio = next(f for s in public for f in s["fields"] if f["id"] == "bio")
    assert (bio["type"], bio["maxLength"], bio["options"], bio["required"]) == ("text", 300, [], False)
    assert "pref" not in bio and bio["placeholder"]
    assert "danych osobowych" in bio["hint"]


# --- validate_answers ---


def test_validate_answers_accepts_valid_and_normalizes():
    answers, errors = onboarding.validate_answers({**VALID_ANSWERS, "vibe": ["art", "art"]}, steps())
    assert errors == []
    assert answers == {
        "who": ["solo_friends"],
        "vibe": ["art"],
        "district": ["Mokotów"],
        "travel": ["nearby"],
    }


def test_validate_answers_skips_empty_optional_fields():
    answers, errors = onboarding.validate_answers({**VALID_ANSWERS, "budget": "", "when": None}, steps())
    assert errors == []
    assert "budget" not in answers and "when" not in answers


def test_validate_answers_not_a_dict():
    assert onboarding.validate_answers(None, steps()) == ({}, ["answers"])
    assert onboarding.validate_answers(["who"], steps()) == ({}, ["answers"])


def test_validate_answers_required_missing():
    _, errors = onboarding.validate_answers({}, steps())
    assert errors == ["district", "travel", "vibe", "who"]


def test_validate_answers_max_select():
    _, errors = onboarding.validate_answers({**VALID_ANSWERS, "vibe": ["art", "chill", "active"]}, steps())
    assert errors == ["vibe"]


def test_validate_answers_single_with_many_values():
    _, errors = onboarding.validate_answers({**VALID_ANSWERS, "who": ["solo_friends", "kids"]}, steps())
    assert errors == ["who"]


def test_validate_answers_unknown_option():
    _, errors = onboarding.validate_answers({**VALID_ANSWERS, "who": "aliens"}, steps())
    assert errors == ["who"]


def test_validate_answers_unknown_field():
    answers, errors = onboarding.validate_answers({**VALID_ANSWERS, "favouriteColour": "red"}, steps())
    assert errors == ["favouriteColour"]
    assert "favouriteColour" not in answers


def test_validate_answers_unknown_district():
    _, errors = onboarding.validate_answers({**VALID_ANSWERS, "district": "Kraków"}, steps())
    assert errors == ["district"]


def test_validate_answers_free_text_is_cleaned_and_optional():
    answers, errors = onboarding.validate_answers({**VALID_ANSWERS, "bio": "  Lubię jazz\n\ni  spacery.\x00 "}, steps())
    assert errors == []
    assert answers["bio"] == ["Lubię jazz i spacery."]
    # z frontu przychodzi też jako lista z jednym tekstem; puste pole = brak odpowiedzi
    assert onboarding.validate_answers({**VALID_ANSWERS, "bio": ["Kino"]}, steps())[0]["bio"] == ["Kino"]
    assert "bio" not in onboarding.validate_answers({**VALID_ANSWERS, "bio": "   "}, steps())[0]


def test_validate_answers_free_text_limits():
    assert onboarding.validate_answers({**VALID_ANSWERS, "bio": "x" * 301}, steps())[1] == ["bio"]
    assert onboarding.validate_answers({**VALID_ANSWERS, "bio": "x" * 300}, steps())[1] == []
    assert onboarding.validate_answers({**VALID_ANSWERS, "bio": 5}, steps())[1] == ["bio"]
    assert onboarding.validate_answers({**VALID_ANSWERS, "bio": ["a", "b"]}, steps())[1] == ["bio"]


def test_validate_answers_wrong_types():
    _, errors = onboarding.validate_answers({**VALID_ANSWERS, "vibe": [1, 2], "who": 5}, steps())
    assert errors == ["vibe", "who"]


# --- compute_preferences / rag_profile ---


def test_compute_preferences_maps_onto_taxonomy():
    answers, _ = onboarding.validate_answers(
        {
            **VALID_ANSWERS,
            "when": ["weekend", "weekday_evening"],
            "budget": "free",
            "registration": "walk_in",
            "bio": "Lubię jazz i spacery",
        },
        steps(),
    )
    prefs = onboarding.compute_preferences(answers, steps())

    assert set(prefs) == set(onboarding.LIST_PREFS) | set(onboarding.SCALAR_PREFS) | set(onboarding.BOOL_PREFS)
    assert prefs["district"] == "Mokotów"
    assert prefs["travelRange"] == "nearby"
    assert prefs["cost"] == ["Bezpłatne"]
    assert prefs["maxPrice"] == 0
    assert prefs["setting"] == []  # bez pytania o styl (pod dachem / plener) - zostaje pusta
    assert prefs["registration"] == ["Wstęp wolny"]
    assert prefs["about"] == "Lubię jazz i spacery"
    assert prefs["weekend"] is True
    # suma bez duplikatów, w kolejności kroków
    assert prefs["audience"] == ["Dorośli (18-64)"]
    assert prefs["interests"] == ["Dla młodzieży i dorosłych", "Czas wolny", "Kultura"]
    # kolejność kanoniczna jak w facets eventów
    assert prefs["days"] == onboarding.WEEKDAYS + onboarding.WEEKEND
    assert prefs["timeOfDay"] == ["rano", "popołudnie", "wieczór"]
    options = taxonomy()
    for pref, dimension in PREF_TO_DIMENSION.items():
        assert set(prefs[pref]) <= set(options[dimension]), pref


def test_every_option_mapping_uses_taxonomy_values():
    options = taxonomy()
    for field in fields_by_id().values():
        for option in field["options"]:
            for pref, values in option["maps"].items():
                if pref in PREF_TO_DIMENSION:
                    assert set(values) <= set(options[PREF_TO_DIMENSION[pref]]), (field["id"], option["id"], pref)


def test_compute_preferences_defaults_when_nothing_chosen():
    prefs = onboarding.compute_preferences({}, steps())
    assert all(prefs[k] == [] for k in onboarding.LIST_PREFS)
    assert all(prefs[k] is None for k in onboarding.SCALAR_PREFS)
    assert prefs["weekend"] is False


def test_rag_profile_format():
    prefs = onboarding.compute_preferences({}, steps())
    prefs.update(
        interests=["Kultura", "Czas wolny"],
        district="Śródmieście",
        cost=["Bezpłatne"],
        mode=["Stacjonarne"],
        audience=["Dorośli (18-64)"],
        maxPrice=0,
        weekend=True,
    )
    assert onboarding.rag_profile(prefs) == (
        "interests=[Kultura, Czas wolny] | district=Śródmieście | cost=Bezpłatne | mode=Stacjonarne"
        " | audience=Dorośli (18-64) | weekend=true"
    )


def test_rag_profile_includes_max_price_when_not_free():
    prefs = onboarding.compute_preferences({}, steps())
    prefs.update(maxPrice=50, travelRange="city", about="Lubię jazz | kino")
    assert onboarding.rag_profile(prefs) == "maxPrice=50 | travel=city | about=Lubię jazz / kino"


def test_rag_profile_empty():
    assert onboarding.rag_profile(onboarding.compute_preferences({}, steps())) == ""


# --- wiek z daty urodzenia (age_on / with_age) ---

TODAY = date(2026, 10, 18)


def test_age_on_counts_full_years():
    assert onboarding.age_on("1990-10-18", TODAY) == 36
    assert onboarding.age_on("1990-10-19", TODAY) == 35
    # urodzeni 29 lutego kończą lata 1 marca (jak ageOn we froncie)
    assert onboarding.age_on("2000-02-29", date(2025, 2, 28)) == 24
    assert onboarding.age_on("2000-02-29", date(2025, 3, 1)) == 25
    assert onboarding.age_on(None, TODAY) is None
    assert onboarding.age_on("17.05.1990", TODAY) is None
    assert onboarding.age_on("2027-01-01", TODAY) is None


@pytest.mark.parametrize(
    ("birth_date", "age_range", "group"),
    [
        ("2009-10-19", "under18", "Młodzież (13-17)"),  # 16 lat, 17 skończy jutro
        ("2008-10-18", "18-29", "Dorośli (18-64)"),  # 18 lat dziś
        ("1996-10-19", "18-29", "Dorośli (18-64)"),
        ("1996-10-18", "30-49", "Dorośli (18-64)"),
        ("1976-10-18", "50-64", "Dorośli (18-64)"),
        ("1961-10-19", "50-64", "Dorośli (18-64)"),
        ("1961-10-18", "65+", "Seniorzy (65+)"),
    ],
)
def test_with_age_sets_range_and_audience_group(birth_date, age_range, group):
    prefs = onboarding.with_age(onboarding.compute_preferences({}, steps()), birth_date, TODAY)
    assert prefs["ageRange"] == age_range
    assert prefs["audience"] == [group]


def test_with_age_adds_group_after_answers_without_duplicates():
    answers, _ = onboarding.validate_answers(VALID_ANSWERS, steps())  # solo_friends -> Dorośli (18-64)
    prefs = onboarding.compute_preferences(answers, steps())

    assert onboarding.with_age(prefs, "1990-05-17", TODAY)["audience"] == ["Dorośli (18-64)"]
    assert onboarding.with_age(prefs, "1950-05-17", TODAY)["audience"] == ["Dorośli (18-64)", "Seniorzy (65+)"]
    # bez daty urodzenia - bez wieku; preferencje wejściowe bez zmian
    assert onboarding.with_age(prefs, None, TODAY) == prefs
    assert prefs["ageRange"] is None
    assert prefs["audience"] == ["Dorośli (18-64)"]


def test_rag_profile_has_age_from_birth_date_before_about():
    prefs = onboarding.with_age(onboarding.compute_preferences({}, steps()), "1990-05-17", TODAY)
    prefs.update(about="Lubię jazz")
    assert onboarding.rag_profile(prefs) == "audience=Dorośli (18-64) | age=30-49 | about=Lubię jazz"
