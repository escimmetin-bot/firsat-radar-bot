"""
FirsatRadar | Twitter (X) Otonom Paylaşım Motoru (Usta Pazarlamacı v4: Birim Fiyat + Çift Komisyonlu Kombin Link + 280 Karakter Uyumlu)
- Gece 01:00 - 08:00 (TR) arası uyku moduna geçer, en iyi fırsatları gece harcamaz!
- Gündüz (08:00 - 18:00) 2 saatte 1, Akşam Prime-Time (18:00 - 01:00) 1 saatte 1 paylaşım yapar.
- Sadece gerçekten marketten ucuz olan (ve Satıcı: Amazon.com.tr olan) ürünlere "MARKETTEN ÇOK DAHA UCUZ!" başlığı atar.
- İlk yorumda hem Ana Ürünün linkini hem de Tamamlayıcı 2. Fırsatın linkini (Çift Komisyon Tuzağı) + Aciliyet bildirim çağrısını paylaşır!
"""
import os
import re
import json
import time
import html
from typing import Tuple, Optional
from playwright.sync_api import sync_playwright

import config

HISTORY_FILE = os.path.join(config.BASE_DIR, "deals_posted_history.json")


def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def save_history(history: list):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history[-150:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Geçmiş kaydedilemedi: {e}")


def can_post_now(force: bool = False) -> Tuple[bool, str]:
    if force:
        return True, "Zorunlu mod aktif."

    now_ts = time.time()
    tr_ts = now_ts + 10800
    tr_hour = int((tr_ts % 86400) // 3600)

    # Gece 01:00 - 08:00 arası Uyku Modu
    if 1 <= tr_hour < 8:
        return False, f"Gece uyku modu ({tr_hour:02d}:00 TR): En iyi fırsatlar sabah 08:00'e saklanıyor."

    hist = load_history()
    posted = [h for h in hist if isinstance(h, dict) and h.get("status") in ("posted", "posted_telegram") and h.get("ts")]
    if not posted:
        return True, "İlk paylaşım."

    last_ts = float(posted[-1]["ts"])
    elapsed = (now_ts - last_ts) / 60.0

    is_prime_time = (tr_hour >= 18 or tr_hour == 0)
    if is_prime_time:
        slot_seconds = 3600
        min_gap_minutes = 45.0
        mode_name = "Prime-Time (1 Saatlik Dilim)"
    else:
        slot_seconds = 7200
        min_gap_minutes = 85.0
        mode_name = "Gündüz Modu (2 Saatlik Dilim)"

    current_slot = int(tr_ts // slot_seconds)
    last_slot = int((last_ts + 10800) // slot_seconds)

    if current_slot <= last_slot:
        next_slot_ts = (current_slot + 1) * slot_seconds - 10800
        rem = max(1.0, round((next_slot_ts - now_ts) / 60.0, 1))
        return False, f"{mode_name} kilidi: Bu dilimde paylaşıldı (Yeni dilime {rem} dk kaldı)."

    if elapsed < min_gap_minutes:
        rem = round(min_gap_minutes - elapsed, 1)
        return False, f"{mode_name} koruma kilidi: Son paylaşımdan {round(elapsed, 1)} dk geçti ({rem} dk kaldı)."

    return True, f"{mode_name} aktif ({round(elapsed, 1)} dk geçti)."


def x_weighted_len(text: str) -> int:
    """X (Twitter) resmi twitter-text v3 ağırlıklı karakter hesabı (URL=23, Emoji/Özel Sembol=2)."""
    if not text:
        return 0
    without_urls = re.sub(r'https?://\S+', '', text)
    url_count = len(re.findall(r'https?://\S+', text))
    char_weight = sum(2 if ord(ch) > 0x10FF else 1 for ch in without_urls)
    return char_weight + (url_count * 23)


def format_deal_tweet(title: str, summary: str, deal_info: dict, deal_link: str = "") -> str:
    """
    Mavi Tiksiz Hesaba (%100 <= 255 karakter) Uygun, Usta Pazarlamacı Ana Tweet:
    - Sadece gerçekten marketten ucuz olan (ve Satıcı: Amazon.com.tr olan) ürünlere "MARKETTEN ÇOK DAHA UCUZ!" der.
    - Birim fiyatı ("💡 Tanesi Sadece 98,50 TL!"), Yıldız puanını (⭐ 4.8/5) ve kasa önü kampanyayı gösterir.
    """
    c_title = html.unescape(title).strip()
    c_title = re.sub(r'[\u200b-\u200f\u202a-\u202e\ufeff]+', '', c_title).strip()

    disc_pct = deal_info.get("discount_percent", 0)
    price = deal_info.get("price", "")
    old_price = deal_info.get("old_price", "")
    savings_str = deal_info.get("savings_str", "")
    category = deal_info.get("category", "GÜNÜN FIRSATI")
    brand_tag = deal_info.get("brand_tag", "#İndirim")
    cat_tag = deal_info.get("category_tag", "#Marketİndirimi")
    rating_str = deal_info.get("rating_str", "")
    sales_badge = deal_info.get("sales_badge", "")
    coupon_text = deal_info.get("coupon_text", "")
    unit_str = deal_info.get("unit_str", "")
    official_low_badge = deal_info.get("official_low_badge", "")
    is_truly_market_cheaper = deal_info.get("is_truly_market_cheaper", False)

    # Dürüst, X Arama Motoru (SEO: "Amazon") Uyumlu & Yüksek Dönüşümlü Kanca Seçimi
    if is_truly_market_cheaper:
        header = f"🛒 AMAZON'DA MARKETTEN UCUZ! (%{disc_pct} İNDİRİM)"
    elif disc_pct >= 32:
        header = f"🚨 AMAZON'DA FİYAT DİBİ GÖRDÜ! (%{disc_pct} İNDİRİM)"
    elif "TEKNOLOJİ" in category:
        header = f"⚡ AMAZON'DA TEKNOLOJİ FIRSATI! (%{disc_pct} İNDİRİM)"
    elif "MODA" in category:
        header = f"👕 AMAZON'DA GİYİM & MODA FIRSATI! (%{disc_pct} İNDİRİM)"
    elif "TEMİZLİK" in category:
        header = f"🧼 AMAZON'DA TEMİZLİK FIRSATI! (%{disc_pct} İNDİRİM)"
    elif "KAHVE" in category:
        header = f"☕ AMAZON'DA KAHVE & MARKET FIRSATI! (%{disc_pct} İNDİRİM)"
    elif "KİŞİSEL BAKIM" in category:
        header = f"🧴 AMAZON'DA KİŞİSEL BAKIM FIRSATI! (%{disc_pct} İNDİRİM)"
    elif "MUTFAK" in category:
        header = f"🍳 AMAZON'DA MUTFAK & EV FIRSATI! (%{disc_pct} İNDİRİM)"
    else:
        header = f"🔥 AMAZON'DA SÜPER FIRSAT! (%{disc_pct} İNDİRİM)"

    price_lines = []
    if old_price and price:
        price_lines.append(f"❌ {old_price} ➔ ✅ Şimdi: {price}")
    elif price:
        price_lines.append(f"✅ Fırsat Fiyatı: {price}")

    # Birim fiyat varsa en vurucu satır olarak ekle!
    if unit_str:
        r_part = f" | ⭐ {rating_str}" if rating_str else ""
        price_lines.append(f"💡 {unit_str}{r_part}")
    else:
        line2_parts = []
        if savings_str:
            line2_parts.append(f"💰 Kazanç: {savings_str}")
        if rating_str:
            line2_parts.append(f"⭐ {rating_str}")
        if line2_parts:
            price_lines.append(" | ".join(line2_parts))

    if official_low_badge:
        clean_low = official_low_badge.replace("Amazon Onaylı: ", "")
        price_lines.append(f"🏆 {clean_low}")
    elif coupon_text:
        price_lines.append(f"🎁 {coupon_text}")
    elif sales_badge:
        price_lines.append(f"🔥 {sales_badge}")

    price_block = "\n".join(price_lines)
    cta_line = "👇 İndirim linkleri ilk yorumda!"

    # X Arama Motorunda Kategoriye Göre Doğal Çeşitlenen Etiketler (Spam Korumalı)
    if brand_tag.lower() in ("#indirim", "#i̇ndirim", "#marketindirimi", "#marketi̇ndirimi", cat_tag.lower()):
        tags = f"{cat_tag} #GülümsetenKasım #İndirim" if cat_tag != "#İndirim" else "#Amazon #GülümsetenKasım #İndirim"
    else:
        second_tag = cat_tag if cat_tag not in ("#İndirim", "#Marketİndirimi") else "#GülümsetenKasım"
        tags = f"{brand_tag} {second_tag} #İndirim"

    def build_tweet(prod_text: str) -> str:
        return f"{header}\n\n📌 {prod_text}\n\n{price_block}\n\n{cta_line}\n{tags}".strip()

    MAX_WEIGHT = 272
    if x_weighted_len(build_tweet(c_title)) <= MAX_WEIGHT:
        return build_tweet(c_title)

    short_title = c_title
    for sep in [" | ", " - ", " – ", ", "]:
        while sep in short_title and x_weighted_len(build_tweet(short_title)) > MAX_WEIGHT:
            short_title = short_title.rsplit(sep, 1)[0].strip()

    if x_weighted_len(build_tweet(short_title)) <= MAX_WEIGHT and len(short_title) >= 16:
        return build_tweet(short_title)

    words = c_title.split()
    trimmed = ""
    for w in words:
        test_str = f"{trimmed} {w}".strip()
        if x_weighted_len(build_tweet(f"{test_str}...")) <= MAX_WEIGHT:
            trimmed = test_str
        else:
            break

    return build_tweet(f"{trimmed}...")


def format_deal_reply(deal_info: dict, deal_link: str, second_deal: Optional[dict] = None) -> str:
    """
    Usta Pazarlamacı İlk Yorum Motoru (280 Karakter Sınırına %100 Uyumlu!):
    - 1. Link: Ana ürünün affiliate linki
    - 2. Link (Varsa): Yanına tamamlayıcı 2. fırsatın affiliate linki (Çift Komisyon Tuzağı!)
    - Alt Kanca: "Satıcı Amazon.com.tr: İndirimli stok bitince fiyat eskiye döner! Bildirimleri (🔔) açın: @bu__cuma"
    """
    disc_pct = deal_info.get("discount_percent", 0)
    price = deal_info.get("price", "")
    badge = f" (%{disc_pct} İndirimle {price})" if disc_pct and price else ""
    handle = getattr(config, "X_HANDLE", "@bu__cuma") or "@bu__cuma"

    if second_deal and second_deal.get("link"):
        s_info = second_deal.get("deal_info", {})
        s_price = s_info.get("price", "")
        s_disc = s_info.get("discount_percent", 0)
        s_title = second_deal.get("title", "Günün 2. Fırsatı").strip()
        if len(s_title) > 32:
            s_title = s_title[:30].strip() + ".."
        reply_with_second = (
            f"🛒 Ürün Linki{badge}:\n"
            f"{deal_link}\n\n"
            f"🔥 Yanına 2. Fırsat ({s_title} -{s_disc}% {s_price}):\n"
            f"{second_deal['link']}\n\n"
            f"⚠️ Stok bitince fiyat eskiye döner! Kaçırmamak için {handle} bildirimlerini (🔔) açın!"
        )
        if x_weighted_len(reply_with_second) <= 272:
            return reply_with_second

    return (
        f"🛒 Amazon İndirimli Ürün Linki{badge}:\n"
        f"{deal_link}\n\n"
        f"⚠️ Satıcı Amazon.com.tr: İndirimli stok bitince fiyat otomatik eskiye döner! Kaçırmamak için {handle} takip edip bildirimleri (🔔) açın!\n"
        f"✈️ Telegram: https://t.me/FirsatRadars"
    )


def post_to_x(text: str, image_path: str = None, reply_link: str = None, deal_info: dict = None, second_deal: Optional[dict] = None) -> dict:
    if not config.TWITTER_AUTH_TOKEN or not config.TWITTER_CT0:
        return {"status": "error", "message": "TWITTER_AUTH_TOKEN veya TWITTER_CT0 eksik."}

    try:
        with sync_playwright() as p:
            launch_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled"
            ]
            browser = None
            try:
                browser = p.chromium.launch(channel="chrome", headless=True, args=launch_args)
            except Exception:
                browser = p.chromium.launch(headless=True, args=launch_args)

            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900}
            )
            ctx.add_cookies([
                {"name": "auth_token", "value": config.TWITTER_AUTH_TOKEN, "domain": ".x.com", "path": "/", "secure": True, "httpOnly": True},
                {"name": "ct0", "value": config.TWITTER_CT0, "domain": ".x.com", "path": "/", "secure": True, "httpOnly": False}
            ])

            page = ctx.new_page()

            page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=30000)

            editor = None
            try:
                page.wait_for_selector('div[role="textbox"]', timeout=8000)
                editor = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
                if not editor.count():
                    editor = page.locator('div[role="textbox"]')
            except Exception:
                pass

            if not editor or not editor.count():
                print("🔄 /compose/post açılmadı, /home sayfasına geçiliyor...")
                page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_selector('div[role="textbox"]', timeout=12000)
                    editor = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
                    if not editor.count():
                        editor = page.locator('div[role="textbox"]')
                except Exception:
                    pass

            if not editor or not editor.count():
                browser.close()
                return {"status": "error", "message": "Tweet metin kutusu bulunamadı"}

            # 2. Ana Tweeti Yaz
            editor.first.click()
            editor.first.fill(text)
            page.wait_for_timeout(600)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

            # 3. Görseli Ana Tweete Yükle
            if image_path and os.path.exists(image_path):
                file_input = page.locator('input[data-testid="fileInput"]').first
                if file_input.count():
                    file_input.set_input_files(image_path)
                    print("⏳ Görsel X'e aktarılıyor...")
                    for sec in range(1, 15):
                        page.wait_for_timeout(1000)
                        attachments = page.locator('div[data-testid="attachments"]').count()
                        if attachments > 0:
                            print(f"✅ Görsel başarıyla yüklendi ({sec}. saniye).")
                            break
                    page.wait_for_timeout(1500)

            # 4. İlk Yorumu (Çift Affiliate Linki + Aciliyet Bildirim Çağrısı) '+' ile Ekle
            if reply_link:
                reply_text = format_deal_reply(deal_info or {}, reply_link, second_deal=second_deal)
                add_btn = page.locator('button[data-testid="addButton"]').first
                if add_btn.count():
                    try:
                        add_btn.click()
                        page.wait_for_timeout(1000)
                        reply_editor = page.locator('div[role="textbox"][data-testid="tweetTextarea_1"]').first
                        if reply_editor.count():
                            reply_editor.click()
                            reply_editor.fill(reply_text)
                            page.wait_for_timeout(700)
                            page.keyboard.press("Escape")
                            page.wait_for_timeout(500)
                            print("🔗 Çift fırsat linki ve aciliyet çağrısı ilk yorum olarak eklendi.")
                    except Exception as e:
                        print(f"⚠️ Alt yorum eklenirken uyarı: {e}")

            # 5. Gönder Butonunu Bekle ve Gönder
            post_btn = page.locator('button[data-testid="tweetButton"]').last
            if not post_btn.count():
                post_btn = page.locator('button[data-testid="tweetButtonInline"]').first

            for _ in range(15):
                aria_dis = post_btn.get_attribute("aria-disabled") if post_btn.count() else "true"
                if aria_dis != "true":
                    break
                page.wait_for_timeout(1000)

            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

            print("🚀 Tweet + İlk Yorum gönderiliyor...")
            try:
                post_btn.click(force=True, timeout=5000)
            except Exception:
                pass

            page.wait_for_timeout(1500)

            if post_btn.count() and post_btn.is_visible():
                try:
                    page.evaluate('''() => {
                        const btn = document.querySelector('button[data-testid="tweetButton"]') || document.querySelector('button[data-testid="tweetButtonInline"]');
                        if (btn) btn.click();
                    }''')
                except Exception:
                    pass

            page.wait_for_timeout(1500)

            if post_btn.count() and post_btn.is_visible():
                try:
                    page.keyboard.press("Control+Enter")
                except Exception:
                    pass

            posted = False
            for _ in range(12):
                page.wait_for_timeout(1000)
                if not post_btn.count() or not post_btn.is_visible():
                    posted = True
                    break

            page.wait_for_timeout(3000)
            browser.close()
            if posted:
                return {"status": "success", "message": "Ana Tweet + İlk Yorum (Çift Link) başarıyla gönderildi."}
            else:
                return {"status": "warning", "message": "Tweet butonu tetiklendi ancak modal kapanmadı."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
