from elaborlog.templates import to_template


def test_template_masks_numbers_and_ips():
    line = "WARN user=42 ip=10.0.0.1 failed after 12ms"
    tpl = to_template(line)
    assert "<num>" in tpl and "<ip>" in tpl


def test_template_masks_emails_urls_and_paths():
    line = (
        "ERROR user=jane email=jane.doe@example.com visited https://example.com/login "
        'path="/var/log/app.log" windows="C:\\Temp\\data.log" uuid=123e4567-e89b-12d3-a456-426614174000 '
        'hex=0xDEADBEEF note="unexpected drop"'
    )
    tpl = to_template(line)
    assert "<email>" in tpl
    assert "<url>" in tpl
    assert tpl.count("<path>") == 2
    assert "<uuid>" in tpl and "<hex>" in tpl
    assert tpl.count("<str>") >= 1
