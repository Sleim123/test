import telegram
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode
from datetime import datetime, timedelta
import logging
import json
from cryptography.fernet import Fernet
from config import TOKEN, ADMIN_ID
import os
import re
import aiofiles
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import asyncio

# Установка уровня логирования: (DEBUG, INFO, WARNING, ERROR, CRITICAL)
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Функции для работы с шифрованием данных
def load_key():
    with open('encryption.key', 'rb') as key_file:
        return key_file.read()

def encrypt_data(data):
    key = load_key()
    fernet = Fernet(key)
    return fernet.encrypt(json.dumps(data).encode())

def decrypt_data(encrypted_data):
    key = load_key()
    fernet = Fernet(key)
    return json.loads(fernet.decrypt(encrypted_data).decode())

# Асинхронное чтение файла
async def load_encrypted_file(filename):
    try:
        if not os.path.exists(filename):
            return {}
        async with aiofiles.open(filename, 'rb') as file:
            encrypted_data = await file.read()
        return decrypt_data(encrypted_data)
    except FileNotFoundError:
        logging.info("Файл не найден. Создается новый.")
        return {}
    except Exception as e:
        logging.error(f"Ошибка при загрузке данных из {filename}: {e}")
        return {}

# Асинхронное сохранение файла
async def save_encrypted_file(filename, data):
    try:
        encrypted_data = encrypt_data(data)
        async with aiofiles.open(filename, 'wb') as file:
            await file.write(encrypted_data)
        logging.info(f"Данные успешно сохранены в файл {filename} (зашифрованы).")
    except Exception as e:
        logging.error(f"Ошибка при сохранении данных в {filename}: {e}")

async def save_data(users):
    await save_encrypted_file('users.json', users)

async def load_data():
    users = await load_encrypted_file('users.json')
    if not users:
        users = {}
        await save_data(users)
    return users

async def save_active_chats():
    try:
        async with aiofiles.open('active_chats.json', 'wb') as file:
            encrypted_data = encrypt_data(active_chats)
            await file.write(encrypted_data)
        logging.info("Активные чаты успешно сохранены.")
    except Exception as e:
        logging.error(f"Ошибка при сохранении активных чатов: {e}")

async def load_active_chats():
    try:
        if not os.path.exists('active_chats.json'):
            return {}
        async with aiofiles.open('active_chats.json', 'rb') as file:
            encrypted_data = await file.read()
        return decrypt_data(encrypted_data)
    except FileNotFoundError:
        logging.info("Файл с активными чатами не найден.")
        return {}
    except Exception as e:
        logging.error(f"Ошибка при загрузке активных чатов: {e}")
        return {}

# Для сохранения заблокированных пользователей
async def save_blocked_users(blocked_users):
    await save_encrypted_file('blocked_users.json', blocked_users)

# Загрузка данных о заблокированных пользователях
async def load_blocked_users():
    return await load_encrypted_file('blocked_users.json')

# Изменение функции is_blocked для проверки тайм-аутов
async def is_blocked(user1, user2):
    blocked_users = await load_blocked_users()
    pair = ",".join(sorted([user1, user2]))
    if pair in blocked_users:
        block_time = datetime.fromisoformat(blocked_users[pair])
        if datetime.now() < block_time:
            return True
        else:
            # Удаляем просроченные блокировки и логируем выход из тайм-аута
            del blocked_users[pair]
            await save_blocked_users(blocked_users)
            logging.info(f"(!) Пользователи {user1} и {user2} вышли из тайм-аута.")
    return False

# Преобразование времени в слова
def convert_timeout_to_words(timeout_str):
    time_amount = int(timeout_str[:-1])
    time_unit = timeout_str[-1]

    if time_unit == 's':
        return f"{time_amount} сек"
    elif time_unit == 'm':
        return f"{time_amount} мин"
    elif time_unit == 'h':
        return f"{time_amount} час"
    elif time_unit == 'd':
        return f"{time_amount} день"

# Обработка команды /timeout
async def timeout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        # Если пользователь не администратор, ничего не отвечаем
        return

    if len(context.args) == 0:
        # Подгружаем актуальный тайм-аут из blocked_users.json
        blocked_users = await load_blocked_users()
        last_timeout = blocked_users.get("timeout_duration", "1h")
        last_timeout_words = convert_timeout_to_words(last_timeout)
        await update.message.reply_text(f"_Используйте команду в формате: /timeout <время>\nТекущий установленный тайм-аут: {last_timeout_words}_", parse_mode=ParseMode.MARKDOWN)
        return

    if len(context.args) != 1:
        await update.message.reply_text("_Некорректный формат команды. Используйте команду в формате: /timeout <время>_", parse_mode=ParseMode.MARKDOWN)
        return

    timeout_str = context.args[0]
    if not re.match(r'^\d+[smhd]$', timeout_str):
        await update.message.reply_text("_Некорректный формат времени. Используйте s для секунд, m для минут, h для часов или d для дней_\n_Например: /timeout 30с, /timeout 1м, /timeout 1ч, /timeout 1д_", parse_mode=ParseMode.MARKDOWN)
        return

    time_amount = int(timeout_str[:-1])
    time_unit = timeout_str[-1]

    if time_unit == 's':
        timeout_duration = timedelta(seconds=time_amount)
    elif time_unit == 'm':
        timeout_duration = timedelta(minutes=time_amount)
    elif time_unit == 'h':
        timeout_duration = timedelta(hours=time_amount)
    elif time_unit == 'd':
        timeout_duration = timedelta(days=time_amount)
    else:
        await update.message.reply_text("_Некорректный формат времени. Используйте s для секунд, m для минут, h для часов или d для дней_", parse_mode=ParseMode.MARKDOWN)
        return

    if timeout_duration > timedelta(days=1):
        await update.message.reply_text(f"_Мы не советуем устанавливать настолько долгий тайм-аут_", parse_mode=ParseMode.MARKDOWN)

    blocked_users = await load_blocked_users()
    blocked_users["timeout_duration"] = timeout_str
    await save_blocked_users(blocked_users)
    context.bot_data["last_timeout"] = timeout_str
    timeout_words = convert_timeout_to_words(timeout_str)
    await update.message.reply_text(f"*⏳ Тайм-аут установлен на {timeout_words}*", parse_mode=ParseMode.MARKDOWN)

