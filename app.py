"""
Dashboard monitoring suhu + cahaya + kontrol LED (versi web).

Logika MQTT-nya sama persis dengan versi Tkinter, hanya tampilannya
dipindah ke browser. Jalankan file ini, lalu buka http://127.0.0.1:5000

Kebutuhan:
    pip install flask paho-mqtt pandas openpyxl
"""

import datetime
import io
import json
import threading

import pandas as pd
import paho.mqtt.client as mqtt
import requests
from flask import Flask, jsonify, render_template, request, send_file

# --- Konfigurasi MQTT
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_SENSOR_TOPIC = "kelompok01_IF_IoT/datasensor"
MQTT_LED_TOPIC = "kelompok01_IF_IoT/led"

# --- Konfigurasi Telegram
# Buat bot lewat @BotFather di Telegram untuk dapat TOKEN.
# Untuk CHAT_ID: chat dulu bot-nya sekali, lalu buka
# https://api.telegram.org/bot<TOKEN>/getUpdates di browser dan cari "chat":{"id":...}
TELEGRAM_BOT_TOKEN = "8902137622:AAHqNaDQCAwdEoFoGuekFeYWGcBvnvINARA"
TELEGRAM_CHAT_ID = "7346607258"

# --- Penyimpanan data (dipakai bersama thread MQTT dan thread web)
lock = threading.Lock()
time_data = []
temp_data = []
light_data = []

collecting = False
led_state = "0"
mqtt_connected = False
session_id = 1  # naik tiap reset, supaya browser tahu harus menggambar ulang


# --- MQTT
def on_connect(client, userdata, flags, reason_code, properties=None):
    global mqtt_connected
    if reason_code.is_failure:
        mqtt_connected = False
        print(f"MQTT gagal terhubung: {reason_code}")
        return
    mqtt_connected = True
    result = client.subscribe(MQTT_SENSOR_TOPIC)
    if result[0] != mqtt.MQTT_ERR_SUCCESS:
        print(f"Gagal subscribe sensor: {mqtt.error_string(result[0])}")
    else:
        print(f"Terhubung ke broker, subscribe {MQTT_SENSOR_TOPIC}")


def on_disconnect(client, userdata, flags, reason_code, properties=None):
    global mqtt_connected
    mqtt_connected = False
    print(f"MQTT terputus: {reason_code}")


def on_message(client, userdata, msg):
    if msg.topic != MQTT_SENSOR_TOPIC or not collecting:
        return
    try:
        payload = json.loads(msg.payload.decode())
        with lock:
            time_data.append(float(payload["time"]))
            temp_data.append(float(payload["temp"]))
            light_data.append(int(payload["light"]))
    except Exception as e:
        print("X Error:", e)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()


# --- Web
app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/data")
def api_data():
    """Kirim hanya data baru sejak indeks `since` supaya ringan."""
    try:
        since = max(0, int(request.args.get("since", 0)))
    except ValueError:
        since = 0

    with lock:
        total = len(time_data)
        if since > total:  # browser ketinggalan / data sudah direset
            since = 0
        chunk = {
            "start": since,
            "time": time_data[since:],
            "temp": temp_data[since:],
            "light": light_data[since:],
            "total": total,
            "latest": {
                "time": time_data[-1] if total else None,
                "temp": temp_data[-1] if total else None,
                "light": light_data[-1] if total else None,
            },
        }

    chunk.update(
        {
            "session": session_id,
            "collecting": collecting,
            "connected": client.is_connected() and mqtt_connected,
            "led": led_state,
        }
    )
    return jsonify(chunk)


@app.post("/api/collect")
def api_collect():
    """Mulai / berhenti merekam data."""
    global collecting
    collecting = bool(request.json.get("active"))
    return jsonify({"collecting": collecting})


@app.post("/api/reset")
def api_reset():
    global session_id
    with lock:
        time_data.clear()
        temp_data.clear()
        light_data.clear()
        session_id += 1
    return jsonify({"session": session_id})


@app.post("/api/led")
def api_led():
    global led_state
    value = "1" if str(request.json.get("value")) == "1" else "0"

    if not client.is_connected():
        return jsonify({"ok": False, "message": "MQTT belum terhubung"}), 503

    result = client.publish(MQTT_LED_TOPIC, value, qos=1)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        return jsonify({"ok": False, "message": mqtt.error_string(result.rc)}), 502

    result.wait_for_publish(timeout=2)
    led_state = value
    label = "menyala" if value == "1" else "mati"
    print(f"Perintah LED ({label}) terkirim")
    return jsonify({"ok": True, "led": led_state, "message": f"LED {label}"})


def send_telegram(pesan):
    """Kirim satu pesan teks ke chat Telegram yang sudah dikonfigurasi."""
    if "GANTI_DENGAN" in TELEGRAM_BOT_TOKEN or "GANTI_DENGAN" in TELEGRAM_CHAT_ID:
        return False, "Token/Chat ID Telegram belum diisi di app.py"

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url, data={"chat_id": TELEGRAM_CHAT_ID, "text": pesan}, timeout=5
        )
        if r.status_code == 200 and r.json().get("ok"):
            return True, "Notifikasi terkirim ke Telegram"
        return False, f"Gagal kirim: {r.text}"
    except requests.RequestException as e:
        return False, f"Gagal kirim: {e}"


@app.post("/api/telegram")
def api_telegram():
    with lock:
        suhu_terakhir = temp_data[-1] if temp_data else None
        cahaya_terakhir = light_data[-1] if light_data else None

    if suhu_terakhir is None:
        return jsonify({"ok": False, "message": "Belum ada data untuk dikirim"}), 400

    pesan = (
        "Sistem Monitoring:\n"
        f"Suhu terakhir tercatat {suhu_terakhir:.1f} °C\n"
        f"Cahaya terakhir tercatat {cahaya_terakhir} ADC"
    )
    ok, keterangan = send_telegram(pesan)
    status = 200 if ok else 502
    return jsonify({"ok": ok, "message": keterangan}), status


@app.get("/api/export")
def api_export():
    """Unduh data sebagai file Excel, sama seperti tombol Simpan Excel."""
    with lock:
        waktu_format = [str(datetime.timedelta(seconds=int(t))) for t in time_data]
        df = pd.DataFrame(
            {
                "Time (HH:MM:SS)": waktu_format,
                "Temperature (C)": list(temp_data),
                "Light (ADC)": list(light_data),
            }
        )

    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"data_sensor_{stamp}.xlsx",
    )


if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    finally:
        client.loop_stop()
        client.disconnect()