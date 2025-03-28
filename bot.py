from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes


# Токен бота (замени на свой из @BotFather)
TOKEN = "7729706158:AAFgUHY62JHT65caVu1vZWlTjG69t69C8Wo"


# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот для консультаций. Отправь /help для списка команд.")


# Обработчик команды /help
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Доступные команды:\n/start - начать\n/help - помощь")


# Запуск бота
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Регистрация команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help))
    
    print("Бот запущен!")
    app.run_polling()