# Исправление функции создания клавиатуры
def get_keyboard(is_searching=False):
    buttons = []
    if not is_searching:
        buttons.append([KeyboardButton("🔎 Поиск собеседника")])
        buttons.append([KeyboardButton("🎭 Поиск по полу")])
        buttons.append([KeyboardButton("📙 Интересы")])
        buttons.append([KeyboardButton("💼 Профиль")])  # Добавляем кнопку профиля
    else:
        buttons.append([KeyboardButton("❌ Остановить поиск")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ПОЛУЧЕНИЕ file_id фото
# async def get_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if update.message.photo:
#         file_id = update.message.photo[-1].file_id
#         await update.message.reply_text(f"file_id: {file_id}")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = await load_data()
    if user_id not in users:
        users[user_id] = {
            "status": "normal",
            "chat_with": None,
            "interests": [],
            "gender": None,
            "premium": False,
            "chats_count": 0,
            "likes": 0,
            "dislikes": 0
        }
        await save_data(users)
    if users[user_id]["status"] == "chatting":
        await update.message.reply_text(
            "🥷 *У вас уже есть собеседник*\n\n/next — _искать нового собеседника_\n/stop — _завершить диалог_",
            parse_mode=telegram.constants.ParseMode.MARKDOWN
        )
        return
    if users[user_id]["status"] == "in search":
        await update.message.reply_text(
            "_Мы уже ищем собеседника..._",
            parse_mode=telegram.constants.ParseMode.MARKDOWN
        )
        return

    photo_file_id = 'AgACAgIAAxkBAAIq72eBGj6uFSeSE1dKa1zxAsS5LbWdAAKN6DEb45v5S1f--cKVyg-zAQADAgADeAADNgQ'

    # Создаем inline-кнопку
    inline_button = InlineKeyboardButton("Автор проекта", url="https://t.me/ibuzy")
    inline_keyboard = InlineKeyboardMarkup([[inline_button]])

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=photo_file_id,
        caption="*👋 Добро пожаловать в Анонимный чат для общения 1 на 1 со случайным собеседником!*\n\n*🛡 Шифрование данных*\n*🎭 Полная анонимность*\n*📙 Интересы для общения*\n*💅 Поиск собеседника полу*\n\n_Просим вас соблюдать правила этикета и придерживаться уважительного и доброжелательного тона в общении в чате._",
        parse_mode=telegram.constants.ParseMode.MARKDOWN,
        reply_markup=inline_keyboard  # Добавляем inline-клавиатуру
    )

    # Отправляем обычную клавиатуру
    await update.message.reply_text(
        "_💭 Для поиска собеседника воспользуйтесь кнопками ниже_",
        parse_mode=telegram.constants.ParseMode.MARKDOWN,
        reply_markup=get_keyboard()
    )

# Функция создания клавиатуры для выбора интересов
def get_interests_keyboard(selected_interests=[]):
    interests = ["Знакомства", "Мемы", "Спорт", "Путешествия", "Кино", "Книги", "Одиночество", "Игры"]
    buttons = []
    for i in range(0, len(interests), 2):
        row = []
        for j in range(2):
            if i + j < len(interests):
                interest = interests[i + j]
                if interest in selected_interests:
                    row.append(InlineKeyboardButton(f"✅ {interest}", callback_data=f"interest_{interest}"))
                else:
                    row.append(InlineKeyboardButton(interest, callback_data=f"interest_{interest}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Сбросить интересы", callback_data="reset_interests")])
    return InlineKeyboardMarkup(buttons)

# Команда /interests
async def interests_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    selected_interests = users[user_id].get("interests", [])
    await update.message.reply_text(
        "*📙 Интересы поиска*\n\n_Мы будем стараться искать вам собеседника с похожими интересами._\n\n_Выберите ваши интересы:_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_interests_keyboard(selected_interests)
    )

# Обработчик для сброса интересов
async def reset_interests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    if users[user_id].get("interests"):
        users[user_id]["interests"] = []
        await save_data(users)
        try:
            await query.edit_message_reply_markup(reply_markup=get_interests_keyboard(users[user_id]["interests"]))
        except telegram.error.BadRequest as e:
            if str(e) == "Message is not modified: specified new message content and reply markup are exactly the same as a current content and reply markup of the message":
                logging.info(f"Интересы пользователя {user_id} уже пусты и сообщение не изменено.")
            else:
                logging.error(f"Ошибка при сбросе интересов: {e}")
    else:
        logging.info(f"Интересы пользователя {user_id} уже пусты.")
        await query.answer("У вас уже нет интересов.", show_alert=False)

