import tkinter as tk
from tkinter import filedialog
import paho.mqtt.client as mqtt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import pandas as pd
import datetime
import json

MQTT_SENSOR_TOPIC = "kelompok01_IF_IoT/datasensor"
MQTT_LED_TOPIC = "kelompok01_IF_IoT/led"

#--- Data Storage
time_data = []
temp_data = []
light_data = []
collecting = False

#--- MQTT Setup
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code.is_failure:
        print(f"MQTT gagal terhubung: {reason_code}")
        return
    result = client.subscribe(MQTT_SENSOR_TOPIC)
    if result[0] != mqtt.MQTT_ERR_SUCCESS:
        print(f"Gagal subscribe sensor: {mqtt.error_string(result[0])}")

def on_message(client, userdata, msg):
    if msg.topic == MQTT_SENSOR_TOPIC and collecting:
        try:
            payload = json.loads(msg.payload.decode())
            time_data.append(float(payload["time"]))
            temp_data.append(float(payload["temp"]))
            light_data.append(int(payload["light"]))
        except Exception as e:
            print("X Error:", e)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect("broker.hivemq.com", 1883, 60)
client.loop_start()

#--- GUI Setup
root = tk.Tk()
root.title("Monitoring Suhu + Cahaya + Kontrol LED")
root.geometry("1100x780")

frame = tk.Frame(root)
frame.pack(pady=10)

btn_font = ("Arial", 12)
tk.Button(frame, text="Start", font=btn_font, width=12, command=lambda: set_collecting(True)).grid(row=0, column=0, padx=5)
tk.Button(frame, text="Stop", font=btn_font, width=12, command=lambda: set_collecting(False)).grid(row=0, column=1, padx=5)
tk.Button(frame, text="Reset", font=btn_font, width=12, command=lambda: reset_data()).grid(row=0, column=2, padx=5)
tk.Button(frame, text="Simpan Excel", font=btn_font, width=12, command=lambda: save_excel()).grid(row=0, column=3, padx=5)
tk.Button(frame, text="Close", font=btn_font, width=12, command=lambda: close_app()).grid(row=0, column=4, padx=5)

led_frame = tk.LabelFrame(root, text="Kontrol LED", font=btn_font, padx=20, pady=10)
led_frame.pack(pady=10)

tk.Button(led_frame, text="LED ON", font=btn_font, width=15, bg="green", fg="white", command=lambda: control_led("1")).pack(side=tk.LEFT, padx=20)
tk.Button(led_frame, text="LED OFF", font=btn_font, width=15, bg="red", fg="white", command=lambda: control_led("0")).pack(side=tk.LEFT, padx=20)

#--- Grafik Matplotlib
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))
fig.subplots_adjust(hspace=0.8)
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(pady=10, fill="both", expand=True)

def update_plot(frame):
    ax1.clear()
    ax2.clear()
    if time_data:
        ax1.plot(time_data, temp_data, color='blue', marker='o')
        ax1.set_title("Suhu terhadap Waktu")
        ax1.set_ylabel("Suhu (°C)")
        ax1.grid(True)
        
        ax2.plot(time_data, light_data, color='orange', marker='x')
        ax2.set_title("Cahaya terhadap Waktu")
        ax2.set_ylabel("ADC Cahaya")
        ax2.set_xlabel("Waktu (detik)")
        ax2.grid(True)
    canvas.draw()

ani = FuncAnimation(fig, update_plot, interval=1000, cache_frame_data=False)

#--- Control Functions
def set_collecting(state):
    global collecting
    collecting = state

def reset_data():
    time_data.clear()
    temp_data.clear()
    light_data.clear()

def save_excel():
    filename = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel Files", "*.xlsx")])
    if filename:
        waktu_format = [str(datetime.timedelta(seconds=int(t))) for t in time_data]
        df = pd.DataFrame({
            "Time (HH:MM:SS)": waktu_format,
            "Temperature (C)": temp_data,
            "Light (ADC)": light_data
        })
        df.to_excel(filename, index=False, engine='openpyxl')

def control_led(value):
    if not client.is_connected():
        print("MQTT belum terhubung; perintah LED tidak dikirim")
        return
    result = client.publish(MQTT_LED_TOPIC, value, qos=1)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        print(f"Gagal mengirim perintah LED: {mqtt.error_string(result.rc)}")
    else:
        result.wait_for_publish(timeout=2)
        print(f"Perintah LED ({'ON' if value == '1' else 'OFF'}) terkirim")

def close_app():
    ani.event_source.stop()
    if canvas._idle_draw_id:
        canvas._tkcanvas.after_cancel(canvas._idle_draw_id)
        canvas._idle_draw_id = None
    client.loop_stop()
    client.disconnect()
    plt.close(fig)
    root.quit()
    root.destroy()

#--- Start GUI
root.protocol("WM_DELETE_WINDOW", close_app)
root.mainloop()
