"""
LANZADOR: abre la plataforma como un programa de escritorio (ventana propia, sin navegador).
Por dentro arranca Streamlit en segundo plano y lo muestra en una ventana con pywebview.
"""
import os
import socket
import subprocess
import sys
import time
import webbrowser

CARPETA = os.path.dirname(os.path.abspath(__file__))
PUERTO = 8517
URL = f"http://localhost:{PUERTO}"


def puerto_listo(puerto, espera=40):
    inicio = time.time()
    while time.time() - inicio < espera:
        try:
            with socket.create_connection(("localhost", puerto), timeout=1):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def main():
    # En Windows, no mostrar la ventana negra de consola de Streamlit
    flags = 0x08000000 if os.name == "nt" else 0
    python = sys.executable.replace("pythonw.exe", "python.exe")
    log = open(os.path.join(CARPETA, "registro.txt"), "w", encoding="utf-8")
    servidor = subprocess.Popen(
        [python, "-m", "streamlit", "run", os.path.join(CARPETA, "app.py"),
         "--server.port", str(PUERTO), "--server.headless", "true"],
        cwd=CARPETA, stdout=log, stderr=log, creationflags=flags)

    try:
        if not puerto_listo(PUERTO):
            raise RuntimeError("Streamlit no arrancó. Revisa el archivo registro.txt")
        try:
            import webview
            webview.create_window("Integridad estructural · EH4000", URL,
                                  width=1400, height=900, min_size=(1000, 700))
            webview.start()          # se queda aquí hasta que cierres la ventana
        except Exception:
            # Si la ventana propia falla, se abre en el navegador como respaldo
            webbrowser.open(URL)
            servidor.wait()
    finally:
        servidor.terminate()
        log.close()


if __name__ == "__main__":
    main()