# Обработчик для выбора интересов
async def handle_interests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    interest = query.data.replace("interest_", "")
    if interest in users[user_id]["interests"]:
        users[user_id]["interests"].remove(interest)
    else:
        users[user_id]["interests"].append(interest)
    await save_data(users)
    await query.edit_message_reply_markup(reply_markup=get_interests_keyboard(users[user_id]["interests"]))

# Обработчик завершения выбора интересов
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.edit_message_text(
        f"Ваши интересы сохранены: {', '.join(users[user_id]['interests']) or 'Нет интересов'}"
    )
    await query.message.reply_text("Интересы выбраны.", reply_markup=get_keyboard())

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE, skip_searching_message=False):
    user_id = str(update.effective_user.id)

    # Проверка наличия пользователя в базе данных
    if user_id not in users:
        users[user_id] = {"status": "normal", "chat_with": None, "interests": [], "gender": None, "premium": False}
        await save_data(users)

    # Проверка, заблокирован ли пользователь
    if users[user_id]["status"] == "banned":
        await update.message.reply_text(
            "*⚠️ Невозможно начать поиск.*\n\n*Вы были заблокированы администратором.*",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Проверка, находится ли пользователь в чате
    if users[user_id]["status"] == "chatting":
        await update.message.reply_text(
            "🥷 *У вас уже есть собеседник*\n\n/next — _искать нового собеседника_\n/stop — _завершить диалог_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # Проверка, ищет ли пользователь собеседника
    if users[user_id]["status"] == "in search":
        if not skip_searching_message:
            await update.message.reply_text("_Мы уже ищем собеседника..._", parse_mode=ParseMode.MARKDOWN, reply_markup=get_keyboard(True))
        return

    logging.info(f"(!) Пользователь {user_id} начал поиск собеседника. (!)")

    users[user_id]["status"] = "in search"
    users[user_id]["search_via_gender"] = False  # Сбрасываем флаг поиска по полу
    await save_data(users)
    if not skip_searching_message:
        await update.message.reply_text("_Ищем собеседника..._", parse_mode=ParseMode.MARKDOWN, reply_markup=get_keyboard(True))

    await find_partner(update, context)

async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_interests = set(users[user_id].get("interests", []))
    search_via_gender = users[user_id].get("search_via_gender", False)
    search_gender = users[user_id].get("search_gender", None)

    for other_user, other_user_data in users.items():
        if other_user_data["status"] == "in search" and other_user != user_id:
            if await is_blocked(user_id, other_user):
                continue

            # Проверка на совпадение пола для гендерного поиска обоих пользователей
            if search_via_gender and other_user_data.get("gender") != search_gender:
                continue
            if other_user_data.get("search_via_gender", False) and other_user_data.get("search_gender") and other_user_data["search_gender"] != users[user_id].get("gender"):
                continue

            other_user_interests = set(users[other_user].get("interests", []))
            common_interests = user_interests & other_user_interests

            # Проверка на совпадение интересов
            if user_interests and other_user_interests and not common_interests:
                continue

            # Проверка, чтобы пользователи без интересов соединялись только с такими же пользователями
            if not user_interests and other_user_interests:
                continue
            if user_interests and not other_user_interests:
                continue

            users[user_id]["chat_with"] = other_user
            users[other_user]["chat_with"] = user_id
            active_chats[user_id] = {"chat_with": other_user, "message_map": {}}
            active_chats[other_user] = {"chat_with": user_id, "message_map": {}}
            users[user_id]["status"] = "chatting"
            users[other_user]["status"] = "chatting"
            await save_data(users)
            await save_active_chats()

            logging.info(f"(!) Создан активный чат между пользователем {user_id} и пользователем {other_user}. (!)")

            common_interests_str = ", ".join(common_interests)
            common_interests_message = f"_Общие интересы: {common_interests_str}_" if common_interests else ""

            # Сообщение для текущего пользователя
            user_message_parts = ["*🔎 Собеседник найден!*"]

            if common_interests:
                user_message_parts.append(f"\n{common_interests_message}")

            user_message_parts.append("\n/next — _искать нового собеседника_\n/stop — _завершить диалог_\n/interests — _изменить интересы поиска_")
            user_message = "\n".join(user_message_parts)

            await update.message.reply_text(user_message, parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())

            # Сообщение для другого пользователя
            other_user_message_parts = ["*🔎 Собеседник найден!*"]

            if common_interests:
                other_user_message_parts.append(f"\n{common_interests_message}")

            other_user_message_parts.append("\n/next — _искать нового собеседника_\n/stop — _завершить диалог_\n/interests — _изменить интересы поиска_")
            other_user_message = "\n".join(other_user_message_parts)

            await context.bot.send_message(other_user, other_user_message, parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
            return

    #await update.message.reply_text("Свободных собеседников нет.\n\nПоиск займет больше времени, чем обычно...", reply_markup=get_keyboard(True))

# Обработчик для кнопки "Поиск по полу"
async def gender_search_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # Проверка, заблокирован ли пользователь
    if users[user_id]["status"] == "banned":
        await update.message.reply_text(
            "*⚠️ Невозможно начать поиск.*\n\n*Вы были заблокированы администратором.*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if not users[user_id].get("premium", False):
        photo_file_id = 'AgACAgIAAxkBAAIrPGeBJTFQfZuJnOmUeXkUoemEdU7oAALj5jEbXEMISHAa4jiqR3QuAQADAgADeAADNgQ'
        
        # Создаем inline-кнопку "Купить премиум"
        inline_button = InlineKeyboardButton("Купить Premium", url="https://t.me/ibuzy")
        inline_keyboard = InlineKeyboardMarkup([[inline_button]])

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=photo_file_id,
            caption='_Для функции_ *🎭 Поиск по полу* _нужен Premium статус!_\n_Приобрести Premium можно у администратора_',
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=inline_keyboard
        )
        return

    buttons = [
        [KeyboardButton("👨‍🦰 Поиск М"), KeyboardButton("👩‍🦱 Поиск Д")],
        [KeyboardButton("◀️ Вернуться назад")]
    ]
    await update.message.reply_text("_Выберите пол для поиска:_", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))

# Обработчик для поиска по полу
async def gender_search(update: Update, context: ContextTypes.DEFAULT_TYPE, skip_searching_message=False):
    user_id = str(update.effective_user.id)
    if not users[user_id].get("premium", False):
        photo_file_id = 'AgACAgIAAxkBAAIrPGeBJTFQfZuJnOmUeXkUoemEdU7oAALj5jEbXEMISHAa4jiqR3QuAQADAgADeAADNgQ'
        
        # Создаем inline-кнопку "Купить премиум"
        inline_button = InlineKeyboardButton("Купить Premium", url="https://t.me/ibuzy")
        inline_keyboard = InlineKeyboardMarkup([[inline_button]])

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=photo_file_id,
            caption='_Для функции_ *🎭 Поиск по полу* _нужен Premium статус!_\n_Приобрести Premium можно у администратора_',
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=inline_keyboard
        )
        return

    gender = None
    if update.message.text == "👨‍🦰 Поиск М":
        gender = "m"
    elif update.message.text == "👩‍🦱 Поиск Д":
        gender = "w"
    else:
        return  # Не отправляем сообщение "Некорректная команда!" и не меняем клавиатуру

    if not skip_searching_message:
        await update.message.reply_text("_Ищем собеседника..._", parse_mode=ParseMode.MARKDOWN, reply_markup=get_keyboard(True))

    users[user_id]["status"] = "in search"
    users[user_id]["search_via_gender"] = True  # Добавляем флаг, указывающий на поиск по полу
    users[user_id]["search_gender"] = gender
    await save_data(users)

    await find_partner(update, context)

# Команда /profile
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = users.get(user_id, {"gender": "не указан", "premium": False, "chats_count": 0, "likes": 0, "dislikes": 0})
    
    current_gender = user_data.get("gender", "не указан")
    if current_gender == "m":
        current_gender_text = "мужчина"
    elif current_gender == "w":
        current_gender_text = "девушка"
    else:
        current_gender_text = "не указан"
    
    premium_status = "Есть" if user_data.get("premium", False) else "Нет"
    chats_count = user_data.get("chats_count", 0)
    likes = user_data.get("likes", 0)
    dislikes = user_data.get("dislikes", 0)

    profile_message = (
        f"#️⃣ ID — {user_id}\n\n"
        f"👫 Пол — {current_gender_text}\n"
        f"💬 Чатов — {chats_count}\n"
        f"👁 Карма — 👍 {likes} 👎 {dislikes}\n\n"
        f"👑 VIP статус — {premium_status}"
    )

    buttons = [
        [InlineKeyboardButton("Настройки пола", callback_data="profile_settings")]
    ]

    if update.message:
        await update.message.reply_text(profile_message, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
    elif update.callback_query:
        query = update.callback_query
        await query.edit_message_text(profile_message, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)

# Обработчик для команды профиля
async def profile_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)

    current_gender = users[user_id].get("gender", "не указан")
    if current_gender == "m":
        current_gender_text = "мужчина"
    elif current_gender == "w":
        current_gender_text = "девушка"
    else:
        current_gender_text = "не указан"

    if current_gender_text == "не указан":
        message_text = "*💅 Настройки пола*\n\n_Укажите свой пол, чтобы поиск по полу находил вам собеседников быстрее._\n\n_У вас не указан пол 👀_"
    else:
        message_text = f"*💅 Настройки пола*\n\n_Укажите свой пол, чтобы поиск по полу находил вам собеседников быстрее._\n\n_Текущий пол: {current_gender_text}_"

    buttons = [
        [
            InlineKeyboardButton("👨‍🦰 Я парень", callback_data="set_gender_m"),
            InlineKeyboardButton("👩‍🦱 Я девушка", callback_data="set_gender_w")
        ],
        [InlineKeyboardButton("❌ Удалить мой пол", callback_data="delete_gender")],
        [InlineKeyboardButton("◀️ Вернуться назад", callback_data="back_to_profile")]
    ]

    await query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)

