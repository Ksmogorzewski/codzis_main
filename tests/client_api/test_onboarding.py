"""Czyste funkcje onboardingu (src/client_api/onboarding.py)."""

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
    "discover": ["skills"],
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
    assert step_ids[:4] == ["who", "vibe", "discover", "city"]


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


# --- validate_answers ---


def test_validate_answers_accepts_valid_and_normalizes():
    answers, errors = onboarding.validate_answers({**VALID_ANSWERS, "vibe": ["art", "art"]}, steps())
    assert errors == []
    assert answers == {
        "who": ["solo_friends"],
        "vibe": ["art"],
        "discover": ["skills"],
        "district": ["Mokotów"],
        "travel": ["nearby"],
    }


def test_validate_answers_skips_empty_optional_fields():
    answers, errors = onboarding.validate_answers({**VALID_ANSWERS, "city": [], "budget": "", "when": None}, steps())
    assert errors == []
    assert "city" not in answers and "budget" not in answers and "when" not in answers


def test_validate_answers_not_a_dict():
    assert onboarding.validate_answers(None, steps()) == ({}, ["answers"])
    assert onboarding.validate_answers(["who"], steps()) == ({}, ["answers"])


def test_validate_answers_required_missing():
    _, errors = onboarding.validate_answers({}, steps())
    assert errors == ["discover", "district", "travel", "vibe", "who"]


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
            "setting": "outdoor",
            "registration": "walk_in",
            "age": "65plus",
        },
        steps(),
    )
    prefs = onboarding.compute_preferences(answers, steps())

    assert set(prefs) == set(onboarding.LIST_PREFS) | set(onboarding.SCALAR_PREFS) | set(onboarding.BOOL_PREFS)
    assert prefs["district"] == "Mokotów"
    assert prefs["travelRange"] == "nearby"
    assert prefs["cost"] == ["Bezpłatne"]
    assert prefs["maxPrice"] == 0
    assert prefs["setting"] == ["Na zewnątrz"]
    assert prefs["registration"] == ["Wstęp wolny"]
    assert prefs["ageRange"] == "65+"
    assert prefs["weekend"] is True
    # suma bez duplikatów, w kolejności kroków
    assert prefs["audience"] == ["Dorośli (18-64)", "Seniorzy (65+)"]
    assert prefs["interests"] == ["Dla młodzieży i dorosłych", "Czas wolny", "Kultura", "Edukacja"]
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
    prefs.update(maxPrice=50, travelRange="city", ageRange="18-29")
    assert onboarding.rag_profile(prefs) == "maxPrice=50 | travel=city | age=18-29"


def test_rag_profile_empty():
    assert onboarding.rag_profile(onboarding.compute_preferences({}, steps())) == ""
