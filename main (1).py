import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, ContextTypes
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from io import BytesIO

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Файлы для хранения данных
PROFILE_FILE = "profile.json"
ESTIMATES_FILE = "estimates.json"
PRICES_FILE = "prices.json"

# Цены услуг (могут редактироваться)
DEFAULT_PRICES = {
    "Поклейка виниловых обоев": 350,
    "Демонтаж старых обоев": 100,
    "Грунтовка стен": 80
}

# Состояния диалога
STATE_PROFILE_NAME = 1
STATE_PROFILE_PHONE = 2
STATE_PROFILE_VK = 3
STATE_PROFILE_TELEGRAM = 4
STATE_ESTIMATE_SERVICES = 5
STATE_ESTIMATE_SIZE = 6
STATE_ESTIMATE_ADDRESS = 7

# Инициализация файлов
def init_files():
    if not os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, 'w') as f:
            json.dump(DEFAULT_PRICES, f, ensure_ascii=False, indent=2)
    
    if not os.path.exists(ESTIMATES_FILE):
        with open(ESTIMATES_FILE, 'w') as f:
            json.dump([], f, ensure_ascii=False, indent=2)

# Загрузка профиля
def load_profile():
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

# Сохранение профиля
def save_profile(profile):
    with open(PROFILE_FILE, 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

# Загрузка цен
def load_prices():
    with open(PRICES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# Загрузка смет
def load_estimates():
    with open(ESTIMATES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# Сохранение смет
def save_estimates(estimates):
    with open(ESTIMATES_FILE, 'w', encoding='utf-8') as f:
        json.dump(estimates, f, ensure_ascii=False, indent=2)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_profile()
    
    if profile:
        # Профиль уже заполнен - показываем главное меню
        await show_main_menu(update, context)
    else:
        # Первый вход - приветствие
        welcome_text = (
            "👋 Добро пожаловать в бот для составления смет!\n\n"
            "📋 Этот бот поможет вам:\n"
            "✅ Быстро составлять сметы на ремонтные работы\n"
            "✅ Сохранять историю всех расчётов\n"
            "✅ Отправлять готовые сметы клиентам в PDF\n\n"
            "Давайте начнём! Укажите название вашей компании или имя:"
        )
        await update.message.reply_text(welcome_text)
        return STATE_PROFILE_NAME

# Получение названия компании
async def get_profile_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['profile_name'] = update.message.text
    await update.message.reply_text("📱 Теперь введите ваш телефон (например, +79991234567):")
    return STATE_PROFILE_PHONE

# Получение телефона
async def get_profile_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text
    if not phone.startswith('+'):
        phone = '+' + phone
    context.user_data['profile_phone'] = phone
    await update.message.reply_text(
        "🔗 Введите ссылку на ВК (или напишите 'пропустить' если нет):"
    )
    return STATE_PROFILE_VK

# Получение VK
async def get_profile_vk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vk = update.message.text if update.message.text.lower() != 'пропустить' else ""
    context.user_data['profile_vk'] = vk
    await update.message.reply_text(
        "📲 Введите ссылку на Телеграм (или напишите 'пропустить' если нет):"
    )
    return STATE_PROFILE_TELEGRAM

# Получение Telegram
async def get_profile_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram = update.message.text if update.message.text.lower() != 'пропустить' else ""
    
    # Сохраняем профиль
    profile = {
        "name": context.user_data['profile_name'],
        "phone": context.user_data['profile_phone'],
        "vk": context.user_data['profile_vk'],
        "telegram": telegram
    }
    save_profile(profile)
    
    await update.message.reply_text(
        "✅ Профиль сохранён!\n\n"
        f"Название: {profile['name']}\n"
        f"Телефон: {profile['phone']}\n"
        f"ВК: {profile['vk'] if profile['vk'] else '—'}\n"
        f"Телеграм: {profile['telegram'] if profile['telegram'] else '—'}"
    )
    
    await show_main_menu(update, context)
    return ConversationHandler.END

# Главное меню
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📋 Создать смету", callback_data="create_estimate")],
        [InlineKeyboardButton("📊 История смет", callback_data="view_history")],
        [InlineKeyboardButton("⚙️ Редактировать профиль", callback_data="edit_profile")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "🏠 Главное меню", 
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "🏠 Главное меню", 
            reply_markup=reply_markup
        )

# Обработка кнопок главного меню
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "create_estimate":
        await create_estimate(update, context)
    elif query.data == "view_history":
        await view_history(update, context)
    elif query.data == "edit_profile":
        await edit_profile(update, context)
    elif query.data.startswith("service_"):
        await toggle_service(update, context)
    elif query.data == "confirm_services":
        await confirm_services(update, context)
    elif query.data.startswith("estimate_"):
        await download_estimate(update, context)
    elif query.data == "back_to_menu":
        await show_main_menu(update, context)

# Создание сметы - выбор услуг
async def create_estimate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = load_prices()
    context.user_data['selected_services'] = {}
    
    # Создаём клавиатуру с чек-боксами
    keyboard = []
    for service in prices.keys():
        price = prices[service]
        keyboard.append([
            InlineKeyboardButton(
                f"☐ {service} ({price} ₽/м²)",
                callback_data=f"service_{service}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("✅ Далее", callback_data="confirm_services")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "📋 Выберите услуги (нажмите на услугу чтобы её выбрать):",
        reply_markup=reply_markup
    )

# Переключение услуги (чек-бокс)
async def toggle_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    service_name = query.data.replace("service_", "")
    
    if service_name not in context.user_data['selected_services']:
        context.user_data['selected_services'][service_name] = True
    else:
        del context.user_data['selected_services'][service_name]
    
    # Перерисовываем меню
    prices = load_prices()
    keyboard = []
    
    for service in prices.keys():
        price = prices[service]
        if service in context.user_data['selected_services']:
            icon = "☑️"
        else:
            icon = "☐"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {service} ({price} ₽/м²)",
                callback_data=f"service_{service}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("✅ Далее", callback_data="confirm_services")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📋 Выберите услуги:",
        reply_markup=reply_markup
    )
    await query.answer()

# Подтверждение услуг и переход к размерам
async def confirm_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('selected_services'):
        await update.callback_query.answer("⚠️ Выберите хотя бы одну услугу!")
        return
    
    await update.callback_query.edit_message_text(
        "📐 Введите размеры помещения в формате: Д Ш В\n"
        "(например: 5 4 3 для 5м длина, 4м ширина, 3м высота)"
    )
    context.user_data['state'] = 'waiting_for_size'

# Получение размеров
async def get_estimate_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sizes = update.message.text.split()
        if len(sizes) != 3:
            await update.message.reply_text(
                "❌ Неверный формат! Введите три числа: Д Ш В\n"
                "(например: 5 4 3)"
            )
            return
        
        d, sh, v = float(sizes[0]), float(sizes[1]), float(sizes[2])
        
        # Расчёт площади: ((Д + Ш) × 2) × В
        area = ((d + sh) * 2) * v
        
        context.user_data['size'] = {'d': d, 'sh': sh, 'v': v}
        context.user_data['area'] = area
        
        await update.message.reply_text(
            f"✅ Размеры: {d}м × {sh}м × {v}м\n"
            f"📐 Площадь стен: {area:.2f} м²\n\n"
            f"📍 Теперь введите адрес объекта:"
        )
        context.user_data['state'] = 'waiting_for_address'
        
    except ValueError:
        await update.message.reply_text(
            "❌ Ошибка! Введите числа: Д Ш В\n"
            "(например: 5 4 3)"
        )

# Получение адреса
async def get_estimate_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text
    context.user_data['address'] = address
    
    # Создаём смету
    await generate_estimate(update, context)

# Генерация PDF сметы
async def generate_estimate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_profile()
    prices = load_prices()
    
    selected_services = context.user_data['selected_services']
    area = context.user_data['area']
    address = context.user_data['address']
    
    # Расчёт стоимости
    estimate_data = {
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "address": address,
        "services": {},
        "total": 0
    }
    
    for service in selected_services:
        price = prices[service]
        cost = price * area
        estimate_data['services'][service] = {
            "price_per_m2": price,
            "area": area,
            "total": cost
        }
        estimate_data['total'] += cost
    
    # Сохраняем в историю
    estimates = load_estimates()
    estimates.append(estimate_data)
    save_estimates(estimates)
    
    # Создаём PDF
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, rightMargin=1*cm, leftMargin=1*cm, topMargin=1*cm, bottomMargin=1*cm)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Заголовок
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1E90FF'),
        spaceAfter=20,
        alignment=1
    )
    story.append(Paragraph("СМЕТА НА РЕМОНТНЫЕ РАБОТЫ", title_style))
    story.append(Spacer(1, 0.5*cm))
    
    # Информация о мастере
    info_style = ParagraphStyle(
        'Info',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.black,
        spaceAfter=10
    )
    
    story.append(Paragraph(f"<b>Мастер:</b> {profile['name']}", info_style))
    story.append(Paragraph(f"<b>Телефон:</b> <a href='tel:{profile['phone']}'>{profile['phone']}</a>", info_style))
    
    if profile['vk']:
        story.append(Paragraph(f"<b>ВК:</b> <a href='{profile['vk']}'>{profile['vk']}</a>", info_style))
    if profile['telegram']:
        story.append(Paragraph(f"<b>Телеграм:</b> <a href='{profile['telegram']}'>{profile['telegram']}</a>", info_style))
    
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(f"<b>Адрес объекта:</b> {address}", info_style))
    story.append(Paragraph(f"<b>Дата:</b> {estimate_data['date']}", info_style))
    story.append(Spacer(1, 0.5*cm))
    
    # Таблица услуг
    table_data = [
        ['Услуга', 'Цена/м²', 'Площадь (м²)', 'Сумма (₽)']
    ]
    
    for service, details in estimate_data['services'].items():
        table_data.append([
            service,
            f"{details['price_per_m2']} ₽",
            f"{details['area']:.2f}",
            f"{details['total']:.0f} ₽"
        ])
    
    # Итого
    table_data.append([
        '',
        '',
        '<b>ИТОГО:</b>',
        f"<b>{estimate_data['total']:.0f} ₽</b>"
    ])
    
    table = Table(table_data, colWidths=[6*cm, 2.5*cm, 2*cm, 2.5*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E90FF')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E0E0E0')),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 1*cm))
    
    # Подпись
    signature_style = ParagraphStyle(
        'Signature',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=5
    )
    story.append(Paragraph("_" * 50, signature_style))
    story.append(Paragraph(f"Подпись мастера: {profile['name']}", signature_style))
    
    doc.build(story)
    pdf_buffer.seek(0)
    
    # Отправляем PDF в Телеграм
    filename = f"smeta_{datetime.now().strftime('%d_%m_%Y_%H_%M')}.pdf"
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=pdf_buffer,
        filename=filename,
        caption=f"✅ Смета готова!\n\n💰 Итого: {estimate_data['total']:.0f} ₽"
    )
    
    # Показываем меню
    keyboard = [
        [InlineKeyboardButton("📋 Создать ещё", callback_data="create_estimate")],
        [InlineKeyboardButton("📊 История смет", callback_data="view_history")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎉 Смета отправлена!\n\nЧто дальше?",
        reply_markup=reply_markup
    )

# История смет
async def view_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    estimates = load_estimates()
    
    if not estimates:
        await update.callback_query.edit_message_text(
            "📊 История смет пуста"
        )
        await show_main_menu(update, context)
        return
    
    keyboard = []
    for i, est in enumerate(reversed(estimates)):
        date = est['date']
        address = est['address']
        total = est['total']
        keyboard.append([
            InlineKeyboardButton(
                f"📝 {date} - {address} ({total:.0f} ₽)",
                callback_data=f"estimate_{len(estimates)-1-i}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "📊 История смет:",
        reply_markup=reply_markup
    )

# Скачивание сметы из истории
async def download_estimate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    estimate_idx = int(query.data.replace("estimate_", ""))
    
    estimates = load_estimates()
    estimate_data = estimates[estimate_idx]
    
    profile = load_profile()
    prices = load_prices()
    
    # Создаём PDF (тот же код что и в generate_estimate)
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, rightMargin=1*cm, leftMargin=1*cm, topMargin=1*cm, bottomMargin=1*cm)
    
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1E90FF'),
        spaceAfter=20,
        alignment=1
    )
    story.append(Paragraph("СМЕТА НА РЕМОНТНЫЕ РАБОТЫ", title_style))
    story.append(Spacer(1, 0.5*cm))
    
    info_style = ParagraphStyle(
        'Info',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.black,
        spaceAfter=10
    )
    
    story.append(Paragraph(f"<b>Мастер:</b> {profile['name']}", info_style))
    story.append(Paragraph(f"<b>Телефон:</b> <a href='tel:{profile['phone']}'>{profile['phone']}</a>", info_style))
    
    if profile['vk']:
        story.append(Paragraph(f"<b>ВК:</b> <a href='{profile['vk']}'>{profile['vk']}</a>", info_style))
    if profile['telegram']:
        story.append(Paragraph(f"<b>Телеграм:</b> <a href='{profile['telegram']}'>{profile['telegram']}</a>", info_style))
    
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(f"<b>Адрес объекта:</b> {estimate_data['address']}", info_style))
    story.append(Paragraph(f"<b>Дата:</b> {estimate_data['date']}", info_style))
    story.append(Spacer(1, 0.5*cm))
    
    table_data = [
        ['Услуга', 'Цена/м²', 'Площадь (м²)', 'Сумма (₽)']
    ]
    
    for service, details in estimate_data['services'].items():
        table_data.append([
            service,
            f"{details['price_per_m2']} ₽",
            f"{details['area']:.2f}",
            f"{details['total']:.0f} ₽"
        ])
    
    table_data.append([
        '',
        '',
        '<b>ИТОГО:</b>',
        f"<b>{estimate_data['total']:.0f} ₽</b>"
    ])
    
    table = Table(table_data, colWidths=[6*cm, 2.5*cm, 2*cm, 2.5*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E90FF')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E0E0E0')),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 1*cm))
    
    signature_style = ParagraphStyle(
        'Signature',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=5
    )
    story.append(Paragraph("_" * 50, signature_style))
    story.append(Paragraph(f"Подпись мастера: {profile['name']}", signature_style))
    
    doc.build(story)
    pdf_buffer.seek(0)
    
    filename = f"smeta_{estimate_data['date'].replace('.', '_').replace(' ', '_').replace(':', '_')}.pdf"
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=pdf_buffer,
        filename=filename,
        caption=f"📄 Смета от {estimate_data['date']}\n💰 Сумма: {estimate_data['total']:.0f} ₽"
    )
    
    await query.answer("✅ Смета отправлена!")