# Обработчик выбора пола
async def handle_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)

    if query.data == "set_gender_m":
        users[user_id]["gender"] = "m"
    elif query.data == "set_gender_w":
        users[user_id]["gender"] = "w"
    elif query.data == "delete_gender":
        if "gender" in users[user_id]:
            del users[user_id]["gender"]

    await save_data(users)
    await profile_command(update, context)

# Обработчик возврата к профилю
async def back_to_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await profile_command(update, context)

# Остановка поиска
async def stop_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if users[user_id]["status"] != "in search":
        await update.message.reply_text("_Вы не в поиске собеседника_", parse_mode=ParseMode.MARKDOWN, reply_markup=get_keyboard())
        return
    logging.info(f"(!) Пользователь {user_id} остановил поиск собеседника. (!)")
    users[user_id]["status"] = "normal"
    was_gender_search = users[user_id].pop("search_via_gender", False)
    users[user_id].pop("search_gender", None)
    await save_data(users)
    
    if was_gender_search:
        await update.message.reply_text("_Поиск остановлен_", parse_mode=ParseMode.MARKDOWN)
        await gender_search_menu(update, context)
    else:
        await update.message.reply_text("_Поиск остановлен_", parse_mode=ParseMode.MARKDOWN, reply_markup=get_keyboard())

