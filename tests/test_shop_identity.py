from tft_analyzer.perception.shop.identity import (
    ShopIdentityLexicon,
    ShopIdentityResolver,
    ShopIdentityResolverSettings,
)


def resolver():
    return ShopIdentityResolver(
        ShopIdentityLexicon(["ornn", "pantheon", "samira", "ezreal", "pyke"]),
        ShopIdentityResolverSettings(
            min_hash_support=2,
            min_hash_ratio=0.75,
        ),
    )


def test_exact_lexicon_identity():
    result = resolver().resolve_ocr("pantheon", 0.99)
    assert result is not None
    assert result.resolved_name == "pantheon"
    assert result.identity_method == "exact_lexicon"
    assert result.identity_confidence == 0.99


def test_orn_is_fuzzy_resolved_to_ornn():
    result = resolver().resolve_ocr("orn", 0.90)
    assert result is not None
    assert result.resolved_name == "ornn"
    assert result.identity_method == "fuzzy_lexicon"
    assert result.identity_confidence < 0.90


def test_arbitrary_token_is_not_semantic_identity():
    assert resolver().resolve_ocr("raksuage", 0.99) is None


def test_hash_consensus_can_fill_missing_ocr():
    r = resolver()
    consensus = r.build_hash_consensus(
        [
            ("abc", "orn", 0.90),
            ("abc", "ornn", 0.96),
            ("abc", "orn", 0.91),
        ]
    )
    assert consensus["abc"].resolved_name == "ornn"

    result = r.resolve(None, 0.0, visual_hash="abc", hash_consensus=consensus)
    assert result is not None
    assert result.resolved_name == "ornn"
    assert result.identity_method == "hash_consensus"
    assert result.hash_support == 3


def test_weak_hash_consensus_is_not_created():
    r = resolver()
    consensus = r.build_hash_consensus([("abc", "pantheon", 0.95)])
    assert "abc" not in consensus
