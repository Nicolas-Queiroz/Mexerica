"""Entry point: the GTK app by default; conversions from the terminal with --to / --tool / --list."""

import argparse
import sys
from pathlib import Path


def _cli(argv: list[str]) -> int:
    from .core import conversions, jobs
    from .core.context import OperationError
    from .core.formats import FORMATS
    from .core.tools import TOOLS, TOOLS_BY_ID

    parser = argparse.ArgumentParser(prog="mexerica", description="Conversor de arquivos offline.")
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--to", metavar="FORMATO", help="converte para o formato (ex.: webp, mp3, docx)")
    parser.add_argument("--tool", metavar="FERRAMENTA", help="aplica uma ferramenta (veja --list)")
    parser.add_argument("--param", action="append", default=[], metavar="CHAVE=VALOR")
    parser.add_argument("--output-dir", metavar="PASTA")
    parser.add_argument("--list", action="store_true", help="lista formatos e ferramentas")
    args = parser.parse_args(argv)

    if args.list:
        print(f"{conversions.total_conversions()} conversões:")
        for source, targets in conversions.REGISTRY.items():
            print(f"  {FORMATS[source].label:>9} → {', '.join(FORMATS[t].label for t in targets)}")
        print(f"\n{len(TOOLS)} ferramentas:")
        for tool in TOOLS:
            params = " ".join(f"{p.key}={p.default or '…'}" for p in tool.params)
            print(f"  {tool.id:<16} {tool.label:<20} {params}")
        return 0
    if not args.files:
        parser.error("informe arquivos")
    try:
        if args.to:
            for path in args.files:
                for result in jobs.run_conversion(path.resolve(), args.to, output_dir=args.output_dir):
                    print(result)
        else:
            tool = TOOLS_BY_ID.get(args.tool)
            if tool is None:
                parser.error(f"ferramenta desconhecida: {args.tool}")
            params = tool.default_params()
            params.update(dict(item.split("=", 1) for item in args.param))
            for result in jobs.run_tool(
                tool, [path.resolve() for path in args.files], params, output_dir=args.output_dir
            ):
                print(result)
    except (OperationError, KeyError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if any(arg in ("--to", "--tool", "--list", "-h", "--help") or arg.startswith(("--to=", "--tool=")) for arg in argv):
        return _cli(argv)
    from .app import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