# Команда /next
async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in active_chats:
        await update.message.reply_text(
            "🚫 *Данную команду можно использовать только в чате!*\n\n/search — _искать нового собеседника_\n/interests — _изменить интересы поиска_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_keyboard()
        )
        return
    other_user = active_chats[user_id]["chat_with"]
    del active_chats[user_id]
    del active_chats[other_user]

    blocked_users = await load_blocked_users()
    timeout_str = blocked_users.get("timeout_duration", "1h")
    time_amount = int(timeout_str[:-1])
    time_unit = timeout_str[-1]

    if time_unit == 's':
        timeout_duration = timedelta(seconds=time_amount)
    elif time_unit == 'm':
        timeout_duration = timedelta(minutes=time_amount)
    elif time_unit == 'h':
        timeout_duration = timedelta(hours=time_amount)
    elif time_unit == 'd':
        timeout_duration = timedelta(days(time_amount))

    now = datetime.now()
    pair = ",".join(sorted([user_id, other_user]))
    blocked_users[pair] = (now + timeout_duration).isoformat()

    await save_blocked_users(blocked_users)
    await save_active_chats()

    users[other_user]["status"] = "normal"
    users[other_user]["chat_with"] = None
    users[other_user]["chats_count"] += 1
    users[user_id]["chats_count"] += 1
    await save_data(users)

    try:
        await context.bot.send_message(
            other_user,
            "🛑 *Ваш собеседник завершил чат*\n\n/search — _искать нового собеседника_\n/interests — _изменить интересы поиска_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_keyboard(),
        )
        await context.bot.send_message(
            other_user,
            "_Пожалуйста, оцените вашего собеседника:_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👍", callback_data=f"like_{user_id}"),
                 InlineKeyboardButton("👎", callback_data=f"dislike_{user_id}")]
            ])
        )
    except Exception as e:
        logging.error(f"Ошибка при уведомлении пользователя {other_user}: {e}")

    # Проверка на поиск по полу
    if users[user_id].get("search_via_gender", False):
        gender = users[other_user].get("gender")
        if gender:
            if gender == "m":
                await update.message.reply_text(
                    "_Текущий чат завершен. Ищем нового собеседника мужского пола..._",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_keyboard(True),
                )
                users[user_id]["search_gender"] = "m"
            elif gender == "w":
                await update.message.reply_text(
                    "_Текущий чат завершен. Ищем нового собеседника женского пола..._",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_keyboard(True),
                )
                users[user_id]["search_gender"] = "w"
            await save_data(users)
            await gender_search(update, context, skip_searching_message=True)
        else:
            await update.message.reply_text(
                "_Текущий чат завершен. Ищем нового собеседника..._",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_keyboard(True),
            )
    else:
        await update.message.reply_text(
            "_Текущий чат завершен. Ищем нового собеседника..._",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_keyboard(True),
        )

    await update.message.reply_text(
        "_Пожалуйста, оцените вашего собеседника:_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👍", callback_data=f"like_{other_user}"),
             InlineKeyboardButton("👎", callback_data=f"dislike_{other_user}")]
        ])
    )

    if users[user_id]["status"] == "premium":
        users[user_id]["search_status"] = "in search"
    else:
        users[user_id]["status"] = "in search"
    users[user_id]["chat_with"] = None
    await save_data(users)

    await search(update, context, skip_searching_message=True)

# Команда /stop
async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in active_chats:
        await update.message.reply_text(
            "🚫 *Данную команду можно использовать только в чате!*\n\n/search — _искать нового собеседника_\n/interests — _изменить интересы поиска_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_keyboard())
        return
    other_user = active_chats[user_id]["chat_with"]
    del active_chats[user_id]
    del active_chats[other_user]

    blocked_users = await load_blocked_users()
    timeout_str = blocked_users.get("timeout_duration", "1h")
    time_amount = int(timeout_str[:-1])
    time_unit = timeout_str[-1]

    if time_unit == 's':
        timeout_duration = timedelta(seconds=time_amount)
    elif time_unit == 'm':
        timeout_duration = timedelta(minutes=time_amount)
    elif time_unit == 'h':
        timeout_duration = timedelta(hours=time_amount)
    elif time_unit == 'd':
        timeout_duration = timedelta(days=time_amount)

    now = datetime.now()
    pair = ",".join(sorted([user_id, other_user]))
    blocked_users[pair] = (now + timeout_duration).isoformat()

    await save_blocked_users(blocked_users)
    await save_active_chats()

    users[user_id]["chat_with"] = None
    users[other_user]["chat_with"] = None
    users[other_user]["status"] = "normal"
    users[other_user]["chats_count"] += 1
    users[user_id]["chats_count"] += 1
    await save_data(users)
    logging.info(f"(!) Чат между пользователем {user_id} и пользователем {other_user} завершен, они занесены в блок на {timeout_duration}. (!)")
    
    if users[user_id]["status"] == "premium":
        users[user_id]["search_status"] = "normal"
    else:
        users[user_id]["status"] = "normal"
    await save_data(users)

    await update.message.reply_text(
        "🛑 *Вы завершили чат*\n\n/search — _искать нового собеседника_\n/interests — _изменить интересы поиска_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_keyboard()
    )

    await update.message.reply_text(
        "_Пожалуйста, оцените вашего собеседника:_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👍", callback_data=f"like_{other_user}"),
             InlineKeyboardButton("👎", callback_data=f"dislike_{other_user}")]
        ])
    )

    await context.bot.send_message(
        other_user,
        "🛑 *Ваш собеседник завершил чат*\n\n/search — _искать нового собеседника_\n/interests — _изменить интересы поиска_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_keyboard(),
    )

    await context.bot.send_message(
        other_user,
        "_Пожалуйста, оцените вашего собеседника:_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👍", callback_data=f"like_{user_id}"),
             InlineKeyboardButton("👎", callback_data=f"dislike_{user_id}")]
        ])
    )

