"""
FirsatRadar | Telegram Yayın & Dağıtım Motoru (Usta Pazarlamacı v4: Birim Fiyat + Tamamlayıcı 2. Fırsat Butonu)
İndirim fırsatlarını @FirsatRadars kanalına fotoğraflı, birim fiyatlı, yıldız puanlı ve çift satın alma butonlu olarak gönderir.
"""
import os
import json
import requests
import html
import urllib.parse
from typing import Optional

import config

TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
TELEGRAM_TARGET_CHAT = config.TELEGRAM_TARGET_CHAT


def format_telegram_caption(title: str, summary: str, deal_info: dict, deal_link: str, channel_handle: str = "@FirsatRadars", second_deal: Optional[dict] = None) -> str:
    """Telegram için şık, birim fiyatlı, yıldız puanlı ve tamamlayıcı 2. fırsat destekli bülten metni."""
    c_title = html.unescape(title).strip()

    cat_name = deal_info.get("category", "GÜNÜN FIRSATI")
    cat_emoji = deal_info.get("category_emoji", "🔥")
    store_name = deal_info.get("store", "AMAZON TR")
    store_emoji = deal_info.get("store_emoji", "🛒")
    price = deal_info.get("price")
    old_price = deal_info.get("old_price")
    savings_str = deal_info.get("savings_str")
    discount = deal_info.get("discount", "")
    disc_pct = deal_info.get("discount_percent", 0)
    rating_str = deal_info.get("rating_str", "")
    reviews_str = deal_info.get("reviews_str", "")
    sales_badge = deal_info.get("sales_badge", "")
    coupon_text = deal_info.get("coupon_text", "")
    unit_str = deal_info.get("unit_str", "")
    is_truly_market_cheaper = deal_info.get("is_truly_market_cheaper", False)

    if is_truly_market_cheaper:
        header_line = f"🛒 <b>MARKETTEN ÇOK DAHA UCUZ! (%{disc_pct} İNDİRİM)</b>"
    elif disc_pct >= 30:
        header_line = f"🚨 <b>FİYAT DİBİ GÖRDÜ! (TAM %{disc_pct} İNDİRİM)</b>"
    else:
        header_line = f"{cat_emoji} <b>{cat_name.upper()}! ({discount} İndirim)</b>"

    price_lines = []
    if old_price:
        price_lines.append(f"❌ <b>Önceki Fiyat:</b> <s>{old_price}</s>")
    if price:
        price_lines.append(f"✅ <b>Fırsat Fiyatı:</b> <b>{price}</b>")
    if unit_str:
        price_lines.append(f"💡 <b>Birim Fiyat:</b> <b>{unit_str}</b>")
    if savings_str:
        price_lines.append(f"💰 <b>Net Kazanç:</b> <b>{savings_str} Cebinizde!</b>")
    if rating_str:
        rev_part = f" ({reviews_str} değerlendirme)" if reviews_str else ""
        price_lines.append(f"⭐ <b>Müşteri Puanı:</b> <b>{rating_str}</b>{rev_part}")
    if sales_badge:
        price_lines.append(f"🔥 <b>Popülerlik:</b> <b>{sales_badge}</b>")
    if coupon_text:
        price_lines.append(f"🎁 <b>Usta Tüyosu:</b> <b>{coupon_text}</b>")

    price_block = "\n".join(price_lines)
    link_line = f"👉 <b><a href=\"{deal_link}\">🛒 Ürünü Amazon'da İncele / Sepete Ekle</a></b>\n" if deal_link else ""

    second_line = ""
    if second_deal and second_deal.get("link"):
        s_info = second_deal.get("deal_info", {})
        s_title = html.unescape(second_deal.get("title", "")).strip()[:45]
        s_price = s_info.get("price", "")
        s_disc = s_info.get("discount_percent", 0)
        second_line = f"🔥 <b><a href=\"{second_deal['link']}\">Yanına 2. Fırsat: {s_title}... (-%{s_disc} | {s_price})</a></b>\n"

    caption = (
        f"{header_line}\n\n"
        f"📌 <b>{c_title}</b>\n\n"
        f"{price_block}\n\n"
        f"{link_line}"
        f"{second_line}\n"
        f"⚠️ <i>İndirimli stok bittiği an fiyat otomatik eski haline döner.</i>\n"
        f"⚡ <b>Fırsat Radarı:</b> {channel_handle} | X: @bu__cuma"
    )
    return caption[:1020]


def send_deal_post_to_telegram(photo_path: str, caption: str, deal_link: str = None, deal_info: dict = None, target_chat: str = None, second_deal: Optional[dict] = None) -> bool:
    chat_id = target_chat or TELEGRAM_TARGET_CHAT
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    payload = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "HTML"
    }

    if deal_link:
        disc_pct = (deal_info or {}).get("discount_percent", 0)
        price = (deal_info or {}).get("price", "")
        btn_label = f"🛒 Amazon'da Fırsata Git (%{disc_pct} İndirim - {price})" if disc_pct else "🛒 Amazon'da Fırsatı Gör"
        share_text = f"🔥 Amazon'da doğrulanmış fırsat ({price}): {deal_link}"
        share_url = f"https://t.me/share/url?url={urllib.parse.quote(deal_link)}&text={urllib.parse.quote(share_text)}"

        keyboard = [[{"text": btn_label, "url": deal_link}]]
        if second_deal and second_deal.get("link"):
            s_info = second_deal.get("deal_info", {})
            s_price = s_info.get("price", "")
            s_title = second_deal.get("title", "2. Fırsat")[:24].strip()
            keyboard.append([{"text": f"🔥 2. Fırsat: {s_title} ({s_price})", "url": second_deal["link"]}])
        keyboard.append([{"text": "📲 Bu Fırsatı Arkadaşına Gönder", "url": share_url}])

        payload["reply_markup"] = json.dumps({"inline_keyboard": keyboard})

    try:
        with open(photo_path, "rb") as f:
            resp = requests.post(
                url,
                data=payload,
                files={"photo": f},
                timeout=25
            )
            data = resp.json()
            if data.get("ok"):
                return True
            else:
                print(f"⚠️ Telegram API Hatası: {data.get('description')}")
                return False
    except Exception as e:
        print(f"⚠️ Telegram Gönderim Hatası: {e}")
        return False
