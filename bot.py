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
auto_posts = {}  # user_id: [{"type": "daily"/"once", "time": "HH:MM" или "YYYY-MM-DD HH:MM", "text": "...", "active": True}]

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С TELEGRAM ==========
def send_telegram(method, params):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        response = requests.post(url, json=params, timeout=30)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка при запросе к Telegram: {e}")
        return {"ok": False, "error": str(e)}

def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    params = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup)
    return send_telegram("sendMessage", params)

def edit_message(chat_id, message_id, text, parse_mode="HTML"):
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
            [{"text": "📅 Ежедневная", "callback_data": "add_daily_auto_publish"}],
            [{"text": "📅 Одноразовая", "callback_data": "add_once_auto_publish"}],
            [{"text": "📋 Мои автопубликации", "callback_data": "list_auto_publish"}],
            [{"text": "🔙 Назад в меню", "callback_data": "back_to_menu"}]
        ]
    }

# ========== ФУНКЦИИ ДЛЯ АВТОПУБЛИКАЦИЙ ==========
def format_auto_posts_list(user_id):
    posts = auto_posts.get(user_id, [])
    if not posts:
        return "📭 У вас нет запланированных автопубликаций."
    
    text = "📋 <b>Ваши автопубликации:</b>\n\n"
    for i, post in enumerate(posts, 1):
        status = "✅" if post.get("active", True) else "⏸️"
        if post["type"] == "daily":
            time_info = f"⏰ {post['time']} (ежедневно)"
        else:
            try:
                dt = datetime.strptime(post['time'], "%Y-%m-%d %H:%M")
                time_info = f"⏰ {dt.strftime('%d.%m.%Y в %H:%M')} (одноразово)"
            except:
                time_info = f"⏰ {post['time']} (одноразово)"
        text += f"{status} <b>{i}.</b> {time_info}\n"
        text += f"📝 <i>{post['text'][:50]}{'...' if len(post['text']) > 50 else ''}</i>\n\n"
    return text

def check_and_send_auto_posts():
    while True:
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            current_datetime = now.strftime("%Y-%m-%d %H:%M")
            
            for user_id, posts in auto_posts.items():
                for post in posts:
                    if not post.get("active", True):
                        continue
                    
                    if post["type"] == "daily":
                        if post.get("time") == current_time:
                            result = send_telegram("sendMessage", {
                                "chat_id": CHANNEL_ID,
                                "text": post["text"],
                                "parse_mode": "HTML"
                            })
                            if result.get("ok"):
                                logger.info(f"✅ Ежедневная автопубликация для {user_id} отправлена в {current_time}")
                            else:
                                logger.error(f"❌ Ошибка ежедневной автопубликации: {result}")
                    
                    elif post["type"] == "once":
                        if post.get("time") == current_datetime:
                            result = send_telegram("sendMessage", {
                                "chat_id": CHANNEL_ID,
                                "text": post["text"],
                                "parse_mode": "HTML"
                            })
                            if result.get("ok"):
                                logger.info(f"✅ Одноразовая автопубликация для {user_id} отправлена в {current_datetime}")
                                post["active"] = False
                                send_message(user_id,
                                    f"✅ <b>Одноразовая автопубликация выполнена!</b>\n\n"
                                    f"⏰ Время: {current_datetime}\n"
                                    f"📝 Текст: {post['text'][:100]}",
                                    reply_markup=get_main_menu()
                                )
                            else:
                                logger.error(f"❌ Ошибка одноразовой автопубликации: {result}")
            time.sleep(30)
        except Exception as e:
            logger.error(f"Ошибка в потоке автопубликаций: {e}")
            time.sleep(60)

auto_publish_thread = threading.Thread(target=check_and_send_auto_posts, daemon=True)
auto_publish_thread.start()

# ========== ОБРАБОТЧИКИ ==========
def handle_start(chat_id, user_id):
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
        f"• Ежедневные и одноразовые автопубликации"
    )
    
    send_message(chat_id, text, reply_markup=get_main_menu())

