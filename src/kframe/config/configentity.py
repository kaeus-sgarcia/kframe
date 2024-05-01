import logging
import os
import sys
from argparse import ArgumentError, ArgumentParser, ArgumentTypeError, Namespace
from collections import ChainMap
from enum import Enum

from .configattr import ConfigAttr, Secret

logger = logging.getLogger("kframe.config")


class ConfigEntityType(Enum):
    base = "base"
    module = "Module"
    command = "Command"


class ConfigEntity(type):
    _commands: set
    _submodules: set
    _attribute_names: set
    _sources: ChainMap
    show_config: ConfigAttr
    attr: Namespace
    attrs: dict[str, ConfigAttr]
    entity_type: ConfigEntityType
    parent_module: "ConfigEntity"
    root_module: "ConfigEntity"

    def show(cls, file=sys.stdout):
        """Prints entity configuration"""

    def __new__(cls, _name, bases, dct, name=None, parent_entity=None, description=None):
        sources = {}

        if len(bases) > 0:
            for k in bases[0]._attribute_names:
                if k not in dct:
                    dct[k] = bases[0].__dict__[k]

        for k, v in dct.items():
            if isinstance(v, ConfigAttr) and k not in dct["_sources"]:
                v._name = k
                sources[k] = {"default": Secret[v.attr_type](v.default_value) if v.secret else v.default_value}
                v.__doc__ = v.description

                if v.env_var is not None and v.env_var in os.environ:
                    sources[k]["env"] = Secret[v.attr_type](v.env_var) if v.secret else os.environ[v.env_var]

                if (
                    v.cli_args is None
                    and v.required
                    and v.default_value is None
                    and isinstance(v.env_var, str)
                    and os.getenv(v.env_var) is None
                ):
                    raise AttributeError(f"Required attribute {v} must have a default value or environment variable")

        dct["_sources"] = ChainMap(sources, dct["_sources"])
        dct["_commands"] = set()
        dct["_submodules"] = set()

        dct["_attribute_names"] = {k for k, v in dct.items() if isinstance(v, ConfigAttr)}

        attr = {k: dct[k] for k in dct["_attribute_names"]}

        def attrs(self) -> dict[str, ConfigAttr]:
            """Entity attributes"""
            return attr

        dct["attr"] = property(lambda self: Namespace(**attr), doc="Entity attributes namespace")
        dct["attrs"] = property(attrs, doc="Entity attributes dictionary")
        dct["namespace"] = property(lambda self: ".".join(dct["_namespace"]), doc="Entity namespace")

        dct["parent_module"] = property(lambda self: parent_entity, doc=f"{dct['entity_type'].value} parent module ")

        def run(self):
            """Execute command"""
            self.execute()

        if dct["entity_type"] == ConfigEntityType.command:
            if "__call__" in dct:
                raise AttributeError("Command class cannot have __call__ method")
            dct["__call__"] = run

        new_cls = super().__new__(cls, _name, bases, dct)
        if parent_entity is not None:
            if new_cls.entity_type == ConfigEntityType.module:
                parent_entity._submodules.add(new_cls)
            if new_cls.entity_type == ConfigEntityType.command:
                parent_entity._commands.add(new_cls)
        elif len(bases) > 0:
            bases[0].root_module = new_cls

        return new_cls

    def __prepare__(cls, bases, name=None, parent_entity=None, description=None):  # noqa: PLW3201
        match len(bases):
            case 0:
                entity_type = ConfigEntityType.base
            case 1:
                match bases[0].__name__:
                    case "AppModule":
                        entity_type = ConfigEntityType.module
                    case "AppCommand":
                        entity_type = ConfigEntityType.command
                    case _:
                        raise AttributeError("Entity parent class must be AppModule or AppCommand")
            case _:
                raise AttributeError("Command inheritance is not permitted, only one base class is allowed")

        dct = {
            "__name__": (name or cls).casefold(),
            "entity_type": entity_type,
        }

        if entity_type is ConfigEntityType.base:
            return dct | {
                "__doc__": f"{entity_type.value.title()} base module",
                "_sources": ChainMap({}),
                "_namespace": [],
            }

        dct |= {
            "__doc__": description or f"<{name or cls}> implementation",
            "_sources": parent_entity._sources if parent_entity is not None else ChainMap({}),
            "_namespace": [dct["__name__"]],
        }

        if parent_entity is not None:
            dct["_namespace"] = (parent_entity._namespace or []) + dct["_namespace"]
            for k in parent_entity._sources:
                if k not in dct:
                    dct[k] = parent_entity.__dict__[k]
        return dct

    def load(
        cls,
        get_command: bool = True,
        require_command: bool = False,
        show_parser_help: bool = True,
    ):
        logger.debug("Loading %s", cls.__name__)

        if cls.entity_type == ConfigEntityType.module:
            base = cls.root_module
        elif cls.entity_type == ConfigEntityType.command:
            base = cls().parent_module.root_module
        else:
            base = None

        if base is None:
            raise AttributeError("Entity must have a base module")

        arg_parser = build_parser(base)
        try:
            args = vars(arg_parser.parse_known_args()[0])
        except (ArgumentError, ArgumentTypeError):
            logger.exception("Error parsing arguments")
            if show_parser_help:
                arg_parser.print_help()

        current_cls = cls()
        while current_cls is not None:
            logger.debug("Loading environment variables for %s: %s", current_cls.__name__, current_cls.attrs.keys())
            for k, attr in current_cls.attrs.items():
                if attr.cli_args is not None and attr.name in args and args[attr.name] is not None:
                    current_cls._sources[k]["cli"] = (
                        Secret[attr.attr_type](args[attr.name]) if attr.secret else args[attr.name]  # type: ignore
                    )
            current_cls = current_cls.parent_module() if current_cls.parent_module is not None else None

        logger.debug("Sources for %s: %s", cls.__name__, cls._sources)

        if get_command or require_command:
            i = 0
            current_cls = base()
            while f"__level_{i}" in args and args[f"__level_{i}"] is not None:
                entity_name = args[f"__level_{i}"]
                for child in current_cls._submodules.union(current_cls._commands):
                    if child().__name__ == entity_name:
                        current_cls = child()
                        break
                i += 1
            logger.debug("Highest level class found: %s", current_cls.__name__)

            if require_command and current_cls.entity_type != ConfigEntityType.command:
                if show_parser_help:
                    arg_parser.print_help()
                else:
                    raise AttributeError("Command not found in CLI arguments")

            if get_command and current_cls.entity_type == ConfigEntityType.command:
                current_cls.__class__.load(get_command=False)
                return current_cls

        return None


