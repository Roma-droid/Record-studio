import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np
from datetime import datetime
import pyautogui
import cv2
from PIL import Image, ImageTk
import threading
import os
import time
import queue

class VoiceRecorder:
    def __init__(self, root):
        self.root = root
        self.root.title("Диктофон и Запись экрана")
        self.root.geometry("450x300")
        
        # Переменные состояния
        self.is_recording_audio = False
        self.is_recording_screen = False
        self.audio_data = queue.Queue()
        self.sample_rate = 44100
        self.video_writer = None
        self.screen_thread = None
        self.audio_thread = None
        self.audio_stream = None
        
        # Настройка интерфейса
        self.setup_ui()
        
    def setup_ui(self):
        # Выбор режима записи
        self.mode_label = ttk.Label(self.root, text="Выберите режим записи:", font=("Arial", 10, "bold"))
        self.mode_label.pack(pady=5)
        
        self.mode_var = tk.StringVar(value="voice")
        mode_frame = ttk.Frame(self.root)
        mode_frame.pack(pady=5)
        
        self.mode_voice = ttk.Radiobutton(mode_frame, text="Запись голоса", variable=self.mode_var, value="voice")
        self.mode_voice.pack(side=tk.LEFT, padx=10)
        self.mode_screen = ttk.Radiobutton(mode_frame, text="Запись экрана", variable=self.mode_var, value="screen")
        self.mode_screen.pack(side=tk.LEFT, padx=10)
        
        # Метка статуса
        self.status_label = ttk.Label(self.root, text="Готов к записи", font=("Arial", 9))
        self.status_label.pack(pady=10)
        
        # Кнопка записи
        self.record_button = ttk.Button(self.root, text="Начать запись", command=self.toggle_recording)
        self.record_button.pack(pady=5)
        
        # Кнопка выбора пути сохранения
        self.path_button = ttk.Button(self.root, text="Выбрать путь сохранения", command=self.select_save_path)
        self.path_button.pack(pady=5)
        
        # Текущий путь сохранения
        self.save_path = os.getcwd()
        self.path_label = ttk.Label(self.root, text=f"Путь: {self.save_path}", wraplength=400)
        self.path_label.pack(pady=5)
        
        # Информационная метка
        self.info_label = ttk.Label(self.root, text="Для остановки записи нажмите кнопку еще раз", 
                                   font=("Arial", 8), foreground="gray")
        self.info_label.pack(pady=5)
        
        # Кнопка выхода
        self.exit_button = ttk.Button(self.root, text="Выход", command=self.safe_exit)
        self.exit_button.pack(pady=5)
        
        # Обработка закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.safe_exit)
        
    def select_save_path(self):
        path = filedialog.askdirectory()
        if path:
            self.save_path = path
            self.path_label.config(text=f"Путь: {self.save_path}")
            
    def toggle_recording(self):
        if not self.is_recording_audio and not self.is_recording_screen:
            self.start_recording()
        else:
            self.stop_recording()
            
    def start_recording(self):
        mode = self.mode_var.get()
        
        if mode == "voice":
            self.start_voice_recording()
        else:
            self.start_screen_recording()
            
    def start_voice_recording(self):
        try:
            # Проверка доступности аудиоустройств
            devices = sd.query_devices()
            default_input = sd.default.device[0]
            
            self.is_recording_audio = True
            self.status_label.config(text="Идет запись голоса...")
            self.record_button.config(text="Остановить запись")
            
            # Очистить очередь данных
            while not self.audio_data.empty():
                self.audio_data.get_nowait()
                
            # Запись звука в отдельном потоке
            self.audio_thread = threading.Thread(target=self.record_audio)
            self.audio_thread.daemon = True
            self.audio_thread.start()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось начать запись голоса: {str(e)}")
            self.is_recording_audio = False
            self.status_label.config(text="Ошибка записи")
            self.record_button.config(text="Начать запись")
    
    def audio_callback(self, indata, frames, time, status):
        """Callback-функция для захвата аудиоданных"""
        if status:
            print(status)
        if self.is_recording_audio:
            self.audio_data.put(indata.copy())
    
    def record_audio(self):
        try:
            # Начать запись звука с использованием callback
            self.audio_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=2,
                callback=self.audio_callback,
                blocksize=1024
            )
            self.audio_stream.start()
            
            # Собираем данные пока идет запись
            recorded_data = []
            while self.is_recording_audio:
                # Собираем данные из очереди
                try:
                    while True:
                        data = self.audio_data.get_nowait()
                        recorded_data.append(data)
                except queue.Empty:
                    time.sleep(0.1)  # Небольшая пауза если очередь пуста
                    continue
            
            # После остановки собрать оставшиеся данные
            try:
                while True:
                    data = self.audio_data.get_nowait()
                    recorded_data.append(data)
            except queue.Empty:
                pass
                
            # Остановить и закрыть поток
            self.audio_stream.stop()
            self.audio_stream.close()
            self.audio_stream = None
            
            # Объединить все данные в один массив
            if recorded_data:
                audio_array = np.concatenate(recorded_data, axis=0)
                
                # Сохранить файл
                filename = os.path.join(self.save_path, f"voice_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.wav")
                write(filename, self.sample_rate, audio_array)
                
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка при записи аудио: {str(e)}"))
            if self.audio_stream:
                self.audio_stream.stop()
                self.audio_stream.close()
                self.audio_stream = None
        
    def start_screen_recording(self):
        self.is_recording_screen = True
        self.status_label.config(text="Идет запись экрана...")
        self.record_button.config(text="Остановить запись")
        
        # Запустить запись экрана в отдельном потоке
        self.screen_thread = threading.Thread(target=self.record_screen)
        self.screen_thread.daemon = True
        self.screen_thread.start()
        
    def record_screen(self):
        try:
            # Получить размер экрана
            screen_size = pyautogui.size()
            
            # Определить кодек и создать объект VideoWriter
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            filename = os.path.join(self.save_path, f"screen_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.avi")
            fps = 12.0
            
            self.video_writer = cv2.VideoWriter(filename, fourcc, fps, screen_size)
            
            while self.is_recording_screen:
                # Захватить скриншот
                img = pyautogui.screenshot()
                
                # Конвертировать в массив numpy
                frame = np.array(img)
                
                # Конвертировать RGB в BGR (OpenCV использует BGR)
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                # Записать кадр
                self.video_writer.write(frame)
                
                # Небольшая задержка для снижения нагрузки на CPU
                time.sleep(1.0 / fps)
                
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка при записи экрана: {str(e)}"))
        finally:
            # Освободить ресурсы
            if hasattr(self, 'video_writer') and self.video_writer is not None:
                self.video_writer.release()
                self.video_writer = None
            
    def stop_recording(self):
        mode = self.mode_var.get()
        
        if mode == "voice":
            self.stop_voice_recording()
        else:
            self.stop_screen_recording()
            
    def stop_voice_recording(self):
        self.is_recording_audio = False
        self.status_label.config(text="Запись голоса завершена")
        self.record_button.config(text="Начать запись")
        
        # Дождаться завершения потока записи аудио
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2.0)
        
    def stop_screen_recording(self):
        self.is_recording_screen = False
        self.status_label.config(text="Запись экрана завершена")
        self.record_button.config(text="Начать запись")
        
        # Дождаться завершения потока записи экрана
        if self.screen_thread and self.screen_thread.is_alive():
            self.screen_thread.join(timeout=2.0)
            
        # Освободить ресурсы VideoWriter
        if hasattr(self, 'video_writer') and self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None
    
    def safe_exit(self):
        # Остановить все записи перед выходом
        if self.is_recording_audio:
            self.stop_voice_recording()
        if self.is_recording_screen:
            self.stop_screen_recording()
            
        # Дать время для завершения потоков
        time.sleep(0.5)
        self.root.destroy()
        
if __name__ == "__main__":
    root = tk.Tk()
    app = VoiceRecorder(root)
    root.mainloop()