def handle_callback_query(callback_data, chat_id, user_id, message_id):
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
            "2️⃣ <b>Автопубликация</b>\n"
            "• Нажмите кнопку 'Автопубликация'\n"
            "• Выберите 'Ежедневная' или 'Одноразовая'\n"
            "• Отправьте текст поста\n"
            "• Укажите время\n\n"
            "3️⃣ <b>Изменение шаблона автозамены</b>\n"
            "• Нажмите кнопку 'Изменить шаблон автозамены'\n"
            "• Отправьте новый текст шаблона"
        )
        send_message(chat_id, help_text, reply_markup=get_back_menu(), parse_mode="HTML")
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
        return
    
    # ====== АВТОПУБЛИКАЦИИ ======
    if callback_data == "auto_publish":
        user_sessions[user_id]["step"] = "auto_publish_menu"
        send_message(chat_id, 
            "📅 <b>Выберите тип автопубликации:</b>\n\n"
            f"{format_auto_posts_list(user_id)}",
            reply_markup=get_auto_publish_menu()
        )
        return
    
    if callback_data == "add_daily_auto_publish":
        user_sessions[user_id]["auto_type"] = "daily"
        user_sessions[user_id]["step"] = "waiting_auto_post_text"
        send_message(chat_id, 
            "📝 <b>Напишите текст поста</b>\n"
            "который будет публиковаться <b>каждый день</b> в указанное время.",
            reply_markup=get_back_menu()
        )
        return
    
    if callback_data == "add_once_auto_publish":
        user_sessions[user_id]["auto_type"] = "once"
        user_sessions[user_id]["step"] = "waiting_auto_post_text"
        send_message(chat_id, 
            "📝 <b>Напишите текст поста</b>\n"
            "который будет опубликован <b>один раз</b> в указанную дату и время.",
            reply_markup=get_back_menu()
        )
        return
    
    if callback_data == "list_auto_publish":
        posts = auto_posts.get(user_id, [])
        if not posts:
            send_message(chat_id, "📭 У вас нет запланированных автопубликаций.", reply_markup=get_auto_publish_menu())
            return
        
        keyboard = []
        for i, post in enumerate(posts, 1):
            status = "✅" if post.get("active", True) else "⏸️"
            if post["type"] == "daily":
                label = f"{status} {i}. Ежедневно в {post['time']}"
            else:
                try:
                    dt = datetime.strptime(post['time'], "%Y-%m-%d %H:%M")
                    label = f"{status} {i}. {dt.strftime('%d.%m %H:%M')} (разово)"
                except:
                    label = f"{status} {i}. {post['time']} (разово)"
            keyboard.append([{"text": label, "callback_data": f"show_{i-1}"}])
        keyboard.append([{"text": "🔙 Назад", "callback_data": "auto_publish"}])
        
        send_message(chat_id, 
            "📋 <b>Ваши автопубликации (нажмите для удаления):</b>",
            reply_markup={"inline_keyboard": keyboard}
        )
        return
    
    if callback_data.startswith("show_"):
        try:
            index = int(callback_data.split("_")[1])
            posts = auto_posts.get(user_id, [])
            if 0 <= index < len(posts):
                post = posts[index]
                if post["type"] == "daily":
                    time_info = f"Ежедневно в {post['time']}"
                else:
                    try:
                        dt = datetime.strptime(post['time'], "%Y-%m-%d %H:%M")
                        time_info = f"Одноразово {dt.strftime('%d.%m.%Y в %H:%M')}"
                    except:
                        time_info = f"Одноразово {post['time']}"
                
                keyboard = [
                    [{"text": "🗑️ Удалить", "callback_data": f"delete_{index}"}],
                    [{"text": "🔙 Назад к списку", "callback_data": "list_auto_publish"}]
                ]
                
                send_message(chat_id,
                    f"📋 <b>Автопубликация #{index + 1}</b>\n\n"
                    f"📌 Тип: {time_info}\n"
                    f"📝 Текст: {post['text']}\n\n"
                    f"Статус: {'✅ Активна' if post.get('active', True) else '⏸️ Выполнена'}",
                    reply_markup={"inline_keyboard": keyboard}
                )
            else:
                send_message(chat_id, "❌ Автопубликация не найдена.", reply_markup=get_auto_publish_menu())
        except Exception as e:
            send_message(chat_id, f"❌ Ошибка: {e}", reply_markup=get_auto_publish_menu())
        return
    
    if callback_data.startswith("delete_"):
        try:
            index = int(callback_data.split("_")[1])
            posts = auto_posts.get(user_id, [])
            if 0 <= index < len(posts):
                deleted = posts.pop(index)
                send_message(chat_id, 
                    f"✅ <b>Автопубликация удалена!</b>",
                    reply_markup=get_auto_publish_menu()
                )
            else:
                send_message(chat_id, "❌ Автопубликация не найдена.", reply_markup=get_auto_publish_menu())
        except Exception as e:
            send_message(chat_id, f"❌ Ошибка: {e}", reply_markup=get_auto_publish_menu())
        return

