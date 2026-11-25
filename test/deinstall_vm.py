"""Prüft auf einem frischen Windows, was die Deinstallation von Antoti mit den Daten macht. Sie startet den Befehl, den
Windows unter „Einstellungen › Apps“ aufruft (UninstallString aus der Registry), schreibt jeden Dialog mit und
beantwortet ihn: die Bestätigung mit Ja, die Frage nach den Daten und die Rückfrage mit der Antwort aus --daten.
Danach prüft sie, ob die Marken im Datenordner noch da sind, und endet mit 1, wenn das nicht zur Antwort passt:
„behalten“ und „still“ behalten alles, „löschen“ lässt keinen Datenordner zurück. Bericht in <arbeit>\\bericht.json.
"""
import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import winreg
from pathlib import Path

from pywinauto import Desktop

LOCAL = Path(os.environ["LOCALAPPDATA"])
DATA = LOCAL / "Antoti"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{FBC695F1-FD50-4032-A310-EBD98A9D5294}_is1"
report = {"schritte": [], "dialoge": []}


def step(name, **facts):
    report["schritte"].append({"schritt": name, "zeit": time.strftime("%H:%M:%S"), **facts})
    print(time.strftime("%H:%M:%S"), name, json.dumps(facts, ensure_ascii=False), flush=True)


def console_answers():
    try:
        with urllib.request.urlopen("http://127.0.0.1:18440/api/session", timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, OSError):
        return None


def registry(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def data_state():
    return {"daten_ordner": DATA.is_dir(), "marke_daten": (DATA / "marke.txt").is_file(),
            "marke_desktop": (DATA / "desktop" / "passwords.json").is_file(),
            "konten": (DATA / "accounts.sqlite3").is_file(),
            "inhalt": sorted(entry.name for entry in DATA.iterdir()) if DATA.is_dir() else []}


def dialogs():
    found = []
    for window in Desktop(backend="uia").windows(visible_only=True):
        try:
            title, kind = window.window_text(), window.class_name()
            if "Antoti" not in title:
                continue
            texts = [item.window_text() for item in window.descendants() if item.window_text().strip()]
            found.append((window, "%s [%s]" % (title, kind), texts))
        except Exception:
            continue
    return found


# Die Dialoge der Deinstallation, am Text erkannt: (Kennung, Text, Knopf; None heißt nichts drücken). Fragen und
# Meldungen erscheinen im Fenster des Fortschritts; als Fortschritt zählt es nur, solange es keinen anderen Text zeigt.
# Ein Fenster von Antoti, das nichts davon ist, beendet den Lauf als Abweichung, statt es wegzuklicken.
KINDS = (("schluss", "successfully removed", "OK"), ("sicher", "really delete", None),
         ("frage", "what should happen", None), ("bestaetigen", "completely remove", "Yes"))
PROGRESS = {"uninstall status", "please wait while antoti is removed from your computer.", "uninstalling antoti...",
            "cancel", "close"}
EXPECTED = {"behalten": ["bestaetigen", "frage", "schluss"], "loeschen": ["bestaetigen", "frage", "sicher", "schluss"],
            "still": []}


def kind_of(texts):
    lower = [text.strip().lower() for text in texts]
    found = next((kind for kind, text, _ in KINDS if text in " ".join(lower)), None)
    return found or ("fortschritt" if set(lower) <= PROGRESS else None)


def press(window, label):
    try:
        for item in window.descendants(control_type="Button"):
            name = item.window_text().replace("&", "")
            if name == label or name.startswith(label + "\n") or name.startswith(label + " "):
                item.invoke()
                return name
    except Exception:
        return None
    return None


def uninstaller_runs():
    """True, solange ein Prozess des Deinstallers läuft; None, wenn tasklist nicht antwortet."""
    listing = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True)
    if listing.returncode != 0 or not listing.stdout.strip():
        return None
    names = [line.split('","')[0].strip('"').lower() for line in listing.stdout.splitlines() if line]
    return any(name.startswith(("_iu", "unins")) for name in names)


