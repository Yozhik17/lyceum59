import asyncio
import logging
import sqlite3
import google.generativeai as genai
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# =========================================================
# НАЛАШТУВАННЯ
# =========================================================
TELEGRAM_TOKEN = '8392393304:AAHBtYGPtXYBZf1DNOxfcjMydPXd3YYHrRw'
# GEMINI_API_KEY = 'GEMINI_КЛЮЧ' поки не працює
ADMIN_ID = 0  # Telegram ID мій як адміна
CLASS_TEACHER_ID = 0  # ID класного керівника
SCHOOL_POLICE_ID = 0  # ID шкільного поліцейського
# =========================================================

logging.basicConfig(level=logging.INFO)

# Ініціалізація ШІ (тільки якщо ключ встановлений)
if GEMINI_API_KEY and GEMINI_API_KEY != 'ВАШ_GEMINI_КЛЮЧ':
    genai.configure(api_key=GEMINI_API_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    ai_model = None
    logging.warning("GEMINI_API_KEY не встановлений. ШІ-функції будуть недоступні.")

# Ініціалізація бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Робота з базами даних
conn = sqlite3.connect('school_bot.db', check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            role TEXT,
            name TEXT,
            class_name TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subject TEXT,
            grade TEXT,
            date TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_name TEXT,
            subject TEXT,
            task TEXT,
            due_date TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user INTEGER,
            to_user INTEGER,
            message TEXT,
            timestamp TEXT
        )
    ''')
    # Додаємо таблицю для розкладу занять (приклад для класу)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_name TEXT,
            day TEXT,
            lessons TEXT
        )
    ''')
    # Додаємо приклад даних для розкладу (якщо таблиця порожня)
    cursor.execute("SELECT COUNT(*) FROM schedule")
    if cursor.fetchone()[0] == 0:
        sample_schedule = [
            ("10-А", "Понеділок", "1. Математика\n2. Українська мова\n3. Історія\n4. Фізика\n5. Англійська\n6. Біологія\n7. Фізкультура"),
            ("10-А", "Вівторок", "1. Література\n2. Геометрія\n3. Хімія\n4. Географія\n5. Інформатика\n6. Музика\n7. Трудове навчання"),
            ("10-А", "Середа", "1. Математика\n2. Українська мова\n3. Історія\n4. Фізика\n5. Англійська\n6. Біологія\n7. Фізкультура"),
            ("10-А", "Четвер", "1. Література\n2. Геометрія\n3. Хімія\n4. Географія\n5. Інформатика\n6. Музика\n7. Трудове навчання"),
            ("10-А", "П'ятниця", "1. Математика\n2. Українська мова\n3. Історія\n4. Фізика\n5. Англійська\n6. Біологія\n7. Фізкультура"),
        ]
        cursor.executemany("INSERT INTO schedule (class_name, day, lessons) VALUES (?, ?, ?)", sample_schedule)
    # Додаємо приклад оцінок (якщо таблиця порожня)
    cursor.execute("SELECT COUNT(*) FROM grades")
    if cursor.fetchone()[0] == 0:
        sample_grades = [
            (12345678, "Математика", "12", "15.10"),
            (12345678, "Українська мова", "11", "16.10"),
            (12345678, "Фізика", "10", "17.10"),
        ]
        cursor.executemany("INSERT INTO grades (user_id, subject, grade, date) VALUES (?, ?, ?, ?)", sample_grades)
    conn.commit()

init_db()

