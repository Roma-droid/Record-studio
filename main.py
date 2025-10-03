import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser
import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np
from datetime import datetime
import pyautogui
import cv2
from PIL import Image, ImageTk, ImageDraw, ImageFont
import threading
import os
import time
import queue
import json
import copy
import argparse
import re
import mss
import mss.tools
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
except ImportError:
    AudioUtilities = None
    IAudioEndpointVolume = None

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Глобальная блокировка для потокобезопасной работы с MSS
mss_lock = threading.Lock()

class TextObject:
    """Класс для представления текстового объекта"""
    def __init__(self, text="Новый текст", x=100, y=100, font_size=24, 
                 font_color="#FFFFFF", font_family="Arial", 
                 background_color=None, background_alpha=0):
        self.text = text
        self.x = x
        self.y = y
        self.font_size = font_size
        self.font_color = font_color
        self.font_family = font_family
        self.background_color = background_color
        self.background_alpha = background_alpha
        self.visible = True
        self.scale = 1.0
        
    def to_dict(self):
        return {
            'text': self.text, 'x': self.x, 'y': self.y, 'font_size': self.font_size,
            'font_color': self.font_color, 'font_family': self.font_family,
            'background_color': self.background_color, 'background_alpha': self.background_alpha,
            'visible': self.visible, 'scale': self.scale
        }
        
    @classmethod
    def from_dict(cls, data):
        text_obj = cls(
            text=data.get('text', 'Новый текст'), x=data.get('x', 100), y=data.get('y', 100),
            font_size=data.get('font_size', 24), font_color=data.get('font_color', '#FFFFFF'),
            font_family=data.get('font_family', 'Arial'), background_color=data.get('background_color'),
            background_alpha=data.get('background_alpha', 0)
        )
        text_obj.visible = data.get('visible', True)
        text_obj.scale = data.get('scale', 1.0)
        return text_obj

class Scene:
    """Класс для представления сцены с настройками"""
    def __init__(self, name="Новая сцена"):
        self.name = name
        self.video_sources = {"full_screen": True, "window": False, "camera": False}
        self.selected_window = None
        self.audio_enabled = True
        self.window_info = "Окно не выбрано"
        self.camera_index = 0
        self.camera_resolution = "640x480"
        self.layout = "single"
        self.text_objects = []
        self.camera_scale = 1.0
        self.camera_offset_x = 0
        self.camera_offset_y = 0
        self.screen_scale = 1.0
        self.screen_offset_x = 0
        self.screen_offset_y = 0
        self.window_scale = 1.0
        self.window_offset_x = 0
        self.window_offset_y = 0
        self.window_rect = None  # Добавляем для хранения координат окна
        
    def to_dict(self):
        return {
            'name': self.name, 'video_sources': self.video_sources, 'audio_enabled': self.audio_enabled,
            'window_info': self.window_info, 'camera_index': self.camera_index, 
            'camera_resolution': self.camera_resolution, 'layout': self.layout,
            'text_objects': [text_obj.to_dict() for text_obj in self.text_objects],
            'camera_scale': self.camera_scale, 'camera_offset_x': self.camera_offset_x, 
            'camera_offset_y': self.camera_offset_y, 'screen_scale': self.screen_scale,
            'screen_offset_x': self.screen_offset_x, 'screen_offset_y': self.screen_offset_y,
            'window_scale': self.window_scale, 'window_offset_x': self.window_offset_x, 
            'window_offset_y': self.window_offset_y, 'window_rect': self.window_rect
        }
        
    @classmethod
    def from_dict(cls, data):
        scene = cls(data['name'])
        scene.video_sources = data.get('video_sources', {"full_screen": True, "window": False, "camera": False})
        scene.audio_enabled = data.get('audio_enabled', True)
        scene.window_info = data.get('window_info', "Окно не выбрано")
        scene.camera_index = data.get('camera_index', 0)
        scene.camera_resolution = data.get('camera_resolution', '640x480')
        scene.layout = data.get('layout', 'single')
        scene.text_objects = [TextObject.from_dict(text_data) for text_data in data.get('text_objects', [])]
        scene.camera_scale = data.get('camera_scale', 1.0)
        scene.camera_offset_x = data.get('camera_offset_x', 0)
        scene.camera_offset_y = data.get('camera_offset_y', 0)
        scene.screen_scale = data.get('screen_scale', 1.0)
        scene.screen_offset_x = data.get('screen_offset_x', 0)
        scene.screen_offset_y = data.get('screen_offset_y', 0)
        scene.window_scale = data.get('window_scale', 1.0)
        scene.window_offset_x = data.get('window_offset_x', 0)
        scene.window_offset_y = data.get('window_offset_y', 0)
        scene.window_rect = data.get('window_rect', None)
        return scene

