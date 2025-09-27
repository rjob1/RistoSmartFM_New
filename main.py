import os
import webview
from threading import Thread
from flask import Flask

os.environ["FLASK_SECRET_KEY"] = "la_tua_chiave_segreta"
os.environ["DB_PATH"] = os.path.join(os.getenv("APPDATA"), "RistoSmartFM", "ristosmart.db")

def run_flask():
    from app import app
    app.run(host='127.0.0.1', port=5000, threaded=True, use_reloader=False)

def start_app():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    window = webview.create_window(
        title="RistoSmart FM",
        url="http://127.0.0.1:5000",
        width=1200,
        height=800,
        resizable=True,
        confirm_close=True
    )
    webview.start()

if __name__ == '__main__':
    start_app()