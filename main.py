"""
FirsatRadar | Ana Çalıştırıcı Motor (Usta Pazarlamacı v4: Birim Fiyat + Çift Komisyonlu Kombin Sepet)
Kullanım:
  python main.py          (Normal döngü)
  python main.py --dry    (Simülasyon / Test modu)
"""
import os
import sys
import time

if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from deals_news import fetch_deal_articles, pick_primary_and_second_deal
from deals_card import generate_deal_card
from deals_poster import can_post_now, format_deal_tweet, format_deal_reply, post_to_x, load_history, save_history
from deals_telegram import format_telegram_caption, send_deal_post_to_telegram


def run_cycle(dry_run: bool = False, force: bool = False):
    print("=" * 60)
    print("🛒 FIRSATRADAR | VİTRİN MIKNATISI & KASA YANI FIRSAT MOTORU (v6)")
    print("=" * 60)

    # 1. Zaman Kilidi Kontrolü
    if not dry_run:
        allowed, reason = can_post_now(force=force)
        if not allowed:
            print(f"⏳ [Zaman Kilidi] {reason}")
            return

    # 2. İndirim Havuzu
    history = load_history()
    posted_slugs = {h.get("slug") for h in history if isinstance(h, dict)}

    print("📡 Vitrin (Teknoloji, Mutfak, Giyim) ve Kasa Yanı (Market, Kahve, Temizlik) fırsatları taranıyor...")
    deals = fetch_deal_articles(config.DEAL_RSS_FEEDS, posted_slugs=posted_slugs, history=history)
    print(f"  • {len(deals)} adet doğrulanmış sıcak fırsat tespit edildi.")

    if not deals:
        print("ℹ️ Şu an paylaşılacak yeni içerik bulunamadı.")
        return

    unposted = [d for d in deals if d["slug"] not in posted_slugs]
    if not unposted:
        print("ℹ️ Havuzdaki tüm fırsatlar daha önce paylaşılmış.")
        return

    candidate, second_deal = pick_primary_and_second_deal(unposted)
    if not candidate:
        print("ℹ️ Uygun ana fırsat bulunamadı.")
        return

    deal_info = candidate["deal_info"]
    print(f"🎯 [1. Vitrin Fırsatı - {candidate['virality_score']} Puan | Kazanç: {deal_info.get('savings_str', '-')}]: {deal_info['category_emoji']} {deal_info['category']} - {candidate['title']}")
    if second_deal:
        print(f"🎁 [2. Kasa Yanı Bonus Fırsat]: {second_deal['title'][:45]} (-%{second_deal['deal_info'].get('discount_percent')} | {second_deal['deal_info'].get('price')})")

    # 3. Editoryal Lüks Kart Tasarımı (Thumb-Stopper v6)
    out_dir = os.path.join(config.BASE_DIR, "output")
    os.makedirs(out_dir, exist_ok=True)
    card_path = os.path.join(out_dir, f"deal_{candidate['slug'][:25]}.jpg")

    generate_deal_card(
        title=candidate["title"],
        output_path=card_path,
        deal_info=deal_info,
        image_url=candidate.get("image_url"),
        product_url=candidate.get("link"),
        brand_name=config.BRAND_NAME,
        handle=config.X_HANDLE,
        second_deal=second_deal
    )
    print(f"🎨 Editoryal İndirim Kartı Oluşturuldu: {card_path}")

    # 4. Tweet (Ana Tweet + Çift Linkli İlk Yorum) & Telegram Formatlama
    tweet_text = format_deal_tweet(candidate["title"], candidate.get("summary", ""), deal_info, candidate["link"])
    reply_text = format_deal_reply(deal_info, candidate["link"], second_deal=second_deal)
    tg_caption = format_telegram_caption(
        candidate["title"],
        candidate.get("summary", ""),
        deal_info,
        candidate["link"],
        channel_handle=config.TELEGRAM_TARGET_CHAT,
        second_deal=second_deal
    )
    print("-" * 40)
    print("[ANA TWEET]:\n" + tweet_text)
    print("\n[İLK YORUM (ÇİFT LİNK + ACİLİYET)]:\n" + reply_text)
    print("-" * 40)

    # 5. Telegram Yayını (Çift Satın Al Butonlu)
    print("✈️ Telegram yayını yapılıyor...")
    tg_ok = send_deal_post_to_telegram(
        card_path,
        tg_caption,
        deal_link=candidate["link"],
        deal_info=deal_info,
        second_deal=second_deal
    )
    if tg_ok:
        print("✅ [Telegram] Fırsat bülteni çift butonlu olarak başarıyla gönderildi!")
    else:
        print("⚠️ [Telegram] Gönderim başarısız oldu.")

    # 6. X (Twitter) Yayını (Ana Tweet + Otomatik İlk Yorumda Çift Link)
    if not dry_run:
        print("🚀 X'e (Ana Tweet + İlk Yorumda Çift Link) gönderiliyor...")
        x_res = post_to_x(
            tweet_text,
            card_path,
            reply_link=candidate["link"],
            deal_info=deal_info,
            second_deal=second_deal
        )
        if x_res.get("status") == "success":
            print("🎉 [FirsatRadar] X'e (Ana Tweet + İlk Yorumda Çift Link) başarıyla paylaşıldı!")
            history.append({
                "slug": candidate["slug"],
                "title": candidate["title"],
                "category": deal_info["category"],
                "status": "posted",
                "ts": time.time()
            })
            save_history(history)
        else:
            print(f"⚠️ [X Hatası] {x_res.get('message')}")
            if tg_ok:
                history.append({
                    "slug": candidate["slug"],
                    "title": candidate["title"],
                    "category": deal_info["category"],
                    "status": "posted_telegram",
                    "ts": time.time()
                })
                save_history(history)
    else:
        print("🧪 [DRY RUN] Tweet atılmadı, simülasyon tamamlandı.")


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    force = "--force" in sys.argv
    run_cycle(dry_run=dry, force=force)
