import pyttsx3
engine = pyttsx3.init()
voices = engine.getProperty('voices')

for index, voice in enumerate(voices):
    # Выведет список: 0 - Ирина, 1 - Павел и т.д.
    print(f"Индекс: {index} | Имя: {voice.name}")