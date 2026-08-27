import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Регистрируем русский шрифт
try:
    pdfmetrics.registerFont(TTFont('DejaVu', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
except:
    logger.warning("DejaVuSans шрифт не найден")

PROFILE_FILE = "profile.json"
ESTIMATES_FILE = "estimates.json"
PRICES_FILE = "prices.json"

DEFAULT_PRICES = {
    "Поклейка виниловых обоев": 350,
    "Демонтаж старых обоев": 100,
    "Грунтовка стен": 80
}

def init_files():
    for file, data in [(PRICES_FILE, DEFAULT_PRICES), (ESTIMATES_FILE, [])]:
        if not os.path.exists(file):
            with open(file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(file):
    try:
        with open(file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {} if file == PROFILE_FILE else []

def save_json(file, data):
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def format_phone(phone):
    phone = phone.replace('+', '').replace('-', '').replace(' ', '')
    if phone.startswith('7'):
        phone = '8' + phone[1:]
    elif not phone.startswith('8'):
        phone = '8' + phone
    return phone

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_json(PROFILE_FILE)
    
    if profile.get('name'):
        await main_menu(update, context)
    else:
        text = "👋 <b>Добро пожаловать!</b>\n\n"
        text += "Это бот для быстрого составления смет на ремонт.\n\n"
        text += "📋 Функции:\n"
        text += "✅ Выбор услуг чек-боксами\n"
        text += "✅ Автоматический расчёт стоимости\n"
        text += "✅ PDF смета в один клик\n"
        text += "✅ История всех расчётов\n\n"
        text += "Давайте создадим ваш профиль!"
        
        keyboard = [[InlineKeyboardButton("➡️ Начать", callback_data="setup_name")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_json(PROFILE_FILE)
    
    text = f"🏠 <b>Главное меню</b>\n\n"
    text += f"👤 Профиль: {profile.get('name', '—')}\n"
    text += f"📱 Телефон: {profile.get('phone', '—')}\n"
    text += f"ВК: {profile.get('vk', '—')}\n"
    text += f"Telegram: {profile.get('telegram', '—')}\n"
    
    keyboard = [
        [InlineKeyboardButton("📋 Создать смету", callback_data="create_estimate")],
        [InlineKeyboardButton("📊 История", callback_data="view_history")],
        [InlineKeyboardButton("⚙️ Профиль", callback_data="edit_profile_menu")],
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # ПРОФИЛЬ
    if query.data == "setup_name":
        context.user_data['step'] = 'name'
        await query.edit_message_text("📝 Введите название компании или имя:")
    
    elif query.data == "setup_phone":
        context.user_data['step'] = 'phone'
        await query.edit_message_text("📱 Введите телефон (8ххххххххх):")
    
    elif query.data == "setup_vk":
        context.user_data['step'] = 'vk'
        await query.edit_message_text("🔗 Введите ссылку на ВК (или 'пропустить'):")
    
    elif query.data == "setup_telegram":
        context.user_data['step'] = 'telegram'
        await query.edit_message_text("📲 Введите ссылку на Telegram (или 'пропустить'):")
    
    # РЕДАКТИРОВАНИЕ ПРОФИЛЯ
    elif query.data == "edit_profile_menu":
        profile = load_json(PROFILE_FILE)
        text = "⚙️ <b>Редактировать профиль</b>\n\n"
        text += f"👤 Название: {profile.get('name', '—')}\n"
        text += f"📱 Телефон: {profile.get('phone', '—')}\n"
        text += f"🔗 ВК: {profile.get('vk', '—')}\n"
        text += f"📲 Telegram: {profile.get('telegram', '—')}\n"
        
        keyboard = [
            [InlineKeyboardButton("✏️ Название", callback_data="edit_name")],
            [InlineKeyboardButton("✏️ Телефон", callback_data="edit_phone")],
            [InlineKeyboardButton("✏️ ВК", callback_data="edit_vk")],
            [InlineKeyboardButton("✏️ Telegram", callback_data="edit_telegram")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_menu")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
    elif query.data == "edit_name":
        context.user_data['edit_field'] = 'name'
        await query.edit_message_text("✏️ Введите новое название:")
    
    elif query.data == "edit_phone":
        context.user_data['edit_field'] = 'phone'
        await query.edit_message_text("✏️ Введите новый телефон:")
    
    elif query.data == "edit_vk":
        context.user_data['edit_field'] = 'vk'
        await query.edit_message_text("✏️ Введите новую ссылку на ВК:")
    
    elif query.data == "edit_telegram":
        context.user_data['edit_field'] = 'telegram'
        await query.edit_message_text("✏️ Введите новую ссылку на Telegram:")
    
    # СМЕТА
    elif query.data == "create_estimate":
        context.user_data['selected'] = {}
        context.user_data['step'] = 'services'
        prices = load_json(PRICES_FILE)
        
        text = "📋 <b>Выберите услуги:</b>\n"
        keyboard = []
        for service in prices:
            keyboard.append([InlineKeyboardButton(f"☐ {service} ({prices[service]} ₽/м²)", callback_data=f"srv_{service}")])
        keyboard.append([InlineKeyboardButton("✅ Далее", callback_data="confirm_srv")])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_menu")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
    elif query.data.startswith("srv_"):
        service = query.data.replace("srv_", "")
        if service in context.user_data['selected']:
            del context.user_data['selected'][service]
        else:
            context.user_data['selected'][service] = True
        
        prices = load_json(PRICES_FILE)
        text = "📋 <b>Выберите услуги:</b>\n"
        keyboard = []
        for s in prices:
            icon = "☑️" if s in context.user_data['selected'] else "☐"
            keyboard.append([InlineKeyboardButton(f"{icon} {s} ({prices[s]} ₽/м²)", callback_data=f"srv_{s}")])
        keyboard.append([InlineKeyboardButton("✅ Далее", callback_data="confirm_srv")])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_menu")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
    elif query.data == "confirm_srv":
        if not context.user_data['selected']:
            await query.answer("⚠️ Выберите услугу!")
            return
        context.user_data['step'] = 'size'
        await query.edit_message_text("📐 Введите размеры: Д Ш В\n(пример: 5 4 3)")
    
    # ИСТОРИЯ
    elif query.data == "view_history":
        estimates = load_json(ESTIMATES_FILE)
        if not estimates:
            await query.edit_message_text("📊 История смет пуста", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_menu")]]))
            return
        
        text = "📊 <b>История смет:</b>\n\n"
        keyboard = []
        for i, est in enumerate(reversed(estimates)):
            keyboard.append([InlineKeyboardButton(f"{est['date']} - {est['total']:.0f}₽", callback_data=f"est_{len(estimates)-1-i}")])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_menu")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
    elif query.data.startswith("est_"):
        idx = int(query.data.replace("est_", ""))
        estimates = load_json(ESTIMATES_FILE)
        est = estimates[idx]
        
        text = f"📄 <b>Смета от {est['date']}</b>\n\n"
        text += f"📍 {est['address']}\n\n"
        for srv, data in est['services'].items():
            text += f"{srv}: {data['total']:.0f}₽\n"
        text += f"\n<b>Итого: {est['total']:.0f}₽</b>"
        
        keyboard = [
            [InlineKeyboardButton("📥 Скачать PDF", callback_data=f"pdf_{idx}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="view_history")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
    elif query.data.startswith("pdf_"):
        idx = int(query.data.replace("pdf_", ""))
        await generate_pdf(update, context, idx)
    
    elif query.data == "back_menu":
        await main_menu(update, context)

async def text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('step')
    text = update.message.text
    profile = load_json(PROFILE_FILE)
    
    # УСТАНОВКА ПРОФИЛЯ
    if step == 'name':
        profile['name'] = text
        save_json(PROFILE_FILE, profile)
        context.user_data['step'] = 'phone'
        keyboard = [[InlineKeyboardButton("📱 Ввести телефон", callback_data="setup_phone")]]
        await update.message.reply_text(f"✅ Название сохранено: <b>{text}</b>\n\nПеревходим к телефону:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
    elif step == 'phone':
        phone = format_phone(text)
        profile['phone'] = phone
        save_json(PROFILE_FILE, profile)
        context.user_data['step'] = 'vk'
        keyboard = [[InlineKeyboardButton("🔗 Ввести ВК", callback_data="setup_vk")]]
        await update.message.reply_text(f"✅ Телефон сохранен: <b>{phone}</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
    elif step == 'vk':
        vk = '' if text.lower() == 'пропустить' else text
        profile['vk'] = vk
        save_json(PROFILE_FILE, profile)
        context.user_data['step'] = 'telegram'
        keyboard = [[InlineKeyboardButton("📲 Ввести Telegram", callback_data="setup_telegram")]]
        await update.message.reply_text(f"✅ ВК сохранен", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
    elif step == 'telegram':
        telegram = '' if text.lower() == 'пропустить' else text
        profile['telegram'] = telegram
        save_json(PROFILE_FILE, profile)
        context.user_data['step'] = None
        await update.message.reply_text("✅ Профиль готов!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➡️ В меню", callback_data="back_menu")]]), parse_mode="HTML")
    
    # РЕДАКТИРОВАНИЕ ПРОФИЛЯ
    elif context.user_data.get('edit_field'):
        field = context.user_data['edit_field']
        if field == 'phone':
            text = format_phone(text)
        elif field in ['vk', 'telegram'] and text.lower() == 'пропустить':
            text = ''
        
        profile[field] = text
        save_json(PROFILE_FILE, profile)
        context.user_data['edit_field'] = None
        
        keyboard = [[InlineKeyboardButton("⚙️ Дальше", callback_data="edit_profile_menu")]]
        await update.message.reply_text(f"✅ {field} обновлен!", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
    # СМЕТА
    elif step == 'size':
        try:
            d, sh, v = map(float, text.split())
            context.user_data['size'] = (d, sh, v)
            context.user_data['area'] = ((d + sh) * 2) * v
            context.user_data['step'] = 'address'
            
            await update.message.reply_text(f"✅ Размеры: {d}×{sh}×{v}м\n📐 Площадь: {context.user_data['area']:.2f}м²\n\n📍 Введите адрес объекта:")
        except:
            await update.message.reply_text("❌ Ошибка! Введите три числа через пробел")
    
    elif step == 'address':
        context.user_data['address'] = text
        await generate_estimate_pdf(update, context)

async def generate_estimate_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_json(PROFILE_FILE)
    prices = load_json(PRICES_FILE)
    
    selected = context.user_data['selected']
    area = context.user_data['area']
    address = context.user_data['address']
    
    estimate_data = {
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "address": address,
        "services": {},
        "total": 0
    }
    
    for service in selected:
        price = prices[service]
        cost = price * area
        estimate_data['services'][service] = {"price_per_m2": price, "area": area, "total": cost}
        estimate_data['total'] += cost
    
    estimates = load_json(ESTIMATES_FILE)
    estimates.append(estimate_data)
    save_json(ESTIMATES_FILE, estimates)
    
    # PDF с русским шрифтом
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, rightMargin=0.8*cm, leftMargin=0.8*cm, topMargin=0.8*cm, bottomMargin=0.8*cm)
    
    story = []
    styles = getSampleStyleSheet()
    
    title = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1E90FF'), alignment=1, spaceAfter=15, fontName='DejaVu')
    story.append(Paragraph("СМЕТА НА РЕМОНТНЫЕ РАБОТЫ", title))
    
    info = ParagraphStyle('Info', parent=styles['Normal'], fontSize=11, spaceAfter=6, fontName='DejaVu')
    story.append(Paragraph(f"<b>Мастер:</b> {profile.get('name', '—')}", info))
    story.append(Paragraph(f"<b>Телефон:</b> {profile.get('phone', '—')}", info))
    if profile.get('vk'):
        story.append(Paragraph(f"<b>ВК:</b> {profile['vk']}", info))
    if profile.get('telegram'):
        story.append(Paragraph(f"<b>Telegram:</b> {profile['telegram']}", info))
    
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(f"<b>Адрес:</b> {address}", info))
    story.append(Paragraph(f"<b>Дата:</b> {estimate_data['date']}", info))
    story.append(Spacer(1, 0.4*cm))
    
    table_data = [['Услуга', 'Цена/м²', 'Площадь', 'Сумма']]
    for service, data in estimate_data['services'].items():
        table_data.append([service, f"{data['price_per_m2']}₽", f"{data['area']:.2f}м²", f"{data['total']:.0f}₽"])
    table_data.append(['', '', '<b>ИТОГО</b>', f"<b>{estimate_data['total']:.0f}₽</b>"])
    
    table = Table(table_data, colWidths=[5.5*cm, 1.8*cm, 1.8*cm, 1.8*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E90FF')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVu'),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVu'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'DejaVu'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#DDDDDD')),
    ]))
    
    story.append(table)
    doc.build(story)
    pdf_buffer.seek(0)
    
    filename = f"smeta_{datetime.now().strftime('%d_%m_%Y_%H_%M')}.pdf"
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=pdf_buffer,
        filename=filename,
        caption=f"✅ Смета готова!\n💰 Итого: {estimate_data['total']:.0f}₽"
    )
    
    keyboard = [
        [InlineKeyboardButton("📋 Создать ещё", callback_data="create_estimate")],
        [InlineKeyboardButton("📊 История", callback_data="view_history")],
        [InlineKeyboardButton("🏠 Меню", callback_data="back_menu")],
    ]
    await update.message.reply_text("🎉 Смета отправлена!", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def generate_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE, idx: int):
    profile = load_json(PROFILE_FILE)
    estimates = load_json(ESTIMATES_FILE)
    est = estimates[idx]
    
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4, rightMargin=0.8*cm, leftMargin=0.8*cm, topMargin=0.8*cm, bottomMargin=0.8*cm)
    
    story = []
    styles = getSampleStyleSheet()
    
    title = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1E90FF'), alignment=1, spaceAfter=15, fontName='DejaVu')
    story.append(Paragraph("СМЕТА НА РЕМОНТНЫЕ РАБОТЫ", title))
    
    info = ParagraphStyle('Info', parent=styles['Normal'], fontSize=11, spaceAfter=6, fontName='DejaVu')
    story.append(Paragraph(f"<b>Мастер:</b> {profile.get('name', '—')}", info))
    story.append(Paragraph(f"<b>Телефон:</b> {profile.get('phone', '—')}", info))
    if profile.get('vk'):
        story.append(Paragraph(f"<b>ВК:</b> {profile['vk']}", info))
    if profile.get('telegram'):
        story.append(Paragraph(f"<b>Telegram:</b> {profile['telegram']}", info))
    
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(f"<b>Адрес:</b> {est['address']}", info))
    story.append(Paragraph(f"<b>Дата:</b> {est['date']}", info))
    story.append(Spacer(1, 0.4*cm))
    
    table_data = [['Услуга', 'Цена/м²', 'Площадь', 'Сумма']]
    for service, data in est['services'].items():
        table_data.append([service, f"{data['price_per_m2']}₽", f"{data['area']:.2f}м²", f"{data['total']:.0f}₽"])
    table_data.append(['', '', '<b>ИТОГО</b>', f"<b>{est['total']:.0f}₽</b>"])
    
    table = Table(table_data, colWidths=[5.5*cm, 1.8*cm, 1.8*cm, 1.8*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E90FF')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVu'),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVu'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'DejaVu'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#DDDDDD')),
    ]))
    
    story.append(table)
    doc.build(story)
    pdf_buffer.seek(0)
    
    filename = f"smeta_{est['date'].replace('.', '_').replace(' ', '_').replace(':', '_')}.pdf"
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=pdf_buffer,
        filename=filename,
        caption=f"📄 Смета от {est['date']}\n💰 {est['total']:.0f}₽"
    )

def main():
    init_files()
    token = os.getenv('TELEGRAM_TOKEN')
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input))
    
    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == '__main__':
    main()
