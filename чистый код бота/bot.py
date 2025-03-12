import logging
import os
from datetime import datetime  # Для работы с датой и временем
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# Настройки для отправки email
EMAIL_SENDER = "berezka_feedback@mail.ru"
EMAIL_PASSWORD = "tE6H2rnufkZu4jqHKpwW"
EMAIL_RECEIVER = "berezka_sauna@mail.ru"

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для диалога
FEEDBACK_CONTENT, PHOTO_ATTACHMENT, VISIT_DETAILS, CONTACT_INFO = range(4)

async def start(update: Update, context):
    """Приветствие пользователя и начало диалога."""
    await update.message.reply_text(
        "Пожалуйста, напишите ваш отзыв ниже. \nВсе обращения рассматриваются непосредственно руководством."
    )
    return FEEDBACK_CONTENT

async def feedback_content(update: Update, context):
    """Обработка содержимого отзыва."""
    context.user_data['feedback_content'] = update.message.text
    # Предлагаем прикрепить фото
    reply_keyboard = [["Да", "Нет"]]
    await update.message.reply_text(
        "Хотите прикрепить фото к отзыву?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return PHOTO_ATTACHMENT

async def photo_attachment(update: Update, context):
    """Обработка прикрепления фото."""
    if update.message.text.lower() == "да":
        context.user_data['photos'] = []  # Инициализируем список для хранения путей к фото
        reply_keyboard = [["Завершить отправку фото"]]  # Кнопка для завершения отправки фото
        await update.message.reply_text(
            "Пожалуйста, отправьте фото. Когда закончите, нажмите 'Завершить отправку фото' или отправьте команду /done.",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        )
        return PHOTO_ATTACHMENT  # Ожидаем фото
    elif update.message.text.lower() == "нет":
        context.user_data['photos'] = []  # Фото отсутствуют
        await update.message.reply_text(
            "Укажите дату, время посещения и название зала (например, '15 мая 2025, 14:00-17:00, Баня Купеческая'). "
            "\nЕсли не хотите указывать, отправьте '-'"
        )
        return VISIT_DETAILS

async def handle_photo(update: Update, context):
    """Скачивание и сохранение фото."""
    photo_file = await update.message.photo[-1].get_file()
    photo_path = f"photos/{photo_file.file_id}.jpg"
    os.makedirs("photos", exist_ok=True)  # Создаем папку для фото
    await photo_file.download_to_drive(photo_path)
    
    # Добавляем путь к фото в список
    if 'photos' not in context.user_data:
        context.user_data['photos'] = []
    context.user_data['photos'].append(photo_path)
    
    reply_keyboard = [["Завершить отправку фото"]]  # Кнопка для завершения отправки фото
    await update.message.reply_text(
        f"Фото успешно прикреплено ({len(context.user_data['photos'])} шт.). "
        "Отправьте еще фото или нажмите 'Завершить отправку фото'.",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return PHOTO_ATTACHMENT

async def done_photos(update: Update, context):
    """Завершение прикрепления фото."""
    await update.message.reply_text(
        "Фото успешно прикреплены. \n\nУкажите дату, время посещения и название зала (например, '15 мая 2025, 14:00-17:00, Баня Купеческая'). "
        "\nЕсли не хотите указывать, отправьте '-'",
        reply_markup=ReplyKeyboardRemove()  # Убираем клавиатуру
    )
    return VISIT_DETAILS

async def visit_details(update: Update, context):
    """Обработка данных о посещении."""
    context.user_data['visit_details'] = update.message.text
    await update.message.reply_text(
        "Пожалуйста, оставьте ваше имя и номер телефона для обратной связи (например, 'Иван, +79991234567'). "
        "\nЕсли не хотите оставлять, отправьте '-'"
    )
    return CONTACT_INFO

async def contact_info(update: Update, context):
    """Обработка контактных данных и отправка отзыва на email."""
    context.user_data['contact_info'] = update.message.text
    # Формируем сообщение для отправки
    feedback_content = context.user_data.get('feedback_content', 'Не указано')
    visit_details = context.user_data.get('visit_details', 'Не указано')
    contact_info = context.user_data.get('contact_info', 'Не указано')
    message = (f"Отзыв: {feedback_content}\n"
               f"Детали посещения: {visit_details}\n"
               f"Контактные данные: {contact_info}")
    # Отправляем сообщение на email
    try:
        photos = context.user_data.get('photos', [])  # Получаем список путей к фото
        send_email(message, photos)
        
        # Удаляем фото после отправки
        for photo_path in photos:
            if os.path.exists(photo_path):
                os.remove(photo_path)
                logger.info(f"Файл удален: {photo_path}")
        
        await update.message.reply_text("Спасибо за ваш отзыв! Мы обязательно его рассмотрим и свяжемся с вами. \n\nДля повторного отзыва нажмите /start")
    except Exception as e:
        logger.error(f"Ошибка при отправке email: {e}")
        await update.message.reply_text("Произошла ошибка при отправке отзыва. \nПожалуйста, попробуйте позже.")
    return ConversationHandler.END

def send_email(message, attachment_paths=None):
    """Отправка email с возможностью прикрепления нескольких файлов."""
    try:
        # Получаем текущую дату и время
        now = datetime.now()
        formatted_datetime = now.strftime("%Y-%m-%d %H:%M")  # Формат: ГГГГ-ММ-ДД ЧЧ:ММ
        # Создаем объект MIMEMultipart
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        msg['Subject'] = f"Новый отзыв - {formatted_datetime}"  # Добавляем дату и время в тему письма
        
        # Добавляем текст сообщения
        msg.attach(MIMEText(message, 'plain'))
        # Если есть файлы для прикрепления
        if attachment_paths:
            for attachment_path in attachment_paths:
                if os.path.exists(attachment_path):
                    with open(attachment_path, 'rb') as file:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(file.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename="{attachment_path.split(os.sep)[-1]}"'
                        )
                        msg.attach(part)
                else:
                    logger.warning(f"Файл для вложения не найден: {attachment_path}")
        else:
            logger.warning("Файлы для вложения не найдены.")
        # Подключаемся к SMTP-серверу Mail.ru
        with smtplib.SMTP('smtp.mail.ru', 587) as server:
            server.starttls()  # Включаем шифрование TLS
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)  # Авторизуемся
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())  # Отправляем письмо
        
        logger.info("Email успешно отправлен.")
    except Exception as e:
        logger.error(f"Ошибка при отправке email: {e}")
        raise

async def cancel(update: Update, context):
    """Отмена диалога."""
    await update.message.reply_text("Диалог отменён.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    """Запуск бота."""
    application = Application.builder().token("7952526744:AAHK5hJGXG_KHF-_tSxgvcyobt9umhJ9x6Y").build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            FEEDBACK_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_content)],
            PHOTO_ATTACHMENT: [
                MessageHandler(filters.PHOTO, handle_photo),  # Обработка фото
                MessageHandler(filters.Regex("^Завершить отправку фото$"), done_photos),  # Обработка кнопки
                CommandHandler('done', done_photos),  # Команда для завершения отправки фото
                MessageHandler(filters.TEXT & ~filters.COMMAND, photo_attachment)  # Обработка текста
            ],
            VISIT_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, visit_details)],
            CONTACT_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_info)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()