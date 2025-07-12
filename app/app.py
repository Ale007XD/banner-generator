import os
import base64
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import mm
from reportlab.lib.colors import CMYKColor, HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import svgwrite
from PIL import Image, ImageDraw, ImageFont
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Конфигурация SMTP (замените на свои данные)
SMTP_CONFIG = {
    'server': 'smtp.gmail.com',
    'port': 587,
    'username': 'your_email@gmail.com',
    'password': 'your_app_password',
    'sender': 'banner_generator@example.com',
    'admin_email': 'alex.deloverov@gmail.com'
}

# Цвета в CMYK и RGB
COLOR_MAP = {
    'white': {'cmyk': (0, 0, 0, 0), 'rgb': '#FFFFFF'},
    'black': {'cmyk': (0, 0, 0, 1), 'rgb': '#000000'},
    'red': {'cmyk': (0, 1, 1, 0), 'rgb': '#FF0000'},
    'yellow': {'cmyk': (0, 0, 1, 0), 'rgb': '#FFFF00'},
    'blue': {'cmyk': (1, 1, 0, 0), 'rgb': '#0000FF'},
    'green': {'cmyk': (1, 0, 1, 0), 'rgb': '#00FF00'}
}

# Шрифты (убедитесь, что файлы находятся в указанных путях)
FONTS = {
    'Golos Text': 'fonts/GolosText.ttf',
    'Tenor Sans': 'fonts/TenorSans.ttf',
    'Fira Sans': 'fonts/FiraSans.ttf',
    'Igra Sans': 'fonts/IgraSans.ttf'
}

# Регистрация шрифтов для ReportLab
for font_name, font_path in FONTS.items():
    try:
        pdfmetrics.registerFont(TTFont(font_name.replace(' ', ''), font_path))
    except:
        print(f"Ошибка регистрации шрифта: {font_name}")

def calculate_font_size(draw, text_lines, font, max_width, max_height, line_spacing=1.2):
    """Адаптивный подбор размера шрифта для безопасной зоны"""
    font_size = 100
    while font_size > 1:
        total_height = 0
        max_line_width = 0
        
        for line in text_lines:
            if line.strip():
                bbox = draw.textbbox((0, 0), line, font=ImageFont.truetype(font, font_size))
                line_width = bbox[2] - bbox[0]
                max_line_width = max(max_line_width, line_width)
        
        total_height = len(text_lines) * font_size * line_spacing
        
        if max_line_width <= max_width and total_height <= max_height:
            return font_size
        font_size -= 1
    return 10

def create_preview(width_mm, height_mm, bg_color, text_lines, text_color, font_name):
    """Генерация RGB превью с помощью Pillow"""
    dpi = 72
    width_px = int(width_mm * dpi / 25.4)
    height_px = int(height_mm * dpi / 25.4)
    
    img = Image.new('RGB', (width_px, height_px), COLOR_MAP[bg_color]['rgb'])
    draw = ImageDraw.Draw(img)
    
    safe_margin = 30 * dpi / 25.4
    safe_width = width_px - 2 * safe_margin
    safe_height = height_px - 2 * safe_margin
    
    if safe_width > 0 and safe_height > 0 and any(text_lines):
        font_path = FONTS[font_name]
        font_size = calculate_font_size(
            draw, 
            [line for line in text_lines if line],
            font_path, 
            safe_width, 
            safe_height
        )
        
        font = ImageFont.truetype(font_path, int(font_size))
        line_spacing = 1.2
        y = (height_px - (len(text_lines) * font_size * line_spacing)) / 2
        
        for line in text_lines:
            if line:
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                x = (width_px - text_width) / 2
                draw.text((x, y), line, fill=COLOR_MAP[text_color]['rgb'], font=font)
                y += font_size * line_spacing
    
    return img

def create_pdf(width_mm, height_mm, bg_color, text_lines, text_color, font_name):
    """Генерация PDF с CMYK цветами"""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width_mm * mm, height_mm * mm))
    
    # Фон
    bg_cmyk = COLOR_MAP[bg_color]['cmyk']
    c.setFillColor(CMYKColor(*bg_cmyk))
    c.rect(0, 0, width_mm * mm, height_mm * mm, fill=True, stroke=False)
    
    # Безопасная зона
    safe_margin = 30
    safe_width = width_mm - 2 * safe_margin
    safe_height = height_mm - 2 * safe_margin
    
    if safe_width > 0 and safe_height > 0 and any(text_lines):
        # Текст
        text_cmyk = COLOR_MAP[text_color]['cmyk']
        c.setFillColor(CMYKColor(*text_cmyk))
        
        font_clean_name = font_name.replace(' ', '')
        font_size = 40  # Начальный размер для подбора
        
        # Упрощенный подбор размера шрифта
        while font_size > 5:
            c.setFont(font_clean_name, font_size)
            total_height = len(text_lines) * font_size * 1.2
            max_width = 0
            
            for line in text_lines:
                if line:
                    width = c.stringWidth(line, font_clean_name, font_size) / mm
                    max_width = max(max_width, width)
            
            if max_width < safe_width and total_height < safe_height:
                break
            font_size -= 1
        
        # Позиционирование текста
        y = (height_mm * mm + total_height) / 2
        for line in reversed(text_lines):
            if line:
                text_width = c.stringWidth(line, font_clean_name, font_size)
                x = (width_mm * mm - text_width) / 2
                c.drawString(x, y - font_size, line)
                y -= font_size * 1.2
    
    c.save()
    buffer.seek(0)
    return buffer