class ModernButton(ttk.Frame):
    """Современная кнопка с иконкой и текстом"""
    def __init__(self, parent, text, command, icon=None, width=120, height=30, style="Modern.TButton"):
        super().__init__(parent, width=width, height=height)
        self.pack_propagate(False)
        self.command = command
        self.style = style
        
        s = ttk.Style()
        s.configure(style, background="#3498db", foreground="white", borderwidth=0, focuscolor="none")
        s.map(style, background=[('active', '#2980b9')])
        
        self.button = ttk.Button(self, text=text, command=self._on_click, style=style, width=width//8)
        self.button.pack(fill=tk.BOTH, expand=True)
        self.bind("<Button-1>", self._on_click)
        for child in self.winfo_children():
            child.bind("<Button-1>", self._on_click)
    
    def _on_click(self, event=None):
        self.command()

class RecordStudio:
    def __init__(self, root):
        self.root = root
        self.root.title("Record Studio Pro")
        
        parser = argparse.ArgumentParser(description='Record Studio Pro - программа для записи экрана')
        parser.add_argument('-f', '--fullscreen', action='store_true', help='Запуск в полноэкранном режиме')
        args, _ = parser.parse_known_args()
        
        self.fullscreen_mode = args.fullscreen
        if self.fullscreen_mode:
            self.root.after(100, self.enter_fullscreen)
        else:
            self.root.geometry("1300x800")
            
        self.root.configure(bg='#1a1a1a')
        self.root.minsize(1100, 700)
        
        self.setup_styles()
        
        self.is_recording = False
        self.is_paused = False
        self.scenes = []
        self.current_scene_index = 0
        self.selected_window = None
        self.windows_list = []
        self.audio_data = queue.Queue()
        self.sample_rate = 44100
        self.video_writer = None
        self.recording_thread = None
        self.audio_stream = None
        self.recording_start_time = None
        self.pause_start_time = None
        self.total_paused_time = 0
        self.recording_timer = None
        self.preview_timer = None
        self.camera = None
        self.available_cameras = self.get_available_cameras()
        self.selected_text_index = -1
        
        # Инициализация MSS и многопоточных компонентов
        self.sct = None
        self.monitor = None
        self.preview_queue = queue.Queue(maxsize=1)
        self.preview_thread = None
        self.preview_running = True
        
        self.sections_expanded = {'sources': True, 'scenes': True, 'text': True, 'transform': True}
        self.control_window = None
        self.hotkeys = {'start_recording': 'Ctrl+R', 'stop_recording': 'Ctrl+S', 'toggle_pause': 'Ctrl+P', 'toggle_fullscreen': 'F11'}
        self.dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.current_drag_type = None
        self.selected_transform_index = 0
        
        self.load_settings()
        if not os.path.exists(self.save_path):
            os.makedirs(self.save_path)
            
        self.load_scenes()
        if not self.scenes:
            self.scenes.append(Scene("Основная сцена"))
        
        self.setup_ui()
        self.setup_hotkeys()
        self.start_preview_thread()
        
    def start_preview_thread(self):
        """Запускает поток для захвата предпросмотра"""
        self.preview_running = True
        self.preview_thread = threading.Thread(target=self.preview_worker, daemon=True)
        self.preview_thread.start()
        self.update_preview()
        
    def stop_preview_thread(self):
        """Останавливает поток предпросмотра"""
        self.preview_running = False
        if self.preview_timer:
            self.root.after_cancel(self.preview_timer)
            self.preview_timer = None
        
        if self.preview_thread and self.preview_thread.is_alive():
            self.preview_thread.join(timeout=2.0)
        
    def preview_worker(self):
        """Рабочая функция для потока предпросмотра"""
        # Создаем отдельный экземпляр MSS для этого потока
        thread_sct = None
        try:
            thread_sct = mss.mss()
            monitor = thread_sct.monitors[1]
        except Exception as e:
            print(f"Ошибка инициализации MSS в потоке предпросмотра: {e}")
            return
            
        while self.preview_running:
            try:
                if not self.preview_running:
                    break
                    
                preview_frame = self.capture_preview_frame(thread_sct, monitor)
                if preview_frame is not None:
                    if self.preview_queue.full():
                        try:
                            self.preview_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self.preview_queue.put(preview_frame)
                time.sleep(0.033)  # ~30 FPS
            except Exception as e:
                print(f"Ошибка в потоке предпросмотра: {e}")
                time.sleep(0.1)
        
        # Закрываем MSS для этого потока
        if thread_sct is not None:
            try:
                thread_sct.close()
            except:
                pass
    
    def capture_preview_frame(self, sct, monitor):
        """Захватывает кадр для предпросмотра (вызывается из потока)"""
        try:
            scene = self.scenes[self.current_scene_index]
            preview_image = None
            
            # Определяем активный источник видео
            active_source = None
            if scene.video_sources["full_screen"]:
                active_source = "full_screen"
            elif scene.video_sources["window"] and scene.window_rect:
                active_source = "window"
            elif scene.video_sources["camera"]:
                active_source = "camera"
            
            if active_source == "full_screen" and sct is not None:
                try:
                    screenshot = sct.grab(monitor)
                    img = np.array(screenshot)
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    preview_image = img
                    
                    # Применяем трансформации для экрана
                    if scene.screen_scale != 1.0 or scene.screen_offset_x != 0 or scene.screen_offset_y != 0:
                        h, w = preview_image.shape[:2]
                        new_w = int(w * scene.screen_scale)
                        new_h = int(h * scene.screen_scale)
                        preview_image = cv2.resize(preview_image, (new_w, new_h))
                        background = np.zeros((h, w, 3), dtype=np.uint8)
                        x = max(0, min(w - new_w, scene.screen_offset_x))
                        y = max(0, min(h - new_h, scene.screen_offset_y))
                        if y + new_h <= h and x + new_w <= w:
                            background[y:y+new_h, x:x+new_w] = preview_image
                        preview_image = background
                        
                except Exception as e:
                    print(f"Ошибка захвата экрана в предпросмотре: {e}")
                    preview_image = np.zeros((480, 640, 3), dtype=np.uint8)
                    
            elif active_source == "window" and scene.window_rect:
                try:
                    # Захватываем область окна
                    left, top, right, bottom = scene.window_rect
                    width = right - left
                    height = bottom - top
                    
                    if width > 0 and height > 0:
                        # Создаем область для захвата
                        capture_area = {
                            "left": max(0, left),
                            "top": max(0, top),
                            "width": min(width, 3840),  # Ограничиваем максимальный размер
                            "height": min(height, 2160)
                        }
                        
                        screenshot = sct.grab(capture_area)
                        img = np.array(screenshot)
                        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                        preview_image = img
                        
                        # Применяем трансформации для окна
                        if scene.window_scale != 1.0 or scene.window_offset_x != 0 or scene.window_offset_y != 0:
                            h, w = preview_image.shape[:2]
                            new_w = int(w * scene.window_scale)
                            new_h = int(h * scene.window_scale)
                            preview_image = cv2.resize(preview_image, (new_w, new_h))
                            background = np.zeros((480, 640, 3), dtype=np.uint8)
                            x = max(0, min(640 - new_w, 320 - new_w//2 + scene.window_offset_x))
                            y = max(0, min(480 - new_h, 240 - new_h//2 + scene.window_offset_y))
                            if y + new_h <= 480 and x + new_w <= 640:
                                background[y:y+new_h, x:x+new_w] = preview_image
                            preview_image = background
                    else:
                        preview_image = np.zeros((480, 640, 3), dtype=np.uint8)
                        cv2.putText(preview_image, "Неверные размеры окна", (50, 50), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                        
                except Exception as e:
                    print(f"Ошибка захвата окна в предпросмотре: {e}")
                    preview_image = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(preview_image, "Ошибка захвата окна", (50, 50), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    
            elif active_source == "camera":
                try:
                    preview_image = self.capture_camera()
                    if scene.camera_scale != 1.0 or scene.camera_offset_x != 0 or scene.camera_offset_y != 0:
                        h, w = preview_image.shape[:2]
                        new_w = int(w * scene.camera_scale)
                        new_h = int(h * scene.camera_scale)
                        preview_image = cv2.resize(preview_image, (new_w, new_h))
                        background = np.zeros((480, 640, 3), dtype=np.uint8)
                        x = max(0, min(640 - new_w, 320 - new_w//2 + scene.camera_offset_x))
                        y = max(0, min(480 - new_h, 240 - new_h//2 + scene.camera_offset_y))
                        if y + new_h <= 480 and x + new_w <= 640:
                            background[y:y+new_h, x:x+new_w] = preview_image
                        preview_image = background
                except Exception as e:
                    print(f"Ошибка захвата камеры в предпросмотре: {e}")
                    preview_image = np.zeros((480, 640, 3), dtype=np.uint8)
            else:
                preview_image = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(preview_image, "Выберите источник видео", (50, 50), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            if preview_image is not None:
                preview_image = cv2.resize(preview_image, (640, 480))
                preview_image = self.apply_text_overlays(preview_image, scene.text_objects)
                
                if self.is_recording:
                    cv2.putText(preview_image, "REC", (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    if self.is_paused:
                        cv2.putText(preview_image, "PAUSED", (10, 60), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                
                return preview_image
                
        except Exception as e:
            print(f"Общая ошибка захвата предпросмотра: {e}")
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def update_preview(self):
        """Обновляет предпросмотр в основном потоке Tkinter"""
        try:
            if not self.preview_queue.empty():
                preview_image = self.preview_queue.get_nowait()
                preview_image = cv2.cvtColor(preview_image, cv2.COLOR_BGR2RGB)
                preview_image = Image.fromarray(preview_image)
                preview_image = ImageTk.PhotoImage(preview_image)
                self.preview_label.config(image=preview_image)
                self.preview_label.image = preview_image
            else:
                self.preview_label.config(text="Загрузка предпросмотра...", foreground="#666", background="#000")
            
        except Exception as e:
            print(f"Ошибка обновления предпросмотра: {e}")
            self.preview_label.config(text=f"Ошибка предпросмотра: {str(e)}", foreground="red", background="black")
        
        if self.preview_running:
            self.preview_timer = self.root.after(50, self.update_preview)

    def capture_screen(self):
        """Захватывает экран или окно для записи"""
        try:
            scene = self.scenes[self.current_scene_index]
            
            # Определяем активный источник видео
            active_source = None
            if scene.video_sources["full_screen"]:
                active_source = "full_screen"
            elif scene.video_sources["window"] and scene.window_rect:
                active_source = "window"
            elif scene.video_sources["camera"]:
                active_source = "camera"
            
            if active_source == "full_screen":
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    screenshot = sct.grab(monitor)
                    img = np.array(screenshot)
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    
                    # Применяем трансформации для экрана
                    if scene.screen_scale != 1.0 or scene.screen_offset_x != 0 or scene.screen_offset_y != 0:
                        h, w = img.shape[:2]
                        new_w = int(w * scene.screen_scale)
                        new_h = int(h * scene.screen_scale)
                        img = cv2.resize(img, (new_w, new_h))
                        background = np.zeros((h, w, 3), dtype=np.uint8)
                        x = max(0, min(w - new_w, scene.screen_offset_x))
                        y = max(0, min(h - new_h, scene.screen_offset_y))
                        if y + new_h <= h and x + new_w <= w:
                            background[y:y+new_h, x:x+new_w] = img
                        img = background
                    
                    return img
                    
            elif active_source == "window" and scene.window_rect:
                with mss.mss() as sct:
                    left, top, right, bottom = scene.window_rect
                    width = right - left
                    height = bottom - top
                    
                    if width > 0 and height > 0:
                        capture_area = {
                            "left": max(0, left),
                            "top": max(0, top),
                            "width": min(width, 3840),
                            "height": min(height, 2160)
                        }
                        
                        screenshot = sct.grab(capture_area)
                        img = np.array(screenshot)
                        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                        
                        # Применяем трансформации для окна
                        if scene.window_scale != 1.0 or scene.window_offset_x != 0 or scene.window_offset_y != 0:
                            h, w = img.shape[:2]
                            new_w = int(w * scene.window_scale)
                            new_h = int(h * scene.window_scale)
                            img = cv2.resize(img, (new_w, new_h))
                            background = np.zeros((1080, 1920, 3), dtype=np.uint8)
                            x = max(0, min(1920 - new_w, 960 - new_w//2 + scene.window_offset_x))
                            y = max(0, min(1080 - new_h, 540 - new_h//2 + scene.window_offset_y))
                            if y + new_h <= 1080 and x + new_w <= 1920:
                                background[y:y+new_h, x:x+new_w] = img
                            img = background
                        
                        return img
                    else:
                        return np.zeros((1080, 1920, 3), dtype=np.uint8)
                        
            elif active_source == "camera":
                img = self.capture_camera()
                # Масштабируем до Full HD для записи
                img = cv2.resize(img, (1920, 1080))
                return img
                
            else:
                return np.zeros((1080, 1920, 3), dtype=np.uint8)
                
        except Exception as e:
            print(f"Ошибка захвата для записи: {e}")
            return np.zeros((1080, 1920, 3), dtype=np.uint8)

    def capture_camera(self):
        """Захватывает изображение с камеры"""
        try:
            if self.camera is None or not self.camera.isOpened():
                scene = self.scenes[self.current_scene_index]
                self.camera = cv2.VideoCapture(scene.camera_index)
                width, height = map(int, scene.camera_resolution.split('x'))
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            
            ret, frame = self.camera.read()
            return frame if ret else np.zeros((480, 640, 3), dtype=np.uint8)
        except Exception as e:
            print(f"Ошибка захвата камеры: {e}")
            return np.zeros((480, 640, 3), dtype=np.uint8)

    def apply_text_overlays(self, frame, text_objects):
        """Накладывает текстовые объекты на кадр"""
        try:
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)
            
            for text_obj in text_objects:
                if not text_obj.visible:
                    continue
                    
                try:
                    font_size = int(text_obj.font_size * text_obj.scale)
                    font = ImageFont.truetype("arial.ttf", font_size)
                except:
                    font = ImageFont.load_default()
                
                if text_obj.background_color and text_obj.background_alpha > 0:
                    bbox = draw.textbbox((text_obj.x, text_obj.y), text_obj.text, font=font)
                    overlay = Image.new('RGBA', pil_img.size, (0, 0, 0, 0))
                    overlay_draw = ImageDraw.Draw(overlay)
                    overlay_draw.rectangle(bbox, fill=text_obj.background_color + (text_obj.background_alpha,))
                    pil_img = Image.alpha_composite(pil_img.convert('RGBA'), overlay).convert('RGB')
                    draw = ImageDraw.Draw(pil_img)
                
                draw.text((text_obj.x, text_obj.y), text_obj.text, fill=text_obj.font_color, font=font)
            
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"Ошибка наложения текста: {e}")
            return frame

    def setup_styles(self):
        """Настраивает современные стили для интерфейса"""
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('.', background='#1a1a1a', foreground='white',
                       fieldbackground='#2d2d2d', selectbackground='#3498db', selectforeground='white')
        style.configure('TFrame', background='#1a1a1a')
        style.configure('Header.TFrame', background='#2d2d2d')
        style.configure('Content.TFrame', background='#2d2d2d')
        style.configure('TLabel', background='#1a1a1a', foreground='white')
        style.configure('Header.TLabel', background='#2d2d2d', foreground='white', font=('Arial', 10, 'bold'))
        style.configure('Title.TLabel', background='#1a1a1a', foreground='white', font=('Arial', 12, 'bold'))
        
        style.configure('TButton', background='#3498db', foreground='white', borderwidth=0, focuscolor='none')
        style.map('TButton', background=[('active', '#2980b9'), ('pressed', '#21618c')])
        
        style.configure('Primary.TButton', background='#e74c3c', foreground='white')
        style.map('Primary.TButton', background=[('active', '#c0392b'), ('pressed', '#a93226')])
        
        style.configure('Success.TButton', background='#2ecc71', foreground='white')
        style.map('Success.TButton', background=[('active', '#27ae60'), ('pressed', '#229954')])
        
        style.configure('Warning.TButton', background='#f39c12', foreground='white')
        style.map('Warning.TButton', background=[('active', '#d68910'), ('pressed', '#b9770e')])
        
        style.configure('TNotebook', background='#1a1a1a', borderwidth=0)
        style.configure('TNotebook.Tab', background='#2d2d2d', foreground='white', padding=[15, 5], borderwidth=0)
        style.map('TNotebook.Tab', background=[('selected', '#3498db'), ('active', '#2980b9')])
        
        style.configure('TEntry', fieldbackground='#2d2d2d', foreground='white', borderwidth=1,
                       lightcolor='#3498db', darkcolor='#3498db')
        style.configure('Modern.TEntry', fieldbackground='#34495e', foreground='white', borderwidth=0, relief='flat')
        style.configure('TCheckbutton', background='#1a1a1a', foreground='white')
        style.configure('TCombobox', fieldbackground='#2d2d2d', foreground='white', background='#3498db')
        style.configure('Horizontal.TProgressbar', background='#3498db', troughcolor='#2d2d2d', borderwidth=0)
        
    def get_available_cameras(self):
        """Получает список доступных камер"""
        cameras = []
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cameras.append(i)
                cap.release()
        return cameras if cameras else [0]
        
    def enter_fullscreen(self):
        """Включает полноэкранный режим"""
        self.root.attributes('-fullscreen', True)
        self.root.bind('<F11>', self.toggle_fullscreen)
        self.root.bind('<Escape>', self.toggle_fullscreen)
        
    def setup_hotkeys(self):
        """Настраивает горячие клавиши для управления записи"""
        try:
            import keyboard
            self.has_global_hotkeys = True
            
            try:
                keyboard.unhook_all()
            except:
                pass
            
            keyboard.add_hotkey('ctrl+r', self.start_recording_hotkey)
            keyboard.add_hotkey('ctrl+s', self.stop_recording_hotkey)
            keyboard.add_hotkey('ctrl+p', self.toggle_pause_hotkey)
            
        except ImportError:
            self.has_global_hotkeys = False
            self.root.bind('<Control-r>', lambda e: self.start_recording_hotkey())
            self.root.bind('<Control-s>', lambda e: self.stop_recording_hotkey())
            self.root.bind('<Control-p>', lambda e: self.toggle_pause_hotkey())
            
    def start_recording_hotkey(self):
        """Обработчик горячей клавиши для начала записи"""
        if not self.is_recording:
            self.start_recording()
            
    def stop_recording_hotkey(self):
        """Обработчик горячей клавиши для остановки записи"""
        if self.is_recording:
            self.stop_recording()
            
    def toggle_pause_hotkey(self):
        """Обработчик горячей клавиши для паузы/возобновления записи"""
        if self.is_recording:
            self.toggle_pause()
        
    def toggle_fullscreen(self, event=None):
        """Переключает полноэкранный режим"""
        self.fullscreen_mode = not self.fullscreen_mode
        self.root.attributes('-fullscreen', self.fullscreen_mode)
        
    def load_settings(self):
        """Загружает настройки из файла"""
        settings_path = os.path.join(os.path.expanduser("~"), ".recordstudio_settings.json")
        default_path = os.path.join(os.path.expanduser("~"), "Videos", "RecordStudio")
        
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.save_path = settings.get('save_path', default_path)
                    self.hotkeys = settings.get('hotkeys', self.hotkeys)
                    
                    loaded_sections = settings.get('sections_expanded', {})
                    self.sections_expanded = {
                        'sources': loaded_sections.get('sources', True),
                        'scenes': loaded_sections.get('scenes', True),
                        'text': loaded_sections.get('text', True),
                        'transform': loaded_sections.get('transform', True)
                    }
            except Exception as e:
                print(f"Ошибка загрузки настроек: {e}")
                self.save_path = default_path
                self.sections_expanded = {'sources': True, 'scenes': True, 'text': True, 'transform': True}
        else:
            self.save_path = default_path
            self.sections_expanded = {'sources': True, 'scenes': True, 'text': True, 'transform': True}
    
    def save_settings(self):
        """Сохраняет настройки в файл"""
        settings_path = os.path.join(os.path.expanduser("~"), ".recordstudio_settings.json")
        try:
            settings = {
                'save_path': self.save_path,
                'hotkeys': self.hotkeys,
                'sections_expanded': self.sections_expanded
            }
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения настроек: {e}")
    
    def load_scenes(self):
        """Загружает сцены из файла"""
        scenes_path = os.path.join(os.path.expanduser("~"), ".recordstudio_scenes.json")
        
        if os.path.exists(scenes_path):
            try:
                with open(scenes_path, 'r', encoding='utf-8') as f:
                    scenes_data = json.load(f)
                    self.scenes = [Scene.from_dict(scene_data) for scene_data in scenes_data]
            except Exception as e:
                print(f"Ошибка загрузки сцен: {e}")
                self.scenes = []
    
    def save_scenes(self):
        """Сохраняет сцены в файл"""
        scenes_path = os.path.join(os.path.expanduser("~"), ".recordstudio_scenes.json")
        try:
            scenes_data = [scene.to_dict() for scene in self.scenes]
            with open(scenes_path, 'w', encoding='utf-8') as f:
                json.dump(scenes_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения сцен: {e}")
        
    def setup_ui(self):
        # Главный контейнер
        main_container = ttk.Frame(self.root, style='TFrame')
        main_container.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # Верхняя панель с кнопками управления
        top_frame = ttk.Frame(main_container, height=60, style='Header.TFrame')
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        top_frame.pack_propagate(False)
        
        # Левый блок верхней панели
        left_top_frame = ttk.Frame(top_frame, style='Header.TFrame')
        left_top_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # Заголовок приложения
        title_label = ttk.Label(left_top_frame, text="RECORD STUDIO PRO", 
                               style='Title.TLabel', font=('Arial', 16, 'bold'))
        title_label.pack(side=tk.LEFT, padx=10)
        
        # Центральный блок верхней панели
        center_top_frame = ttk.Frame(top_frame, style='Header.TFrame')
        center_top_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=20)
        
        # Кнопка записи
        self.record_button = ttk.Button(center_top_frame, 
                                       text=f"● НАЧАТЬ ЗАПИСЬ ({self.hotkeys['start_recording']})", 
                                       command=self.toggle_recording,
                                       style='Primary.TButton',
                                       width=25)
        self.record_button.pack(side=tk.LEFT, padx=5)
        
        # Таймер записи
        self.timer_label = ttk.Label(center_top_frame, text="00:00:00", 
                                    font=("Arial", 18, "bold"), 
                                    foreground="#2ecc71",
                                    background='#2d2d2d')
        self.timer_label.pack(side=tk.LEFT, padx=20)
        
        # Кнопка паузы
        self.pause_button = ttk.Button(center_top_frame, 
                                      text=f"⏸ ПАУЗА ({self.hotkeys['toggle_pause']})", 
                                      command=self.toggle_pause,
                                      style='Warning.TButton',
                                      width=15)
        self.pause_button.pack(side=tk.LEFT, padx=5)
        self.pause_button.config(state="disabled")
        
        # Правый блок верхней панели
        right_top_frame = ttk.Frame(top_frame, style='Header.TFrame')
        right_top_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10)
        
        # Кнопка переключения полноэкранного режима
        self.fullscreen_button = ttk.Button(right_top_frame, text="⛶", 
                                          command=self.toggle_fullscreen, 
                                          width=3,
                                          style='TButton')
        self.fullscreen_button.pack(side=tk.RIGHT, padx=5)
        
        # Кнопка настройки горячих клавиш
        self.hotkeys_button = ttk.Button(right_top_frame, text="⌨", 
                                        command=self.show_hotkeys_settings, 
                                        width=3,
                                        style='TButton')
        self.hotkeys_button.pack(side=tk.RIGHT, padx=5)
        
        # Кнопка выбора пути сохранения
        self.path_button = ttk.Button(right_top_frame, text="📁", 
                                     command=self.select_save_path, 
                                     width=3,
                                     style='TButton')
        self.path_button.pack(side=tk.RIGHT, padx=5)
        
        # Кнопка выхода
        self.exit_button = ttk.Button(right_top_frame, text="✕", 
                                     command=self.safe_exit, 
                                     width=3,
                                     style='Primary.TButton')
        self.exit_button.pack(side=tk.RIGHT, padx=5)
        
        # Основная область
        main_area = ttk.Frame(main_container, style='TFrame')
        main_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Левая панель (источники и настройки)
        left_panel = ttk.Frame(main_area, width=280, style='Content.TFrame')
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left_panel.pack_propagate(False)
        
        # Правая панель (предпросмотр)
        right_panel = ttk.Frame(main_area, style='Content.TFrame')
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Заголовок предпросмотра
        preview_header = ttk.Frame(right_panel, style='Header.TFrame', height=30)
        preview_header.pack(fill=tk.X, pady=(0, 5))
        preview_header.pack_propagate(False)
        
        preview_title = ttk.Label(preview_header, text="ПРЕДПРОСМОТР", 
                                 style='Header.TLabel', font=('Arial', 10, 'bold'))
        preview_title.pack(side=tk.LEFT, padx=10, pady=5)
        
        # Область предпросмотра
        preview_content = ttk.Frame(right_panel, style='Content.TFrame')
        preview_content.pack(fill=tk.BOTH, expand=True)
        
        # Метка для предпросмотра экрана
        self.preview_label = tk.Label(preview_content, text="Загрузка предпросмотра...", 
                                     background="#000", foreground="#666", 
                                     font=("Arial", 14), anchor=tk.CENTER,
                                     relief='sunken', bd=2)
        self.preview_label.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # Привязываем события мыши для перемещения и масштабирования
        self.preview_label.bind("<ButtonPress-1>", self.on_preview_click)
        self.preview_label.bind("<B1-Motion>", self.on_preview_drag)
        self.preview_label.bind("<ButtonRelease-1>", self.on_preview_release)
        self.preview_label.bind("<MouseWheel>", self.on_preview_scroll)
        
        # Настройка левой панели
        self.setup_left_panel(left_panel)
        
        # Статус бар
        self.setup_status_bar(main_container)
        
    def setup_left_panel(self, parent):
        """Настраивает левую панель с настройками"""
        # Создаем Notebook для организации настроек
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Вкладка источников
        sources_frame = ttk.Frame(notebook)
        notebook.add(sources_frame, text="Источники")
        
        # Вкладка сцен
        scenes_frame = ttk.Frame(notebook)
        notebook.add(scenes_frame, text="Сцены")
        
        # Вкладка текста
        text_frame = ttk.Frame(notebook)
        notebook.add(text_frame, text="Текст")
        
        # Вкладка трансформации
        transform_frame = ttk.Frame(notebook)
        notebook.add(transform_frame, text="Трансформация")
        
        # Наполняем вкладки содержимым
        self.setup_sources_tab(sources_frame)
        self.setup_scenes_tab(scenes_frame)
        self.setup_text_tab(text_frame)
        self.setup_transform_tab(transform_frame)
    
    def setup_sources_tab(self, parent):
        """Настраивает вкладку источников видео"""
        content_frame = ttk.Frame(parent)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Источники видео
        sources_label = ttk.Label(content_frame, text="Источники видео:")
        sources_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Экран
        self.screen_var = tk.BooleanVar(value=True)
        screen_cb = ttk.Checkbutton(content_frame, text="Экран", 
                                   variable=self.screen_var,
                                   command=self.on_source_change)
        screen_cb.pack(anchor=tk.W, pady=2)
        
        # Окно
        self.window_var = tk.BooleanVar()
        window_cb = ttk.Checkbutton(content_frame, text="Окно", 
                                   variable=self.window_var,
                                   command=self.on_source_change)
        window_cb.pack(anchor=tk.W, pady=2)
        
        # Кнопка выбора окна
        self.window_button = ttk.Button(content_frame, text="Выбрать окно", 
                                       command=self.select_window,
                                       width=15)
        self.window_button.pack(anchor=tk.W, pady=5)
        self.window_button.config(state="normal" if self.window_var.get() else "disabled")
        
        # Метка выбранного окна
        self.window_label = ttk.Label(content_frame, text="Окно не выбрано", 
                                     foreground="#666", font=("Arial", 8))
        self.window_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Камера
        self.camera_var = tk.BooleanVar()
        camera_cb = ttk.Checkbutton(content_frame, text="Камера", 
                                   variable=self.camera_var,
                                   command=self.on_source_change)
        camera_cb.pack(anchor=tk.W, pady=2)
        
        # Выбор камеры
        camera_frame = ttk.Frame(content_frame)
        camera_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(camera_frame, text="Камера:").pack(side=tk.LEFT)
        self.camera_combo = ttk.Combobox(camera_frame, values=[f"Камера {i}" for i in self.available_cameras],
                                        state="readonly", width=12)
        self.camera_combo.pack(side=tk.RIGHT)
        self.camera_combo.set("Камера 0")
        self.camera_combo.bind('<<ComboboxSelected>>', self.on_camera_change)
        
        # Разрешение камеры
        res_frame = ttk.Frame(content_frame)
        res_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(res_frame, text="Разрешение:").pack(side=tk.LEFT)
        self.res_combo = ttk.Combobox(res_frame, 
                                     values=["320x240", "640x480", "800x600", "1024x768", "1280x720"],
                                     state="readonly", width=12)
        self.res_combo.pack(side=tk.RIGHT)
        self.res_combo.set("640x480")
        self.res_combo.bind('<<ComboboxSelected>>', self.on_resolution_change)
        
        # Аудио
        audio_label = ttk.Label(content_frame, text="Аудио:")
        audio_label.pack(anchor=tk.W, pady=(10, 5))
        
        self.audio_var = tk.BooleanVar(value=True)
        audio_cb = ttk.Checkbutton(content_frame, text="Записывать аудио", 
                                  variable=self.audio_var,
                                  command=self.on_audio_change)
        audio_cb.pack(anchor=tk.W, pady=2)
        
        # Макет
        layout_label = ttk.Label(content_frame, text="Макет:")
        layout_label.pack(anchor=tk.W, pady=(10, 5))
        
        layout_frame = ttk.Frame(content_frame)
        layout_frame.pack(fill=tk.X, pady=5)
        
        self.layout_var = tk.StringVar(value="single")
        layouts = [("Одиночный", "single"), ("Картинка в картинке", "pip"), 
                  ("Сплит-экран", "split"), ("Квадраты", "quad")]
        
        for text, value in layouts:
            rb = ttk.Radiobutton(layout_frame, text=text, value=value,
                                variable=self.layout_var,
                                command=self.on_layout_change)
            rb.pack(anchor=tk.W, pady=2)
    
    def setup_scenes_tab(self, parent):
        """Настраивает вкладку сцен"""
        content_frame = ttk.Frame(parent)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Список сцен
        scenes_list_frame = ttk.Frame(content_frame, height=150)
        scenes_list_frame.pack(fill=tk.X, pady=(0, 10))
        scenes_list_frame.pack_propagate(False)
        
        # Контейнер для списка сцен
        self.scenes_listbox = tk.Listbox(scenes_list_frame, bg='#2d2d2d', fg='white', 
                                        selectbackground='#3498db', borderwidth=0,
                                        font=('Arial', 9))
        self.scenes_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.scenes_listbox.bind('<<ListboxSelect>>', self.on_scene_select)
        
        # Кнопки управления сценами
        scenes_buttons_frame = ttk.Frame(content_frame)
        scenes_buttons_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(scenes_buttons_frame, text="Добавить", 
                  command=self.add_scene).pack(side=tk.LEFT, padx=2)
        ttk.Button(scenes_buttons_frame, text="Удалить", 
                  command=self.delete_scene).pack(side=tk.LEFT, padx=2)
        ttk.Button(scenes_buttons_frame, text="Переименовать", 
                  command=self.rename_scene).pack(side=tk.LEFT, padx=2)
        ttk.Button(scenes_buttons_frame, text="Дублировать", 
                  command=self.duplicate_scene).pack(side=tk.LEFT, padx=2)
        
        # Настройки текущей сцены
        scene_settings_label = ttk.Label(content_frame, text="Настройки сцены:")
        scene_settings_label.pack(anchor=tk.W, pady=(10, 5))
        
        # Имя сцены
        name_frame = ttk.Frame(content_frame)
        name_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(name_frame, text="Имя:").pack(side=tk.LEFT)
        self.scene_name_entry = ttk.Entry(name_frame)
        self.scene_name_entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
        self.scene_name_entry.bind('<KeyRelease>', self.on_scene_name_change)
    
    def setup_text_tab(self, parent):
        """Настраивает вкладку текста"""
        content_frame = ttk.Frame(parent)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Список текстовых объектов
        text_list_frame = ttk.Frame(content_frame, height=120)
        text_list_frame.pack(fill=tk.X, pady=(0, 10))
        text_list_frame.pack_propagate(False)
        
        # Контейнер для списка текстов
        self.text_listbox = tk.Listbox(text_list_frame, bg='#2d2d2d', fg='white', 
                                      selectbackground='#3498db', borderwidth=0,
                                      font=('Arial', 9), height=4)
        self.text_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.text_listbox.bind('<<ListboxSelect>>', self.on_text_select)
        
        # Кнопки управления текстом
        text_buttons_frame = ttk.Frame(content_frame)
        text_buttons_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(text_buttons_frame, text="Добавить", 
                  command=self.add_text).pack(side=tk.LEFT, padx=2)
        ttk.Button(text_buttons_frame, text="Удалить", 
                  command=self.delete_text).pack(side=tk.LEFT, padx=2)
        ttk.Button(text_buttons_frame, text="Вверх", 
                  command=self.move_text_up).pack(side=tk.LEFT, padx=2)
        ttk.Button(text_buttons_frame, text="Вниз", 
                  command=self.move_text_down).pack(side=tk.LEFT, padx=2)
        
        # Настройки текста
        text_settings_label = ttk.Label(content_frame, text="Настройки текста:")
        text_settings_label.pack(anchor=tk.W, pady=(10, 5))
        
        # Текст
        text_frame = ttk.Frame(content_frame)
        text_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(text_frame, text="Текст:").pack(side=tk.LEFT)
        self.text_entry = ttk.Entry(text_frame)
        self.text_entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
        self.text_entry.bind('<KeyRelease>', self.on_text_change)
        
        # Шрифт и размер
        font_frame = ttk.Frame(content_frame)
        font_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(font_frame, text="Шрифт:").pack(side=tk.LEFT)
        self.font_combo = ttk.Combobox(font_frame, values=["Arial", "Times New Roman", "Courier New", "Verdana"],
                                      state="readonly", width=15)
        self.font_combo.pack(side=tk.RIGHT)
        self.font_combo.set("Arial")
        self.font_combo.bind('<<ComboboxSelected>>', self.on_font_change)
        
        size_frame = ttk.Frame(content_frame)
        size_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(size_frame, text="Размер:").pack(side=tk.LEFT)
        self.size_scale = ttk.Scale(size_frame, from_=8, to=72, orient=tk.HORIZONTAL, length=120)
        self.size_scale.set(24)
        self.size_scale.pack(side=tk.RIGHT)
        self.size_scale.bind('<ButtonRelease-1>', self.on_size_change)
        
        # Цвет текста
        color_frame = ttk.Frame(content_frame)
        color_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(color_frame, text="Цвет текста:").pack(side=tk.LEFT)
        self.color_button = ttk.Button(color_frame, text="Выбрать", 
                                      command=self.choose_text_color,
                                      width=10)
        self.color_button.pack(side=tk.RIGHT)
        
        # Фон текста
        bg_frame = ttk.Frame(content_frame)
        bg_frame.pack(fill=tk.X, pady=5)
        
        self.bg_var = tk.BooleanVar()
        bg_cb = ttk.Checkbutton(bg_frame, text="Фон текста", 
                               variable=self.bg_var,
                               command=self.on_bg_toggle)
        bg_cb.pack(side=tk.LEFT)
        
        self.bg_color_button = ttk.Button(bg_frame, text="Цвет фона", 
                                         command=self.choose_bg_color,
                                         width=10)
        self.bg_color_button.pack(side=tk.RIGHT)
        self.bg_color_button.config(state="disabled")
        
        # Прозрачность фона
        alpha_frame = ttk.Frame(content_frame)
        alpha_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(alpha_frame, text="Прозрачность:").pack(side=tk.LEFT)
        self.alpha_scale = ttk.Scale(alpha_frame, from_=0, to=255, orient=tk.HORIZONTAL, length=120)
        self.alpha_scale.set(0)
        self.alpha_scale.pack(side=tk.RIGHT)
        self.alpha_scale.bind('<ButtonRelease-1>', self.on_alpha_change)
        self.alpha_scale.config(state="disabled")
        
        # Видимость
        self.visible_var = tk.BooleanVar(value=True)
        visible_cb = ttk.Checkbutton(content_frame, text="Видимый", 
                                    variable=self.visible_var,
                                    command=self.on_visibility_change)
        visible_cb.pack(anchor=tk.W, pady=5)
    
    def setup_transform_tab(self, parent):
        """Настраивает вкладку трансформации"""
        content_frame = ttk.Frame(parent)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Выбор источника для трансформации
        source_frame = ttk.Frame(content_frame)
        source_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(source_frame, text="Источник:").pack(anchor=tk.W)
        
        self.transform_var = tk.StringVar(value="screen")
        transform_sources = [("Экран", "screen"), ("Камера", "camera"), ("Окно", "window")]
        
        for text, value in transform_sources:
            rb = ttk.Radiobutton(source_frame, text=text, value=value,
                                variable=self.transform_var,
                                command=self.on_transform_source_change)
            rb.pack(anchor=tk.W, pady=2)
        
        # Масштаб
        scale_frame = ttk.Frame(content_frame)
        scale_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(scale_frame, text="Масштаб:").pack(side=tk.LEFT)
        self.scale_var = tk.StringVar()
        self.scale_entry = ttk.Entry(scale_frame, textvariable=self.scale_var, width=8)
        self.scale_entry.pack(side=tk.RIGHT)
        self.scale_entry.bind('<KeyRelease>', self.on_scale_change)
        
        self.scale_slider = ttk.Scale(content_frame, from_=0.1, to=3.0, 
                                     orient=tk.HORIZONTAL, value=1.0)
        self.scale_slider.pack(fill=tk.X, pady=5)
        self.scale_slider.bind('<ButtonRelease-1>', self.on_scale_slider_change)
        
        # Позиция
        pos_label = ttk.Label(content_frame, text="Позиция:")
        pos_label.pack(anchor=tk.W, pady=(10, 5))
        
        # X координата
        x_frame = ttk.Frame(content_frame)
        x_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(x_frame, text="X:").pack(side=tk.LEFT)
        self.x_var = tk.StringVar()
        self.x_entry = ttk.Entry(x_frame, textvariable=self.x_var, width=8)
        self.x_entry.pack(side=tk.RIGHT)
        self.x_entry.bind('<KeyRelease>', self.on_position_change)
        
        self.x_slider = ttk.Scale(content_frame, from_=-500, to=500, 
                                 orient=tk.HORIZONTAL, value=0)
        self.x_slider.pack(fill=tk.X, pady=2)
        self.x_slider.bind('<ButtonRelease-1>', self.on_position_slider_change)
        
        # Y координата
        y_frame = ttk.Frame(content_frame)
        y_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(y_frame, text="Y:").pack(side=tk.LEFT)
        self.y_var = tk.StringVar()
        self.y_entry = ttk.Entry(y_frame, textvariable=self.y_var, width=8)
        self.y_entry.pack(side=tk.RIGHT)
        self.y_entry.bind('<KeyRelease>', self.on_position_change)
        
        self.y_slider = ttk.Scale(content_frame, from_=-500, to=500, 
                                 orient=tk.HORIZONTAL, value=0)
        self.y_slider.pack(fill=tk.X, pady=2)
        self.y_slider.bind('<ButtonRelease-1>', self.on_position_slider_change)
        
        # Кнопки сброса
        reset_frame = ttk.Frame(content_frame)
        reset_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(reset_frame, text="Сбросить позицию", 
                  command=self.reset_position).pack(side=tk.LEFT, padx=2)
        ttk.Button(reset_frame, text="Сбросить масштаб", 
                  command=self.reset_scale).pack(side=tk.LEFT, padx=2)
    
    def setup_status_bar(self, parent):
        """Настраивает статус бар"""
        status_frame = ttk.Frame(parent, height=25)
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        status_frame.pack_propagate(False)
        
        # Левая часть статус бара
        left_status = ttk.Frame(status_frame)
        left_status.pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        self.status_label = ttk.Label(left_status, text="Готов к записи", 
                                     foreground="#2ecc71", font=("Arial", 9))
        self.status_label.pack(side=tk.LEFT)
        
        # Правая часть статус бара
        right_status = ttk.Frame(status_frame)
        right_status.pack(side=tk.RIGHT, fill=tk.Y, padx=10)
        
        self.performance_label = ttk.Label(right_status, text="CPU: --% | RAM: --MB", 
                                          foreground="#666", font=("Arial", 8))
        self.performance_label.pack(side=tk.RIGHT)
        
        # Обновление производительности
        self.update_performance()
    
    def update_performance(self):
        """Обновляет информацию о производительности"""
        try:
            if PSUTIL_AVAILABLE:
                cpu_percent = psutil.cpu_percent()
                memory = psutil.virtual_memory()
                memory_mb = memory.used // (1024 * 1024)
                self.performance_label.config(text=f"CPU: {cpu_percent:.1f}% | RAM: {memory_mb}MB")
            else:
                self.performance_label.config(text="Установите psutil для мониторинга")
        except Exception as e:
            self.performance_label.config(text="Ошибка мониторинга")
        
        self.root.after(2000, self.update_performance)
    
    def on_source_change(self):
        """Обработчик изменения источников видео"""
        scene = self.scenes[self.current_scene_index]
        scene.video_sources = {
            "full_screen": self.screen_var.get(),
            "window": self.window_var.get(),
            "camera": self.camera_var.get()
        }
        
        # Обновляем состояние кнопки выбора окна
        self.window_button.config(state="normal" if self.window_var.get() else "disabled")
        
        self.save_scenes()
    
    def on_audio_change(self):
        """Обработчик изменения настроек аудио"""
        scene = self.scenes[self.current_scene_index]
        scene.audio_enabled = self.audio_var.get()
        self.save_scenes()
    
    def on_layout_change(self):
        """Обработчик изменения макета"""
        scene = self.scenes[self.current_scene_index]
        scene.layout = self.layout_var.get()
        self.save_scenes()
    
    def on_camera_change(self, event=None):
        """Обработчик изменения камеры"""
        scene = self.scenes[self.current_scene_index]
        selected = self.camera_combo.get()
        if selected.startswith("Камера"):
            index = int(selected.split()[-1])
            scene.camera_index = index
            # Переоткрываем камеру с новым индексом
            if self.camera is not None:
                self.camera.release()
                self.camera = None
            self.save_scenes()
    
    def on_resolution_change(self, event=None):
        """Обработчик изменения разрешения камеры"""
        scene = self.scenes[self.current_scene_index]
        scene.camera_resolution = self.res_combo.get()
        # Переоткрываем камеру с новым разрешением
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        self.save_scenes()
    
    def on_scene_select(self, event=None):
        """Обработчик выбора сцены"""
        selection = self.scenes_listbox.curselection()
        if selection:
            self.current_scene_index = selection[0]
            self.load_scene_settings()
    
    def on_scene_name_change(self, event=None):
        """Обработчик изменения имени сцены"""
        if 0 <= self.current_scene_index < len(self.scenes):
            scene = self.scenes[self.current_scene_index]
            scene.name = self.scene_name_entry.get()
            # Обновляем список сцен
            self.update_scenes_list()
            self.save_scenes()
    
    def on_text_select(self, event=None):
        """Обработчик выбора текстового объекта"""
        selection = self.text_listbox.curselection()
        if selection:
            self.selected_text_index = selection[0]
            self.load_text_settings()
        else:
            self.selected_text_index = -1
    
    def on_text_change(self, event=None):
        """Обработчик изменения текста"""
        if 0 <= self.selected_text_index < len(self.scenes[self.current_scene_index].text_objects):
            text_obj = self.scenes[self.current_scene_index].text_objects[self.selected_text_index]
            text_obj.text = self.text_entry.get()
            self.update_text_list()
            self.save_scenes()
    
    def on_font_change(self, event=None):
        """Обработчик изменения шрифта"""
        if 0 <= self.selected_text_index < len(self.scenes[self.current_scene_index].text_objects):
            text_obj = self.scenes[self.current_scene_index].text_objects[self.selected_text_index]
            text_obj.font_family = self.font_combo.get()
            self.save_scenes()
    
    def on_size_change(self, event=None):
        """Обработчик изменения размера шрифта"""
        if 0 <= self.selected_text_index < len(self.scenes[self.current_scene_index].text_objects):
            text_obj = self.scenes[self.current_scene_index].text_objects[self.selected_text_index]
            text_obj.font_size = int(self.size_scale.get())
            self.save_scenes()
    
    def on_visibility_change(self):
        """Обработчик изменения видимости текста"""
        if 0 <= self.selected_text_index < len(self.scenes[self.current_scene_index].text_objects):
            text_obj = self.scenes[self.current_scene_index].text_objects[self.selected_text_index]
            text_obj.visible = self.visible_var.get()
            self.save_scenes()
    
    def on_bg_toggle(self):
        """Обработчик включения/выключения фона текста"""
        state = "normal" if self.bg_var.get() else "disabled"
        self.bg_color_button.config(state=state)
        self.alpha_scale.config(state=state)
        
        if 0 <= self.selected_text_index < len(self.scenes[self.current_scene_index].text_objects):
            text_obj = self.scenes[self.current_scene_index].text_objects[self.selected_text_index]
            if not self.bg_var.get():
                text_obj.background_color = None
                text_obj.background_alpha = 0
            self.save_scenes()
    
    def on_alpha_change(self, event=None):
        """Обработчик изменения прозрачности фона"""
        if 0 <= self.selected_text_index < len(self.scenes[self.current_scene_index].text_objects):
            text_obj = self.scenes[self.current_scene_index].text_objects[self.selected_text_index]
            text_obj.background_alpha = int(self.alpha_scale.get())
            self.save_scenes()
    
    def on_transform_source_change(self):
        """Обработчик изменения источника для трансформации"""
        self.selected_transform_index = {"screen": 0, "camera": 1, "window": 2}[self.transform_var.get()]
        self.load_transform_settings()
    
    def on_scale_change(self, event=None):
        """Обработчик изменения масштаба через поле ввода"""
        try:
            scale = float(self.scale_var.get())
            self.scale_slider.set(scale)
            self.apply_transform_settings()
        except ValueError:
            pass
    
    def on_scale_slider_change(self, event=None):
        """Обработчик изменения масштаба через слайдер"""
        scale = self.scale_slider.get()
        self.scale_var.set(f"{scale:.2f}")
        self.apply_transform_settings()
    
    def on_position_change(self, event=None):
        """Обработчик изменения позиции через поле ввода"""
        try:
            x = int(self.x_var.get())
            y = int(self.y_var.get())
            self.x_slider.set(x)
            self.y_slider.set(y)
            self.apply_transform_settings()
        except ValueError:
            pass
    
    def on_position_slider_change(self, event=None):
        """Обработчик изменения позиции через слайдер"""
        x = self.x_slider.get()
        y = self.y_slider.get()
        self.x_var.set(str(int(x)))
        self.y_var.set(str(int(y)))
        self.apply_transform_settings()
    
    def apply_transform_settings(self):
        """Применяет настройки трансформации к выбранному источнику"""
        scene = self.scenes[self.current_scene_index]
        
        try:
            scale = float(self.scale_var.get())
            x = int(self.x_var.get())
            y = int(self.y_var.get())
            
            if self.transform_var.get() == "screen":
                scene.screen_scale = scale
                scene.screen_offset_x = x
                scene.screen_offset_y = y
            elif self.transform_var.get() == "camera":
                scene.camera_scale = scale
                scene.camera_offset_x = x
                scene.camera_offset_y = y
            elif self.transform_var.get() == "window":
                scene.window_scale = scale
                scene.window_offset_x = x
                scene.window_offset_y = y
            
            self.save_scenes()
        except ValueError:
            pass
    
    def reset_position(self):
        """Сбрасывает позицию выбранного источника"""
        if self.transform_var.get() == "screen":
            self.x_var.set("0")
            self.y_var.set("0")
            self.x_slider.set(0)
            self.y_slider.set(0)
        elif self.transform_var.get() == "camera":
            self.x_var.set("0")
            self.y_var.set("0")
            self.x_slider.set(0)
            self.y_slider.set(0)
        elif self.transform_var.get() == "window":
            self.x_var.set("0")
            self.y_var.set("0")
            self.x_slider.set(0)
            self.y_slider.set(0)
        
        self.apply_transform_settings()
    
    def reset_scale(self):
        """Сбрасывает масштаб выбранного источника"""
        self.scale_var.set("1.0")
        self.scale_slider.set(1.0)
        self.apply_transform_settings()
    
    def load_scene_settings(self):
        """Загружает настройки выбранной сцены"""
        if 0 <= self.current_scene_index < len(self.scenes):
            scene = self.scenes[self.current_scene_index]
            
            # Источники видео
            self.screen_var.set(scene.video_sources["full_screen"])
            self.window_var.set(scene.video_sources["window"])
            self.camera_var.set(scene.video_sources["camera"])
            
            # Аудио
            self.audio_var.set(scene.audio_enabled)
            
            # Окно
            self.window_label.config(text=scene.window_info)
            
            # Камера
            if 0 <= scene.camera_index < len(self.available_cameras):
                self.camera_combo.set(f"Камера {scene.camera_index}")
            self.res_combo.set(scene.camera_resolution)
            
            # Макет
            self.layout_var.set(scene.layout)
            
            # Имя сцены
            self.scene_name_entry.delete(0, tk.END)
            self.scene_name_entry.insert(0, scene.name)
            
            # Текстовые объекты
            self.update_text_list()
            
            # Трансформация
            self.load_transform_settings()
            
            # Обновляем состояние кнопки выбора окна
            self.window_button.config(state="normal" if self.window_var.get() else "disabled")
    
    def load_text_settings(self):
        """Загружает настройки выбранного текстового объекта"""
        if 0 <= self.selected_text_index < len(self.scenes[self.current_scene_index].text_objects):
            text_obj = self.scenes[self.current_scene_index].text_objects[self.selected_text_index]
            
            self.text_entry.delete(0, tk.END)
            self.text_entry.insert(0, text_obj.text)
            
            self.font_combo.set(text_obj.font_family)
            self.size_scale.set(text_obj.font_size)
            
            self.visible_var.set(text_obj.visible)
            
            has_bg = text_obj.background_color is not None and text_obj.background_alpha > 0
            self.bg_var.set(has_bg)
            self.bg_color_button.config(state="normal" if has_bg else "disabled")
            self.alpha_scale.config(state="normal" if has_bg else "disabled")
            
            if has_bg:
                self.alpha_scale.set(text_obj.background_alpha)
    
    def load_transform_settings(self):
        """Загружает настройки трансформации для выбранного источника"""
        scene = self.scenes[self.current_scene_index]
        
        if self.transform_var.get() == "screen":
            self.scale_var.set(f"{scene.screen_scale:.2f}")
            self.scale_slider.set(scene.screen_scale)
            self.x_var.set(str(scene.screen_offset_x))
            self.x_slider.set(scene.screen_offset_x)
            self.y_var.set(str(scene.screen_offset_y))
            self.y_slider.set(scene.screen_offset_y)
        elif self.transform_var.get() == "camera":
            self.scale_var.set(f"{scene.camera_scale:.2f}")
            self.scale_slider.set(scene.camera_scale)
            self.x_var.set(str(scene.camera_offset_x))
            self.x_slider.set(scene.camera_offset_x)
            self.y_var.set(str(scene.camera_offset_y))
            self.y_slider.set(scene.camera_offset_y)
        elif self.transform_var.get() == "window":
            self.scale_var.set(f"{scene.window_scale:.2f}")
            self.scale_slider.set(scene.window_scale)
            self.x_var.set(str(scene.window_offset_x))
            self.x_slider.set(scene.window_offset_x)
            self.y_var.set(str(scene.window_offset_y))
            self.y_slider.set(scene.window_offset_y)
    
    def update_scenes_list(self):
        """Обновляет список сцен"""
        self.scenes_listbox.delete(0, tk.END)
        for scene in self.scenes:
            self.scenes_listbox.insert(tk.END, scene.name)
        
        if self.scenes:
            self.scenes_listbox.selection_set(self.current_scene_index)
    
    def update_text_list(self):
        """Обновляет список текстовых объектов"""
        self.text_listbox.delete(0, tk.END)
        scene = self.scenes[self.current_scene_index]
        for text_obj in scene.text_objects:
            display_text = text_obj.text[:20] + "..." if len(text_obj.text) > 20 else text_obj.text
            self.text_listbox.insert(tk.END, display_text)
        
        if scene.text_objects and 0 <= self.selected_text_index < len(scene.text_objects):
            self.text_listbox.selection_set(self.selected_text_index)
    
    def add_scene(self):
        """Добавляет новую сцену"""
        new_scene = Scene(f"Сцена {len(self.scenes) + 1}")
        self.scenes.append(new_scene)
        self.current_scene_index = len(self.scenes) - 1
        self.update_scenes_list()
        self.load_scene_settings()
        self.save_scenes()
    
    def delete_scene(self):
        """Удаляет текущую сцену"""
        if len(self.scenes) > 1:
            del self.scenes[self.current_scene_index]
            self.current_scene_index = min(self.current_scene_index, len(self.scenes) - 1)
            self.update_scenes_list()
            self.load_scene_settings()
            self.save_scenes()
        else:
            messagebox.showwarning("Предупреждение", "Нельзя удалить последнюю сцену")
    
    def rename_scene(self):
        """Переименовывает текущую сцену"""
        if 0 <= self.current_scene_index < len(self.scenes):
            new_name = simpledialog.askstring("Переименовать сцену", "Введите новое имя сцены:",
                                             initialvalue=self.scenes[self.current_scene_index].name)
            if new_name:
                self.scenes[self.current_scene_index].name = new_name
                self.update_scenes_list()
                self.load_scene_settings()
                self.save_scenes()
    
    def duplicate_scene(self):
        """Дублирует текущую сцену"""
        if 0 <= self.current_scene_index < len(self.scenes):
            original_scene = self.scenes[self.current_scene_index]
            duplicated_scene = copy.deepcopy(original_scene)
            duplicated_scene.name = f"{original_scene.name} (копия)"
            self.scenes.append(duplicated_scene)
            self.current_scene_index = len(self.scenes) - 1
            self.update_scenes_list()
            self.load_scene_settings()
            self.save_scenes()
    
    def add_text(self):
        """Добавляет новый текстовый объект"""
        scene = self.scenes[self.current_scene_index]
        new_text = TextObject("Новый текст", 100, 100)
        scene.text_objects.append(new_text)
        self.selected_text_index = len(scene.text_objects) - 1
        self.update_text_list()
        self.load_text_settings()
        self.save_scenes()
    
    def delete_text(self):
        """Удаляет текущий текстовый объект"""
        scene = self.scenes[self.current_scene_index]
        if scene.text_objects and 0 <= self.selected_text_index < len(scene.text_objects):
            del scene.text_objects[self.selected_text_index]
            self.selected_text_index = min(self.selected_text_index, len(scene.text_objects) - 1)
            self.update_text_list()
            self.load_text_settings()
            self.save_scenes()
    
    def move_text_up(self):
        """Перемещает текстовый объект вверх по списку"""
        scene = self.scenes[self.current_scene_index]
        if scene.text_objects and self.selected_text_index > 0:
            scene.text_objects[self.selected_text_index], scene.text_objects[self.selected_text_index - 1] = \
                scene.text_objects[self.selected_text_index - 1], scene.text_objects[self.selected_text_index]
            self.selected_text_index -= 1
            self.update_text_list()
            self.save_scenes()
    
    def move_text_down(self):
        """Перемещает текстовый объект вниз по списку"""
        scene = self.scenes[self.current_scene_index]
        if scene.text_objects and self.selected_text_index < len(scene.text_objects) - 1:
            scene.text_objects[self.selected_text_index], scene.text_objects[self.selected_text_index + 1] = \
                scene.text_objects[self.selected_text_index + 1], scene.text_objects[self.selected_text_index]
            self.selected_text_index += 1
            self.update_text_list()
            self.save_scenes()
    
    def choose_text_color(self):
        """Выбирает цвет текста"""
        if 0 <= self.selected_text_index < len(self.scenes[self.current_scene_index].text_objects):
            color = colorchooser.askcolor(title="Выберите цвет текста")
            if color[1]:
                text_obj = self.scenes[self.current_scene_index].text_objects[self.selected_text_index]
                text_obj.font_color = color[1]
                self.save_scenes()
    
    def choose_bg_color(self):
        """Выбирает цвет фона текста"""
        if 0 <= self.selected_text_index < len(self.scenes[self.current_scene_index].text_objects):
            color = colorchooser.askcolor(title="Выберите цвет фона")
            if color[1]:
                text_obj = self.scenes[self.current_scene_index].text_objects[self.selected_text_index]
                text_obj.background_color = color[1]
                self.save_scenes()
    
    def select_window(self):
        """Улучшенная функция выбора окон с несколькими методами"""
        try:
            import win32gui
        except ImportError:
            messagebox.showwarning("Предупреждение", 
                                 "Для выбора окон необходимо установить pywin32: pip install pywin32")
            return
        
        # Создаем диалоговое окно с выбором метода
        dialog = tk.Toplevel(self.root)
        dialog.title("Выбор метода выбора окна")
        dialog.geometry("500x300")
        dialog.configure(bg='#2d2d2d')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Центрируем окно
        dialog.update_idletasks()
        x = (self.root.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (self.root.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Заголовок
        title_label = tk.Label(dialog, text="ВЫБЕРИТЕ МЕТОД ВЫБОРА ОКНА", 
                              bg='#2d2d2d', fg='white', font=('Arial', 12, 'bold'))
        title_label.pack(pady=20)
        
        # Фрейм для кнопок методов
        methods_frame = tk.Frame(dialog, bg='#2d2d2d')
        methods_frame.pack(pady=20)
        
        # Метод 1: Список окон
        list_btn = ttk.Button(methods_frame, text="📋 Выбор из списка окон", 
                             command=lambda: [self.show_windows_list(), dialog.destroy()],
                             width=25)
        list_btn.pack(pady=10)
        
        # Метод 2: Ручной выбор
        manual_btn = ttk.Button(methods_frame, text="🎯 Ручной выбор (клик)", 
                               command=lambda: [self.manual_window_select(dialog)],
                               width=25)
        manual_btn.pack(pady=10)
        
        # Метод 3: Простой выбор
        simple_btn = ttk.Button(methods_frame, text="⚡ Простой выбор (активное окно)", 
                               command=lambda: [self.select_window_simple(), dialog.destroy()],
                               width=25)
        simple_btn.pack(pady=10)
        
        # Информация
        info_label = tk.Label(dialog, 
                             text="Рекомендуем использовать 'Ручной выбор' для лучших результатов",
                             bg='#2d2d2d', fg='#cccccc', font=('Arial', 9))
        info_label.pack(pady=10)
        
        # Кнопка отмены
        cancel_btn = ttk.Button(dialog, text="Отмена", command=dialog.destroy)
        cancel_btn.pack(pady=10)

    def show_windows_list(self):
        """Показывает диалог со списком окон"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Список окон")
        dialog.geometry("600x500")
        dialog.configure(bg='#2d2d2d')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Заголовок
        title_label = tk.Label(dialog, text="СПИСОК ДОСТУПНЫХ ОКОН", 
                              bg='#2d2d2d', fg='white', font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        # Кнопка обновления
        refresh_btn = ttk.Button(dialog, text="Обновить список", 
                               command=lambda: self.load_windows_list_to_tree(tree))
        refresh_btn.pack(pady=5)
        
        # Treeview с окнами
        tree_frame = ttk.Frame(dialog)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        columns = ("window", "pid", "size")
        tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings", height=15)
        
        tree.heading("window", text="Окно")
        tree.heading("pid", text="PID")
        tree.heading("size", text="Размер")
        
        tree.column("window", width=350)
        tree.column("pid", width=80)
        tree.column("size", width=100)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Загружаем окна
        self.load_windows_list_to_tree(tree)
        
        # Кнопки
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        select_btn = ttk.Button(button_frame, text="Выбрать", 
                              command=lambda: self.confirm_tree_selection(tree, dialog),
                              style='Primary.TButton')
        select_btn.pack(side=tk.RIGHT, padx=5)
        
        cancel_btn = ttk.Button(button_frame, text="Отмена", command=dialog.destroy)
        cancel_btn.pack(side=tk.RIGHT, padx=5)
        
        tree.bind('<Double-1>', lambda e: self.confirm_tree_selection(tree, dialog))

    def load_windows_list_to_tree(self, tree):
        """Загружает список окон в указанное дерево"""
        try:
            # Очищаем дерево
            for item in tree.get_children():
                tree.delete(item)
            
            # Загружаем список окон
            self.load_windows_list()
            
            # Добавляем окна в дерево
            for window in getattr(self, 'windows_list', []):
                display_text = f"{window['title']} [{window['process']}]"
                tree.insert("", "end", values=(
                    display_text,
                    window['pid'],
                    window['size']
                ), tags=(window['hwnd'],))
                
        except Exception as e:
            print(f"Ошибка загрузки окон в дерево: {e}")

    def load_windows_list(self):
        """Загружает список всех видимых окон с улучшенным обнаружением"""
        try:
            import win32gui
            import win32process
            
            # Очищаем текущий список
            self.windows_list = []
            
            def enum_windows_callback(hwnd, _):
                try:
                    # Проверяем, что окно видимо и имеет заголовок
                    if win32gui.IsWindowVisible(hwnd):
                        window_title = win32gui.GetWindowText(hwnd)
                        
                        # Если окно без заголовка, пропускаем его
                        if not window_title:
                            return
                        
                        # Проверяем, что окно не является системным или скрытым
                        if window_title in ['', 'Program Manager', 'MSCTFIME UI', 'Default IME']:
                            return
                        
                        # Получаем PID окна
                        try:
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                            
                            # Получаем информацию о процессе
                            process_name = "Unknown"
                            if PSUTIL_AVAILABLE:
                                try:
                                    process = psutil.Process(pid)
                                    process_name = process.name()
                                    
                                    # Пропускаем системные процессы
                                    system_processes = ['dwm.exe', 'explorer.exe', 'taskhostw.exe', 
                                                      'sihost.exe', 'ctfmon.exe', 'fontdrvhost.exe']
                                    if process_name.lower() in system_processes:
                                        return
                                        
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    process_name = "System"
                            
                            # Получаем размеры окна
                            try:
                                rect = win32gui.GetWindowRect(hwnd)
                                left, top, right, bottom = rect
                                width = right - left
                                height = bottom - top
                                
                                # Пропускаем окна с слишком маленькими размерами
                                if width < 100 or height < 50:
                                    return
                                
                                # Проверяем, что окно не выходит за границы экрана
                                if left < -1000 or top < -1000:
                                    return
                                    
                                self.windows_list.append({
                                    'hwnd': hwnd,
                                    'title': window_title,
                                    'pid': pid,
                                    'process': process_name,
                                    'rect': rect,
                                    'size': f"{width}x{height}"
                                })
                                
                            except Exception as e:
                                print(f"Ошибка получения размеров окна {hwnd}: {e}")
                                return
                                
                        except Exception as e:
                            print(f"Ошибка получения PID окна {hwnd}: {e}")
                            return
                            
                except Exception as e:
                    print(f"Ошибка обработки окна {hwnd}: {e}")
            
            # Перечисляем все окна
            win32gui.EnumWindows(enum_windows_callback, None)
            
            # Дополнительный способ получения окон через psutil (только если доступен)
            if PSUTIL_AVAILABLE:
                try:
                    for proc in psutil.process_iter(['pid', 'name']):
                        try:
                            if proc.info['name'].lower() in ['chrome.exe', 'firefox.exe', 'msedge.exe', 
                                                           'notepad.exe', 'calc.exe', 'explorer.exe']:
                                # Для известных процессов пытаемся найти их окна
                                pass
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                except Exception as e:
                    print(f"Ошибка получения окон через psutil: {e}")
            
            # Сортируем по имени процесса и заголовку
            self.windows_list.sort(key=lambda x: (x['process'].lower(), x['title'].lower()))
            
            # Обновляем статус
            if self.windows_list:
                self.status_label.config(text=f"Найдено {len(self.windows_list)} окон")
            else:
                self.status_label.config(text="Не найдено подходящих окон", foreground="orange")
                
        except Exception as e:
            print(f"Ошибка загрузки списка окон: {e}")
            messagebox.showerror("Ошибка", f"Не удалось загрузить список окон: {e}")

    def confirm_tree_selection(self, tree, dialog):
        """Подтверждает выбор окна из дерева"""
        try:
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("Предупреждение", "Выберите окно из списка")
                return
            
            item = selection[0]
            hwnd = int(tree.item(item, "tags")[0])
            
            # Находим информацию об окне
            window_info = None
            for window in getattr(self, 'windows_list', []):
                if window['hwnd'] == hwnd:
                    window_info = window
                    break
            
            if window_info:
                self.apply_window_selection(window_info)
                dialog.destroy()
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось выбрать окно: {e}")

    def apply_window_selection(self, window_info):
        """Применяет выбранное окно к сцене"""
        try:
            import win32gui
            
            # Подсвечиваем выбранное окно
            try:
                win32gui.FlashWindow(window_info['hwnd'], True)
            except:
                pass
            
            # Сохраняем информацию
            scene = self.scenes[self.current_scene_index]
            scene.window_info = f"{window_info['title']} [{window_info['process']}]"
            scene.window_rect = window_info['rect']
            scene.video_sources["window"] = True
            
            # Обновляем интерфейс
            self.window_label.config(text=scene.window_info)
            self.window_var.set(True)
            self.on_source_change()
            
            self.status_label.config(text=f"Выбрано окно: {window_info['title']}")
            self.save_scenes()
            
            messagebox.showinfo("Успех", f"Окно '{window_info['title']}' выбрано для записи")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка применения выбора окна: {e}")

    def manual_window_select(self, parent_dialog):
        """Ручной выбор окна кликом с улучшенным обнаружением"""
        try:
            import win32gui
            import win32con
            
            parent_dialog.withdraw()  # Скрываем диалог
            
            # Создаем прозрачное окно для захвата кликов
            overlay = tk.Toplevel(self.root)
            overlay.attributes('-fullscreen', True)
            overlay.attributes('-alpha', 0.1)  # Почти прозрачное
            overlay.attributes('-topmost', True)
            overlay.configure(bg='#0000FF', cursor='crosshair')
            overlay.focus_force()
            
            # Информационная метка
            info_label = tk.Label(overlay, 
                                 text="Щелкните по нужному окну\nНажмите ESC для отмены",
                                 bg='#0000FF', fg='white', font=('Arial', 16, 'bold'),
                                 relief='raised', bd=3)
            info_label.place(relx=0.5, rely=0.1, anchor=tk.CENTER)
            
            # Показываем подсказку о текущем окне при наведении
            hover_label = tk.Label(overlay, text="", bg='yellow', fg='black', 
                                  font=('Arial', 10), relief='solid', bd=1)
            
            def update_hover_label(event):
                try:
                    x, y = event.x_root, event.y_root
                    hwnd = win32gui.WindowFromPoint((x, y))
                    
                    # Получаем информацию об окне
                    window_title = win32gui.GetWindowText(hwnd)
                    
                    if window_title and win32gui.IsWindowVisible(hwnd):
                        try:
                            rect = win32gui.GetWindowRect(hwnd)
                            width = rect[2] - rect[0]
                            height = rect[3] - rect[1]
                            
                            # Получаем класс окна для дополнительной информации
                            class_name = win32gui.GetClassName(hwnd)
                            
                            hover_text = f"{window_title}\n{width}x{height} ({class_name})"
                            hover_label.config(text=hover_text)
                            hover_label.place(x=x+10, y=y+10)
                        except:
                            hover_label.config(text=window_title)
                            hover_label.place(x=x+10, y=y+10)
                    else:
                        hover_label.place_forget()
                except:
                    hover_label.place_forget()
            
            def on_click(event):
                try:
                    # Получаем координаты клика
                    x, y = event.x_root, event.y_root
                    
                    # Находим окно по координатам
                    hwnd = win32gui.WindowFromPoint((x, y))
                    window_title = win32gui.GetWindowText(hwnd)
                    
                    if window_title and win32gui.IsWindowVisible(hwnd):
                        # Получаем полную информацию об окне
                        rect = win32gui.GetWindowRect(hwnd)
                        width = rect[2] - rect[0]
                        height = rect[3] - rect[1]
                        
                        # Проверяем, что окно подходящего размера
                        if width < 50 or height < 50:
                            messagebox.showwarning("Предупреждение", 
                                                 "Выбранное окно слишком маленькое для записи")
                            return
                        
                        # Подсвечиваем выбранное окно
                        try:
                            # Мигаем окном
                            for _ in range(3):
                                win32gui.FlashWindow(hwnd, True)
                                time.sleep(0.1)
                        except:
                            pass
                        
                        # Получаем дополнительную информацию
                        process_name = "Unknown"
                        try:
                            import win32process
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                            if PSUTIL_AVAILABLE:
                                process = psutil.Process(pid)
                                process_name = process.name()
                        except:
                            process_name = "Unknown"
                        
                        # Сохраняем информацию
                        scene = self.scenes[self.current_scene_index]
                        scene.window_info = f"{window_title} [{process_name}] ({width}x{height})"
                        scene.window_rect = rect
                        scene.video_sources["window"] = True
                        
                        # Обновляем интерфейс
                        self.window_label.config(text=scene.window_info)
                        self.window_var.set(True)
                        self.on_source_change()
                        
                        self.status_label.config(text=f"Выбрано окно: {window_title}")
                        self.save_scenes()
                        
                        # Закрываем окна
                        overlay.destroy()
                        parent_dialog.destroy()
                        
                        messagebox.showinfo("Успех", f"Окно '{window_title}' выбрано для записи")
                    else:
                        messagebox.showwarning("Предупреждение", 
                                             "Выберите видимое окно с заголовком")
                    
                except Exception as e:
                    print(f"Ошибка при выборе окна: {e}")
                    messagebox.showerror("Ошибка", f"Не удалось выбрать окно: {e}")
                    overlay.destroy()
                    parent_dialog.deiconify()
            
            def cancel_selection(event):
                overlay.destroy()
                parent_dialog.deiconify()
            
            # Привязываем события
            overlay.bind('<Motion>', update_hover_label)
            overlay.bind('<Button-1>', on_click)
            overlay.bind('<Escape>', cancel_selection)
            overlay.focus_set()
            
            # Центрируем информационную метку
            overlay.update_idletasks()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка ручного выбора: {e}")
            parent_dialog.deiconify()

    def select_window_simple(self):
        """Простой и надежный способ выбора окна"""
        try:
            import win32gui
            
            # Создаем простое диалоговое окно
            dialog = tk.Toplevel(self.root)
            dialog.title("Выбор окна - упрощенный режим")
            dialog.geometry("400x200")
            dialog.configure(bg='#2d2d2d')
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Центрируем окно
            dialog.update_idletasks()
            x = (self.root.winfo_screenwidth() - dialog.winfo_width()) // 2
            y = (self.root.winfo_screenheight() - dialog.winfo_height()) // 2
            dialog.geometry(f"+{x}+{y}")
            
            # Инструкция
            instruction = tk.Label(dialog, 
                                  text="Нажмите кнопку ниже, затем щелкните по нужному окну.\n\nПрограмма найдет и выберет первое подходящее окно.",
                                  bg='#2d2d2d', fg='white', font=('Arial', 10), justify=tk.CENTER)
            instruction.pack(pady=20)
            
            def start_simple_selection():
                dialog.withdraw()
                
                # Даем пользователю время переключиться на нужное окно
                messagebox.showinfo("Подготовка", 
                                  "Нажмите OK, затем в течение 5 секунд переключитесь на окно, которое хотите записывать")
                
                time.sleep(5)  # Даем время на переключение
                
                try:
                    # Получаем активное окно
                    hwnd = win32gui.GetForegroundWindow()
                    window_title = win32gui.GetWindowText(hwnd)
                    
                    if window_title and win32gui.IsWindowVisible(hwnd):
                        rect = win32gui.GetWindowRect(hwnd)
                        
                        # Сохраняем информацию
                        scene = self.scenes[self.current_scene_index]
                        scene.window_info = f"{window_title} (активное окно)"
                        scene.window_rect = rect
                        scene.video_sources["window"] = True
                        
                        # Обновляем интерфейс
                        self.window_label.config(text=scene.window_info)
                        self.window_var.set(True)
                        self.on_source_change()
                        
                        self.status_label.config(text=f"Выбрано активное окно: {window_title}")
                        self.save_scenes()
                        
                        messagebox.showinfo("Успех", f"Окно '{window_title}' выбрано для записи")
                    else:
                        messagebox.showwarning("Ошибка", "Не удалось найти подходящее активное окно")
                        
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Ошибка выбора окна: {e}")
                
                dialog.destroy()
            
            # Фрейм для кнопок
            button_frame = tk.Frame(dialog, bg='#2d2d2d')
            button_frame.pack(pady=10)
            
            # Кнопка начала выбора
            select_btn = ttk.Button(button_frame, text="Выбрать активное окно", 
                                  command=start_simple_selection)
            select_btn.pack(side=tk.LEFT, padx=5)
            
            # Кнопка отмены
            cancel_btn = ttk.Button(button_frame, text="Отмена", command=dialog.destroy)
            cancel_btn.pack(side=tk.LEFT, padx=5)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось запустить выбор окна: {e}")
    
    def select_save_path(self):
        """Выбирает путь для сохранения записей"""
        path = filedialog.askdirectory(initialdir=self.save_path)
        if path:
            self.save_path = path
            self.save_settings()
            self.status_label.config(text=f"Путь сохранения: {path}")
    
    def show_hotkeys_settings(self):
        """Показывает настройки горячих клавиш"""
        messagebox.showinfo("Горячие клавиши", 
                           f"Текущие горячие клавиши:\n"
                           f"{self.hotkeys['start_recording']} - Начать запись\n"
                           f"{self.hotkeys['stop_recording']} - Остановить запись\n"
                           f"{self.hotkeys['toggle_pause']} - Пауза/Продолжить\n"
                           f"{self.hotkeys['toggle_fullscreen']} - Полноэкранный режим")
    
    def on_preview_click(self, event):
        """Обработчик клика по предпросмотру для перемещения текста"""
        if self.selected_text_index >= 0:
            scene = self.scenes[self.current_scene_index]
            text_obj = scene.text_objects[self.selected_text_index]
            
            # Преобразуем координаты клика в координаты предпросмотра (640x480)
            scale_x = 640 / self.preview_label.winfo_width()
            scale_y = 480 / self.preview_label.winfo_height()
            
            click_x = event.x * scale_x
            click_y = event.y * scale_y
            
            # Проверяем, был ли клик рядом с текстом
            text_rect = self.get_text_rect(text_obj)
            if text_rect and self.is_point_in_rect(click_x, click_y, text_rect):
                self.dragging = True
                self.drag_start_x = click_x
                self.drag_start_y = click_y
                self.current_drag_type = "text"
    
    def on_preview_drag(self, event):
        """Обработчик перемещения мыши при перетаскивании"""
        if self.dragging:
            scale_x = 640 / self.preview_label.winfo_width()
            scale_y = 480 / self.preview_label.winfo_height()
            
            current_x = event.x * scale_x
            current_y = event.y * scale_y
            
            if self.current_drag_type == "text" and self.selected_text_index >= 0:
                scene = self.scenes[self.current_scene_index]
                text_obj = scene.text_objects[self.selected_text_index]
                
                dx = current_x - self.drag_start_x
                dy = current_y - self.drag_start_y
                
                text_obj.x = max(0, min(640, text_obj.x + dx))
                text_obj.y = max(0, min(480, text_obj.y + dy))
                
                self.drag_start_x = current_x
                self.drag_start_y = current_y
                self.save_scenes()
    
    def on_preview_release(self, event):
        """Обработчик отпускания кнопки мыши"""
        self.dragging = False
        self.current_drag_type = None
    
    def on_preview_scroll(self, event):
        """Обработчик прокрутки колесика мыши для масштабирования текста"""
        if self.selected_text_index >= 0:
            scene = self.scenes[self.current_scene_index]
            text_obj = scene.text_objects[self.selected_text_index]
            
            if event.delta > 0:
                text_obj.scale = min(3.0, text_obj.scale + 0.1)
            else:
                text_obj.scale = max(0.5, text_obj.scale - 0.1)
            
            self.save_scenes()
    
    def get_text_rect(self, text_obj):
        """Возвращает прямоугольник, занимаемый текстом"""
        try:
            # Создаем временное изображение для измерения текста
            temp_img = Image.new('RGB', (640, 480))
            draw = ImageDraw.Draw(temp_img)
            font_size = int(text_obj.font_size * text_obj.scale)
            font = ImageFont.truetype("arial.ttf", font_size)
            
            bbox = draw.textbbox((text_obj.x, text_obj.y), text_obj.text, font=font)
            return bbox
        except:
            return None
    
    def is_point_in_rect(self, x, y, rect):
        """Проверяет, находится ли точка внутри прямоугольника"""
        return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]
    
    def toggle_recording(self):
        """Переключает состояние записи"""
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def start_recording(self):
        """Начинает запись"""
        try:
            self.is_recording = True
            self.is_paused = False
            self.recording_start_time = time.time()
            self.total_paused_time = 0
            
            # Создаем имя файла с временной меткой
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"record_{timestamp}.avi"
            filepath = os.path.join(self.save_path, filename)
            
            # Настройки видео
            fps = 30
            frame_size = (1920, 1080)  # Full HD
            
            # Создаем видеописатель
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            self.video_writer = cv2.VideoWriter(filepath, fourcc, fps, frame_size)
            
            if self.video_writer is None:
                raise Exception("Не удалось создать видеофайл")
            
            # Начинаем запись аудио, если включено
            if self.scenes[self.current_scene_index].audio_enabled:
                self.audio_stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=2,
                    callback=self.audio_callback
                )
                self.audio_stream.start()
            
            # Запускаем поток записи
            self.recording_thread = threading.Thread(target=self.recording_worker, daemon=True)
            self.recording_thread.start()
            
            # Обновляем интерфейс
            self.record_button.config(text=f"■ ОСТАНОВИТЬ ({self.hotkeys['stop_recording']})")
            self.pause_button.config(state="normal")
            self.status_label.config(text=f"Запись: {filename}", foreground="#e74c3c")
            
            # Запускаем таймер
            self.update_timer()
            
        except Exception as e:
            self.is_recording = False
            messagebox.showerror("Ошибка", f"Не удалось начать запись: {str(e)}")
            self.status_label.config(text="Ошибка начала записи", foreground="red")
    
    def stop_recording(self):
        """Останавливает запись"""
        self.is_recording = False
        
        # Останавливаем аудиопоток
        if self.audio_stream is not None:
            self.audio_stream.stop()
            self.audio_stream.close()
            self.audio_stream = None
        
        # Закрываем видеописатель
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None
        
        # Останавливаем таймер
        if self.recording_timer:
            self.root.after_cancel(self.recording_timer)
            self.recording_timer = None
        
        # Обновляем интерфейс
        self.record_button.config(text=f"● НАЧАТЬ ЗАПИСЬ ({self.hotkeys['start_recording']})")
        self.pause_button.config(state="disabled", text="⏸ ПАУЗА")
        self.timer_label.config(text="00:00:00")
        self.status_label.config(text="Запись завершена", foreground="#2ecc71")
    
    def toggle_pause(self):
        """Переключает паузу"""
        if not self.is_recording:
            return
            
        self.is_paused = not self.is_paused
        
        if self.is_paused:
            self.pause_start_time = time.time()
            self.pause_button.config(text="▶ ПРОДОЛЖИТЬ")
            self.status_label.config(text="Запись на паузе", foreground="#f39c12")
        else:
            self.total_paused_time += time.time() - self.pause_start_time
            self.pause_button.config(text="⏸ ПАУЗА")
            self.status_label.config(text="Запись...", foreground="#e74c3c")
    
    def audio_callback(self, indata, frames, time, status):
        """Callback функция для записи аудио"""
        if status:
            print(f"Аудио ошибка: {status}")
        self.audio_data.put(indata.copy())
    
    def recording_worker(self):
        """Рабочая функция для потока записи"""
        while self.is_recording:
            if not self.is_paused:
                try:
                    # Захватываем экран или окно
                    frame = self.capture_screen()
                    
                    if frame is not None:
                        # Изменяем размер до Full HD (если необходимо)
                        if frame.shape[0] != 1080 or frame.shape[1] != 1920:
                            frame = cv2.resize(frame, (1920, 1080))
                        
                        # Накладываем текстовые объекты
                        scene = self.scenes[self.current_scene_index]
                        frame = self.apply_text_overlays(frame, scene.text_objects)
                        
                        # Добавляем индикатор записи
                        if self.is_recording:
                            cv2.putText(frame, "REC", (10, 30), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                            if self.is_paused:
                                cv2.putText(frame, "PAUSED", (10, 60), 
                                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                        
                        # Записываем кадр
                        if self.video_writer is not None:
                            self.video_writer.write(frame)
                    
                    # Небольшая задержка для контроля FPS
                    time.sleep(0.03)  # ~30 FPS
                    
                except Exception as e:
                    print(f"Ошибка записи кадра: {e}")
                    time.sleep(0.1)
            else:
                time.sleep(0.1)  # Пауза
    
    def update_timer(self):
        """Обновляет таймер записи"""
        if self.is_recording:
            if not self.is_paused:
                current_time = time.time()
                elapsed = current_time - self.recording_start_time - self.total_paused_time
                
                hours = int(elapsed // 3600)
                minutes = int((elapsed % 3600) // 60)
                seconds = int(elapsed % 60)
                
                time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                self.timer_label.config(text=time_str)
            
            self.recording_timer = self.root.after(1000, self.update_timer)
    
    def safe_exit(self):
        """Безопасный выход из приложения"""
        if self.is_recording:
            if messagebox.askyesno("Подтверждение", 
                                  "Запись все еще идет. Вы уверены, что хотите выйти?"):
                self.stop_recording()
                self.cleanup()
                self.root.quit()
        else:
            self.cleanup()
            self.root.quit()
    
    def cleanup(self):
        """Очистка ресурсов"""
        self.stop_preview_thread()
        
        # Закрываем камеру
        if self.camera is not None:
            self.camera.release()
        
        # Останавливаем аудиопоток
        if self.audio_stream is not None:
            self.audio_stream.stop()
            self.audio_stream.close()
        
        # Сохраняем настройки и сцены
        self.save_settings()
        self.save_scenes()
        
        # Пытаемся отключить глобальные горячие клавиши
        try:
            import keyboard
            keyboard.unhook_all()
        except:
            pass

def main():
    """Основная функция приложения"""
    try:
        root = tk.Tk()
        app = RecordStudio(root)
        
        # Обработка закрытия окна
        root.protocol("WM_DELETE_WINDOW", app.safe_exit)
        
        # Запускаем обновление интерфейса
        app.update_scenes_list()
        app.load_scene_settings()
        
        root.mainloop()
        
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        messagebox.showerror("Ошибка", f"Произошла критическая ошибка: {str(e)}")

if __name__ == "__main__":
    main()