def handle_text_message(chat_id, user_id, text):
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
    
    # ====== АВТОПУБЛИКАЦИЯ ======
    if step == "waiting_auto_post_text":
        user_sessions[user_id]["auto_post_text"] = text
        auto_type = user_sessions[user_id].get("auto_type", "daily")
        
        if auto_type == "daily":
            user_sessions[user_id]["step"] = "waiting_auto_post_time"
            send_message(chat_id, 
                "⏰ <b>Напишите время в формате ЧЧ:ММ</b>\n"
                "Например: <code>09:00</code> — пост будет публиковаться каждый день в 9:00\n\n"
                "⚠️ Время в 24-часовом формате!",
                reply_markup=get_back_menu(),
                parse_mode="HTML"
            )
        else:
            user_sessions[user_id]["step"] = "waiting_auto_post_datetime"
            send_message(chat_id, 
                "⏰ <b>Напишите дату и время в формате:</b>\n"
                "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
                "📌 Например: <code>15.07.2026 09:00</code>\n"
                "Пост будет опубликован <b>один раз</b> в это время.",
                reply_markup=get_back_menu(),
                parse_mode="HTML"
            )
        return
    
    if step == "waiting_auto_post_time":
        if not re.match(r'^([0-1][0-9]|2[0-3]):[0-5][0-9]$', text):
            send_message(chat_id, 
                "❌ <b>Неверный формат!</b>\n\n"
                "Используйте формат <code>ЧЧ:ММ</code>",
                reply_markup=get_back_menu(),
                parse_mode="HTML"
            )
            return
        
        post_text = user_sessions[user_id].get("auto_post_text", "")
        auto_type = user_sessions[user_id].get("auto_type", "daily")
        
        if user_id not in auto_posts:
            auto_posts[user_id] = []
        
        auto_posts[user_id].append({
            "type": "daily",
            "time": text,
            "text": post_text,
            "active": True
        })
        
        send_message(chat_id, 
            f"✅ <b>Ежедневная автопубликация добавлена!</b>\n\n"
            f"⏰ Время: <code>{text}</code>\n"
            f"📝 Текст: {post_text[:200]}",
            reply_markup=get_auto_publish_menu(),
            parse_mode="HTML"
        )
        
        user_sessions[user_id]["step"] = "auto_publish_menu"
        return
    
    if step == "waiting_auto_post_datetime":
        if not re.match(r'^(\d{2})\.(\d{2})\.(\d{4}) (\d{2}):(\d{2})$', text):
            send_message(chat_id, 
                "❌ <b>Неверный формат!</b>\n\n"
                "Используйте формат <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
                reply_markup=get_back_menu(),
                parse_mode="HTML"
            )
            return
        
        try:
            dt_obj = datetime.strptime(text, "%d.%m.%Y %H:%M")
            dt_str = dt_obj.strftime("%Y-%m-%d %H:%M")
            
            if dt_obj <= datetime.now():
                send_message(chat_id, 
                    "⚠️ <b>Дата и время должны быть в будущем!</b>",
                    reply_markup=get_back_menu(),
                    parse_mode="HTML"
                )
                return
            
            post_text = user_sessions[user_id].get("auto_post_text", "")
            auto_type = user_sessions[user_id].get("auto_type", "once")
            
            if user_id not in auto_posts:
                auto_posts[user_id] = []
            
            auto_posts[user_id].append({
                "type": "once",
                "time": dt_str,
                "text": post_text,
                "active": True
            })
            
            display_dt = dt_obj.strftime("%d.%m.%Y в %H:%M")
            
            send_message(chat_id, 
                f"✅ <b>Одноразовая автопубликация добавлена!</b>\n\n"
                f"⏰ Время: <code>{display_dt}</code>\n"
                f"📝 Текст: {post_text[:200]}",
                reply_markup=get_auto_publish_menu(),
                parse_mode="HTML"
            )
            
            user_sessions[user_id]["step"] = "auto_publish_menu"
            
        except ValueError:
            send_message(chat_id, 
                "❌ <b>Ошибка!</b>\n\n"
                "Используйте формат <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
                reply_markup=get_back_menu(),
                parse_mode="HTML"
            )
        return
    
    # ====== ИЗМЕНЕНИЕ ШАБЛОНА ======
    if step == "waiting_new_template":
        user_templates[user_id] = text
        send_message(chat_id, "✅ <b>Шаблон обновлён!</b>", reply_markup=get_main_menu())
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
        
        if "message" in data:
            msg = data["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]
            text = msg.get("text", "")
            
            if text == "/start":
                handle_start(chat_id, user_id)
            elif not text.startswith("/"):
                handle_text_message(chat_id, user_id, text)
        
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