def create_svg(width_mm, height_mm, bg_color, text_lines, text_color, font_name):
    """Генерация SVG файла"""
    dwg = svgwrite.Drawing(size=(f"{width_mm}mm", f"{height_mm}mm"))
    
    # Фон
    dwg.add(dwg.rect(
        insert=(0, 0), 
        size=(f"{width_mm}mm", f"{height_mm}mm"),
        fill=COLOR_MAP[bg_color]['rgb']
    ))
    
    # Безопасная зона
    safe_margin = 30
    safe_width = width_mm - 2 * safe_margin
    safe_height = height_mm - 2 * safe_margin
    
    if safe_width > 0 and safe_height > 0 and any(text_lines):
        # Группа для текста
        text_group = dwg.g(
            font_family=font_name,
            fill=COLOR_MAP[text_color]['rgb'],
            text_anchor="middle",
            dominant_baseline="middle"
        )
        
        # Эмпирический подбор размера шрифта
        font_size = min(safe_width / 10, safe_height / len(text_lines))
        y_pos = height_mm / 2 - (len(text_lines) * font_size * 0.3)
        
        for line in text_lines:
            if line:
                text_group.add(dwg.text(
                    line,
                    insert=(f"{width_mm/2}mm", f"{y_pos}mm"),
                    font_size=f"{font_size}mm"
                ))
                y_pos += font_size * 1.2
        
        dwg.add(text_group)
    
    # Комментарии с CMYK значениями
    dwg.add(dwg.comment(f"Background CMYK: {COLOR_MAP[bg_color]['cmyk']}"))
    dwg.add(dwg.comment(f"Text CMYK: {COLOR_MAP[text_color]['cmyk']}"))
    
    return dwg.tostring()

def send_email(recipient, subject, content, attachments=None):
    """Отправка электронной почты с вложениями"""
    msg = MIMEMultipart()
    msg['From'] = SMTP_CONFIG['sender']
    msg['To'] = recipient
    msg['Subject'] = subject
    
    msg.attach(MIMEText(content, 'plain'))
    
    if attachments:
        for name, data, mime_type in attachments:
            part = MIMEApplication(data, Name=name)
            part['Content-Disposition'] = f'attachment; filename="{name}"'
            msg.attach(part)
    
    with smtplib.SMTP(SMTP_CONFIG['server'], SMTP_CONFIG['port']) as server:
        server.starttls()
        server.login(SMTP_CONFIG['username'], SMTP_CONFIG['password'])
        server.send_message(msg)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_banner():
    # Получение данных из формы
    try:
        width = max(500, min(3000, int(request.form['width'])))
        height = max(500, min(3000, int(request.form['height'])))
        bg_color = request.form['bg_color']
        num_lines = int(request.form['num_lines'])
        text_lines = [request.form.get(f'line{i}', '').strip() for i in range(1, num_lines + 1)]
        text_color = request.form['text_color']
        font_name = request.form['font_family']
        user_email = request.form['email']
    except:
        return redirect(url_for('index'))
    
    # Генерация превью
    preview_img = create_preview(width, height, bg_color, text_lines, text_color, font_name)
    preview_buffer = BytesIO()
    preview_img.save(preview_buffer, format='PNG')
    
    # Генерация PDF и SVG
    pdf_file = create_pdf(width, height, bg_color, text_lines, text_color, font_name)
    svg_file = create_svg(width, height, bg_color, text_lines, text_color, font_name)
    
    # Отправка email пользователю
    send_email(
        recipient=user_email,
        subject='Превью вашего баннера',
        content='Спасибо за использование нашего сервиса! Во вложении превью вашего баннера.',
        attachments=[('preview.png', preview_buffer.getvalue(), 'image/png')]
    )
    
    # Отправка файлов администратору
    send_email(
        recipient=SMTP_CONFIG['admin_email'],
        subject=f'Новый баннер {width}x{height}мм',
        content=f'Детали заказа:\nРазмер: {width}x{height}мм\nЦвет фона: {bg_color}\nШрифт: {font_name}',
        attachments=[
            ('banner.pdf', pdf_file.read(), 'application/pdf'),
            ('banner.svg', svg_file.encode('utf-8'), 'image/svg+xml')
        ]
    )
    
    # Отображение превью на странице
    preview_base64 = base64.b64encode(preview_buffer.getvalue()).decode('utf-8')
    return render_template('result.html', preview=preview_base64)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
