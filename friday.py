import sys
import os
import json
import time
import queue
import random
import requests
import datetime
import webbrowser
import pyautogui
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen
import sounddevice as sd
import numpy as np
from vosk import Model, KaldiRecognizer
from gigachat import GigaChat
from gigachat.models import Chat, Messages
import pyttsx3


#Настройки

AUTH_DATA = "Вставьте сюда свой апи ключ гига чата"
CITY = "Kemerovo"
WAKE_WORD = "пятница"
VOSK_MODEL_PATH = "model"
SAMPLERATE = 16000


#Голос+ии

class FridayLogicThread(QThread):
    signal_status = pyqtSignal(str)     
    signal_text_out = pyqtSignal(str)   
    signal_command_out = pyqtSignal(str) 

    def __init__(self):
        super().__init__()
        self.q = queue.Queue()
        self.history = []
        
        if not os.path.exists(VOSK_MODEL_PATH):
            print("Ошибка: Папка 'model' не найдена!")
            return

        self.model_vosk = Model(VOSK_MODEL_PATH)
        self.rec = KaldiRecognizer(self.model_vosk, SAMPLERATE)
        
        try:
            self.tts_engine = pyttsx3.init()
            voices = self.tts_engine.getProperty('voices')
            self.tts_engine.setProperty('voice', voices[0].id)
            self.tts_engine.setProperty('rate', 190)
        except: 
            self.tts_engine = None

    def say(self, text):
        #Отображаем текст в интерфейсе
        self.signal_text_out.emit(text)
        self.signal_status.emit('speaking')
        print(f"Пятница: {text}")
        
        try:
            #Инициализируем движок
            engine = pyttsx3.init('sapi5')
            voices = engine.getProperty('voices')
            
            #Настройка женского голоса
            
            female_voice_id = None
            for v in voices:
                if "Irina" in v.name or "Elena" in v.name or "Female" in v.name:
                    female_voice_id = v.id
                    break
            
            #Если не будет найден женский голос ставится первый попавшийся
            if female_voice_id:
                engine.setProperty('voice', female_voice_id)
            else:
                engine.setProperty('voice', voices[0].id)
            
            #Параметры голоса
            engine.setProperty('rate', 175)
            engine.setProperty('volume', 1.0) #Громкость на максимум
            
            #Произносим фразу
            engine.say(text)
            engine.runAndWait()
            
            engine.stop()
            del engine 
            
        except Exception as e:
            print(f"Ошибка голосового модуля: {e}")
            
        self.signal_status.emit('idle')

    def ask_gigachat(self, prompt):
        self.signal_status.emit('thinking')
        try:
            with GigaChat(credentials=AUTH_DATA, verify_ssl_certs=False) as giga:
                system_msg = Messages(role="system", content="Ты — Пятница, ИИ Тони Старка. Отвечай кратко.")
                msgs = [system_msg] + [Messages(role=h["role"], content=h["content"]) for h in self.history] + [Messages(role="user", content=prompt)]
                response = giga.chat(Chat(messages=msgs, model="GigaChat"))
                content = response.choices[0].message.content
                
                self.history.append({"role": "user", "content": prompt})
                self.history.append({"role": "assistant", "content": content})
                if len(self.history) > 6: self.history.pop(0)
                return content
        except Exception as e:
            return f"Ошибка связи: {e}"

    def get_weather(self):
        try:
            res = requests.get(f"https://wttr.in/{CITY}?format=%t+и+%C", timeout=5)
            return res.text
        except: 
            return "недоступна"

    def callback_audio(self, indata, frames, time, status):
        self.q.put(bytes(indata))

    def run(self):
        device = sd.default.device[0]
        self.signal_status.emit('idle')
        
        with sd.RawInputStream(samplerate=SAMPLERATE, blocksize=8000, device=device, dtype='int16',
                                channels=1, callback=self.callback_audio):
            while True:
                data = self.q.get()
                if self.rec.AcceptWaveform(data):
                    result = json.loads(self.rec.Result())
                    text = result.get("text", "")

                    if WAKE_WORD in text:
                        self.say("Да, сэр?")
                        self.signal_status.emit('listening')
                        
                        start_time = time.time()
                        command_found = False
                        
                        while time.time() - start_time < 7:
                            data_cmd = self.q.get()
                            if self.rec.AcceptWaveform(data_cmd):
                                res_cmd = json.loads(self.rec.Result())
                                command = res_cmd.get("text", "").lower()
                                
                                if command:
                                    self.signal_command_out.emit(command)
                                    if "время" in command:
                                        self.say(f"На часах 3 {datetime.datetime.now().strftime('%H:%M')}")
                                    elif "погода" in command:
                                        self.say(f"В Кемерово {self.get_weather()}")
                                    elif "скриншот" in command:
                                        pyautogui.screenshot(f"shot_{int(time.time())}.png")
                                        self.say("Уже в папке.")
                                    elif "открой" in command:
                                        if "ютуб" in command: 
                                            webbrowser.open("https://youtube.com")
                                            self.say("Открываю")
                                        if "музыку" in command: 
                                            webbrowser.open("https://soundcloud.com")
                                            self.say("Сново грнаж? Может что то новенькое?")
                                    elif "стоп" in command or "выход" in command:
                                        self.say("До связи.")
                                        QApplication.quit()
                                        return
                                    else:
                                        answer = self.ask_gigachat(command)
                                        self.say(answer)
                                    
                                    command_found = True
                                    self.signal_status.emit('idle')
                                    break
                        
                        if not command_found:
                            self.signal_status.emit('idle')