class AppCommand(metaclass=ConfigEntity):
    root_module: "AppModule"

    show_config = ConfigAttr(
        default=False,
        description="Show configuration",
        cli_args=["--show-config"],
        attr_type=bool,
    )

    def show(self, file=sys.stdout):
        file.write(f"\nCommand     : {self.__name__}")
        file.write(f"\nNamespace   : {self.namespace}")
        file.write(f"\nDescription : {self.__doc__}")
        file.write("\nAttributes")
        for f in self._attribute_names:
            if getattr(self.attr, f).required:
                file.write("\n  * ")
            else:
                file.write("\n  - ")
            file.write(f"{getattr(self.attr, f).name}: {getattr(self, f)}")
        file.write("\n\n")


class AppModule(metaclass=ConfigEntity):
    root_module: "AppModule"

    def show(self, file=sys.stdout):
        file.write(f"\nModule      : {self.__name__}")
        file.write(f"\nNamespace   : {self.namespace}")
        file.write(f"\nDescription : {self.__doc__}")
        file.write("\nAttributes:")
        for f in self._attribute_names:
            if getattr(self.attr, f).required:
                file.write("\n  * ")
            else:
                file.write("\n  - ")
            file.write(f"{getattr(self.attr, f).name}: {getattr(self, f)}")

        file.write("\nCommands:")
        for f in self._commands:
            file.write(f"\n  * {f.__name__}")

        file.write("\nSubmodules:")
        for f in self._submodules:
            file.write(f"\n  * {f.__name__}")
        file.write("\n\n")


def build_parser(entity: ConfigEntity = AppModule, level=0, arg_parser=None):
    _entity = entity()

    if _entity.entity_type is ConfigEntityType.module and entity is entity.root_module:
        logger.debug("Building parser for %s", entity.__name__)
        arg_parser = ArgumentParser(sys.argv[0], description=entity.__doc__)

    logger.debug("Adding arguments for %s", entity.__name__)

    logger.debug(arg_parser)
    for attr in _entity._attribute_names:
        logger.debug("Adding argument %s to %s", attr, _entity.__name__)
        logger.debug(_entity.attr)
        if getattr(_entity.attr, attr).cli_args is not None:
            arg_parser.add_argument(
                *getattr(_entity.attr, attr).cli_args[0],
                **getattr(_entity.attr, attr).cli_args[1],
            )

    if len(entity._submodules) + len(entity._commands) > 0:
        subparsers = arg_parser.add_subparsers(metavar="", dest=f"__level_{level}", help="Commands and submodules")

    for module in entity._submodules:
        subparser = subparsers.add_parser(module().__name__, help=module.__doc__)
        build_parser(module, level + 1, arg_parser=subparser)

    for command in entity._commands:
        subparser = subparsers.add_parser(command().__name__, help=command.__doc__)
        build_parser(command, level + 1, arg_parser=subparser)

    if level > 0:
        return None

    return arg_parser
