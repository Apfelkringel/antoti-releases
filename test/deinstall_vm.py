"""Prüft auf einem frischen Windows, was die Deinstallation von Antoti mit den Daten macht. Sie startet den Befehl, den
Windows unter „Einstellungen › Apps“ aufruft (UninstallString aus der Registry), schreibt jeden Dialog mit und
beantwortet ihn: die Bestätigung mit Ja, die Frage nach den Daten mit der Antwort aus --daten (behalten = Nein).
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


def press(window, labels):
    for item in window.descendants(control_type="Button"):
        name = item.window_text().replace("&", "")
        if any(name == label or name.startswith(label + "\n") or name.startswith(label + " ") for label in labels):
            item.invoke()
            return name
    return None


def uninstall(answer_data):
    command = registry("UninstallString")
    step("Befehl aus der Registry", UninstallString=command, QuietUninstallString=registry("QuietUninstallString"))
    if answer_data == "still":
        command += " /VERYSILENT /SUPPRESSMSGBOXES /NORESTART"
    process = subprocess.Popen(command)
    seen = set()
    deadline = time.monotonic() + 15 * 60
    listed = time.monotonic() + 20
    done = False
    while time.monotonic() < deadline:
        for window, title, texts in dialogs():
            key = (title, tuple(texts))
            text = " ".join(texts)
            lower = text.lower()
            if "successfully removed" in lower:
                labels = {"OK"}
            elif "really delete" in lower:
                labels = {"Delete everything"} if answer_data == "loeschen" else {"Keep the data"}
            elif "what should happen" in lower:
                labels = {"Delete everything"} if answer_data == "loeschen" else {"Keep the data"}
            elif "data" in lower:
                labels = {"Yes"} if answer_data == "loeschen" else {"No"}
            elif "remove" in lower:
                labels = {"Yes"}
            else:
                labels = {"OK"}
            pressed = press(window, labels)
            if key not in seen or pressed:
                report["dialoge"].append({"zeit": time.strftime("%H:%M:%S"), "titel": title, "texte": texts,
                                          "gedrueckt": pressed})
                print("Dialog:", title, texts, "->", pressed, flush=True)
                seen.add(key)
        if listed and time.monotonic() > listed:
            listed = None
            everything = []
            for window in Desktop(backend="uia").windows(visible_only=True):
                try:
                    everything.append("%s [%s]" % (window.window_text(), window.class_name()))
                except Exception:
                    continue
            step("Fenster nach 20 s", fenster=everything)
        if process.poll() is not None and not any(True for _ in dialogs()):
            names = subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower()
            if "_iu" not in names and "unins" not in names:
                done = True
                break
        time.sleep(0.5)
    return {"exitcode_starter": process.poll(), "fertig": done}


def verdict(answer_data, state, finished):
    """Gibt die Abweichungen vom erwarteten Ergebnis zurück, leer, wenn alles stimmt."""
    problems = [] if finished["fertig"] else ["Deinstallation lief nach 15 Minuten noch"]
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
        while console_answers() is None and time.monotonic() - started < 300:
            time.sleep(3)
        (DATA / "marke.txt").write_text("Daten vor der Deinstallation\n", encoding="utf-8")
        (DATA / "desktop").mkdir(exist_ok=True)
        (DATA / "desktop" / "passwords.json").write_text('{"entries": [], "never": []}', encoding="utf-8")
        step("1 installiert", exitcode=code, konsole=console_answers(), **data_state())
        finished = uninstall(args.daten)
        state = data_state()
        step("2 deinstalliert", antwort_daten=args.daten, **finished, **state)
        report["abweichungen"] = verdict(args.daten, state, finished)
    finally:
        (work / "bericht.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for problem in report["abweichungen"]:
        print("FEHLER:", problem, flush=True)
    return 1 if report["abweichungen"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
