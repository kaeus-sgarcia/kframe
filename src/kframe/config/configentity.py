import os
import sys
from argparse import ArgumentParser, Namespace
from collections import ChainMap
from enum import Enum

from .configattr import ConfigAttr, Secret


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

        dct["parent_module"] = property(lambda self: parent_entity, doc=f"{dct['type'].value} parent module ")

        def run(self):
            """Execute command"""
            self.execute()

        if dct["type"] == ConfigEntityType.command:
            if "__call__" in dct:
                raise AttributeError("Command class cannot have __call__ method")
            dct["__call__"] = run

        new_cls = super().__new__(cls, _name, bases, dct)
        if parent_entity is not None:
            # if new_cls.type == AppModuleType.command:
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
                type_ = ConfigEntityType.base
            case 1:
                match bases[0].__name__:
                    case "AppModule":
                        type_ = ConfigEntityType.module
                    case "AppCommand":
                        type_ = ConfigEntityType.command
                    case _:
                        raise AttributeError("Entity parent class must be AppModule or AppCommand")
            case _:
                raise AttributeError("Command inheritance is not permitted, only one base class is allowed")

        dct = {
            "__name__": (name or cls).casefold(),
            "type": type_,
        }

        if type_ is ConfigEntityType.base:
            return dct | {
                "__doc__": f"{type_.value.title()} base module",
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


class AppCommand(metaclass=ConfigEntity):
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


def parse_args(entity: ConfigEntity = AppModule, level=0, arg_parser=None):
    if entity is AppModule:
        if entity().root_module is None:
            raise AttributeError("Root module not set")
        entity = entity().root_module()
        arg_parser = ArgumentParser(sys.argv[0], description=entity.__doc__)
    else:
        entity = entity()

    for attr in entity._attribute_names:
        if getattr(entity.attr, attr).cli_args is not None:
            arg_parser.add_argument(
                *getattr(entity.attr, attr).cli_args[0],
                **getattr(entity.attr, attr).cli_args[1],
            )

    if len(entity._submodules) + len(entity._commands) > 0:
        subparsers = arg_parser.add_subparsers(metavar="", dest=f"__level_{level}", help="Commands and submodules")

    for module in entity._submodules:
        subparser = subparsers.add_parser(module().__name__, help=module.__doc__)
        parse_args(module, level + 1, arg_parser=subparser)

    for command in entity._commands:
        subparser = subparsers.add_parser(command().__name__, help=command.__doc__)
        parse_args(command, level + 1, arg_parser=subparser)

    if level == 0:
        args = vars(arg_parser.parse_args())

        command = None
        i = 0
        while f"__level_{i}" in args and args[f"__level_{i}"] is not None:
            entity_name = args[f"__level_{i}"]
            for child in entity._submodules.union(entity._commands):
                if child().__name__ == entity_name:
                    entity = child()
                    break
            i += 1

        if entity.entity_type == ConfigEntityType.command:
            for k, attr in entity.attrs.items():
                if k in args and args[k] is not None:
                    entity._sources[k]["cli"] = (
                        Secret[attr.attr_type](args[k]) if attr.secret else args[k]  # type: ignore
                    )
                if attr.required and getattr(entity, k) is None:
                    raise AttributeError(f"Required attribute {attr} not set")
            runner = entity
            command = entity.__name__
        else:
            arg_parser.print_help()

        if entity.show_config:
            entity.show()

        return runner, command

    return None
