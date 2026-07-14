from flask import Flask, request, jsonify
import requests
import time
import threading
import os
import json
import logging
from datetime import datetime, timedelta
import re

app = Flask(__name__)

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8589215471:AAFV7jemD5gUeYvmQVynRxGSfBOylMOx3LA"
CHANNEL_ID = "@Cryyptoschool"

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище данных пользователей
user_sessions = {}
user_templates = {}
scheduled_tasks = {}
auto_posts = {}  # user_id: [{"datetime": "2026-07-15 09:00", "text": "...", "active": True}]

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С TELEGRAM ==========
def send_telegram(method, params):
    """Отправка запроса к Telegram API"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        response = requests.post(url, json=params, timeout=30)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка при запросе к Telegram: {e}")
        return {"ok": False, "error": str(e)}

def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    """Отправка сообщения пользователю"""
    params = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup)
    return send_telegram("sendMessage", params)

def edit_message(chat_id, message_id, text, parse_mode="HTML"):
    """Редактирование сообщения"""
    return send_telegram("editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode
    })

# ========== КЛАВИАТУРЫ ==========
def get_main_menu():
    return {
        "inline_keyboard": [
            [{"text": "📝 Публикация поста", "callback_data": "publish_post"}],
            [{"text": "📅 Автопубликация", "callback_data": "auto_publish"}],
            [{"text": "✏️ Изменить шаблон автозамены", "callback_data": "change_template"}],
            [{"text": "ℹ️ Помощь", "callback_data": "help"}]
        ]
    }

def get_back_menu():
    return {
        "inline_keyboard": [
            [{"text": "🔙 Назад в меню", "callback_data": "back_to_menu"}]
        ]
    }

def get_auto_publish_menu():
    return {
        "inline_keyboard": [
            [{"text": "➕ Добавить автопубликацию", "callback_data": "add_auto_publish"}],
            [{"text": "🗑️ Удалить автопубликацию", "callback_data": "delete_auto_publish"}],
            [{"text": "📋 Список автопубликаций", "callback_data": "list_auto_publish"}],
            [{"text": "🔙 Назад в меню", "callback_data": "back_to_menu"}]
        ]
    }

# ========== ФУНКЦИИ ДЛЯ АВТОПУБЛИКАЦИЙ ==========
def format_auto_posts_list(user_id):
    """Форматирует список автопубликаций для отображения"""
    posts = auto_posts.get(user_id, [])
    if not posts:
        return "📭 У вас пока нет запланированных автопубликаций."
    
    text = "📋 <b>Ваши запланированные автопубликации:</b>\n\n"
    for i, post in enumerate(posts, 1):
        status = "✅ Активна" if post.get("active", True) else "⏸️ Приостановлена"
        # Преобразуем дату для красивого отображения
        try:
            dt = datetime.strptime(post['datetime'], "%Y-%m-%d %H:%M")
            dt_str = dt.strftime("%d.%m.%Y в %H:%M")
        except:
            dt_str = post['datetime']
        text += f"<b>{i}.</b> ⏰ {dt_str} | {status}\n"
        text += f"📝 <i>{post['text'][:50]}{'...' if len(post['text']) > 50 else ''}</i>\n\n"
    return text

def check_and_send_auto_posts():
    """Фоновый поток для проверки и отправки автопубликаций"""
    while True:
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            for user_id, posts in auto_posts.items():
                for post in posts:
                    if post.get("active", True) and post.get("datetime") == current_time:
                        # Отправка поста в канал
                        result = send_telegram("sendMessage", {
                            "chat_id": CHANNEL_ID,
                            "text": post["text"],
                            "parse_mode": "HTML"
                        })
                        if result.get("ok"):
                            logger.info(f"✅ Автопубликация для пользователя {user_id} отправлена в {current_time}")
                            # Деактивируем автопубликацию после отправки (одноразовая)
                            post["active"] = False
                            # Уведомляем пользователя
                            send_message(user_id,
                                f"✅ <b>Автопубликация выполнена!</b>\n\n"
                                f"⏰ Время: {current_time}\n"
                                f"📝 Текст: {post['text'][:100]}\n\n"
                                f"🔄 Автопубликация деактивирована (одноразовая).",
                                reply_markup=get_auto_publish_menu()
                            )
                        else:
                            logger.error(f"❌ Ошибка автопубликации для {user_id}: {result}")
            time.sleep(30)  # Проверка каждые 30 секунд
        except Exception as e:
            logger.error(f"Ошибка в потоке автопубликаций: {e}")
            time.sleep(60)

# Запуск фонового потока для автопубликаций
auto_publish_thread = threading.Thread(target=check_and_send_auto_posts, daemon=True)
auto_publish_thread.start()

# ========== ОБРАБОТЧИКИ ==========
def handle_start(chat_id, user_id):
    """Обработчик команды /start"""
    user_sessions[user_id] = {"step": "menu"}
    
    if user_id not in user_templates:
        user_templates[user_id] = "⚠️ ВНИМАНИЕ! Этот пост был автоматически заменён по истечении времени."
    
    if user_id not in auto_posts:
        auto_posts[user_id] = []
    
    text = (
        f"🌟 Добро пожаловать! 🌟\n\n"
        f"🤖 Я бот для публикации постов в канал с автоматической заменой текста.\n\n"
        f"📌 <b>Что я умею:</b>\n"
        f"• Публиковать посты в канал\n"
        f"• Автоматически заменять текст поста через заданное время\n"
        f"• Настраивать шаблон для автозамены\n"
        f"• Одноразовые автопубликации в заданное время"
    )
    
    send_message(chat_id, text, reply_markup=get_main_menu())

def handle_callback_query(callback_data, chat_id, user_id, message_id):
    """Обработка нажатий на кнопки"""
    if user_id not in user_sessions:
        user_sessions[user_id] = {"step": "menu"}
    
    # Возврат в главное меню
    if callback_data == "back_to_menu":
        user_sessions[user_id]["step"] = "menu"
        send_message(chat_id, "🌟 <b>Главное меню</b> 🌟", reply_markup=get_main_menu())
        return
    
    # Помощь
    if callback_data == "help":
        help_text = (
            "🤖 <b>Инструкция по использованию</b> 🤖\n\n"
            "1️⃣ <b>Публикация поста</b>\n"
            "• Нажмите кнопку 'Публикация поста'\n"
            "• Отправьте текст поста\n"
            "• Укажите время в минутах до автозамены\n\n"
            "2️⃣ <b>Автопубликация</b>\n"
            "• Нажмите кнопку 'Автопубликация'\n"
            "• Выберите 'Добавить автопубликацию'\n"
            "• Отправьте текст поста\n"
            "• Укажите дату и время в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
            "• Пост будет опубликован один раз в это время\n\n"
            "3️⃣ <b>Изменение шаблона автозамены</b>\n"
            "• Нажмите кнопку 'Изменить шаблон автозамены'\n"
            "• Отправьте новый текст шаблона"
        )
        send_message(chat_id, help_text, reply_markup=get_back_menu(), parse_mode="HTML")
        return
    
    # Публикация поста
    if callback_data == "publish_post":
        user_sessions[user_id]["step"] = "waiting_post_text"
        send_message(chat_id, "📝 <b>Напишите текст поста</b>", reply_markup=get_back_menu())
        return
    
    # Изменение шаблона
    if callback_data == "change_template":
        user_sessions[user_id]["step"] = "waiting_new_template"
        current_template = user_templates.get(user_id, "⚠️ ВНИМАНИЕ! Этот пост был автоматически заменён по истечении времени.")
        send_message(chat_id, 
            f"✏️ <b>Напишите новый шаблон для автозамены</b>\n\n"
            f"📋 <b>Текущий шаблон:</b>\n"
            f"<i>{current_template[:150]}</i>", 
            reply_markup=get_back_menu()
        )
        return
    
    # ====== АВТОПУБЛИКАЦИИ ======
    if callback_data == "auto_publish":
        user_sessions[user_id]["step"] = "auto_publish_menu"
        send_message(chat_id, 
            "📅 <b>Управление автопубликациями</b>\n\n"
            f"{format_auto_posts_list(user_id)}",
            reply_markup=get_auto_publish_menu()
        )
        return
    
    if callback_data == "add_auto_publish":
        user_sessions[user_id]["step"] = "waiting_auto_post_text"
        send_message(chat_id, 
            "📝 <b>Напишите текст поста</b>\n"
            "который будет опубликован один раз в указанное время.",
            reply_markup=get_back_menu()
        )
        return
    
    if callback_data == "list_auto_publish":
        send_message(chat_id, format_auto_posts_list(user_id), reply_markup=get_auto_publish_menu())
        return
    
    if callback_data == "delete_auto_publish":
        posts = auto_posts.get(user_id, [])
        if not posts:
            send_message(chat_id, "📭 У вас нет запланированных автопубликаций.", reply_markup=get_auto_publish_menu())
            return
        
        # Формируем клавиатуру со списком автопубликаций для удаления
        keyboard = []
        for i, post in enumerate(posts, 1):
            status = "✅" if post.get("active", True) else "⏸️"
            try:
                dt = datetime.strptime(post['datetime'], "%Y-%m-%d %H:%M")
                dt_str = dt.strftime("%d.%m %H:%M")
            except:
                dt_str = post['datetime']
            keyboard.append([{"text": f"{status} {i}. {dt_str} - {post['text'][:15]}...", "callback_data": f"delete_{i-1}"}])
        keyboard.append([{"text": "🔙 Назад", "callback_data": "auto_publish"}])
        
        send_message(chat_id, 
            "🗑️ <b>Выберите автопубликацию для удаления:</b>",
            reply_markup={"inline_keyboard": keyboard}
        )
        return
    
    # Обработка удаления конкретной автопубликации
    if callback_data.startswith("delete_"):
        try:
            index = int(callback_data.split("_")[1])
            posts = auto_posts.get(user_id, [])
            if 0 <= index < len(posts):
                deleted = posts.pop(index)
                send_message(chat_id, 
                    f"✅ <b>Автопубликация удалена!</b>\n\n"
                    f"⏰ Время: {deleted['datetime']}\n"
                    f"📝 Текст: {deleted['text'][:100]}",
                    reply_markup=get_auto_publish_menu()
                )
            else:
                send_message(chat_id, "❌ Автопубликация не найдена.", reply_markup=get_auto_publish_menu())
        except Exception as e:
            send_message(chat_id, f"❌ Ошибка: {e}", reply_markup=get_auto_publish_menu())
        return

def handle_text_message(chat_id, user_id, text):
    """Обработка текстовых сообщений"""
    if user_id not in user_sessions:
        user_sessions[user_id] = {"step": "menu"}
        send_message(chat_id, "Используйте /start для начала работы", reply_markup=get_main_menu())
        return
    
    step = user_sessions[user_id].get("step", "menu")
    
    # ====== ОБЫЧНАЯ ПУБЛИКАЦИЯ ======
    if step == "waiting_post_text":
        user_sessions[user_id]["post_text"] = text
        user_sessions[user_id]["step"] = "waiting_replace_time"
        send_message(chat_id, "⏰ <b>Напишите время в минутах</b>", reply_markup=get_back_menu())
        return
    
    if step == "waiting_replace_time":
        try:
            minutes = int(text)
            if minutes <= 0:
                raise ValueError("Время должно быть больше 0")
            
            post_text = user_sessions[user_id].get("post_text", "")
            
            # Отправка в канал
            result = send_telegram("sendMessage", {
                "chat_id": CHANNEL_ID,
                "text": post_text,
                "parse_mode": "HTML"
            })
            
            if result.get("ok"):
                msg_id = result["result"]["message_id"]
                send_message(chat_id, 
                    f"✅ <b>Пост опубликован!</b>\n⏰ Автозамена через {minutes} минут(ы)",
                    reply_markup=get_main_menu()
                )
                
                # Запуск задачи замены в отдельном потоке
                template = user_templates.get(user_id, "⚠️ ВНИМАНИЕ! Этот пост был автоматически заменён по истечении времени.")
                
                def replace_post():
                    time.sleep(minutes * 60)
                    try:
                        edit_message(CHANNEL_ID, msg_id, template)
                        logger.info(f"Пост {msg_id} заменён на шаблон")
                    except Exception as e:
                        logger.error(f"Ошибка замены поста: {e}")
                
                thread = threading.Thread(target=replace_post)
                thread.daemon = True
                thread.start()
                
                user_sessions[user_id]["step"] = "menu"
            else:
                send_message(chat_id, 
                    f"❌ Ошибка публикации: {result.get('description', 'Неизвестная ошибка')}",
                    reply_markup=get_main_menu()
                )
                
        except ValueError:
            send_message(chat_id, "❌ Введите положительное число (минуты)", reply_markup=get_back_menu())
        return
    
    # ====== АВТОПУБЛИКАЦИЯ (ОДНОРАЗОВАЯ) ======
    if step == "waiting_auto_post_text":
        user_sessions[user_id]["auto_post_text"] = text
        user_sessions[user_id]["step"] = "waiting_auto_post_datetime"
        send_message(chat_id, 
            "⏰ <b>Напишите дату и время в формате:</b>\n"
            "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
            "📌 Например:\n"
            "<code>15.07.2026 09:00</code> — 15 июля 2026 в 9:00\n"
            "<code>20.07.2026 18:30</code> — 20 июля 2026 в 18:30\n\n"
            "⚠️ Время в 24-часовом формате!\n"
            "📌 Пост будет опубликован один раз в это время.",
            reply_markup=get_back_menu(),
            parse_mode="HTML"
        )
        return
    
    if step == "waiting_auto_post_datetime":
        # Проверка формата даты и времени
        if not re.match(r'^(\d{2})\.(\d{2})\.(\d{4}) (\d{2}):(\d{2})$', text):
            send_message(chat_id, 
                "❌ <b>Неверный формат!</b>\n\n"
                "Используйте формат <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
                "Например: <code>15.07.2026 09:00</code>",
                reply_markup=get_back_menu(),
                parse_mode="HTML"
            )
            return
        
        try:
            # Преобразуем введённую дату в формат YYYY-MM-DD HH:MM
            dt_obj = datetime.strptime(text, "%d.%m.%Y %H:%M")
            dt_str = dt_obj.strftime("%Y-%m-%d %H:%M")
            
            # Проверяем, что дата не в прошлом
            if dt_obj <= datetime.now():
                send_message(chat_id, 
                    "⚠️ <b>Дата и время должны быть в будущем!</b>\n\n"
                    "Пожалуйста, укажите время, которое ещё не наступило.",
                    reply_markup=get_back_menu(),
                    parse_mode="HTML"
                )
                return
            
            post_text = user_sessions[user_id].get("auto_post_text", "")
            
            # Сохраняем автопубликацию
            if user_id not in auto_posts:
                auto_posts[user_id] = []
            
            auto_posts[user_id].append({
                "datetime": dt_str,
                "text": post_text,
                "active": True
            })
            
            # Красивое отображение даты для пользователя
            display_dt = dt_obj.strftime("%d.%m.%Y в %H:%M")
            
            send_message(chat_id, 
                f"✅ <b>Автопубликация добавлена!</b> ✅\n\n"
                f"⏰ Время: <code>{display_dt}</code>\n"
                f"📝 Текст: {post_text[:200]}{'...' if len(post_text) > 200 else ''}\n\n"
                f"📌 Пост будет опубликован один раз в указанное время.",
                reply_markup=get_auto_publish_menu(),
                parse_mode="HTML"
            )
            
            user_sessions[user_id]["step"] = "auto_publish_menu"
            
        except ValueError as e:
            send_message(chat_id, 
                f"❌ <b>Ошибка!</b>\n\n"
                f"Неверный формат даты. Используйте <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
                reply_markup=get_back_menu(),
                parse_mode="HTML"
            )
        return
    
    # ====== ИЗМЕНЕНИЕ ШАБЛОНА ======
    if step == "waiting_new_template":
        user_templates[user_id] = text
        send_message(chat_id, f"✅ <b>Шаблон обновлён!</b>", reply_markup=get_main_menu())
        user_sessions[user_id]["step"] = "menu"
        return
    
    send_message(chat_id, "Используйте кнопки меню", reply_markup=get_main_menu())

# ========== ВЕБ-СЕРВЕР ==========
@app.route("/", methods=["GET"])
def index():
    return "Бот работает на Render!", 200

@app.route("/", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        if not data:
            return "OK", 200
        
        # Обработка сообщений
        if "message" in data:
            msg = data["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]
            text = msg.get("text", "")
            
            if text == "/start":
                handle_start(chat_id, user_id)
            elif not text.startswith("/"):
                handle_text_message(chat_id, user_id, text)
        
        # Обработка нажатий на кнопки
        elif "callback_query" in data:
            callback = data["callback_query"]
            callback_data = callback.get("data", "")
            chat_id = callback["message"]["chat"]["id"]
            user_id = callback["from"]["id"]
            message_id = callback["message"]["message_id"]
            
            handle_callback_query(callback_data, chat_id, user_id, message_id)
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
        return "Error", 500

@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    webhook_url = "https://pereprod.onrender.com/"
    result = send_telegram("setWebhook", {"url": webhook_url})
    return f"Webhook set! Ответ: {result}", 200

@app.route("/delete_webhook", methods=["GET"])
def delete_webhook():
    result = send_telegram("deleteWebhook", {})
    return f"Webhook deleted! Ответ: {result}", 200

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
