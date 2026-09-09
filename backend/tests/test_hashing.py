from app.services.hashing import sha256_hex


def test_deterministic_for_same_bytes():
    data = b"hello world"
    assert sha256_hex(data) == sha256_hex(data)


def test_differs_for_different_bytes():
    assert sha256_hex(b"a") != sha256_hex(b"b")


def test_known_vector():
    # sha256("") is a well-known constant.
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