#Интерфейс

class ReactorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(100, 100)
        self.status = 'idle'
        self.angle = 0
        self.alpha = 150
        self.pulse_dir = 1
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(20)

    def set_status(self, status):
        self.status = status
        self.update()

    def animate(self):
        self.angle = (self.angle + 5) % 360
        if self.status == 'idle':
            self.alpha += self.pulse_dir * 5
            if self.alpha >= 200 or self.alpha <= 100: self.pulse_dir *= -1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() // 2, self.height() // 2
        radius = 35
        color = QColor(0, 255, 255, self.alpha)
        
        if self.status == 'idle':
            painter.setPen(QPen(color, 2))
            painter.setBrush(QColor(0, 255, 255, 30))
            painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        elif self.status == 'listening':
            painter.setPen(QPen(QColor(0, 255, 255), 4))
            painter.drawArc(cx-radius, cy-radius, radius*2, radius*2, self.angle*16, 150*16)
        elif self.status == 'thinking':
            painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.PenStyle.DotLine))
            painter.drawEllipse(cx-radius, cy-radius, radius*2, radius*2)
        elif self.status == 'speaking':
            painter.setPen(QPen(QColor(0, 255, 255), 3))
            for i in range(5):
                h = random.randint(10, 35)
                painter.drawLine(cx-20+i*10, cy-h//2, cx-20+i*10, cy+h//2)

class FridayUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(300, 200)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 320, screen.height() - 250)
        
        layout = QVBoxLayout()
        self.reactor = ReactorWidget()
        layout.addWidget(self.reactor, 0, Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_command = QLabel("")
        self.lbl_command.setStyleSheet("color: rgba(0, 255, 255, 180); font-size: 11px;")
        layout.addWidget(self.lbl_command, 0, Qt.AlignmentFlag.AlignCenter)

        self.lbl_response = QLabel("Системы активны")
        self.lbl_response.setStyleSheet("color: cyan; font-size: 14px; font-weight: bold; padding: 5px;")
        self.lbl_response.setWordWrap(True)
        layout.addWidget(self.lbl_response, 0, Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)

    def update_text(self, text):
        self.lbl_response.setText(text)
        self.lbl_command.setText("")

    def update_command(self, text):
        self.lbl_command.setText(f"Сэр: {text}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ui = FridayUI()
    ui.show()
    logic = FridayLogicThread()
    logic.signal_status.connect(ui.reactor.set_status)
    logic.signal_text_out.connect(ui.update_text)
    logic.signal_command_out.connect(ui.update_command)
    logic.start()
    sys.exit(app.exec())