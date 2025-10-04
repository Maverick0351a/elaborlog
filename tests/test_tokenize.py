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


def test_camel_split_disabled():
    # Without flag, token remains whole
    assert "mixedCaseToken".lower() in tokens("mixedCaseToken")


def test_camel_split_enabled():
    toks = tokens("mixedCaseToken", split_camel=True)
    assert "mixedcasetoken" in toks  # original
    # components expected: mixed, case, token
    for part in ["mixed", "case", "token"]:
        assert part in toks


def test_dot_split_enabled():
    toks = tokens("alpha.beta.gamma", split_dot=True)
    assert "alpha.beta.gamma" in toks
    for part in ["alpha", "beta", "gamma"]:
        assert part in toks


def test_dot_and_camel_combo():
    toks = tokens("Service.alphaBeta.gammaID42", split_dot=True, split_camel=True)
    # Original collapsed lowercase tokens
    assert "service.alphabeta.gammaid42" in toks or "service" in toks  # base extraction may split punctuation
    # Check for camel splits
    for part in ["alpha", "beta", "gamma", "id", "42"]:
        assert part in toks
