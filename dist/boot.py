#!/usr/bin/env python3
"""Lançador de um clique: cria a venv (se faltar), instala as dependências
(se faltar) e abre o app — sem terminal visível.

Uso pretendido no Windows: um atalho apontando pro pythonw.exe (do
sistema, na primeira vez) chamando este arquivo. pythonw.exe não tem
console nenhum — nem esse script nem o app que ele abre em seguida
mostram janela preta.

Se algo falhar (sem internet pra instalar dependências, por exemplo), o
erro cai em bootup.log ao lado deste arquivo — sem console, não tem outro
jeito de saber o que deu errado.
"""

import os
import subprocess
import sys
import traceback
from pathlib import Path

# Este arquivo mora em dist/ — a pasta real do projeto (venv, app.py,
# requirements.txt) é um nível acima.
BASE_DIR = Path(__file__).resolve().parent.parent
VENV_DIR = BASE_DIR / "venv"
LOG_FILE = Path(__file__).resolve().parent / "bootup.log"
IS_WINDOWS = os.name == "nt"


def _venv_python(pythonw=False):
    if IS_WINDOWS:
        name = "pythonw.exe" if pythonw else "python.exe"
        return VENV_DIR / "Scripts" / name
    return VENV_DIR / "bin" / "python"


def _log(message):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def ensure_venv():
    if _venv_python().exists():
        return
    _log("Criando ambiente virtual...")
    subprocess.run(
        [sys.executable, "-m", "venv", str(VENV_DIR)],
        check=True,
        cwd=BASE_DIR,
    )
    _log("Instalando dependências (requirements.txt)...")
    subprocess.run(
        [str(_venv_python()), "-m", "pip", "install", "-r", "requirements.txt"],
        check=True,
        cwd=BASE_DIR,
    )
    _log("Ambiente pronto.")


def launch_app():
    # pythonw.exe (Windows) não tem console de propósito — evita ter que
    # mexer com creationflags/CREATE_NO_WINDOW. No Linux não existe
    # equivalente (não precisa: o binário normal já não abre console
    # nenhum, isso é só um problema de terminal do Windows).
    python = _venv_python(pythonw=True) if IS_WINDOWS else _venv_python()
    kwargs = {"cwd": BASE_DIR}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([str(python), str(BASE_DIR / "app.py")], **kwargs)


if __name__ == "__main__":
    try:
        ensure_venv()
        launch_app()
    except Exception:
        _log("ERRO:\n" + traceback.format_exc())