# Обработчик для кнопок оценки
async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split('_')
    action = data[0]
    rated_user_id = data[1]

    if action == "like":
        users[rated_user_id]["likes"] += 1
    elif action == "dislike":
        users[rated_user_id]["dislikes"] += 1

    await save_data(users)
    await query.answer()
    await query.edit_message_text("_Спасибо за отзыв!_", parse_mode=ParseMode.MARKDOWN)

# Команда /link
async def link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in active_chats:
        await update.message.reply_text(
            "🚫 *Данную команду можно использовать только в чате!*\n\n/search — _искать нового собеседника_\n/interests — _изменить интересы поиска_",
            parse_mode=ParseMode.MARKDOWN)
        return
    other_user_id = active_chats[user_id]["chat_with"]
    if not update.effective_user.username:
        await update.message.reply_text("Ваше имя пользователя скрыто настройками конфиденциальности. Измените настройки, чтобы делиться аккаунтом.")
        return
    try:
        await context.bot.send_message(
            chat_id=other_user_id,
            text=f"Ваш собеседник отправил ссылку на свой профиль: @{update.effective_user.username}"
        )
        await update.message.reply_text("Ссылка на ваш профиль отправлена собеседнику.")
    except Exception as e:
        logging.error(f"Ошибка при отправке ссылки: {e}")
        await update.message.reply_text("Произошла ошибка при отправке ссылки.")

# Обработчик завершения выбора интересов
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.edit_message_text(
        f"Ваши интересы сохранены: {', '.join(users[user_id]['interests']) or 'Нет интересов'}"
    )
    await query.message.reply_text("Интересы выбраны.", reply_markup=get_keyboard())

# Обработчик сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        users[user_id] = {"status": "normal", "chat_with": None, "interests": [], "gender": None, "premium": False}
        await save_data(users)
    if user_id not in active_chats:
        if update.message.text == "🔎 Поиск собеседника":
            await search(update, context)
        elif update.message.text == "❌ Остановить поиск":
            await stop_search(update, context)
        elif update.message.text == "📙 Интересы":
            await interests_command(update, context)
        elif update.message.text == "🎭 Поиск по полу":
            await gender_search_menu(update, context)
        elif update.message.text == "💼 Профиль":
            await profile_command(update, context)
        elif update.message.text == "👨‍🦰 Поиск М" or update.message.text == "👩‍🦱 Поиск Д":
            await gender_search(update, context)
        elif update.message.text == "◀️ Вернуться назад":
            users[user_id]["status"] = "normal"
            await save_data(users)
            await update.message.reply_text(
                "_Вы вернулись в главное меню_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_keyboard()
            )
        else:
            if users[user_id].get("search_via_gender", False):
                reply_markup = get_keyboard(True)
            elif users[user_id]["status"] == "in search":
                reply_markup = get_keyboard(True)
            else:
                reply_markup = get_keyboard()
        return

    other_user_id = active_chats[user_id]["chat_with"]
    text = update.message.text

    if text and "@" in text and not text.startswith("/link"):
        await update.message.reply_text("Отправка упоминаний запрещена. Используйте /link.")
        return
    if text and re.search(r"(https?://|www\.[a-zA-Z]|[a-zA-Z]\.[a-z]{2,})", text.replace(" ", "")):
        await update.message.reply_text("Отправка ссылок запрещена.")
        return

    try:
        reply_to_message_id = None
        if update.message.reply_to_message:
            replied_message_id = update.message.reply_to_message.message_id
            if "message_map" in active_chats[user_id] and replied_message_id in active_chats[user_id]["message_map"]:
                reply_to_message_id = active_chats[user_id]["message_map"][replied_message_id]

        if update.message.text:
            sent_message = await context.bot.send_message(
                chat_id=other_user_id,
                text=update.message.text,
                entities=update.message.entities,
                reply_to_message_id=reply_to_message_id,
                protect_content=True,
            )
        elif update.message.photo:
            sent_message = await context.bot.send_photo(
                chat_id=other_user_id,
                photo=update.message.photo[-1].file_id,
                caption=update.message.caption,
                reply_to_message_id=reply_to_message_id,
                protect_content=True,
                caption_entities=update.message.caption_entities,
            )
        elif update.message.video:
            sent_message = await context.bot.send_video(
                chat_id=other_user_id,
                video=update.message.video.file_id,
                caption=update.message.caption,
                reply_to_message_id=reply_to_message_id,
                protect_content=True,
                caption_entities=update.message.caption_entities,
            )
        elif update.message.document:
            sent_message = await context.bot.send_document(
                chat_id=other_user_id,
                document=update.message.document.file_id,
                caption=update.message.caption,
                reply_to_message_id=reply_to_message_id,
                protect_content=True,
                caption_entities=update.message.caption_entities,
            )
        elif update.message.audio:
            sent_message = await context.bot.send_audio(
                chat_id=other_user_id,
                audio=update.message.audio.file_id,
                caption=update.message.caption,
                reply_to_message_id=reply_to_message_id,
                protect_content=True,
                caption_entities=update.message.caption_entities,
            )
        elif update.message.voice:
            sent_message = await context.bot.send_voice(
                chat_id=other_user_id,
                voice=update.message.voice.file_id,
                caption=update.message.caption,
                reply_to_message_id=reply_to_message_id,
                protect_content=True,
                caption_entities=update.message.caption_entities,
            )
        elif update.message.sticker:
            sent_message = await context.bot.send_sticker(
                chat_id=other_user_id,
                sticker=update.message.sticker.file_id,
                reply_to_message_id=reply_to_message_id,
                protect_content=True,
            )
        elif update.message.video_note:
            sent_message = await context.bot.send_video_note(
                chat_id=other_user_id,
                video_note=update.message.video_note.file_id,
                reply_to_message_id=reply_to_message_id,
                protect_content=True,
            )
        else:
            await update.message.reply_text("Этот тип сообщения не поддерживается.")
            return

        if "message_map" not in active_chats[user_id]:
            active_chats[user_id]["message_map"] = {}
        if "message_map" not in active_chats[other_user_id]:
            active_chats[other_user_id]["message_map"] = {}
        active_chats[user_id]["message_map"][update.message.message_id] = sent_message.message_id
        active_chats[other_user_id]["message_map"][sent_message.message_id] = update.message.message_id

        await save_active_chats()

    except Exception as e:
        logging.error(f"Ошибка при обработке сообщения: {e}")
        await update.message.reply_text("Произошла ошибка при пересылке сообщения.")

