"""
FirsatRadar | Usta Pazarlamacı Konuşan Afiş & Fırsat Kartı Motoru (Thumb-Stopper v6)
- 1200x675 HD 16:9 Kart Tasarımı
- Boşluksuz dinamik dikey yerleşim + Temizlenmiş ürün başlığı
- Vektörel Altın Yıldız + Müşteri Puanı + Amazon Resmi "Son X Günün En Düşüğü" Rozeti
- Birim Fiyat ("TANESİ SADECE X,XX TL!") veya Kasa Önü Kampanya rozeti
- Alt şeritte "► YORUMDA +1 BONUS FIRSAT: [2. Ürün] (-%XX | XXX TL)" + "2 LİNK DE İLK YORUMDA ▼" kancası!
"""
import os
import re
import math
import textwrap
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

import config

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_PATH = os.path.join(FONT_DIR, "arialbd.ttf")


def get_font(size: int):
    if os.path.exists(FONT_PATH):
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception:
            pass
    try:
        return ImageFont.truetype("arialbd.ttf", size)
    except Exception:
        return ImageFont.load_default()


def clean_price_display(p_str: str) -> str:
    if not p_str:
        return ""
    s = re.sub(r'^[^0-9]+', '', str(p_str)).strip()
    return s


def tr_upper(text: str) -> str:
    if not text:
        return ""
    return text.replace("i", "İ").replace("ı", "I").upper()


def draw_gold_star(draw: ImageDraw.ImageDraw, cx: float, cy: float, r_out: float = 10.0, r_in: float = 4.5):
    pts = []
    for idx in range(10):
        ang = math.radians(-90 + idx * 36)
        r_curr = r_out if idx % 2 == 0 else r_in
        pts.append((cx + r_curr * math.cos(ang), cy + r_curr * math.sin(ang)))
    draw.polygon(pts, fill=(251, 191, 36))


