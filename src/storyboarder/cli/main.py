"""Scriptable CLI generated from the shared, explicit command catalog."""
import argparse
import json
import logging
import os
from pathlib import Path
import sys
import webbrowser
from rich.console import Console
from rich.table import Table
from storyboarder import __version__
from storyboarder.application.commands import COMMANDS, execute
from storyboarder.application.projects import Project, Workspace, discover
from storyboarder.application.service import Service
from storyboarder.application.recovery import restore
from storyboarder.automation.registry import ScriptRegistry
from storyboarder.domain.errors import StoryboardError, Conflict, NotFound


class UsageError(Exception):
    """Argument syntax failure, rendered once at the process boundary."""


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def output(value, as_json=False, as_jsonl=False):
    if as_jsonl:
        rows = value.get("items", [value]) if isinstance(value, dict) else value if isinstance(value, list) else [value]
        for row in rows:
            print(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False))
        if isinstance(value, dict) and value.get("next_offset") is not None:
            print(json.dumps({"page": {k: value[k] for k in ("total", "limit", "offset", "next_offset")}}), file=sys.stderr)
        return
    if as_json:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
        return
    console = Console(highlight=False)
    rows = value.get("items") if isinstance(value, dict) and "items" in value else value
    if isinstance(rows, list) and rows and all(isinstance(r, dict) for r in rows):
        preferred = ["id", "title", "kind", "state", "status", "revision", "position", "original_name", "relation", "role", "path"]
        columns = [k for k in preferred if any(k in r for r in rows)]
        if not columns:
            columns = list(rows[0])[:6]
        table = Table(show_lines=False)
        for key in columns:
            table.add_column(key.replace("_", " ").title(), overflow="fold")
        for row in rows:
            table.add_row(*(str(row.get(k, "")) for k in columns))
        console.print(table)
        if isinstance(value, dict) and "total" in value:
            console.print(f"{len(rows)} of {value['total']} records · offset {value.get('offset', 0)}")
    elif rows == []:
        console.print("No matching records. Create or import content to begin.")
    else:
        console.print_json(json.dumps(value, ensure_ascii=False), highlight=False)


def common(parser):
    parser.add_argument("-p", "--project", default=argparse.SUPPRESS, help="Explicit portable project folder")
    parser.add_argument("-w", "--workspace", default=argparse.SUPPRESS, help="Workspace navigator folder")
    parser.add_argument("--jsonl", action="store_true", default=argparse.SUPPRESS, help="One result per line; pagination metadata on stderr")
    parser.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS, help="Disable terminal colors")
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Stable JSON result and errors")


def get_service(args):
    if getattr(args, "project", None):
        return Service(Project(args.project))
    if getattr(args, "workspace", None):
        return Service(Workspace(args.workspace).current())
    return Service(discover())


