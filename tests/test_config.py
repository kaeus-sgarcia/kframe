import io
import sys
import logging
logging.basicConfig(level=logging.ERROR, force=True)


from kframe.config.configattr import ConfigAttr
from kframe.config.configentity import AppCommand, AppModule, ConfigEntityType
import pytest

class TestConfig:
    def test_modules_and_submodules(self):
        class RootModule(AppModule, name="root"):
            log_level = ConfigAttr(default="ERROR", description="Log level", cli_args=["-l", "--log-level"])
            a = ConfigAttr(env_var="A_VALUE", required=True, default="default_a", cli_args=["-a", "--a-value"])

        class Module1(AppModule, name="module_1", parent_entity=RootModule):
            b = ConfigAttr(env_var="B_VALUE", required=True, default="default_b", cli_args=["--b-value1"])

        class Command1(AppCommand, name="command_0", description="Command 0 extended help", parent_entity=Module1):
            x = ConfigAttr(env_var="X_VALUE", required=True, default="default_x", cli_args=["--x-value"])
            bool_attr = ConfigAttr(default=False, description="Boolean attribute", cli_args=["--bool-attr"], attr_type=bool)
        assert Command1().x == "default_x"
        assert Command1().b == "default_b"
        assert Command1().a == "default_a"
        assert Command1().log_level == "ERROR"
        assert Command1().bool_attr == False
        assert type(Command1().bool_attr) == bool
        assert set(Command1().attrs.keys()) == {"x", "a", "b", "log_level", "show_config", "bool_attr"}

    def test_root_module_config(self):
        sys.argv = ["test.py", "module_1", "command_1", "-a", "cli_a", "-l", "DEBUG", "-b", "cli_b", "-x", "cli_x"]
        class RootModule(AppModule, name="root"):
            log_level = ConfigAttr(default="ERROR", description="Log level", cli_args=["-l", "--log-level"])
            a = ConfigAttr(env_var="A_VALUE", required=True, default="default_a", cli_args=["-a", "--a-value"])

        class Module1(AppModule, name="module_1", parent_entity=RootModule):
            b = ConfigAttr(env_var="B_VALUE", required=True, default="default_b", cli_args=["-b", "--b-value1"])

        class Command1(AppCommand, name="command_1", description="Command 0 extended help", parent_entity=Module1):
            x = ConfigAttr(env_var="X_VALUE", required=True, default="default_x", cli_args=["-x", "--x-value"])

        RootModule.load(get_command=False)
        Module1.load(get_command=False)
        Command1.load(get_command=False)

        root_config = RootModule()
        module1_config = Module1()
        command1_config = Command1()

        output = io.StringIO("")
        root_config.show(output)
        logging.debug(f"RootModule config:\n{output.getvalue()}")
        output = io.StringIO("")
        module1_config.show(output)
        logging.debug(f"Module1 config:\n{output.getvalue()}")
        output = io.StringIO("")
        command1_config.show(output)
        logging.debug(f"Command1 config:\n{output.getvalue()}")

        assert command1_config.x == "cli_x"
        assert command1_config.b == "cli_b"
        assert command1_config.a == "cli_a"
        assert command1_config.log_level == "DEBUG"
        assert module1_config.b == "cli_b"
        assert module1_config.a == "cli_a"
        assert module1_config.log_level == "DEBUG"
        assert root_config.a == "cli_a"
        assert root_config.log_level == "DEBUG"

    def test_get_command(self):
        sys.argv = ["test.py", "module_1", "command_1", "-a", "cli_a", "-l", "DEBUG", "-b", "cli_b", "-x", "cli_x"]
        class RootModule(AppModule, name="root"):
            log_level = ConfigAttr(default="ERROR", description="Log level", cli_args=["-l", "--log-level"])
            a = ConfigAttr(env_var="A_VALUE", required=True, default="default_a", cli_args=["-a", "--a-value"])

        class Module1(AppModule, name="module_1", parent_entity=RootModule):
            b = ConfigAttr(env_var="B_VALUE", required=True, default="default_b", cli_args=["-b", "--b-value1"])

        class Command1(AppCommand, name="command_1", description="Command 0 extended help", parent_entity=Module1):
            x = ConfigAttr(env_var="X_VALUE", required=True, default="default_x", cli_args=["-x", "--x-value"])

            def execute(self):
                assert self.x == "cli_x"
                assert self.b == "cli_b"
                assert self.a == "cli_a"
                assert self.log_level == "DEBUG"

        command = RootModule.load(get_command=True, require_command=True, show_parser_help=False)
        logging.debug(f"Command: {command}")
        
        assert command.entity_type is ConfigEntityType.command

        logging.debug(f"Command sources: {command._sources}")
        command()

        
