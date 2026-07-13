from flask import Flask, request, jsonify
import requests
import time
import threading
import os
import json
import logging

app = Flask(__name__)

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8589215471:AAFV7jemD5gUeYvmQVynRxGSfBOylMOx3LA"
CHANNEL_ID = "Cryyptoschool"

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище данных пользователей
user_sessions = {}
user_templates = {}
scheduled_tasks = {}

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

# ========== ОБРАБОТЧИКИ ==========
def handle_start(chat_id, user_id):
    """Обработчик команды /start"""
    user_sessions[user_id] = {"step": "menu"}
    
    if user_id not in user_templates:
        user_templates[user_id] = "⚠️ ВНИМАНИЕ! Этот пост был автоматически заменён по истечении времени."
    
    text = (
        f"🌟 Добро пожаловать! 🌟\n\n"
        f"🤖 Я бот для публикации постов в канал с автоматической заменой текста.\n\n"
        f"📌 <b>Что я умею:</b>\n"
        f"• Публиковать посты в канал\n"
        f"• Автоматически заменять текст поста через заданное время\n"
        f"• Настраивать шаблон для автозамены"
    )
    
    send_message(chat_id, text, reply_markup=get_main_menu())

def handle_callback_query(callback_data, chat_id, user_id, message_id):
    """Обработка нажатий на кнопки"""
    if user_id not in user_sessions:
        user_sessions[user_id] = {"step": "menu"}
    
    if callback_data == "back_to_menu":
        user_sessions[user_id]["step"] = "menu"
        send_message(chat_id, "🌟 <b>Главное меню</b> 🌟", reply_markup=get_main_menu())
        return
    
    if callback_data == "help":
        help_text = (
            "🤖 <b>Инструкция по использованию</b> 🤖\n\n"
            "1️⃣ <b>Публикация поста</b>\n"
            "• Нажмите кнопку 'Публикация поста'\n"
            "• Отправьте текст поста\n"
            "• Укажите время в минутах до автозамены\n\n"
            "2️⃣ <b>Изменение шаблона автозамены</b>\n"
            "• Нажмите кнопку 'Изменить шаблон автозамены'\n"
            "• Отправьте новый текст шаблона"
        )
        send_message(chat_id, help_text, reply_markup=get_back_menu())
        return
    
    if callback_data == "publish_post":
        user_sessions[user_id]["step"] = "waiting_post_text"
        send_message(chat_id, "📝 <b>Напишите текст поста</b>", reply_markup=get_back_menu())
        return
    
    if callback_data == "change_template":
        user_sessions[user_id]["step"] = "waiting_new_template"
        current_template = user_templates.get(user_id, "⚠️ ВНИМАНИЕ! Этот пост был автоматически заменён по истечении времени.")
        send_message(chat_id, 
            f"✏️ <b>Напишите новый шаблон для автозамены</b>\n\n"
            f"📋 <b>Текущий шаблон:</b>\n"
            f"<i>{current_template[:150]}</i>", 
            reply_markup=get_back_menu()
        )

def handle_text_message(chat_id, user_id, text):
    """Обработка текстовых сообщений"""
    if user_id not in user_sessions:
        user_sessions[user_id] = {"step": "menu"}
        send_message(chat_id, "Используйте /start для начала работы", reply_markup=get_main_menu())
        return
    
    step = user_sessions[user_id].get("step", "menu")
    
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
    webhook_url = "https://snapsell-esys.onrender.com/"
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
