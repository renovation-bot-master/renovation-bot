import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, ContextTypes
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from io import BytesIO

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

PROFILE_FILE = "profile.json"
ESTIMATES_FILE = "estimates.json"
PRICES_FILE = "prices.json"

DEFAULT_PRICES = {
    "Поклейка виниловых обоев": 350,
    "Демонтаж старых обоев": 100,
    "Грунтовка стен": 80
}

PROFILE_NAME, PROFILE_PHONE, PROFILE_VK, PROFILE_TELEGRAM = range(4)

def init_files():
    if not os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_PRICES, f, ensure_ascii=False, indent=2)
    
    if not os.path.exists(ESTIMATES_FILE):
        with open(ESTIMATES_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def load_profile():
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def save_profile(profile):
    with open(PROFILE_FILE, 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

def load_prices():
    with open(PRICES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_estimates():
    with open(ESTIMATES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_estimates(estimates):
    with open(ESTIMATES_FILE, 'w', encoding='utf-8') as f:
        json.dump(estimates, f, ensure_ascii=False, indent=2)

def format_phone(phone):
    """Преобразует номер в формат 8ххххххххххх"""
    phone = phone.replace('+', '').replace('-', '').replace(' ', '')
    if phone.startswith('7'):
        phone = '8' + phone[1:]
    elif not phone.startswith('8'):
        phone = '8' + phone
    return phone

def get_bottom_menu():
    """Возвращает постоянное меню внизу"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👤 Профиль", callback_data="show_profile"),
            InlineKeyboardButton("📋 Смета", callback_data="create_estimate")
        ]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_profile()
    
    if profile:
        await show_main_menu(update, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "👋 Добро пожаловать в бот для составления смет!\n\n"
            "Этот бот поможет вам:\n"
            "✅ Быстро составлять сметы на ремонтные работы\n"
            "✅ Сохранять историю всех расчётов\n"
            "✅ Отправлять готовые сметы клиентам в PDF\n\n"
            "Давайте начнём! Укажите название вашей компании или имя:"
        )
        return PROFILE_NAME

async def input_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['profile_name'] = update.message.text
    await update.message.reply_text("📱 Теперь введите ваш телефон (например, 89991234567):")
    return PROFILE_PHONE

async def input_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = format_phone(update.message.text)
    context.user_data['profile_phone'] = phone
    await update.message.reply_text("🔗 Введите ссылку на ВК (или напишите 'пропустить'):")
    return PROFILE_VK

async def input_vk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vk = update.message.text if update.message.text.lower() != 'пропустить' else ""
    context.user_data['profile_vk'] = vk
    await update.message.reply_text("📲 Введите ссылку на Телеграм (или напишите 'пропустить'):")
    return PROFILE_TELEGRAM

async def input_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram = update.message.text if update.message.text.lower() != 'пропустить' else ""
    
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
        f"Телеграм: {profile['telegram'] if profile['telegram'] else '—'}",
        reply_markup=get_bottom_menu()
    )
    
    await show_main_menu(update, context)
    return ConversationHandler.END

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📋 Создать смету", callback_data="create_estimate")],
        [InlineKeyboardButton("📊 История смет", callback_data="view_history")],
        [InlineKeyboardButton("⚙️ Редактировать профиль", callback_data="edit_profile")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text("🏠 Главное меню", reply_markup=reply_markup)
    else:
        await update.message.reply_text("🏠 Главное меню", reply_markup=reply_markup)

async def show_profile_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает профиль пользователя"""
    query = update.callback_query
    profile = load_profile()
    
    if not profile:
        await query.answer("Профиль не найден")
        return
    
    text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"<b>Название:</b> {profile['name']}\n"
        f"<b>Телефон:</b> {profile['phone']}\n"
        f"<b>ВК:</b> {profile.get('vk', '—')}\n"
        f"<b>Телеграм:</b> {profile.get('telegram', '—')}"
    )
    
    keyboard = [
        [InlineKeyboardButton("✏️ Редактировать", callback_data="edit_profile")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "create_estimate":
        await create_estimate_menu(query, context)
    elif query.data == "view_history":
        await view_history(query, context)
    elif query.data == "edit_profile":
        await edit_profile_menu(query, context)
    elif query.data == "show_profile":
        await show_profile_info(update, context)
    elif query.data.startswith("service_"):
        await toggle_service(query, context)
    elif query.data == "confirm_services":
        await confirm_services(query, context)
    elif query.data.startswith("estimate_"):
        await download_estimate(query, context)
    elif query.data == "back_to_menu" or query.data == "back_to_main":
        await show_main_menu(update, context)
    elif query.data.startswith("edit_"):
        await edit_field_start(query, context)

async def create_estimate_menu(query, context):
    prices = load_prices()
    context.user_data['selected_services'] = {}
    
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
    await query.edit_message_text("📋 Выберите услуги:", reply_markup=reply_markup)

async def toggle_service(query, context):
    service_name = query.data.replace("service_", "")
    
    if service_name not in context.user_data.get('selected_services', {}):
        context.user_data['selected_services'][service_name] = True
    else:
        del context.user_data['selected_services'][service_name]
    
    prices = load_prices()
    keyboard = []
    
    for service in prices.keys():
        price = prices[service]
        if service in context.user_data.get('selected_services', {}):
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
    
    await query.edit_message_text("📋 Выберите услуги:", reply_markup=reply_markup)
    await query.answer()

async def confirm_services(query, context):
    if not context.user_data.get('selected_services'):
        await query.answer("⚠️ Выберите хотя бы одну услугу!")
        return
    
    context.user_data['estimate_step'] = 'size'
    await query.edit_message_text(
        "📐 Введите размеры помещения в формате: Д Ш В\n"
        "(например: 5 4 3)"
    )

async def input_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('estimate_step')
    
    if step == 'size':
        try:
            sizes = update.message.text.split()
            if len(sizes) != 3:
                await update.message.reply_text("❌ Неверный формат! Введите три числа: Д Ш В")
                return
            
            d, sh, v = float(sizes[0]), float(sizes[1]), float(sizes[2])
            area = ((d + sh) * 2) * v
            
            context.user_data['size'] = {'d': d, 'sh': sh, 'v': v}
            context.user_data['area'] = area
            
            await update.message.reply_text(
                f"✅ Размеры: {d}м × {sh}м × {v}м\n"
                f"📐 Площадь стен: {area:.2f} м²\n\n"
                f"📍 Теперь введите адрес объекта:"
            )
            context.user_data['estimate_step'] = 'address'
            
        except ValueError:
            await update.message.reply_text("❌ Ошибка! Введите числа: Д Ш В")
    
    elif step == 'address':
        address = update.message.text
        context.user_data['address'] = address
        await generate_pdf(update, context)

async def generate_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info("Начинаю генерировать PDF...")
        
        profile = load_profile()
        prices = load_prices()
        
        selected_services = context.user_data.get('selected_services', {})
        area = context.user_data.get('area', 0)
        address = context.user_data.get('address', '')
        
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
        
        estimates = load_estimates()
        estimates.append(estimate_data)
        save_estimates(estimates)
        
        # Создаём PDF
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
        story.append(Paragraph(f"<b>Телефон:</b> {profile['phone']}", info_style))
        
        if profile.get('vk'):
            story.append(Paragraph(f"<b>ВК:</b> {profile['vk']}", info_style))
        if profile.get('telegram'):
            story.append(Paragraph(f"<b>Телеграм:</b> {profile['telegram']}", info_style))
        
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(f"<b>Адрес объекта:</b> {address}", info_style))
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
        
        filename = f"smeta_{datetime.now().strftime('%d_%m_%Y_%H_%M')}.pdf"
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=pdf_buffer,
            filename=filename,
            caption=f"✅ Смета готова!\n\n💰 Итого: {estimate_data['total']:.0f} ₽"
        )
        
        # Меню после создания
        keyboard = [
            [InlineKeyboardButton("📋 Создать ещё", callback_data="create_estimate")],
            [InlineKeyboardButton("📊 История смет", callback_data="view_history")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text("🎉 Смета отправлена!\n\nЧто дальше?", reply_markup=reply_markup)
        context.user_data['estimate_step'] = None
        
    except Exception as e:
        logger.error(f"Ошибка при генерации PDF: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def view_history(query, context):
    estimates = load_estimates()
    
    if not estimates:
        await query.edit_message_text("📊 История смет пуста")
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
    
    await query.edit_message_text("📊 История смет:", reply_markup=reply_markup)

async def download_estimate(query, context):
    estimate_idx = int(query.data.replace("estimate_", ""))
    
    estimates = load_estimates()
    estimate_data = estimates[estimate_idx]
    
    profile = load_profile()
    
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
    story.append(Paragraph(f"<b>Телефон:</b> {profile['phone']}", info_style))
    
    if profile.get('vk'):
        story.append(Paragraph(f"<b>ВК:</b> {profile['vk']}", info_style))
    if profile.get('telegram'):
        story.append(Paragraph(f"<b>Телеграм:</b> {profile['telegram']}", info_style))
    
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
        chat_id=query.from_user.id,
        document=pdf_buffer,
        filename=filename,
        caption=f"📄 Смета от {estimate_data['date']}\n💰 Сумма: {estimate_data['total']:.0f} ₽"
    )
    
    await query.answer("✅ Смета отправлена!")

async def edit_profile_menu(query, context):
    profile = load_profile()
    
    text = (
        "⚙️ Редактирование профиля\n\n"
        f"Текущие данные:\n"
        f"👤 Название: {profile['name']}\n"
        f"📱 Телефон: {profile['phone']}\n"
        f"🔗 ВК: {profile.get('vk', '—')}\n"
        f"📲 Телеграм: {profile.get('telegram', '—')}\n\n"
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
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def edit_field_start(query, context):
    field = query.data.replace("edit_", "")
    
    field_names = {
        "name": "название компании",
        "phone": "телефон",
        "vk": "ссылку на ВК",
        "telegram": "ссылку на Телеграм"
    }
    
    context.user_data['editing_field'] = field
    context.user_data['editing_mode'] = True
    await query.edit_message_text(f"✏️ Введите новое значение для '{field_names[field]}':")

async def edit_field_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('editing_mode'):
        return
    
    field = context.user_data.get('editing_field')
    if not field:
        return
    
    value = update.message.text
    
    if field == "phone":
        value = format_phone(value)
    
    profile = load_profile()
    profile[field] = value
    save_profile(profile)
    
    context.user_data['editing_field'] = None
    context.user_data['editing_mode'] = False
    
    # Показываем меню редактирования профиля с кнопкой назад
    text = (
        "⚙️ Редактирование профиля\n\n"
        f"Текущие данные:\n"
        f"👤 Название: {profile['name']}\n"
        f"📱 Телефон: {profile['phone']}\n"
        f"🔗 ВК: {profile.get('vk', '—')}\n"
        f"📲 Телеграм: {profile.get('telegram', '—')}\n\n"
        f"✅ {field} обновлён!\n\n"
        f"Что ещё хотите изменить?"
    )
    
    keyboard = [
        [InlineKeyboardButton("👤 Название", callback_data="edit_name")],
        [InlineKeyboardButton("📱 Телефон", callback_data="edit_phone")],
        [InlineKeyboardButton("🔗 ВК", callback_data="edit_vk")],
        [InlineKeyboardButton("📲 Телеграм", callback_data="edit_telegram")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup)

def main():
    init_files()
    
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        logger.error("Токен не найден!")
        return
    
    app = Application.builder().token(token).build()
    
    # Conversation handler для профиля
    profile_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            PROFILE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_name)],
            PROFILE_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_phone)],
            PROFILE_VK: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_vk)],
            PROFILE_TELEGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_telegram)],
        },
        fallbacks=[CommandHandler('start', start)],
    )
    
    # Обработчики
    app.add_handler(profile_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, input_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field_save))
    
    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == '__main__':
    main()