def generate_deal_card(
    title: str,
    output_path: str,
    deal_info: dict,
    image_url: str = None,
    product_url: str = None,
    brand_name: str = "FIRSAT & İNDİRİM RADARI",
    handle: str = "@bu__cuma",
    second_deal: dict = None
) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    W, H = 1200, 675
    card = Image.new("RGB", (W, H), (10, 14, 23))
    draw = ImageDraw.Draw(card)

    # Dış Çerçeve (Altın / Kehribar İnce Vurgu)
    draw.rounded_rectangle([(14, 14), (W - 14, H - 14)], radius=20, outline=(245, 158, 11), width=2)

    raw_discount = deal_info.get("discount", "")
    pct_digits = re.sub(r'[^0-9]+', '', str(raw_discount))
    pct_int = int(pct_digits) if pct_digits.isdigit() else 0

    # 1. Üst Rozetler (Kategori + Gerçek Yıldız Puanı / Satış Kanıtı Rozeti)
    f_badge = get_font(20)
    if deal_info.get("is_truly_market_cheaper"):
        cat_text = "MARKETTEN ÇOK DAHA UCUZ!"
    else:
        cat_text = tr_upper(deal_info.get("category", "GÜNÜN FIRSATI"))

    rating_str = deal_info.get("rating_str", "")
    reviews_str = deal_info.get("reviews_str", "")
    sales_badge = deal_info.get("sales_badge", "")
    lowest_days = deal_info.get("lowest_days", 0)

    if rating_str and lowest_days >= 30:
        proof_text = f"PUAN: {rating_str} • SON {lowest_days} GÜNÜN EN DÜŞÜĞÜ"
    elif lowest_days >= 30:
        proof_text = f"▼ AMAZON ONAYLI: SON {lowest_days} GÜNÜN DİP FİYATI"
    elif rating_str and sales_badge:
        proof_text = f"PUAN: {rating_str} • {tr_upper(sales_badge)}"
    elif rating_str and reviews_str:
        proof_text = f"PUAN: {rating_str} ({reviews_str} YORUM)"
    elif rating_str:
        proof_text = f"MÜŞTERİ PUANI: {rating_str}"
    elif sales_badge:
        proof_text = f"▲ {tr_upper(sales_badge)}"
    elif deal_info.get("is_amazon_seller"):
        proof_text = "▼ SATICI: AMAZON.COM.TR"
    else:
        proof_text = "▼ DOĞRULANMIŞ FIRSAT"

    # Kategori Rozeti (Altın Sarısı)
    c_bbox = draw.textbbox((0, 0), cat_text, font=f_badge)
    c_w = (c_bbox[2] - c_bbox[0]) + 28
    draw.rounded_rectangle([(45, 32), (45 + c_w, 74)], radius=10, fill=(245, 158, 11))
    draw.text((59, 42), cat_text, font=f_badge, fill=(0, 0, 0))

    # Sosyal Kanıt / Doğrulama Rozeti (Vektörel Altın Yıldız + Koyu Lacivert Çerçeve)
    s_bbox = draw.textbbox((0, 0), proof_text, font=f_badge)
    has_star = bool(rating_str)
    star_pad = 26 if has_star else 0
    s_w = (s_bbox[2] - s_bbox[0]) + 28 + star_pad
    s_x = 45 + c_w + 12
    if s_x + s_w < W - 35:
        draw.rounded_rectangle([(s_x, 32), (s_x + s_w, 74)], radius=10, fill=(30, 41, 59), outline=(56, 189, 248), width=2)
        if has_star:
            draw_gold_star(draw, s_x + 22, 53, 10, 4.5)
        draw.text((s_x + 14 + star_pad, 42), proof_text, font=f_badge, fill=(240, 249, 255))

    has_second = bool(second_deal and second_deal.get("title"))

    # 2. Sağ Panel: Ürün Görseli Çerçevesi
    img_box_x1, img_box_y1 = 685, 88
    img_box_x2, img_box_y2 = 1150, (536 if has_second else 562)
    draw.rounded_rectangle([(img_box_x1, img_box_y1), (img_box_x2, img_box_y2)], radius=20, fill=(255, 255, 255), outline=(245, 158, 11), width=4)

    if image_url:
        try:
            r = requests.get(image_url, timeout=7, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                raw = Image.open(BytesIO(r.content)).convert("RGBA")
                max_w = (img_box_x2 - img_box_x1) - 34
                max_h = (img_box_y2 - img_box_y1) - 34
                raw.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                pw, ph = raw.size
                px = img_box_x1 + ((img_box_x2 - img_box_x1) - pw) // 2
                py = img_box_y1 + ((img_box_y2 - img_box_y1) - ph) // 2
                card.paste(raw, (px, py), raw)
        except Exception as e:
            print(f"⚠️ Görsel karta işlenemedi: {e}")

    # Ürün kutusunun sağ üst köşesine kırmızı "-%XX" indirim damgası
    if 15 <= pct_int <= 90:
        f_corner = get_font(30)
        c_tag = f"-%{pct_int}"
        cb = draw.textbbox((0, 0), c_tag, font=f_corner)
        cw = (cb[2] - cb[0]) + 28
        draw.rounded_rectangle([(img_box_x2 - cw - 14, img_box_y1 + 14), (img_box_x2 - 14, img_box_y1 + 64)], radius=12, fill=(220, 38, 38))
        draw.text((img_box_x2 - cw, img_box_y1 + 22), c_tag, font=f_corner, fill=(255, 255, 255))

    # 3. Sol Panel: Başlık & Boşluksuz Dinamik Yerleşim
    f_title = get_font(35)
    clean_t = re.sub(r'\s+', ' ', title).strip()
    if "," in clean_t:
        parts = [p.strip() for p in clean_t.split(",") if p.strip()]
        if len(parts) >= 2 and parts[-1].lower() in parts[0].lower():
            clean_t = ", ".join(parts[:-1])

    lines = textwrap.wrap(clean_t, width=27)[:3]
    cur_y = 90
    for line in lines:
        draw.text((45, cur_y), line, font=f_title, fill=(255, 255, 255))
        cur_y += 42

    # İndirim + Satıcı Güvencesi Rozeti
    disc_y = cur_y + 12
    if pct_int >= 28:
        disc_text = f"▼ %{pct_int} DİP FİYAT İNDİRİMİ"
    elif 15 <= pct_int < 28:
        disc_text = f"▼ %{pct_int} DOĞRULANMIŞ İNDİRİM"
    else:
        disc_text = "GÜNÜN FIRSAT ÜRÜNÜ"

    f_disc = get_font(22)
    d_bbox = draw.textbbox((0, 0), disc_text, font=f_disc)
    d_w = (d_bbox[2] - d_bbox[0]) + 28
    draw.rounded_rectangle([(45, disc_y), (45 + d_w, disc_y + 40)], radius=8, fill=(220, 38, 38))
    draw.text((59, disc_y + 8), disc_text, font=f_disc, fill=(255, 255, 255))

    # "NET KAZANÇ: X TL CEBİNİZDE!" Kutusu
    price_y = disc_y + 48
    savings_str = deal_info.get("savings_str", "")
    if savings_str:
        sav_label = f"NET KAZANÇ: {savings_str} CEBİNİZDE!"
        f_sav = get_font(23)
        sv_bbox = draw.textbbox((0, 0), sav_label, font=f_sav)
        sv_w = (sv_bbox[2] - sv_bbox[0]) + 28
        draw.rounded_rectangle([(45, price_y), (45 + sv_w, price_y + 40)], radius=10, fill=(6, 78, 59), outline=(16, 185, 129), width=2)
        draw.text((59, price_y + 8), sav_label, font=f_sav, fill=(52, 211, 153))
        price_y += 48

    # Birim Fiyat ("TANESİ SADECE 11,77 TL!") veya Ek Kampanya Kutusu
    unit_str = deal_info.get("unit_str", "")
    coupon_text = deal_info.get("coupon_text", "")
    raw_hl = unit_str if unit_str else (coupon_text if coupon_text else "")
    highlight_bar = tr_upper(raw_hl)
    if highlight_bar:
        f_unit = get_font(21)
        u_label = f"► {highlight_bar}"
        ub = draw.textbbox((0, 0), u_label, font=f_unit)
        uw = min(615, (ub[2] - ub[0]) + 28)
        draw.rounded_rectangle([(45, price_y), (45 + uw, price_y + 38)], radius=9, fill=(69, 26, 3), outline=(245, 158, 11), width=2)
        draw.text((59, price_y + 7), u_label, font=f_unit, fill=(253, 224, 71))
        price_y += 46

    # Fiyat Bilgisi (Eski Fiyat Üstü Çizili + Dev Yeni Fiyat)
    price = clean_price_display(deal_info.get("price", ""))
    old_price = clean_price_display(deal_info.get("old_price", ""))

    if old_price:
        f_old = get_font(24)
        old_text = f"Önceki Fiyat: {old_price}"
        draw.text((45, price_y), old_text, font=f_old, fill=(148, 163, 184))
        o_bbox = draw.textbbox((45, price_y), old_text, font=f_old)
        mid_y = (o_bbox[1] + o_bbox[3]) // 2
        draw.line([(45, mid_y), (o_bbox[2] + 4, mid_y)], fill=(239, 68, 68), width=3)
        price_y += 32

    if price:
        f_price = get_font(56)
        draw.text((45, price_y), price, font=f_price, fill=(16, 185, 129))

    # 4. Alt Şeritler:
    # Eğer 2. Fırsat (Kasa Yanı Bonus) varsa üstte "YORUMDA +1 BONUS FIRSAT" şeridi + altta Takipçi Şeridi!
    if has_second:
        s_info = second_deal.get("deal_info", {})
        s_title_raw = re.sub(r'\s+', ' ', second_deal.get("title", "")).strip()
        if len(s_title_raw) > 46:
            s_title_raw = s_title_raw[:44].strip() + ".."
        s_disc = s_info.get("discount_percent", 0)
        s_price = s_info.get("price", "")

        # Üst Alt-Şerit: YORUMDA +1 BONUS FIRSAT (y = 548..594)
        draw.rounded_rectangle([(30, 548), (W - 30, 594)], radius=10, fill=(30, 27, 75), outline=(168, 85, 247), width=2)
        f_bonus = get_font(20)
        bonus_left = f"► YORUMDA +1 BONUS FIRSAT: {tr_upper(s_title_raw)}"
        draw.text((46, 560), bonus_left, font=f_bonus, fill=(253, 224, 71))

        bonus_right = f"-%{s_disc} İNDİRİM  |  {s_price} ▼"
        br_bbox = draw.textbbox((0, 0), bonus_right, font=f_bonus)
        draw.text((W - 46 - (br_bbox[2] - br_bbox[0]), 560), bonus_right, font=f_bonus, fill=(52, 211, 153))

        # Alt Şerit: Takip & İki Link Çağrısı (y = 602..648)
        draw.rounded_rectangle([(30, 602), (W - 30, 648)], radius=10, fill=(17, 24, 39), outline=(245, 158, 11), width=2)
        f_footer = get_font(20)
        cta_left = f"► ANLIK İNDİRİM RADARI İÇİN TAKİP ET: {handle}"
        draw.text((46, 614), cta_left, font=f_footer, fill=(251, 191, 36))

        cta_right = "2 LİNK DE İLK YORUMDA ▼"
        r_bbox = draw.textbbox((0, 0), cta_right, font=f_footer)
        draw.text((W - 46 - (r_bbox[2] - r_bbox[0]), 614), cta_right, font=f_footer, fill=(52, 211, 153))
    else:
        draw.rounded_rectangle([(30, 582), (W - 30, 646)], radius=12, fill=(17, 24, 39), outline=(245, 158, 11), width=2)
        f_footer = get_font(22)
        cta_left = f"► ANLIK İNDİRİM RADARI İÇİN TAKİP ET: {handle}"
        draw.text((48, 602), cta_left, font=f_footer, fill=(251, 191, 36))

        cta_right = "LİNK İLK YORUMDA ▼"
        r_bbox = draw.textbbox((0, 0), cta_right, font=f_footer)
        draw.text((W - 48 - (r_bbox[2] - r_bbox[0]), 602), cta_right, font=f_footer, fill=(52, 211, 153))

    card.save(output_path, "JPEG", quality=95)
    return output_path