def build_parser():
    parser = ArgumentParser(prog="storyboarder", description="A local story production desk. No arguments opens the TUI in an interactive terminal.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--verbose", action="store_true")
    common(parser)
    groups = parser.add_subparsers(dest="group")
    group_parsers, subparsers = {}, {}
    def add(group, action, help):
        if group not in group_parsers:
            parent = groups.add_parser(group, help=group.title() + " workflows")
            common(parent)
            group_parsers[group] = parent
            subparsers[group] = parent.add_subparsers(dest="verb")
        child = subparsers[group].add_parser(action, help=help, description=help)
        common(child)
        child.set_defaults(command=group + "." + action)
        return child
    for name, command in COMMANDS.items():
        group, action = name.split(".")
        child = add(group, action, command.label)
        child.add_argument("--payload", help="JSON object or @path/to/payload.json; named flags override it")
        for f in command.fields:
            kwargs = {"dest": "arg_" + f.name, "default": argparse.SUPPRESS, "help": f.label + (". " + f.help if f.help else "")}
            if f.type == "boolean":
                kwargs["action"] = argparse.BooleanOptionalAction
            elif f.type == "integer":
                kwargs["type"] = int
            elif f.type == "number":
                kwargs["type"] = float
            else:
                kwargs["type"] = str
            if f.options:
                kwargs["choices"] = f.options
            child.add_argument("--" + f.name.replace("_", "-"), **kwargs)
    p = add("workspace", "init", "Create an optional workspace navigator")
    p.add_argument("path", nargs="?")
    add("workspace", "list", "List registered and discoverable projects")
    p = add("workspace", "register", "Register a project path explicitly")
    p.add_argument("path")
    p = add("workspace", "switch", "Remember the selected project")
    p.add_argument("id")
    p = add("project", "create", "Create a portable project in an empty folder")
    p.add_argument("path", nargs="?")
    p.add_argument("--title", required=True)
    p.add_argument("--slug", help="Create inside the supplied workspace's projects folder")
    p = add("project", "open", "Open a project by path; optionally register it")
    p.add_argument("path")
    add("project", "show", "Show the selected project")
    add("project", "list", "List workspace projects")
    p = add("project", "switch", "Switch workspace project")
    p.add_argument("id")
    p = add("script", "register", "Explicitly trust an external script (runs with your OS permissions)")
    p.add_argument("name")
    p.add_argument("--max-file-bytes", type=int, default=50*1024*1024)
    p.add_argument("--max-output-bytes", type=int, default=250*1024*1024)
    p.add_argument("--command", required=True, dest="script_command", help='JSON argument array, no shell string')
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--env-keys", default="", help="Comma-separated environment variable names, never values")
    p.add_argument("--description", default="")
    add("script", "list", "List trusted external scripts")
    p = add("script", "remove", "Unregister a script")
    p.add_argument("name")
    for name in ("ui", "tui", "doctor", "backup", "restore", "import", "compose"):
        p = groups.add_parser(name, help={"ui": "Start loopback API and bundled React app", "tui": "Open the multi-page terminal app", "doctor": "Check project health", "backup": "Create project backup", "restore": "Restore backup to a new folder", "import": "Import still images into intake", "compose": "Preview resolved story composition"}[name])
        common(p)
        p.set_defaults(command=name)
        if name == "ui":
            p.add_argument("--port", type=int, default=7430)
            p.add_argument("--no-browser", action="store_true")
        if name == "doctor":
            p.add_argument("--hashes", action="store_true")
        if name == "restore":
            p.add_argument("archive")
            p.add_argument("destination")
        if name == "import":
            p.add_argument("path")
            p.add_argument("--recursive", action="store_true")
        if name == "compose":
            p.add_argument("owner_id")
    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except UsageError as exc:
        if "--json" in argv or "--jsonl" in argv:
            print(json.dumps({"error": {"code": "invalid_arguments", "message": str(exc)}}), file=sys.stderr)
        else:
            parser.print_usage(sys.stderr)
            print(f"storyboarder: {exc}", file=sys.stderr)
        raise SystemExit(2)
    as_jsonl = getattr(args, "jsonl", False)
    as_json = getattr(args, "json", False) or as_jsonl
    if getattr(args, "no_color", False):
        os.environ["NO_COLOR"] = "1"
    logging.basicConfig(level=logging.DEBUG if getattr(args, "verbose", False) else logging.WARNING)
    command = getattr(args, "command", None)
    if command is None:
        if not getattr(args, "group", None) and sys.stdin.isatty() and sys.stdout.isatty():
            command = "tui"
        else:
            parser.print_help()
            return 0
    try:
        workspace = Workspace(args.workspace) if getattr(args, "workspace", None) else None
        if command in ("ui", "tui"):
            project = None
            if getattr(args, "project", None):
                project = Project(args.project)
            elif not workspace:
                try:
                    project = Project(discover())
                except NotFound:
                    workspace = Workspace(Path.cwd() / "storyboards")
            if command == "tui":
                from storyboarder.tui.app import run_tui
                run_tui(project, workspace)
            else:
                from storyboarder.api.server import serve
                serve(project, workspace, args.port, not args.no_browser)
            return 0
        if command.startswith("workspace.") or command in ("project.list", "project.switch"):
            workspace = workspace or Workspace(getattr(args, "path", None) or Path.cwd())
            action = command.split(".")[1]
            if action == "init":
                result = Workspace(args.path).init() if getattr(args, "path", None) else workspace.init()
            elif action == "list":
                result = workspace.list()
            elif action == "register":
                result = workspace.register(args.path)
            else:
                result = workspace.switch(args.id)
        elif command == "project.create":
            if workspace and args.slug:
                result = workspace.create(args.title, args.slug).summary()
            elif args.path:
                project = Project.create(args.path, args.title)
                result = workspace.register(project.root) if workspace else project.summary()
            else:
                raise StoryboardError("Pass a new project path, or --workspace PATH and --slug NAME.")
        elif command == "project.open":
            result = workspace.register(args.path) if workspace else Project(args.path).summary()
        elif command == "project.show":
            result = get_service(args).project.summary()
        elif command.startswith("script."):
            registry = ScriptRegistry()
            if command == "script.register":
                result = registry.register(args.name, json.loads(args.script_command), args.timeout, args.env_keys, args.description, args.max_file_bytes, args.max_output_bytes)
            elif command == "script.remove":
                result = registry.remove(args.name)
            else:
                result = registry.list()
        elif command == "restore":
            result = restore(args.archive, args.destination)
            if workspace:
                workspace.register(result["path"])
        else:
            service = get_service(args)
            if command == "doctor":
                result = service.doctor(args.hashes)
            elif command == "backup":
                result = service.backup()
            elif command == "import":
                result = service.import_path(args.path, args.recursive)
            elif command == "compose":
                result = service.compose(args.owner_id)
            else:
                payload = {}
                if getattr(args, "payload", None):
                    raw = args.payload
                    payload = json.loads(Path(raw[1:]).read_text() if raw.startswith("@") else raw)
                    if not isinstance(payload, dict):
                        raise StoryboardError("Payload must be a JSON object.")
                for field in COMMANDS[command].fields:
                    key = "arg_" + field.name
                    if hasattr(args, key):
                        value = getattr(args, key)
                        if field.type == "json":
                            value = json.loads(Path(value[1:]).read_text() if value.startswith("@") else value)
                        payload[field.name] = value
                result = execute(service, command, payload)
        output(result, as_json, as_jsonl)
        failed = isinstance(result, dict) and (result.get("healthy") is False or result.get("status") == "failed" or bool(result.get("errors")))
        if failed:
            raise SystemExit(4)
        return 0
    except StoryboardError as exc:
        if as_json:
            print(json.dumps({"error": exc.as_dict()}, ensure_ascii=False), file=sys.stderr)
        else:
            Console(stderr=True).print("[bold red]Could not complete this action.[/] " + str(exc), markup=True, highlight=False)
        raise SystemExit(3 if isinstance(exc, Conflict) else 2 if isinstance(exc, NotFound) else 1)
    except (OSError, ValueError) as exc:
        message = {"code": "input_or_io", "message": str(exc)}
        print(json.dumps({"error": message}) if as_json else "Could not complete this action: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
