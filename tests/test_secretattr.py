import pytest

from kframe.config import Secret


class TestSecretAttr:
    def test_internal_variable_access(self):
        """Test that the secret attribute is not accessible from the outside."""
        value = "test value"
        # Test that the secret attribute is not accessible from the outside
        a = Secret(value)
        with pytest.raises(AttributeError):
            print(a._value)

        # Test that the secret attribute is accessible from the inside
        a = Secret[type(value)](value)
        assert a.secret_value == value

    def test_secret_value_read(self):
        """Test that the secret value is readable."""
        value = "test value"
        a = Secret[type(value)](value)
        assert a.secret_value == value

    def test_secret_value_write(self):
        """Test that the secret value is writable."""
        value = "test value"
        a = Secret[str](value)
        assert a.secret_value == value
        a.secret_value = "new value"
        assert a.secret_value == "new value"

        with pytest.raises(TypeError):
            a.secret_value = 1