def uninstall(answer_data, command):
    step("Befehl aus der Registry", UninstallString=command, QuietUninstallString=registry("QuietUninstallString"))
    if answer_data == "still":
        command += " /VERYSILENT /SUPPRESSMSGBOXES /NORESTART"
    choice = "Delete everything" if answer_data == "loeschen" else "Keep the data"
    process = subprocess.Popen(command)
    seen, answered, problems = set(), [], []
    deadline = time.monotonic() + 15 * 60
    done = False
    while time.monotonic() < deadline and not problems:
        for window, title, texts in dialogs():
            kind = kind_of(texts)
            label = next((button for name, _, button in KINDS if name == kind), None)
            if kind in ("sicher", "frage"):
                label = choice
            pressed = press(window, label) if label and answer_data != "still" else None
            if pressed and kind not in answered:
                answered.append(kind)
            if (title, tuple(texts)) not in seen or pressed:
                report["dialoge"].append({"zeit": time.strftime("%H:%M:%S"), "titel": title, "art": kind,
                                          "texte": texts, "gedrueckt": pressed})
                print("Dialog:", kind, title, texts, "->", pressed, flush=True)
                seen.add((title, tuple(texts)))
            if kind is None or answer_data == "still":
                problems.append("Unerwartetes Fenster: %s %s" % (title, texts[:3]))
        if not problems and process.poll() is not None and not dialogs() and uninstaller_runs() is False:
            done = True
            break
        time.sleep(0.5)
    return {"exitcode_starter": process.poll(), "fertig": done, "beantwortet": answered, "fehler": problems}


def verdict(answer_data, state, finished, app):
    """Gibt die Abweichungen vom erwarteten Ergebnis zurück, leer, wenn alles stimmt."""
    problems = list(finished["fehler"])
    if not finished["fertig"] and not problems:
        problems.append("Deinstallation lief nach 15 Minuten noch")
    if finished["exitcode_starter"] != 0:
        problems.append("Deinstaller endete mit %s" % finished["exitcode_starter"])
    if registry("UninstallString") is not None:
        problems.append("Antoti ist noch als App eingetragen")
    if app.exists():
        problems.append("Programmordner blieb: %s" % app)
    if console_answers() is not None:
        problems.append("Die Konsole antwortet noch")
    if finished["beantwortet"] != EXPECTED[answer_data]:
        problems.append("Dialoge %s, erwartet %s" % (finished["beantwortet"], EXPECTED[answer_data]))
    if answer_data == "loeschen":
        problems += ["Datenordner blieb: %s" % state["inhalt"]] if state["daten_ordner"] else []
    else:
        problems += ["%s fehlt" % name for name in ("marke_daten", "marke_desktop", "konten") if not state[name]]
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", type=Path, required=True)
    parser.add_argument("--daten", choices=("behalten", "loeschen", "still"), required=True)
    parser.add_argument("--arbeit", type=Path, required=True)
    args = parser.parse_args()
    work = args.arbeit.resolve()
    work.mkdir(parents=True, exist_ok=True)
    try:
        code = subprocess.run([str(args.setup.resolve()), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                               "/MODE=server", "/LOG=" + str(work / "install.log")], timeout=20 * 60).returncode
        started = time.monotonic()
        while code == 0 and console_answers() is None and time.monotonic() - started < 300:
            time.sleep(3)
        console, command, installed = console_answers(), registry("UninstallString"), data_state()
        step("1 installiert", exitcode=code, konsole=console, **installed)
        if code != 0 or console is None or command is None or not installed["konten"]:
            report["abweichungen"] = ["Installation nicht bereit: Exitcode %s, Konsole %s, Eintrag %s, Konten %s"
                                      % (code, console, command, installed["konten"])]
        else:
            (DATA / "marke.txt").write_text("Daten vor der Deinstallation\n", encoding="utf-8")
            (DATA / "desktop").mkdir(exist_ok=True)
            (DATA / "desktop" / "passwords.json").write_text('{"entries": [], "never": []}', encoding="utf-8")
            finished = uninstall(args.daten, command)
            state = data_state()
            step("2 deinstalliert", antwort_daten=args.daten, **finished, **state)
            report["abweichungen"] = verdict(args.daten, state, finished, Path(command.strip('"')).parent)
    finally:
        (work / "bericht.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for problem in report["abweichungen"]:
        print("FEHLER:", problem, flush=True)
    return 1 if report["abweichungen"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