# Команда /premium
async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        # Если пользователь не администратор, ничего не отвечаем
        return

    if len(context.args) != 1:
        await update.message.reply_text("_Используйте команду в формате: /premium <id пользователя>_", parse_mode=ParseMode.MARKDOWN)
        return

    target_id = context.args[0]
    if target_id not in users:
        await update.message.reply_text(f"_Пользователь с id {target_id} не найден._", parse_mode=ParseMode.MARKDOWN)
        return

    users[target_id]["premium"] = True
    await save_data(users)

    await context.bot.send_message(
        chat_id=target_id,
        text="*👑 Вам был выдан Premium статус!*",
        parse_mode=ParseMode.MARKDOWN,
    )
    await update.message.reply_text(f"*👑 Пользователю с id {target_id} был выдан Premium статус*", parse_mode=ParseMode.MARKDOWN)

# Команда /unpremium
async def unpremium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        # Если пользователь не администратор, ничего не отвечаем
        return

    if len(context.args) != 1:
        await update.message.reply_text("Используйте команду в формате: /unpremium <id пользователя>", parse_mode=ParseMode.MARKDOWN)
        return

    target_id = context.args[0]
    if target_id not in users:
        await update.message.reply_text(f"_Пользователь с id {target_id} не найден._", parse_mode=ParseMode.MARKDOWN)
        return

    users[target_id]["premium"] = False
    await save_data(users)

    await update.message.reply_text(f"*⚔️ У пользователя с id {target_id} был забран Premium статус*", parse_mode=ParseMode.MARKDOWN)

# Команда /ban
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        # Если пользователь не администратор, ничего не отвечаем
        return

    if len(context.args) != 1:
        await update.message.reply_text("_Используйте команду в формате: /ban <id пользователя>_", parse_mode=ParseMode.MARKDOWN)
        return

    target_id = context.args[0]
    if target_id not in users:
        await update.message.reply_text(f"_Пользователь с id {target_id} не найден._", parse_mode=ParseMode.MARKDOWN)
        return

    users[target_id]["status"] = "banned"
    await save_data(users)

    if target_id in active_chats:
        chat_with_id = active_chats[target_id]["chat_with"]
        del active_chats[target_id]
        del active_chats[chat_with_id]
        await save_active_chats()
        await context.bot.send_message(
            chat_with_id,
            "*⚠️ Пользователь, с которым вы общались, был заблокирован администратором*\n\n/search — _искать нового собеседника_\n/interests — _изменить интересы поиска_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_keyboard()
        )
        await context.bot.send_message(
            target_id,
            "*⚠️ Вы были заблокированы администратором. Чат завершен.*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_keyboard()
        )
        # Присваиваем статус "normal" собеседнику заблокированного пользователя
        users[chat_with_id]["status"] = "normal"
        await save_data(users)

    await update.message.reply_text(f"*🚫 Пользователь с id {target_id} заблокирован*", parse_mode=ParseMode.MARKDOWN)