# Редактирование профиля
async def edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_profile()
    
    text = (
        "⚙️ Редактирование профиля\n\n"
        f"Текущие данные:\n"
        f"👤 Название: {profile['name']}\n"
        f"📱 Телефон: {profile['phone']}\n"
        f"🔗 ВК: {profile['vk'] if profile['vk'] else '—'}\n"
        f"📲 Телеграм: {profile['telegram'] if profile['telegram'] else '—'}\n\n"
        f"Что хотите изменить?"
    )
    
    keyboard = [
        [InlineKeyboardButton("👤 Название", callback_data="edit_name")],
        [InlineKeyboardButton("📱 Телефон", callback_data="edit_phone")],
        [InlineKeyboardButton("🔗 ВК", callback_data="edit_vk")],
        [InlineKeyboardButton("📲 Телеграм", callback_data="edit_telegram")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

# Обработка редактирования профиля
async def edit_profile_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    field = query.data.replace("edit_", "")
    
    field_names = {
        "name": "название компании",
        "phone": "телефон",
        "vk": "ссылку на ВК",
        "telegram": "ссылку на Телеграм"
    }
    
    context.user_data['editing_field'] = field
    
    await query.edit_message_text(
        f"✏️ Введите новое значение для '{field_names[field]}':"
    )

# Получение нового значения поля
async def save_profile_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'editing_field' not in context.user_data:
        return
    
    field = context.user_data['editing_field']
    value = update.message.text
    
    if field == "phone" and not value.startswith('+'):
        value = '+' + value
    
    profile = load_profile()
    profile[field] = value
    save_profile(profile)
    
    await update.message.reply_text(f"✅ {field} обновлён!")
    await edit_profile(update, context)

# Главная функция
def main():
    init_files()
    
    token = os.getenv('TELEGRAM_TOKEN')
    app = Application.builder().token(token).build()
    
    # ConversationHandler для профиля
    profile_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            STATE_PROFILE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_profile_name)],
            STATE_PROFILE_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_profile_phone)],
            STATE_PROFILE_VK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_profile_vk)],
            STATE_PROFILE_TELEGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_profile_telegram)],
        },
        fallbacks=[CommandHandler('start', start)],
    )
    
    # Обработчики для смет
    size_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, get_estimate_size)
    address_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, get_estimate_address)
    edit_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, save_profile_field)
    
    app.add_handler(profile_handler)
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(CallbackQueryHandler(edit_profile_field, pattern="^edit_"))
    app.add_handler(size_handler)
    app.add_handler(address_handler)
    app.add_handler(edit_handler)
    
    app.run_polling()

if __name__ == '__main__':
    main()
