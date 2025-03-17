import os
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackContext,
)
from dotenv import load_dotenv  # Для загрузки переменных из .env
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import smtplib
from flask import Flask, request
from hypercorn.config import Config
from hypercorn.asyncio import serve
import asyncio

# Загружаем переменные окружения из .env
load_dotenv()

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для диалога
FEEDBACK_CONTENT, PHOTO_ATTACHMENT, VISIT_DETAILS, CONTACT_INFO = range(4)

# Получаем чувствительные данные из переменных окружения
BOT_TOKEN = os.environ.get("BOT_TOKEN")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

# Проверяем наличие необходимых переменных окружения
if not all([BOT_TOKEN, EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER]):
    logger.error("Missing required environment variables.")
    exit(1)

# Создаем Flask-приложение
app = Flask(__name__)

# Обработчик /start
async def start(update: Update, context):
    try:
        logger.info("Entering start handler.")
        await update.message.reply_text(
            "Пожалуйста, напишите ваш отзыв ниже. \n"
            "Все обращения рассматриваются непосредственно руководством."
        )
        return FEEDBACK_CONTENT
    except Exception as e:
        logger.error(f"Error in start handler: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END

# Обработчик команды /cancel
async def cancel(update: Update, context: CallbackContext):
    try:
        logger.info("Entering cancel handler.")
        await update.message.reply_text(
            "Действие отменено. Для повторного старта нажмите /start."
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in cancel handler: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте позже.")
        return ConversationHandler.END

# Обработка содержимого отзыва
async def feedback_content(update: Update, context):
    try:
        logger.info("Entering feedback_content handler.")
        context.user_data["feedback_content"] = update.message.text
        reply_keyboard = [["Да", "Нет"]]
        await update.message.reply_text(
            "Хотите прикрепить фото к отзыву?",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
        )
        return PHOTO_ATTACHMENT
    except Exception as e:
        logger.error(f"Error in feedback_content handler: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END

# Обработка прикрепления фото
async def photo_attachment(update: Update, context):
    try:
        logger.info("Entering photo_attachment handler.")
        if update.message.text.lower() == "да":
            context.user_data["photos"] = []  # Инициализируем список для хранения путей к фото
            reply_keyboard = [["Завершить отправку фото"]]
            await update.message.reply_text(
                "Пожалуйста, отправьте фото. Когда закончите, нажмите 'Завершить отправку фото' или отправьте команду /done.",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
            )
            return PHOTO_ATTACHMENT
        elif update.message.text.lower() == "нет":
            context.user_data["photos"] = []  # Фото отсутствуют
            await update.message.reply_text(
                "Укажите дату, время посещения и название зала (например, '15 мая 2025, 14:00-17:00, Баня Купеческая'). "
                "\nЕсли не хотите указывать, отправьте '-'",
                reply_markup=ReplyKeyboardRemove(),
            )
            return VISIT_DETAILS
    except Exception as e:
        logger.error(f"Error in photo_attachment handler: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END

# Обработка фото
async def handle_photo(update: Update, context):
    try:
        logger.info("Entering handle_photo handler.")
        photo_file = await update.message.photo[-1].get_file()
        photo_path = f"photos/{photo_file.file_id}.jpg"
        os.makedirs("photos", exist_ok=True)  # Создаем папку для фото
        await photo_file.download_to_drive(photo_path)

        # Добавляем путь к фото в список
        if "photos" not in context.user_data:
            context.user_data["photos"] = []
        context.user_data["photos"].append(photo_path)

        reply_keyboard = [["Завершить отправку фото"]]
        await update.message.reply_text(
            f"Фото успешно прикреплено ({len(context.user_data['photos'])} шт.). "
            "Отправьте еще фото или нажмите 'Завершить отправку фото'.",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
        )
        return PHOTO_ATTACHMENT
    except Exception as e:
        logger.error(f"Error in handle_photo handler: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END

# Завершение прикрепления фото
async def done_photos(update: Update, context):
    try:
        logger.info("Entering done_photos handler.")
        await update.message.reply_text(
            "Фото успешно прикреплены. \n\n"
            "Укажите дату, время посещения и название зала (например, '15 мая 2025, 14:00-17:00, Баня Купеческая'). "
            "\nЕсли не хотите указывать, отправьте '-'",
            reply_markup=ReplyKeyboardRemove(),
        )
        return VISIT_DETAILS
    except Exception as e:
        logger.error(f"Error in done_photos handler: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END

# Обработка данных о посещении
async def visit_details(update: Update, context):
    try:
        logger.info("Entering visit_details handler.")
        context.user_data["visit_details"] = update.message.text
        await update.message.reply_text(
            "Пожалуйста, оставьте ваше имя и номер телефона для обратной связи (например, 'Иван, +79991234567'). "
            "\nЕсли не хотите оставлять, отправьте '-'"
        )
        return CONTACT_INFO
    except Exception as e:
        logger.error(f"Error in visit_details handler: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END

# Обработка контактных данных и отправка отзыва на email
async def contact_info(update: Update, context):
    try:
        logger.info("Entering contact_info handler.")
        context.user_data["contact_info"] = update.message.text

        # Формируем сообщение для отправки
        feedback_content = context.user_data.get("feedback_content", "Не указано")
        visit_details = context.user_data.get("visit_details", "Не указано")
        contact_info = context.user_data.get("contact_info", "Не указано")
        message = (
            f"Отзыв: {feedback_content}\n"
            f"Детали посещения: {visit_details}\n"
            f"Контактные данные: {contact_info}"
        )

        photos = context.user_data.get("photos", [])
        send_email(message, photos)

        # Удаляем фото после отправки
        for photo_path in photos:
            if os.path.exists(photo_path):
                os.remove(photo_path)
                logger.info(f"Файл удален: {photo_path}")

        await update.message.reply_text(
            "Спасибо за ваш отзыв! Мы обязательно его рассмотрим и свяжемся с вами. \n\n"
            "Для повторного отзыва нажмите /start"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке email: {e}")
        await update.message.reply_text(
            "Произошла ошибка при отправке отзыва. \nПожалуйста, попробуйте позже."
        )
    return ConversationHandler.END

# Отправка email
def send_email(message, attachment_paths=None):
    try:
        now = datetime.now()
        formatted_datetime = now.strftime("%Y-%m-%d %H:%M")  # Формат: ГГГГ-ММ-ДД ЧЧ:ММ

        # Создаем объект MIMEMultipart
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER
        msg["Subject"] = f"Новый отзыв - {formatted_datetime}"

        # Добавляем текст сообщения
        msg.attach(MIMEText(message, "plain"))

        # Прикрепляем файлы
        if attachment_paths:
            for attachment_path in attachment_paths:
                if os.path.exists(attachment_path):
                    with open(attachment_path, "rb") as file:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(file.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition",
                            f'attachment; filename="{attachment_path.split(os.sep)[-1]}"',
                        )
                        msg.attach(part)
                else:
                    logger.warning(f"Файл для вложения не найден: {attachment_path}")
        else:
            logger.warning("Файлы для вложения не найдены.")

        # Подключаемся к SMTP-серверу Mail.ru
        with smtplib.SMTP("smtp.mail.ru", 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

        logger.info("Email успешно отправлен.")
    except Exception as e:
        logger.error(f"Ошибка при отправке email: {e}")
        raise

# Обработчик ошибок для Telegram
async def error_handler(update: Update, context: CallbackContext):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if update and update.message:
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте позже.")

# Настройка вебхука
@app.route("/" + BOT_TOKEN, methods=["POST"])
async def webhook():
    try:
        logger.info("Entering webhook handler.")
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        await bot_app.process_update(update)
        return "!", 200
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}")
        return "Internal Server Error", 500

# Маршрут для проверки работоспособности
@app.route("/", methods=["GET", "HEAD"])
def health_check():
    logger.info("Health check requested.")
    return "OK", 200

# Запуск Flask-приложения
if __name__ == "__main__":
    # Инициализация бота
    bot_app = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики в бота
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FEEDBACK_CONTENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_content)
            ],
            PHOTO_ATTACHMENT: [
                MessageHandler(filters.PHOTO, handle_photo),
                MessageHandler(filters.Regex("^Завершить отправку фото$"), done_photos),
                CommandHandler("done", done_photos),
                MessageHandler(filters.TEXT & ~filters.COMMAND, photo_attachment),
            ],
            VISIT_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, visit_details)
            ],
            CONTACT_INFO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, contact_info)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],  # Добавляем обработчик команды /cancel
    )
    bot_app.add_handler(conv_handler)

    # Добавляем обработчик ошибок
    bot_app.add_error_handler(error_handler)

    # Асинхронная настройка вебхука
    async def setup_webhook():
        webhook_url = f"https://berezka-feedback-bot.onrender.com/{BOT_TOKEN}"
        await bot_app.initialize()  # Инициализируем Application
        await bot_app.bot.set_webhook(url=webhook_url)
        logger.info("Webhook successfully set.")

    # Запускаем настройку вебхука
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup_webhook())

    # Явно указываем порт для Flask
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting Flask on port {port}")

    # Используем асинхронный сервер для Flask
    config = Config()
    config.bind = [f"0.0.0.0:{port}"]

    # Запускаем Flask через Hypercorn
    try:
        loop.run_until_complete(serve(app, config))
    except KeyboardInterrupt:
        pass