# Команда /unban
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        # Если пользователь не администратор, ничего не отвечаем
        return

    if len(context.args) != 1:
        await update.message.reply_text("_Используйте команду в формате: /unban <id пользователя>_", parse_mode=ParseMode.MARKDOWN)
        return

    target_id = context.args[0]
    if target_id not in users:
        await update.message.reply_text(f"_Пользователь с id {target_id} не найден._", parse_mode=ParseMode.MARKDOWN)
        return

    users[target_id]["status"] = "normal"
    await save_data(users)
    await update.message.reply_text(f"*✅ Пользователь с id {target_id} разблокирован*", parse_mode=ParseMode.MARKDOWN)

# Обработка команды /stats
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        # Если пользователь не администратор, ничего не отвечаем
        return

    # Загрузка данных
    users = await load_data()
    active_chats = await load_active_chats()
    blocked_users = await load_blocked_users()

    total_users = len(users)
    active_chats_count = len(active_chats)
    blocked_users_count = sum(1 for user in users.values() if user["status"] == "banned")
    timeout_users_count = sum(1 for pair, block_time in blocked_users.items() if block_time != "timeout_duration")
    searching_users_count = sum(1 for user in users.values() if user["status"] == "in search")

    stats_message = (
        f"*📊 Статистика бота*\n\n"
        f"👥 Общее количество пользователей: {total_users}\n"
        f"💬 Количество активных чатов: {active_chats_count}\n"
        f"🔍 Пользователи в поиске: {searching_users_count}\n"
        f"⏳ Пользователи в тайм-ауте: {timeout_users_count}\n"
        f"🚫 Заблокированные пользователи: {blocked_users_count}"
    )

    await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)

# Команда /debug
async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        # Если пользователь не администратор, ничего не отвечаем
        return
    
    # Устанавливаем статус всех пользователей на "normal", кроме заблокированных
    for user in users:
        if users[user]["status"] != "banned":
            users[user]["status"] = "normal"
    
    # Сохраняем изменения в users.json
    await save_data(users)
    
    # Очищаем active_chats.json
    active_chats.clear()
    await save_active_chats()

    # Очищаем заблокированных пользователей, но оставляем timeout_duration
    blocked_users = await load_blocked_users()
    timeout_duration = blocked_users.get("timeout_duration", "1h")
    blocked_users = {"timeout_duration": timeout_duration}
    await save_blocked_users(blocked_users)

    await update.message.reply_text("Дебаг успешно прошёл. Все пользователи сброшены в 'normal', активные чаты очищены, заблокированные пользователи удалены.")

# Команда /getid
async def getid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)  # Приведение user_id к строке
    if user_id != str(ADMIN_ID):  # Приведение ADMIN_ID к строке для сравнения
        # Если пользователь не администратор, ничего не отвечаем
        return

    if user_id not in active_chats:
        await update.message.reply_text("🚫 *Данную команду можно использовать только в чате!*\n\n/search — _искать нового собеседника_\n/interests — _изменить интересы поиска_", parse_mode=ParseMode.MARKDOWN)
        return

    chat_with_id = active_chats[user_id]["chat_with"]
    await update.message.reply_text(f"_ID собеседника: {chat_with_id}_", parse_mode=ParseMode.MARKDOWN)

# Запуск бота
async def run_bot():
    # Инициализация приложения
    application = Application.builder().token(TOKEN).build()

    # Загрузка данных асинхронно
    global users, active_chats, blocked_users
    users = await load_data()
    active_chats = await load_active_chats()
    blocked_users = await load_blocked_users()

    # Добавление обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("next", next_command))
    application.add_handler(CommandHandler("stop", stop_chat))
    application.add_handler(CommandHandler("link", link))
    application.add_handler(CommandHandler("interests", interests_command))
    application.add_handler(CommandHandler("debug", debug_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("getid", getid_command))
    application.add_handler(CommandHandler("timeout", timeout_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("premium", premium_command))
    application.add_handler(CommandHandler("unpremium", unpremium_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CallbackQueryHandler(handle_interests, pattern="^interest_"))
    application.add_handler(CallbackQueryHandler(done, pattern="^done$"))
    application.add_handler(CallbackQueryHandler(reset_interests, pattern="^reset_interests$"))
    application.add_handler(CallbackQueryHandler(handle_gender, pattern="^set_gender_"))
    application.add_handler(CallbackQueryHandler(handle_gender, pattern="^delete_gender$"))
    application.add_handler(CallbackQueryHandler(profile_settings, pattern="^profile_settings$"))
    application.add_handler(CallbackQueryHandler(back_to_profile, pattern="^back_to_profile$"))
    application.add_handler(CallbackQueryHandler(handle_rating, pattern="^(like|dislike)_"))
    application.add_handler(MessageHandler((filters.TEXT | filters.ATTACHMENT) & ~filters.COMMAND, handle_message))

    # Сохранение текущего тайм-аута в контекст бота при запуске
    if "timeout_duration" in blocked_users:
        application.bot_data["last_timeout"] = blocked_users["timeout_duration"]
    else:
        application.bot_data["last_timeout"] = "1h"

    return application

def main():
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        # Создаем и устанавливаем event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Инициализируем бота
        app = loop.run_until_complete(run_bot())
        
        # Запускаем polling в отдельном потоке
        loop.run_until_complete(app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            stop_signals=None
        ))
        
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
        loop.run_until_complete(app.stop())
    except Exception as e:
        logging.error(f"Bot stopped due to error: {e}")
    finally:
        # Закрываем loop
        loop.close()

if __name__ == "__main__":
    main()