from elaborlog.templates import to_template


def test_very_long_line_masking_stability():
    # Construct an extremely long line with many numeric / hex / uuid patterns
    parts = []
    for i in range(500):
        parts.append(str(i))
        parts.append(f"0x{i:04x}")
    long_line = "BEGIN " + " ".join(parts) + " END some-email@example.com http://example.com/path/segment/value"  # noqa: E501

    template = to_template(long_line)

    # Ensure we replaced numbers, hex, email, url tokens
    assert '<num>' in template
    assert '<hex>' in template
    assert '<email>' in template
    assert '<url>' in template

    # Placeholder coverage: we expect many <num> and <hex> tokens (>= 400 each)
    assert template.count('<num>') >= 400
    assert template.count('<hex>') >= 400

    # Sanity: transformation should not enlarge the token count drastically
    raw_tokens = len(long_line.split())
    templ_tokens = len(template.split())
    assert templ_tokens <= raw_tokens + 20

    # Idempotency: applying to_template again should not change result
    assert to_template(template) == template
