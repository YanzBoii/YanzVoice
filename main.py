import sys

USAGE = """YanzVoice — dictée vocale

  main.py                       lance l'application
  main.py --install             raccourcis Bureau et menu Démarrer
  main.py --install --startup   ajoute le démarrage automatique
  main.py --install --refresh-icon  force Windows à relire l'icône
  main.py --uninstall           retire tous les raccourcis
  main.py --diagnose            teste réseau, encodage et micro
  main.py --export-config [f]   sauvegarde les réglages (clé API incluse)
  main.py --import-config <f>   restaure des réglages sauvegardés
  main.py --help                affiche ceci
"""


def _value_after(args: list[str], flag: str) -> str | None:
    """The argument following `flag`, when it is not itself an option."""
    if flag not in args:
        return None
    index = args.index(flag) + 1
    if index < len(args) and not args[index].startswith("-"):
        return args[index]
    return None


def main() -> int:
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(USAGE)
        return 0

    if "--install" in args:
        from yanzvoice.branding import install

        return install(
            startup="--startup" in args,
            refresh_icon="--refresh-icon" in args,
        )

    if "--uninstall" in args:
        from yanzvoice.branding import uninstall

        return uninstall()

    if "--diagnose" in args:
        from yanzvoice.diagnose import diagnose

        return diagnose()

    if "--export-config" in args:
        from yanzvoice.backup import export_config

        return export_config(_value_after(args, "--export-config"))

    if "--import-config" in args:
        from yanzvoice.backup import import_config

        source = _value_after(args, "--import-config")
        if not source:
            print("Indique le fichier à importer :")
            print("  main.py --import-config chemin\\vers\\sauvegarde.json")
            return 1
        return import_config(source)

    from yanzvoice.app import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
