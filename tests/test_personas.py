from bot_service.personas.pool import get_personas


def test_get_personas_returns_requested_count() -> None:
    personas = get_personas(3)

    assert len(personas) == 3


def test_get_personas_returns_empty_list_for_zero_or_negative_limit() -> None:
    assert get_personas(0) == []
    assert get_personas(-1) == []


def test_get_personas_generates_unique_bot_ids_when_pool_repeats() -> None:
    personas = get_personas(12)
    bot_ids = [persona["bot_id"] for persona in personas]

    assert len(bot_ids) == len(set(bot_ids))


def test_get_personas_has_varied_first_eight_personas() -> None:
    personas = get_personas(8)
    base_names = {persona["name"].rstrip("0123456789") for persona in personas}

    assert len(base_names) == 8


def test_get_personas_first_eight_include_live_room_noise_roles() -> None:
    personas = get_personas(8)
    names = {persona["name"].rstrip("0123456789") for persona in personas}

    assert {"凑热闹", "阴阳人", "跑题观众", "赌气球迷"}.issubset(names)


def test_get_personas_returns_required_fields() -> None:
    persona = get_personas(1)[0]

    assert set(persona) == {"bot_id", "name", "persona"}
    assert persona["bot_id"] == "bot_001"
    assert persona["name"]
    assert persona["persona"]
