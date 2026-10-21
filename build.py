from pathlib import Path
import configparser
import shutil
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parent
FILES = (
    "LICENSE",
    "manifest.ini",
    "appModules/happ/__init__.py",
    "appModules/happ/context.py",
    "appModules/happ/dialog.py",
    "appModules/happ/dialogLabels.py",
    "appModules/happ/groupLabels.py",
    "appModules/happ/panel.py",
    "appModules/happ/panelLabels.py",
    "appModules/happ/serverLabels.py",
    "appModules/happ/servers.py",
    "appModules/happ/settings.py",
    "appModules/happ/settingsGroups.py",
    "appModules/happ/subscriptionActions.py",
    "doc/ru/readme.html",
)


def build():
    manifest = configparser.ConfigParser(interpolation=None)
    manifest.read_string("[addon]\n" + (ROOT / "addon/manifest.ini").read_text(encoding="utf-8"))
    values = {key: value.strip('"') for key, value in manifest["addon"].items()}
    for key in ("name", "summary", "version", "author", "description", "docfilename",
                "minimumnvdaversion", "lasttestednvdaversion"):
        if not values.get(key):
            raise ValueError(f"Missing manifest field: {key}")
    if not all(character.isalnum() or character in ".-_" for character in values["name"] + values["version"]):
        raise ValueError("Unsafe package name")
    if "doc/ru/" + values["docfilename"] not in FILES:
        raise ValueError("Missing documentation")
    output = ROOT / "dist" / f"{values['name']}-{values['version']}.nvda-addon"
    output.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="happ-build-") as temporary:
        staging = Path(temporary)
        for relative in FILES:
            source = ROOT / relative if relative == "LICENSE" else ROOT / "addon" / relative
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"Invalid source: {relative}")
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
            for relative in FILES:
                archive.write(staging / relative, relative)
    with zipfile.ZipFile(output) as archive:
        if archive.namelist() != list(FILES) or archive.testzip() is not None:
            raise ValueError("Package verification failed")
        for relative in FILES:
            source = ROOT / relative if relative == "LICENSE" else ROOT / "addon" / relative
            if archive.read(relative) != source.read_bytes():
                raise ValueError(f"Package content mismatch: {relative}")
    print(output)
    print(f"Verified {len(FILES)} files")


if __name__ == "__main__":
    build()
