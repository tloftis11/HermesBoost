from app.services.llm.prompts import build_intent_chat_system_prompt


def test_intent_chat_prompt_base_only_has_no_join_language():
    columns = [
        {"name": "fips", "dtype": "id", "source": "sales.csv", "usable": True},
        {"name": "amount", "dtype": "numeric", "source": "sales.csv", "usable": True},
    ]
    prompt = build_intent_chat_system_prompt("sales.csv", columns)

    assert '"name": "fips"' in prompt
    assert '"name": "amount"' in prompt
    assert "joined onto" not in prompt
    assert "can't be used as-is" not in prompt


def test_intent_chat_prompt_lists_joined_columns_with_source():
    columns = [
        {"name": "fips", "dtype": "id", "source": "shared join key", "usable": True},
        {"name": "amount", "dtype": "numeric", "source": "sales.csv", "usable": True},
        {"name": "population", "dtype": "numeric", "source": "region_stats.csv", "usable": True},
    ]
    prompt = build_intent_chat_system_prompt("sales.csv", columns)

    assert '"name": "population"' in prompt
    assert '"source": "region_stats.csv"' in prompt
    assert "joined onto 'sales.csv'" in prompt


def test_intent_chat_prompt_excludes_ambiguous_columns_and_warns():
    columns = [
        {"name": "fips", "dtype": "id", "source": "shared join key", "usable": True},
        {"name": "amount", "dtype": "numeric", "source": "sales.csv", "usable": False},
        {"name": "amount", "dtype": "numeric", "source": "region_stats.csv", "usable": False},
    ]
    prompt = build_intent_chat_system_prompt("sales.csv", columns)

    assert '"name": "amount"' not in prompt  # never offered as a usable column
    assert "can't be used as-is" in prompt
    assert "'amount'" in prompt  # named in the warning
