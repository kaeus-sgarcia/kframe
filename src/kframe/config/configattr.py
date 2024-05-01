import weakref
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class Secret(Generic[T]):
    """A secret attribute that hides its value from the outside."""

    def __init__(self, value: T) -> None:
        """Create a secret attribute with a value of type T."""
        self._value: T = value
        super().__init__()

    def __str__(self) -> str:
        """Return a string representation of the secret attribute."""
        return "******"

    def __repr__(self) -> str:
        """Return a string representation of the secret attribute."""
        return "SecretAttr()"

    @property
    def secret_value(self) -> T:
        """Return the secret value of the attribute."""
        return self.__dict__["_value"]

    @secret_value.setter
    def secret_value(self, value: T):
        """Set the secret value of the attribute.

        Args:
        ----
            value (T): The value to set, must by of the defined type.

        Raises:
        ------
            TypeError: If the value is not of the defined type.

        """
        if not isinstance(value, type(self.__dict__["_value"])):
            raise TypeError(f'Value must be of type {type(self.__dict__["_value"])}')
        self._value = value

    def __getattribute__(self, name: str) -> Any:
        """Get an attribute of the secret attribute.

        Args:
        ----
            name (str): The name of the attribute to get.

        Raises:
        ------
            AttributeError: if trying to access the internal value directly.

        Returns:
        -------
            Any: The attribute value.

        """
        if name == "_value":
            raise AttributeError("Secret value is not accessible")
        return super().__getattribute__(name)


class ConfigAttr:
    """A configuration attribute that can be set from different sources."""

    def __init__(
        self,
        default=None,
        required=False,
        description=None,
        env_var=None,
        cli_args=None,
        secret=False,
        attr_type=str,
    ):
        """Create a new ConfigAttr instance.

        Args:
        ----
            default (Any, optional): The default value of the attribute. Defaults to None.
            required (bool, optional): Whether the attribute is required. Defaults to False.
            description (str, optional): The help text for the attribute. Defaults to None.
            env_var (str, optional): The environment variable for the attribute. Defaults to None.
            cli_args (List[str], optional): The CLI arguments for the attribute. Defaults to None.
            secret (bool, optional): Whether the attribute is a secret. Defaults to False.
            attr_type (type, optional): The type of the attribute. Defaults to str.

        """
        self._default_value = default
        self._description = description
        self._name = None
        self._required = required
        self._env_var = env_var
        self._secret = secret
        self._attr_type = attr_type
        self._cli_args = cli_args

    def __get__(self, instance, owner):
        """Get the value of the data descriptor."""
        if instance is None:
            return self
        sources = instance.__class__._sources[self._name]
        source_priority = ["cli", "env", "default"]
        for source in source_priority:
            if source in sources:
                return sources[source]
        raise AttributeError(f"Value for {self.name} was not set.")

    def __set__(self, instance, value):
        """Set the value of the data descriptor."""
        raise AttributeError("Cannot set value to ConfigAttr")

    def __set_name__(self, owner, name):
        """Set the name of the data descriptor."""
        self._name = name
        self._owner = weakref.ref(owner)

    @property
    def default_value(self):
        """Return the default value for the attribute."""
        return getattr(self, "_default_value", None)

    @property
    def env_var(self):
        """Return the environment variable for the attribute."""
        return getattr(self, "_env_var", None)

    @property
    def cli_args(self):
        """Return the CLI arguments for the attribute."""
        if self._cli_args is not None:
            desc_attrs = []
            if self.required:
                desc_attrs.append("required")
            if self.env_var is not None:
                desc_attrs.append(f"env: {self.env_var}")
            description = f"{self.description} ({', '.join(desc_attrs)})"

            attrs = {"help": description, "dest": self._name}
            if self.attr_type is bool:
                attrs |= {"action": "store_const", "const": True}
            return (self._cli_args, attrs)
        return None

    @property
    def required(self):
        """Return whether the attribute is required."""
        return getattr(self, "_required", False)

    @property
    def secret(self):
        """Return whether the attribute is a secret."""
        return getattr(self, "_secret", False)

    @property
    def name(self):
        """Return the name of the attribute."""
        return getattr(self, "_name", "<Not set>")

    @property
    def description(self):
        """Return the help text for the attribute."""
        if self._description is None:
            return f"Help for {self.name}"
        return self._description

    @property
    def owner(self):
        """Return the owner of the attribute."""
        return self._owner()

    @property
    def attr_type(self):
        """Return the type of the attribute."""
        return self._attr_type

    def __repr__(self):
        return (
            "<ConfigAttr ("
            f"name={self.name}, "
            f"default={self.default_value}, "
            f"required={self.required}, "
            f"env_var={self.env_var}, "
            f"cli_args={self._cli_args}, "
            f"secret={self.secret}, "
            f'help="{self.description}, "'
            f"type={self.attr_type}, "
            ")>"
        )
