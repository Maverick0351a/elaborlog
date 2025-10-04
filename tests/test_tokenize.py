from elaborlog.tokenize import tokens


def test_simple_tokens():
    assert tokens("Error: Code 500") == ["error", "code", "500"]

def test_tokens_with_bigrams():
    assert tokens("Error Code 500", include_bigrams=True) == [
        "error",
        "code",
        "500",
        "error__code",
        "code__500",
    ]
