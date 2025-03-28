import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler
)
from datetime import datetime, timedelta
import sqlite3
import openpyxl
from openpyxl import Workbook
import pytz

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
NAME, PHONE, COMPANY, REQUEST = range(4)
ADMIN_MENU, SEND_MESSAGE, SELECT_RECIPIENTS, SCHEDULE, CONFIRM_SEND = range(4, 9)

# Настройка базы данных
def init_db():
    conn = sqlite3.connect('consultations.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        phone TEXT,
        company TEXT,
        request TEXT,
        registration_date TEXT,
        is_active INTEGER DEFAULT 1,
        last_activity TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        admin_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        is_superadmin INTEGER DEFAULT 0
    )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# Проверка админа
def is_admin(user_id):
    conn = sqlite3.connect('consultations.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM admins WHERE admin_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def is_superadmin(user_id):
    conn = sqlite3.connect('consultations.db')
    cursor = conn.cursor()
    cursor.execute('SELECT is_superadmin FROM admins WHERE admin_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result and result[0] == 1

# Добавление пользователя в базу
def add_user(user_data):
    conn = sqlite3.connect('consultations.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT OR REPLACE INTO users 
    (user_id, username, first_name, last_name, phone, company, request, registration_date, is_active, last_activity)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
    ''', (
        user_data['user_id'],
        user_data.get('username'),
        user_data.get('first_name'),
        user_data.get('last_name'),
        user_data.get('phone'),
        user_data.get('company'),
        user_data.get('request'),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ))
    
    conn.commit()
    conn.close()

# Стартовое сообщение
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = {
        'user_id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name
    }
    
    # Добавляем пользователя в базу
    add_user(user_data)
    
    # Приветственное сообщение
    welcome_text = (
        "Привет! Я виртуальный ассистент Александра Трибунского. 🤝\n"
        "Вы сделали первый шаг, чтобы качнуть свой бизнес. Теперь мне нужно немного информации о вас и вашем бизнесе, "
        "чтобы сделать консультацию максимально полезной.\n\n"
        "Пожалуйста, введите ваше имя:"
    )
    
    keyboard = [
        [InlineKeyboardButton("Написать Александру лично", url="https://t.me/username")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    return NAME

# Обработка имени
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    
    await update.message.reply_text("Отлично! Теперь введите ваш номер телефона:")
    return PHONE

# Обработка телефона
async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text
    
    await update.message.reply_text("Введите название вашей компании:")
    return COMPANY

# Обработка компании
async def get_company(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['company'] = update.message.text
    
    await update.message.reply_text("Опишите ваш запрос на консультацию:")
    return REQUEST

# Обработка запроса и завершение
async def get_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['request'] = update.message.text
    user = update.effective_user
    
    # Сохраняем данные
    user_data = {
        'user_id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'phone': context.user_data['phone'],
        'company': context.user_data['company'],
        'request': context.user_data['request']
    }
    add_user(user_data)
    
    # Отправляем менеджерам
    await notify_managers(context, user_data)
    
    # Благодарность
    await update.message.reply_text(
        "Спасибо! Ваша заявка принята. Мы свяжемся с вами в ближайшее время.\n\n"
        "Вы также можете написать Александру лично:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Написать Александру", url="https://t.me/username")]
        ])
    )
    
    return ConversationHandler.END

# Уведомление менеджеров
async def notify_managers(context, user_data):
    conn = sqlite3.connect('consultations.db')
    cursor = conn.cursor()
    cursor.execute('SELECT admin_id FROM admins WHERE is_superadmin = 0')
    managers = cursor.fetchall()
    conn.close()
    
    message_text = (
        "📌 Новая заявка на консультацию:\n\n"
        f"👤 Имя: {user_data.get('first_name', '')} {user_data.get('last_name', '')}\n"
        f"📱 Телефон: {user_data['phone']}\n"
        f"🏢 Компания: {user_data['company']}\n"
        f"📝 Запрос: {user_data['request']}\n\n"
        f"🆔 ID пользователя: {user_data['user_id']}"
    )
    
    for manager in managers:
        try:
            await context.bot.send_message(
                chat_id=manager[0],
                text=message_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Написать клиенту", url=f"tg://user?id={user_data['user_id']}")]
                ])
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления менеджеру {manager[0]}: {e}")

# Админ-панель
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📤 Выгрузить базу", callback_data="export")],
        [InlineKeyboardButton("📩 Сделать рассылку", callback_data="broadcast")],
    ]
    
    if is_superadmin(update.effective_user.id):
        keyboard.append([InlineKeyboardButton("👨‍💼 Добавить админа", callback_data="add_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Админ-панель:", reply_markup=reply_markup)
    return ADMIN_MENU

# Обработка кнопок админ-панели
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "stats":
        await show_stats(update, context)
    elif query.data == "export":
        await export_to_excel(update, context)
    elif query.data == "broadcast":
        await start_broadcast(update, context)
    elif query.data == "add_admin":
        await add_admin(update, context)
    
    return ADMIN_MENU

# Показать статистику
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('consultations.db')
    cursor = conn.cursor()
    
    # Общее количество
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    # За сегодня
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute('SELECT COUNT(*) FROM users WHERE date(registration_date) = ?', (today,))
    today_users = cursor.fetchone()[0]
    
    # Активные
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_active = 1')
    active_users = cursor.fetchone()[0]
    
    # Неактивные
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_active = 0')
    inactive_users = cursor.fetchone()[0]
    
    conn.close()
    
    stats_text = (
        "📊 Статистика пользователей:\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"🆕 Сегодня: {today_users}\n"
        f"✅ Активные: {active_users}\n"
        f"❌ Неактивные: {inactive_users}"
    )
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=stats_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ])
    )

# Выгрузка в Excel
async def export_to_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('consultations.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()
    conn.close()
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Пользователи"
    
    # Заголовки
    headers = [
        "ID", "Username", "Имя", "Фамилия", "Телефон", 
        "Компания", "Запрос", "Дата регистрации", "Активен", "Последняя активность"
    ]
    ws.append(headers)
    
    # Данные
    for user in users:
        ws.append(user)
    
    # Сохраняем файл
    filename = f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    wb.save(filename)
    
    # Отправляем файл
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=open(filename, 'rb'),
        caption="Экспорт базы пользователей",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ])
    )

# Начало рассылки
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Всем пользователям", callback_data="broadcast_all")],
        [InlineKeyboardButton("Новым (за неделю)", callback_data="broadcast_new")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ]
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите получателей рассылки:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_RECIPIENTS

# Обработка выбора получателей
async def select_recipients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "broadcast_all":
        context.user_data['broadcast_type'] = 'all'
    elif query.data == "broadcast_new":
        context.user_data['broadcast_type'] = 'new'
    elif query.data == "back":
        await admin_panel(update, context)
        return ADMIN_MENU
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Введите сообщение для рассылки (можно с фото):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ])
    )
    return SEND_MESSAGE

# Обработка сообщения для рассылки
async def get_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['broadcast_photo'] = update.message.photo[-1].file_id
        context.user_data['broadcast_text'] = update.message.caption or ""
    else:
        context.user_data['broadcast_text'] = update.message.text
    
    keyboard = [
        [InlineKeyboardButton("Моментально", callback_data="schedule_now")],
        [InlineKeyboardButton("Запланировать", callback_data="schedule_later")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ]
    
    await update.message.reply_text(
        "Когда сделать рассылку?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SCHEDULE

# Обработка времени рассылки
async def schedule_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "schedule_now":
        context.user_data['schedule_time'] = 'now'
        await confirm_broadcast(update, context)
        return CONFIRM_SEND
    elif query.data == "schedule_later":
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Введите дату и время рассылки в формате ДД.ММ.ГГГГ ЧЧ:ММ (МСК):"
        )
        return SCHEDULE
    elif query.data == "back":
        await start_broadcast(update, context)
        return SELECT_RECIPIENTS

# Подтверждение рассылки
async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('schedule_time') == 'later':
        try:
            date_str = update.message.text
            date_obj = datetime.strptime(date_str, '%d.%m.%Y %H:%M')
            context.user_data['schedule_time'] = date_obj
        except ValueError:
            await update.message.reply_text("Неверный формат даты. Попробуйте снова.")
            return SCHEDULE
    
    broadcast_type = "всем пользователям" if context.user_data['broadcast_type'] == 'all' else "новым пользователям (за неделю)"
    schedule_time = "моментально" if context.user_data['schedule_time'] == 'now' else f"запланировано на {context.user_data['schedule_time'].strftime('%d.%m.%Y %H:%M')}"
    
    confirm_text = (
        "Подтвердите рассылку:\n\n"
        f"🔹 Получатели: {broadcast_type}\n"
        f"⏰ Время: {schedule_time}\n\n"
        "Сообщение:"
    )
    
    if 'broadcast_photo' in context.user_data:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=context.user_data['broadcast_photo'],
            caption=f"{confirm_text}\n{context.user_data['broadcast_text']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_send")],
                [InlineKeyboardButton("❌ Отменить", callback_data="cancel_send")]
            ])
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"{confirm_text}\n{context.user_data['broadcast_text']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_send")],
                [InlineKeyboardButton("❌ Отменить", callback_data="cancel_send")]
            ])
        )
    return CONFIRM_SEND

# Запуск рассылки
async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_send":
        conn = sqlite3.connect('consultations.db')
        cursor = conn.cursor()
        
        if context.user_data['broadcast_type'] == 'all':
            cursor.execute('SELECT user_id FROM users WHERE is_active = 1')
        else:
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('SELECT user_id FROM users WHERE is_active = 1 AND registration_date >= ?', (week_ago,))
        
        users = cursor.fetchall()
        conn.close()
        
        success = 0
        failed = 0
        
        for user in users:
            try:
                if 'broadcast_photo' in context.user_data:
                    await context.bot.send_photo(
                        chat_id=user[0],
                        photo=context.user_data['broadcast_photo'],
                        caption=context.user_data['broadcast_text'],
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("Написать Александру", url="https://t.me/username")]
                        ])
                    )
                else:
                    await context.bot.send_message(
                        chat_id=user[0],
                        text=context.user_data['broadcast_text'],
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("Написать Александру", url="https://t.me/username")]
                        ])
                    )
                success += 1
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {user[0]}: {e}")
                failed += 1
                # Помечаем пользователя как неактивного
                conn = sqlite3.connect('consultations.db')
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET is_active = 0 WHERE user_id = ?', (user[0],))
                conn.commit()
                conn.close()
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Рассылка завершена:\n\n✅ Успешно: {success}\n❌ Не доставлено: {failed}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 В админ-панель", callback_data="back")]
            ])
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Рассылка отменена",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 В админ-панель", callback_data="back")]
            ])
        )
    
    return ADMIN_MENU

# Добавление админа (только для суперадмина)
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_superadmin(update.effective_user.id):
        await update.message.reply_text("У вас нет прав для этой операции.")
        return ADMIN_MENU
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Перешлите любое сообщение от пользователя, которого хотите сделать администратором:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ])
    )
    return ADMIN_MENU

# Обработка пересланного сообщения для добавления админа
async def process_new_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.forward_from:
        await update.message.reply_text("Пожалуйста, перешлите сообщение от пользователя.")
        return ADMIN_MENU
    
    new_admin = update.message.forward_from
    
    conn = sqlite3.connect('consultations.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO admins (admin_id, username, full_name) VALUES (?, ?, ?)', 
                  (new_admin.id, new_admin.username, f"{new_admin.first_name} {new_admin.last_name}"))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"Пользователь @{new_admin.username} добавлен как администратор.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 В админ-панель", callback_data="back")]
        ])
    )
    return ADMIN_MENU

# Отмена
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END

# Основная функция
def main():
    application = ApplicationBuilder().token("7729706158:AAFgUHY62JHT65caVu1vZWlTjG69t69C8Wo").build()
    
    # Обработчик для сбора заявок
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            COMPANY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_company)],
            REQUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_request)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Обработчик для админ-панели
    admin_handler = ConversationHandler(
        entry_points=[CommandHandler('admin', admin_panel)],
        states={
            ADMIN_MENU: [CallbackQueryHandler(button_handler)],
            SELECT_RECIPIENTS: [CallbackQueryHandler(select_recipients)],
            SEND_MESSAGE: [MessageHandler(filters.TEXT | filters.PHOTO, get_broadcast_message)],
            SCHEDULE: [
                CallbackQueryHandler(schedule_broadcast),
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_broadcast)
            ],
            CONFIRM_SEND: [CallbackQueryHandler(send_broadcast)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Добавляем обработчики
    application.add_handler(conv_handler)
    application.add_handler(admin_handler)
    application.add_handler(MessageHandler(filters.FORWARD & filters.USER, process_new_admin))
    
    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