# --- Допоміжні функції ---
def get_user_data(user_id):
    cursor.execute("SELECT role, class_name FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def get_main_menu(role):
    builder = ReplyKeyboardBuilder()
    if role == 'student':
        buttons = ["📚 Розклад", "📝 Д/З", "📊 Оцінки", "🤖 ШІ Помічник", "🔔 Дзвінки", "🍽️ Меню їдальні", "📝 Адміністрація", "👨‍🏫 Класний керівник", "👮 Шкільний поліцейський", "📰 Новини"]
    elif role == 'teacher':
        buttons = ["➕ Додати оцінку", "📝 Додати Д/З", "📈 Статистика", "📢 Оголошення"]
    elif role == 'admin':
        buttons = ["📢 Розсилка", "👥 Користувачі", "⚙️ Налаштування"]
    else:
        return None

    for btn in buttons:
        builder.button(text=btn)
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# Статичний розклад дзвінків на 7 уроків (приклад)
BELL_SCHEDULE = """
🔔 **Розклад дзвінків:**
1. 08:00 - 08:45
2. 08:55 - 09:40
3. 09:50 - 10:35
4. 10:50 - 11:35
5. 11:45 - 12:30
6. 12:40 - 13:25
7. 13:35 - 14:20
"""

# Статичне меню їдальні (приклад)
CAFETERIA_MENU = """
🍽️ **Меню шкільної їдальні на сьогодні:**
- Сніданок: Каша вівсяна з фруктами, чай
- Обід: Борщ, котлета з картоплею, компот
- Вечеря: Салат, йогурт
"""

# Статичні новини (приклад)
NEWS = """
📰 **Шкільні новини:**
- 15.10: Відбудеться батьківська зустріч.
- 20.10: Спортивні змагання з футболу.
- 25.10: Екскурсія до музею.
"""

# --- Обробники команд ---

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    if not user_data:
        builder = ReplyKeyboardBuilder()
        builder.button(text="Я Учень")
        builder.button(text="Я Вчитель")
        await message.answer("Вітаю! Оберіть свою роль:", reply_markup=builder.as_markup(resize_keyboard=True))
    else:
        await message.answer(f"З поверненням! Ви увійшли як {user_data[0]}", reply_markup=get_main_menu(user_data[0]))

@dp.message(Command("myid"))
async def myid_handler(message: types.Message):
    await message.answer(f"Ваш ID: `{message.from_user.id}`", parse_mode="Markdown")

@dp.message(F.text.in_(["Я Учень", "Я Вчитель"]))
async def role_selection(message: types.Message):
    role = 'student' if "Учень" in message.text else 'teacher'
    # Для тесту автоматично ставимо клас 10-А (в продакшені додайте вибір)
    cursor.execute("INSERT OR REPLACE INTO users (user_id, role, name, class_name) VALUES (?, ?, ?, ?)", 
                   (message.from_user.id, role, message.from_user.first_name, "10-А"))
    conn.commit()
    await message.answer(f"Роль {role} збережено!", reply_markup=get_main_menu(role))

# --- Логіка для Вчителів (Введення даних) ---

@dp.message(F.text == "➕ Додати оцінку")
async def ask_grade(message: types.Message):
    await message.answer("Надішліть оцінку у форматі:\n`Оцінка: ID_учня Предмет Оцінка`\nПриклад: `Оцінка: 12345678 Математика 12`", parse_mode="Markdown")

@dp.message(F.text.startswith("Оцінка:"))
async def process_add_grade(message: types.Message):
    try:
        parts = message.text.split()
        if len(parts) < 4:
            raise ValueError("Недостатньо частин у повідомленні")
        u_id, subject, val = int(parts[1]), parts[2], parts[3]
        date = datetime.now().strftime("%d.%m")
        cursor.execute("INSERT INTO grades (user_id, subject, grade, date) VALUES (?, ?, ?, ?)", (u_id, subject, val, date))
        conn.commit()
        await message.answer("✅ Оцінку додано!")
        try:
            await bot.send_message(u_id, f"🔔 Нова оцінка: {subject} - {val}")
        except Exception as e:
            logging.error(f"Не вдалося надіслати повідомлення учню {u_id}: {e}")
    except ValueError as e:
        await message.answer(f"❌ Помилка формату: {str(e)}. Перевірте приклад.")
    except Exception as e:
        logging.error(f"Помилка при додаванні оцінки: {e}")
        await message.answer("❌ Сталася невідома помилка.")

@dp.message(F.text == "📝 Додати Д/З")
async def ask_hw(message: types.Message):
    await message.answer("Надішліть Д/З у форматі:\n`ДЗ: Клас Предмет Завдання`\nПриклад: `ДЗ: 10-А Фізика Стор. 45 впр. 3`", parse_mode="Markdown")

@dp.message(F.text.startswith("ДЗ:"))
async def process_add_hw(message: types.Message):
    try:
        parts = message.text.replace("ДЗ:", "").strip().split(maxsplit=2)
        if len(parts) < 3:
            raise ValueError("Недостатньо частин у повідомленні")
        c_name, subject, task = parts[0], parts[1], parts[2]
        date = datetime.now().strftime("%d.%m")
        cursor.execute("INSERT INTO homework (class_name, subject, task, due_date) VALUES (?, ?, ?, ?)", (c_name, subject, task, date))
        conn.commit()
        await message.answer(f"✅ Завдання для {c_name} додано!")
    except ValueError as e:
        await message.answer(f"❌ Помилка формату: {str(e)}. Перевірте приклад.")
    except Exception as e:
        logging.error(f"Помилка при додаванні Д/З: {e}")
        await message.answer("❌ Сталася невідома помилка.")

# --- Логіка для Учнів ---

@dp.message(F.text == "📊 Оцінки")
async def show_grades(message: types.Message):
    cursor.execute("SELECT subject, grade, date FROM grades WHERE user_id = ?", (message.from_user.id,))
    res = cursor.fetchall()
    if not res:
        return await message.answer("Оцінок поки немає.")
    text = "📈 **Твої оцінки:**\n" + "\n".join([f"• {g[0]}: {g[1]} ({g[2]})" for g in res])
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📝 Д/З")
async def show_hw(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    if not user_data:
        return await message.answer("Спочатку оберіть роль через /start.")
    cursor.execute("SELECT subject, task FROM homework WHERE class_name = ?", (user_data[1],))
    res = cursor.fetchall()
    if not res:
        return await message.answer("На сьогодні завдань немає! 🎉")
    text = "📚 **Домашнє завдання:**\n" + "\n".join([f"• {h[0]}: {h[1]}" for h in res])
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🔔 Дзвінки")
async def show_bells(message: types.Message):
    await message.answer(BELL_SCHEDULE, parse_mode="Markdown")

@dp.message(F.text == "🍽️ Меню їдальні")
async def show_cafeteria_menu(message: types.Message):
    await message.answer(CAFETERIA_MENU, parse_mode="Markdown")

@dp.message(F.text == "📰 Новини")
async def show_news(message: types.Message):
    await message.answer(NEWS, parse_mode="Markdown")

@dp.message(F.text == "📝 Адміністрація")
async def write_to_admin(message: types.Message):
    await message.answer("Напишіть ваше повідомлення для адміністрації:")

@dp.message(F.text == "👨‍🏫 Класний керівник")
async def write_to_teacher(message: types.Message):
    await message.answer("Напишіть ваше повідомлення для класного керівника:")

@dp.message(F.text == "👮 Шкільний поліцейський")
async def write_to_police(message: types.Message):
    await message.answer("Напишіть ваше повідомлення для шкільного поліцейського:")

# Обробник для повідомлень після вибору отримувача
@dp.message(F.text & ~F.text.startswith(("/", "Оцінка:", "ДЗ:", "Я ")) & ~F.text.in_(["📚 Розклад", "📝 Д/З", "📊 Оцінки", "🤖 ШІ Помічник", "🔔 Дзвінки", "🍽️ Меню їдальні", "📝 Адміністрація", "👨‍🏫 Класний керівник", "👮 Шкільний поліцейський", "📰 Новини", "➕ Додати оцінку", "📝 Додати Д/З", "📈 Статистика", "📢 Оголошення", "📢 Розсилка", "👥 Користувачі", "⚙️ Налаштування"]))
async def handle_message_to_staff(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    if not user_data or user_data[0] != 'student':
        return  # Тільки для учнів
    

    
    # Додамо таблицю для активних повідомлень
    cursor.execute("CREATE TABLE IF NOT EXISTS active_messages (user_id INTEGER PRIMARY KEY, target TEXT)")
    conn.commit()
    
    # Перевіряємо, чи є активний запит
    cursor.execute("SELECT target FROM active_messages WHERE user_id = ?", (message.from_user.id,))
    active = cursor.fetchone()
    if active:
        target = active[0]
        target_id = None
        if target == "admin":
            target_id = ADMIN_ID
        elif target == "teacher":
            target_id = CLASS_TEACHER_ID
        elif target == "police":
            target_id = SCHOOL_POLICE_ID
        
        if target_id and target_id != 0:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO messages (from_user, to_user, message, timestamp) VALUES (?, ?, ?, ?)", 
                           (message.from_user.id, target_id, message.text, timestamp))
            conn.commit()
            try:
                await bot.send_message(target_id, f"📩 Повідомлення від {message.from_user.first_name} ({user_data[1]}):\n{message.text}")
                await message.answer("✅ Повідомлення надіслано!")
            except Exception as e:
                logging.error(f"Не вдалося надіслати повідомлення до {target_id}: {e}")
                await message.answer("❌ Не вдалося надіслати повідомлення.")
        else:
            await message.answer("❌ ID отримувача не встановлений.")
        
        # Видаляємо активний запит
        cursor.execute("DELETE FROM active_messages WHERE user_id = ?", (message.from_user.id,))
        conn.commit()
    else:
        # Якщо немає активного, передаємо до ШІ або ігноруємо
        if ai_model:
            sent_msg = await message.answer("🤔 Думаю...")
            try:
                response = ai_model.generate_content(f"Ти помічник ліцеїста. Дай коротку відповідь українською мовою (не більше 1000 символів): {message.text}")
                reply_text = response.text.strip() if response.text else "❌ Не вдалося отримати відповідь від ШІ."
                if len(reply_text) > 4000:
                    reply_text = reply_text[:4000] + "..."
                await sent_msg.edit
                await sent_msg.edit_text(reply_text)
            except Exception as e:
                logging.error(f"Помилка ШІ: {e}")
                await sent_msg.edit_text("❌ Вибач, сталася помилка при зверненні до ШІ.")

# Додаємо встановлення активного запиту для повідомлень
@dp.message(F.text == "📝 Адміністрація")
async def write_to_admin(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    if not user_data or user_data[0] != 'student':
        return await message.answer("❌ Доступ заборонено.")
    cursor.execute("INSERT OR REPLACE INTO active_messages (user_id, target) VALUES (?, ?)", (message.from_user.id, "admin"))
    conn.commit()
    await message.answer("Напишіть ваше повідомлення для адміністрації:")

@dp.message(F.text == "👨‍🏫 Класний керівник")
async def write_to_teacher(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    if not user_data or user_data[0] != 'student':
        return await message.answer("❌ Доступ заборонено.")
    cursor.execute("INSERT OR REPLACE INTO active_messages (user_id, target) VALUES (?, ?)", (message.from_user.id, "teacher"))
    conn.commit()
    await message.answer("Напишіть ваше повідомлення для класного керівника:")

@dp.message(F.text == "👮 Шкільний поліцейський")
async def write_to_police(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    if not user_data or user_data[0] != 'student':
        return await message.answer("❌ Доступ заборонено.")
    cursor.execute("INSERT OR REPLACE INTO active_messages (user_id, target) VALUES (?, ?)", (message.from_user.id, "police"))
    conn.commit()
    await message.answer("Напишіть ваше повідомлення для шкільного поліцейського:")

@dp.message(F.text == "📚 Розклад")
async def show_schedule(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    if not user_data:
        return await message.answer("Спочатку оберіть роль через /start.")
    
    # Inline-клавіатура для вибору дня
    builder = InlineKeyboardBuilder()
    days = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця"]
    for d in days:
        builder.button(text=d, callback_data=f"schedule_{d}")
    builder.adjust(1)  # Одна колонка
    
    # Отримуємо сьогоднішній день
    day_of_week = datetime.now().strftime("%A")
    day_map = {
        "Monday": "Понеділок",
        "Tuesday": "Вівторок",
        "Wednesday": "Середа",
        "Thursday": "Четвер",
        "Friday": "П'ятниця",
        "Saturday": "Субота",
        "Sunday": "Неділя"
    }
    ukr_day = day_map.get(day_of_week, day_of_week)
    
    # Якщо сьогодні робочий день, показуємо розклад на сьогодні + кнопки
    if ukr_day in days:
        cursor.execute("SELECT lessons FROM schedule WHERE class_name = ? AND day = ?", (user_data[1], ukr_day))
        res = cursor.fetchone()
        if res:
            text_today = f"📅 **Розклад на сьогодні ({ukr_day}) для {user_data[1]}:**\n{res[0]}"
            await message.answer(text_today, parse_mode="Markdown", reply_markup=builder.as_markup())
        else:
            await message.answer("Розкладу на сьогодні немає.", reply_markup=builder.as_markup())
    else:
        # Якщо вихідний, показуємо кнопки для вибору
        await message.answer("Сьогодні вихідний. Оберіть день тижня:", reply_markup=builder.as_markup())

# Обробник для inline-кнопок розкладу
@dp.callback_query(F.data.startswith("schedule_"))
async def handle_schedule_callback(callback: types.CallbackQuery):
    day = callback.data.split("_")[1]
    user_data = get_user_data(callback.from_user.id)
    if not user_data:
        return await callback.answer("Спочатку оберіть роль через /start.")
    
    cursor.execute("SELECT lessons FROM schedule WHERE class_name = ? AND day = ?", (user_data[1], day))
    res = cursor.fetchone()
    if not res:
        await callback.answer(f"Розкладу на {day} немає.")
        return
    
    text = f"📅 **Розклад на {day} для {user_data[1]}:**\n{res[0]}"
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()

# --- Штучний Інтелект ---

@dp.message(F.text == "🤖 ШІ Помічник")
async def ai_welcome(message: types.Message):
    if not ai_model:
        return await message.answer("❌ ШІ недоступний (перевірте GEMINI_API_KEY).")
    await message.answer("Я твій розумний помічник. Просто напиши мені будь-яке запитання з навчання (наприклад: 'Поясни теорему Піфагора').")

# --- Адмін-панель ---

@dp.message(F.text == "📢 Розсилка")
async def broadcast_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("❌ Доступ заборонено.")
    await message.answer("Надішліть текст розсилки у форматі: `Рассылка: Текст`")

@dp.message(F.text.startswith("Рассылка:"))
async def do_broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("❌ Доступ заборонено.")
    text = message.text.replace("Рассылка:", "").strip()
    if not text:
        return await message.answer("❌ Текст розсилки порожній.")
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    count = 0
    for u in users:
        try:
            await bot.send_message(u[0], f"📢 **Оголошення:**\n\n{text}", parse_mode="Markdown")
            count += 1
            await asyncio.sleep(0.1)  # Затримка, щоб уникнути обмежень Telegram
        except Exception as e:
            logging.error(f"Не вдалося надіслати до {u[0]}: {e}")
    await message.answer(f"✅ Розсилку отримали {count} користувачів.")

# --- Запуск ---
async def main():
    print("Бот запущений!")
    try:
        await dp.start_polling(bot)
    finally:
        conn.close()  # Закриття БД при завершенні

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот зупинений")
