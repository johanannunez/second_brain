from scripts.privacy_scan import scan_text


def test_privacy_scan_flags_private_values_but_allows_configured_business_contacts():
    assert scan_text("Contact guest@example.test or 605-555-0101.")
    assert scan_text("Bank account number: 123456789012")
    assert scan_text("Wi-Fi password: correct-horse-battery")
    assert not scan_text("hello@theparcelco.com, (605) 800-7033")
