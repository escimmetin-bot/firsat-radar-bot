"""
FirsatRadar | Usta Pazarlamacı & "Vitrin Mıknatısı + Kasa Yanı Çapraz Satış" Otonom Fırsat Motoru (v6)
- "Vitrin Ürünü (Ana Tweet)" ile "Kasa Yanı Sepet Tamamlayıcı (Yorumdaki 2. Link)" ayrımı yapar:
  * Ana Tweete ASLA diş ipi, sıvı sabun, ruj, soğuk çay, peçete gibi X'te kimsenin aratmadığı ürünler çıkamaz!
  * Ana Tweete sadece X'te aranma hacmi yüksek Vitrin Markaları (Teknoloji/Oyuncu, Philips/Stanley/Karcher/Tefal/Karaca, Puma/Adidas/Jack&Jones/Levi's, Finish/Fairy/Jacobs/Nutella dev paketler) çıkar.
  * 50-250 TL arası küçük market/bakım ürünleri ise otomatik olarak İlk Yorumdaki "🔥 Yanına Sepetlik 2. Fırsat" koltuğuna atanır!
- Marka & Kategori Tekrar Kilidi (Anti-Spam): Son 8 paylaşımda kullanılan bir markayı (örn. Julius Meinl) tekrar ana tweete çıkarmaz ve üst üste aynı kategoriyi paylaşmaz.
- Kendi Fiyat Hafızası (deals_price_db.json) + Amazon Resmi "30/60/90/365 Günün En Düşük Fiyatı" + Birim Fiyat + Satıcı Amazon.com.tr doğrulaması.
"""
import os
import re
import json
import time
import html
import sys
from typing import List, Dict, Optional, Set
from playwright.sync_api import sync_playwright

if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config

PRICE_DB_FILE = os.path.join(config.BASE_DIR, "deals_price_db.json")
HISTORY_FILE = os.path.join(config.BASE_DIR, "deals_posted_history.json")


def load_price_db() -> Dict[str, Dict]:
    if os.path.exists(PRICE_DB_FILE):
        try:
            with open(PRICE_DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def save_price_db(db: Dict[str, Dict]):
    try:
        if len(db) > 1500:
            sorted_items = sorted(db.items(), key=lambda x: x[1].get("ts", 0), reverse=True)[:1500]
            db = dict(sorted_items)
        with open(PRICE_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Fiyat hafızası kaydedilemedi: {e}")


def check_and_record_price_memory(price_db: Dict[str, Dict], asin: str, cur_val: float, title: str = "") -> Dict:
    """
    Kendi Fiyat Hafızamız (Sahte İndirim Dedektörü).
    - Ürünü daha önce daha düşük fiyattan gördüysek ve satıcı bugün zam yapıp 'indirim' diye sunuyorsa yakalar!
    """
    now_ts = time.time()
    rec = price_db.get(asin)
    is_fake_markup = False
    prev_high = 0.0
    prev_min = cur_val

    if rec and isinstance(rec, dict):
        prev_min = float(rec.get("min_price", cur_val))
        prev_high = float(rec.get("max_price", cur_val))

        if prev_min > 0 and cur_val > prev_min * 1.06:
            is_fake_markup = True

        new_min = min(prev_min, cur_val)
        new_max = max(prev_high, cur_val)
    else:
        new_min = cur_val
        new_max = cur_val

    price_db[asin] = {
        "title": (title or "")[:60],
        "min_price": round(new_min, 2),
        "max_price": round(new_max, 2),
        "last_price": round(cur_val, 2),
        "ts": round(now_ts, 1)
    }
    return {
        "is_fake_markup": is_fake_markup,
        "prev_min": prev_min,
        "prev_high": prev_high,
        "dropped_from_memory": (prev_high > cur_val * 1.05)
    }


MIN_DISCOUNT_PERCENT = 15   # Minimum %15 gerçek indirim şartı
MAX_PRICE_TL = 4500.0       # 4.500 TL üstü pahalı ürünleri kesinlikle ele
MIN_RATING = 4.0            # Puanı 4.0 yıldızın altında olan ürünleri ele

# Kesinlikle Paylaşılmayacak Ürünler (Su, maden suyu vb.)
BANNED_KEYWORDS = [
    "maden suyu", "doğal kaynak suyu", "içme suyu", "mineralli su", "freşa", "akmina", "sırma su", "beypazarı", "kızılay", "erikli"
]

# KASA YANI / SEPET TAMAMLAYICI ÜRÜNLER:
# Bu kelimeleri içeren ürünler X'te kimse tarafından aranmadığı için ASLA Ana Tweet (1. Ürün) olamaz!
# Sadece İlk Yorumdaki "🔥 Yanına 2. Fırsat (Sepet Tamamlayıcı)" koltuğuna seçilebilirler!
BASKET_FILLER_KEYWORDS = [
    "diş ipi", "kürdan", "kulak çubuğu", "yara bandı", "pamuk", "sıvı sabun", "el sabunu", "kalıp sabun",
    "banyo lifi", "soğuk çay", "fusetea", "ice tea", "meyve suyu", "gazoz", "enerji içeceği",
    "ruj", "lip balm", "dudak", "oje", "maskara", "rimel", "göz kalemi", "allık", "fondöten", "far paleti", "flormar", "maybelline", "pastel", "golden rose",
    "bulaşık süngeri", "temizlik bezi", "mikrofiber bez", "çöp torbası", "buzdolabı poşeti", "streç film", "alüminyum folyo", "pişirme kağıdı",
    "peçete", "ıslak mendil", "cep mendili", "sakız", "gofret", "kraker", "bisküvi", "kek ", "browni", "çubuk kraker",
    "oda kokusu", "klozet bloğu", "banyo kokusu", "tüy toplayıcı", "ayakkabı boyası", "pil ", "kalem pil", "ince pil"
]

# VİTRİN MIKNATISI (YÜKSEK ARAMA HACMİ OLAN) MARKALAR (+175 Görüntülenme & Keşfet Bonusu)
HERO_SEARCH_BRANDS = [
    # Teknoloji & Gaming Ekipman
    "logitech", "razer", "hyperx", "steelseries", "corsair", "asus", "msi", "anker", "soundcore",
    "spigen", "baseus", "ugreen", "xiaomi", "redmi", "samsung", "jbl", "sony", "apple", "airpods",
    "magsafe", "sandisk", "kingston", "crucial", "wd ", "seagate", "tp-link", "huawei", "lenovo",
    # Mutfak, Termos & Ev Cihazları
    "stanley", "philips", "oneblade", "airfryer", "lumea", "karcher", "kärcher", "tefal", "karaca",
    "zwilling", "wmf", "staub", "brita", "bosch", "makita", "einhell", "lego", "paşabahçe", "emsan", "korkmaz",
    # Giyim, Moda & Spor Ayakkabı (%8-%10 Yüksek Komisyon)
    "puma", "adidas", "nike", "under armour", "skechers", "columbia", "salomon", "merrell", "the north face",
    "new balance", "crocs", "vans", "converse", "asics", "reebok", "tommy hilfiger", "calvin klein", "lacoste",
    "jack & jones", "jack jones", "levi's", "levis", "mavi", "u.s. polo", "us polo", "defacto", "koton",
    # Sadece Türkiye'de En Çok Aranan Dev Market/Temizlik Markaları
    "finish", "fairy", "ariel", "persil", "jacobs", "kahve dünyası", "tchibo", "mehmet efendi",
    "nutella", "çaykur", "gillette", "oral-b", "cerave", "la roche", "bioderma"
]

# Marka -> Gerçek Hashtag Eşleşmesi
BRAND_HASHTAG_MAP = [
    (["jacobs"], "#Jacobs"),
    (["kahve dünyası", "kahve dunyasi"], "#KahveDünyası"),
    (["tchibo"], "#Tchibo"),
    (["mehmet efendi", "kurukahveci"], "#Kahve"),
    (["nescafe", "nescafé"], "#Nescafe"),
    (["julius meinl", "lavazza", "illy", "starbucks", "caffe nero"], "#Kahve"),
    (["çaykur", "caykur", "lipton", "doğuş çay", "dogus cay"], "#Çay"),
    (["eti "], "#Eti"),
    (["ülker", "ulker"], "#Ülker"),
    (["nutella", "barilla", "calve", "knorr", "tamek", "komili", "kırlangıç", "tariş"], "#Market"),
    (["finish"], "#Finish"),
    (["fairy"], "#Fairy"),
    (["pril"], "#Pril"),
    (["ariel"], "#Ariel"),
    (["perwoll"], "#Perwoll"),
    (["omo"], "#Omo"),
    (["bingo"], "#Bingo"),
    (["domestos", "cif", "asperox", "vissmat", "marc", "vanish", "rinso", "abc deterjan", "vernel", "yumos", "yumoş"], "#Temizlik"),
    (["selpak", "solo", "familia", "papia", "maylo", "sofia"], "#Market"),
    (["gillette", "venus"], "#Gillette"),
    (["oral-b", "oral b"], "#OralB"),
    (["nivea"], "#Nivea"),
    (["head & shoulders", "head and shoulders", "pantene", "elidor", "clear", "elseve", "gliss"], "#KişiselBakım"),
    (["sensodyne", "colgate", "parodontax", "listerine", "signal"], "#KişiselBakım"),
    (["cerave", "la roche", "bioderma", "vichy", "garnier", "loreal", "l'oréal", "neutrogena", "bepanthol"], "#CiltBakımı"),
    (["dove", "rexona", "axe", "blade", "old spice", "palmolive", "duru", "activex"], "#KişiselBakım"),
    (["prima", "sleepy", "molfix", "uni baby"], "#AnneBebek"),
    (["stanley"], "#Stanley"),
    (["tefal"], "#Tefal"),
    (["philips", "oneblade", "airfryer", "lumea"], "#Philips"),
    (["karcher", "kärcher"], "#Karcher"),
    (["brita"], "#Brita"),
    (["karaca"], "#Karaca"),
    (["emsan", "jumbo", "korkmaz", "arzum", "fakir", "sinbo", "kiwi"], "#Mutfak"),
    (["zwilling", "staub", "wmf", "paşabahçe", "pasabahce", "lav ", "luminarc", "borcam", "pyrex"], "#Mutfak"),
    (["bosch"], "#Bosch"),
    (["makita"], "#Makita"),
    (["einhell"], "#Einhell"),
    (["xiaomi", "redmi", "mi "], "#Xiaomi"),
    (["anker", "soundcore"], "#Anker"),
    (["baseus", "ugreen", "spigen"], "#Aksesuar"),
    (["jbl"], "#JBL"),
    (["sony"], "#Sony"),
    (["samsung"], "#Samsung"),
    (["apple", "airpods", "magsafe"], "#Apple"),
    (["logitech"], "#Logitech"),
    (["razer", "steelseries", "hyperx", "corsair"], "#Gaming"),
    (["asus", "msi", "lenovo", "acer", "hp "], "#Teknoloji"),
    (["sandisk", "kingston", "seagate", "wd ", "crucial"], "#Depolama"),
    (["lego"], "#Lego"),
    (["jack & jones", "jack and jones", "jack jones"], "#JackAndJones"),
    (["levi's", "levis"], "#Levis"),
    (["defacto"], "#DeFacto"),
    (["koton"], "#Koton"),
    (["mavi"], "#Mavi"),
    (["u.s. polo", "us polo"], "#USPolo"),
    (["puma"], "#Puma"),
    (["adidas"], "#Adidas"),
    (["nike"], "#Nike"),
    (["under armour"], "#UnderArmour"),
    (["skechers"], "#Skechers"),
    (["columbia", "salomon", "merrell", "the north face"], "#Outdoor"),
    (["crocs", "havaianas", "lumberjack", "vans", "converse", "new balance", "reebok", "asics"], "#Ayakkabı"),
    (["tommy hilfiger", "calvin klein", "lacoste", "guess", "pierre cardin"], "#Moda"),
]

# Dengeli Kategori Öncelik Grupları:
# (Anahtar kelimeler, Kategori Başlığı, Kategori Hashtag'i, Kategori Emojisi, Öncelik Bonusu, Satıcı Amazon Zorunlu Mu?)
PRIORITY_CATEGORIES = [
    # 1. Popüler Teknoloji, Aksesuar & Oyuncu Ekipmanı (+255 Bonus — X'te en yüksek görüntülenme alan grup!)
    (
        [
            "kulaklık", "bluetooth hoparlör", "hoparlör", "powerbank", "şarj", "hızlı şarj", "kablo", "adaptör",
            "mouse", "oyuncu mouse", "klavye", "gamepad", "oyun kolu", "mikrofon", "webcam", "ssd", "taşınabilir ssd",
            "flash bellek", "hafıza kartı", "akıllı saat", "bileklik", "wifi", "router", "menzil genişletici",
            "anker", "soundcore", "baseus", "ugreen", "spigen", "xiaomi", "redmi", "jbl", "sony", "samsung",
            "logitech", "razer", "hyperx", "steelseries", "corsair", "sandisk", "kingston", "crucial", "lego"
        ],
        "TEKNOLOJİ & EKİPMAN FIRSATI", "#Teknoloji", "⚡", 255, False
    ),
    # 2. Yüksek Komisyon (%8-%10): Giyim, Tişört, Pantolon & Spor Ayakkabı (+255 Bonus)
    (
        [
            "tişört", "t-shirt", "tshirt", "polo yaka", "pantolon", "jean", "kot", "eşofman", "sweatshirt", "kapüşonlu",
            "gömlek", "kazak", "hırka", "şort", "mont", "ceket", "yelek", "elbise", "pijama", "boxer",
            "ayakkabı", "sneaker", "koşu ayakkabısı", "spor ayakkabı", "terlik", "sandalet", "bot ",
            "jack & jones", "jack jones", "defacto", "koton", "levi's", "levis", "mavi", "u.s. polo",
            "puma", "adidas", "nike", "under armour", "skechers", "crocs", "lumberjack", "vans", "new balance", "columbia", "salomon", "tommy hilfiger", "calvin klein"
        ],
        "MODA & GİYİM FIRSATI", "#Moda", "👕", 255, False
    ),
    # 3. Mutfak, Termos, Kahve Makinesi & Ev Aletleri (+255 Bonus)
    (
        [
            "termos", "stanley", "brita", "su arıtma", "tava", "tencere", "düdüklü", "saklama kabı", "bıçak", "kesme tahtası",
            "kahve makinesi", "espresso makinesi", "çaycı", "su ısıtıcısı", "kettle", "airfryer", "fritöz", "blender", "mikser", "tost makinesi", "ütü",
            "tefal", "karaca", "zwilling", "wmf", "paşabahçe", "borcam", "karcher", "kärcher", "cam temizleme", "süpürge", "philips", "oneblade",
            "bosch", "makita", "einhell", "matkap", "vidalama", "takım çantası"
        ],
        "MUTFAK & EV FIRSATI", "#Mutfak", "🍳", 255, False
    ),
    # 4. Deterjan, Bulaşık Tableti & Ev Temizliği (+240 Bonus | Satıcı Amazon.com.tr Zorunlu!)
    (
        [
            "bulaşık", "deterjan", "kapsül", "tablet", "çamaşır", "yumuşatıcı", "leke çıkarıcı",
            "finish", "fairy", "pril", "ariel", "persil", "perwoll", "omo", "bingo", "domestos", "asperox", "cif", "vanish", "vernel", "yumoş",
            "tuvalet kağıdı", "kağıt havlu", "selpak", "solo", "familia", "papia"
        ],
        "MARKET & TEMİZLİK FIRSATI", "#Marketİndirimi", "🧼", 240, True
    ),
    # 5. Kahve, Çay & Süpermarket (+235 Bonus | Satıcı Amazon.com.tr Zorunlu!)
    (
        [
            "kahve", "espresso", "filtre kahve", "çekirdek kahve", "granül kahve", "kapsül kahve",
            "jacobs", "tchibo", "mehmet efendi", "nescafe", "nescafé", "julius meinl", "lavazza", "illy", "starbucks",
            "çay", "çaykur", "caykur", "lipton", "nutella", "fındık kreması", "zeytinyağı", "makarna", "barilla",
            "çikolata", "yulaf", "bal ", "ton balığı"
        ],
        "MARKET & KAHVE FIRSATI", "#Marketİndirimi", "☕", 235, True
    ),
    # 6. Kişisel Bakım & Cilt Bakımı (+225 Bonus | Satıcı Amazon.com.tr Zorunlu!)
    (
        [
            "şampuan", "diş macunu", "diş fırçası", "deodorant", "roll-on", "tıraş", "jilet",
            "gillette", "oral-b", "nivea", "head & shoulders", "pantene", "elidor", "clear", "sensodyne", "colgate", "listerine",
            "cerave", "la roche", "bioderma", "nemlendirici", "güneş kremi", "yüz yıkama", "serum", "dove", "rexona", "bebek bezi", "sleepy", "prima"
        ],
        "KİŞİSEL BAKIM FIRSATI", "#İndirim", "🧴", 225, True
    ),
]


def clean_product_title(raw_title: str) -> str:
    """Başlıktaki ', Stark' gibi gereksiz kelime tekrarlarını temizler."""
    t = html.unescape(raw_title or "").strip()
    t = re.sub(r'\s+', ' ', t)
    if "," in t:
        parts = [p.strip() for p in t.split(",") if p.strip()]
        if len(parts) >= 2 and parts[-1].lower() in parts[0].lower():
            t = ", ".join(parts[:-1])
    return t


def extract_brand_key(title: str) -> str:
    """
    Ürünün marka anahtarını çıkarır (Son 8 paylaşımda aynı markanın tekrar paylaşılmasını engellemek için!).
    Örn: 'Julius Meinl Präsident...' -> 'julius meinl', 'ASUS ROG Strix...' -> 'asus'
    """
    t_low = clean_product_title(title).lower()
    known_multi = [
        "julius meinl", "kahve dünyası", "kahve dunyasi", "mehmet efendi", "jack & jones", "jack and jones", "jack jones",
        "under armour", "new balance", "the north face", "tommy hilfiger", "calvin klein", "u.s. polo", "us polo",
        "la roche", "head & shoulders", "oral-b", "oral b", "tp-link", "levi's", "levis"
    ]
    for km in known_multi:
        if km in t_low:
            return km.replace("and", "&").replace("dunyasi", "dünyası")

    for kw_list, _ in BRAND_HASHTAG_MAP:
        for kw in kw_list:
            kw_clean = kw.strip()
            if len(kw_clean) >= 3 and kw_clean in t_low:
                return kw_clean

    words = re.findall(r'[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+', t_low)
    if words:
        return words[0][:15]
    return "genel"


def get_recent_post_constraints(history_list: list = None) -> Dict:
    """
    Son paylaşımları analiz ederek:
    - Son 8 paylaşımda kullanılan markaları (recent_brands) -> Tekrar paylaşılması YASAK!
    - Son paylaşımın kategorisini (last_category) -> Üst üste aynı kategoriye ceza!
    döndürür.
    """
    if history_list is None:
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    history_list = json.load(f)
            except Exception:
                history_list = []
        else:
            history_list = []

    posted = [h for h in (history_list or []) if isinstance(h, dict) and h.get("title")]
    last_8 = posted[-8:]
    recent_brands: Set[str] = set()
    for item in last_8:
        b_key = extract_brand_key(item.get("title", ""))
        if b_key and b_key != "genel":
            recent_brands.add(b_key)

    last_cat = posted[-1].get("category", "") if posted else ""
    prev_cat = posted[-2].get("category", "") if len(posted) >= 2 else ""
    return {
        "recent_brands": recent_brands,
        "last_category": last_cat,
        "prev_category": prev_cat,
    }


def is_basket_filler_item(title: str, cur_val: float) -> bool:
    """
    Ürünün 'Ana Tweet (Vitrin)' yerine 'Yorumdaki 2. Link (Kasa Yanı Sepet Tamamlayıcı)' olup olmadığını belirler.
    - Diş ipi, sıvı sabun, ruj, soğuk çay, peçete, bisküvi vb. ürünler her zaman Basket Filler'dır.
    - Ayrıca 140 TL altındaki küçük market/bakım ürünleri (eğer Anker/Ugreen/Spigen/Xiaomi/Logitech değilse) Basket Filler'dır.
    """
    t_low = title.lower()
    if any(bf in t_low for bf in BASKET_FILLER_KEYWORDS):
        return True
    if cur_val < 140.0 and not any(hb in t_low for hb in ["anker", "ugreen", "spigen", "baseus", "xiaomi", "logitech", "sandisk", "kingston", "philips", "bosch", "stanley", "puma", "adidas", "jack & jones", "levis"]):
        return True
    return False


def attach_affiliate_link(url: str) -> str:
    if not url:
        return ""
    tag = config.AMAZON_AFFILIATE_TAG or "firsatrada050-21"
    clean_base = url.split("?")[0]
    return f"{clean_base}?tag={tag}"


def parse_price(price_str: str) -> float:
    if not price_str:
        return 0.0
    s = re.sub(r'[^0-9,\.]', '', price_str).strip()
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except Exception:
        return 0.0


def format_tl(val: float) -> str:
    if val <= 0:
        return ""
    iv = int(round(val))
    return f"{iv:,}".replace(",", ".") + " TL"


def extract_brand_hashtag(title_low: str, fallback_tag: str = "#İndirim") -> str:
    for kw_list, b_tag in BRAND_HASHTAG_MAP:
        for kw in kw_list:
            if kw in title_low:
                return b_tag
    return fallback_tag


def calculate_unit_price_info(title: str, cur_val: float, core_price_text: str = "") -> Dict:
    """
    Ürünün adet / yıkama / kapsül / kg başına birim fiyatını hesaplar ve
    gerçekten zincir marketlerden (BİM/Migros/A101) ucuz olup olmadığını denetler!
    """
    t_low = title.lower()
    unit_price_val = 0.0
    unit_label = ""

    patterns = [
        (r'(\d+)\s*yıkama', "Yıkaması"),
        (r'(\d+)\s*(?:kapsül|tablet)', "Kapsülü"),
        (r'(\d+)\s*(?:\'li|\'lu|\'lü|\'lı|li\s+set|lü\s+set|lu\s+set|lı\s+set|li\s+paket|lü\s+paket)', "Tanesi"),
        (r'(\d+)\s*adet', "Tanesi"),
    ]
    for pat, label in patterns:
        m = re.search(pat, t_low)
        if m:
            cnt = int(m.group(1))
            if 2 <= cnt <= 200:
                unit_price_val = round(cur_val / cnt, 2)
                unit_label = label
                break

    if not unit_price_val and core_price_text:
        m_amz = re.search(r'([0-9]+,[0-9]{2})\s*TL\s*/\s*(adet|parça|yıkama|kg|l\b)', core_price_text.lower())
        if m_amz:
            u_val = parse_price(m_amz.group(1))
            u_type = m_amz.group(2)
            if 0 < u_val < cur_val:
                unit_price_val = u_val
                unit_label = "Kapsülü" if "bulaşık" in t_low else ("Kg Fiyatı" if u_type == "kg" else "Tanesi")

    unit_str = ""
    if unit_price_val > 0:
        u_fmt = f"{unit_price_val:.2f}".replace(".", ",").replace(",00", "")
        unit_str = f"{unit_label} Sadece {u_fmt} TL!"

    is_truly_market_cheaper = False
    if any(k in t_low for k in ["bulaşık", "finish", "fairy", "pril", "bingo", "asperox"]):
        if 0 < unit_price_val <= 5.80:
            is_truly_market_cheaper = True
    elif any(k in t_low for k in ["kahve", "jacobs", "tchibo", "mehmet efendi", "nescafe", "çaykur", "lipton", "nutella", "ariel", "perwoll", "omo"]):
        is_truly_market_cheaper = True

    return {
        "unit_price_val": unit_price_val,
        "unit_str": unit_str,
        "is_truly_market_cheaper": is_truly_market_cheaper
    }


def detect_viral_profile(
    title: str,
    disc_percent: int,
    savings_tl: float,
    cur_val: float,
    rating: float = 0.0,
    is_amazon_seller: bool = True,
    constraints: Dict = None
) -> dict:
    t_low = title.lower()
    cat_label = "GÜNÜN FIRSATI"
    cat_tag = "#İndirim"
    cat_emoji = "🔥"
    cat_bonus = 70
    require_amazon_seller = False

    for keywords, label, tag, emoji, bonus, req_amz in PRIORITY_CATEGORIES:
        if any(kw in t_low for kw in keywords):
            cat_label = label
            cat_tag = tag
            cat_emoji = emoji
            cat_bonus = bonus
            require_amazon_seller = req_amz
            break

    brand_tag = extract_brand_hashtag(t_low, fallback_tag=cat_tag)
    brand_key = extract_brand_key(title)
    basket_filler = is_basket_filler_item(title, cur_val)
    is_hero_brand = any(hb in t_low for hb in HERO_SEARCH_BRANDS)

    # Alım Gücü Bandı Bonusu (Vitrin ürünleri için en tatlı bant 180 TL - 2.200 TL arası!)
    if 180 <= cur_val <= 1450:
        price_tier_bonus = 195
    elif 1450 < cur_val <= 2600:
        price_tier_bonus = 155
    elif 45 <= cur_val < 180:
        price_tier_bonus = 130
    elif 2600 < cur_val <= MAX_PRICE_TL:
        price_tier_bonus = 65
    else:
        price_tier_bonus = -500

    # Vitrin Mıknatısı (X'te Çok Aranan Marka) Bonusu
    hero_bonus = 175 if is_hero_brand else 0

    # Eğer ürün Kasa Yanı (Diş ipi, sıvı sabun, ruj, soğuk çay vb.) ise Ana Tweet puanını düşür, 2. Link havuzuna ayır!
    filler_penalty = -380 if basket_filler else 0
    if cur_val > 750 and any(acc in t_low for acc in ["kartlık", "cüzdan", "anahtarlık", "cc holder", "card holder"]):
        filler_penalty -= 180

    # Marka & Kategori Tekrar Kilidi (Anti-Spam)
    brand_cooldown_penalty = 0
    cat_rotation_penalty = 0
    is_brand_on_cooldown = False
    if constraints:
        recent_brands = constraints.get("recent_brands", set())
        if brand_key in recent_brands:
            is_brand_on_cooldown = True
            brand_cooldown_penalty = -750
        last_cat = constraints.get("last_category", "")
        prev_cat = constraints.get("prev_category", "")
        if last_cat and cat_label == last_cat:
            cat_rotation_penalty = -210
        elif prev_cat and cat_label == prev_cat:
            cat_rotation_penalty = -80

    discount_score = disc_percent * 4
    rating_bonus = int((rating - 4.0) * 50) if rating >= 4.0 else 0
    seller_bonus = 110 if is_amazon_seller else 0

    total_score = (
        100
        + cat_bonus
        + price_tier_bonus
        + hero_bonus
        + filler_penalty
        + brand_cooldown_penalty
        + cat_rotation_penalty
        + discount_score
        + rating_bonus
        + seller_bonus
    )
    return {
        "category": cat_label,
        "category_tag": cat_tag,
        "category_emoji": cat_emoji,
        "brand_tag": brand_tag,
        "brand_key": brand_key,
        "is_hero_brand": is_hero_brand,
        "is_basket_filler": basket_filler,
        "is_brand_on_cooldown": is_brand_on_cooldown,
        "require_amazon_seller": require_amazon_seller,
        "virality_score": total_score
    }


def verify_product_page_price(page, deal: Dict, price_db: Dict[str, Dict] = None, constraints: Dict = None) -> Optional[Dict]:
    """
    Ürünün kendi Amazon sayfasına (/dp/ASIN) girerek gerçek fiyatı, satıcıyı,
    Fiyat Hafızasını, 30/60/90/365 gün dip fiyat damgasını, birim fiyatı ve puanı doğrular.
    """
    url = deal["link"].split("?")[0]
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1350)

        low_stock_badge = ""
        avail_el = page.locator("#availability").first
        if avail_el.count():
            avail_txt = avail_el.inner_text().strip()
            avail_low = avail_txt.lower()
            if "mevcut değil" in avail_low or "stokta yok" in avail_low:
                print(f"  ❌ [Elendi - Stok Yok]: {deal['title'][:40]}")
                return None
            m_st = re.search(r'stokta sadece (\d+) adet kald', avail_low)
            if m_st:
                low_stock_badge = f"Son {m_st.group(1)} Adet Stok!"

        title_el = page.locator("span#productTitle").first
        if title_el.count():
            real_title = clean_product_title(title_el.inner_text())
            if len(real_title) > 8:
                deal["title"] = real_title

        t_low = deal["title"].lower()
        if any(b_kw in t_low for b_kw in BANNED_KEYWORDS):
            print(f"  ❌ [Elendi - Yasaklı Kategori (Su/Soda)]: {deal['title'][:40]}")
            return None

        seller_txt = ""
        for m_sel in ["#merchantInfoFeature_feature_div", "#merchant-info", "#tabular-buybox"]:
            mloc = page.locator(m_sel).first
            if mloc.count():
                seller_txt += " " + mloc.inner_text().strip()
        is_amazon_seller = ("amazon.com.tr" in seller_txt.lower())

        real_cur_val = 0.0
        core_price_text = ""
        core_div = page.locator("#corePriceDisplay_desktop_feature_div").first
        if core_div.count():
            core_price_text = core_div.inner_text().replace("\xa0", " ").strip()

        for sel in [
            "#corePriceDisplay_desktop_feature_div .priceToPay",
            "#corePriceDisplay_desktop_feature_div .apexPriceToPay",
            "#corePrice_feature_div .a-price",
            "#apex_desktop .a-price"
        ]:
            loc = page.locator(sel).first
            if loc.count():
                raw_txt = loc.inner_text().strip().replace("\n", "")
                val = parse_price(raw_txt)
                if val > 0:
                    real_cur_val = val
                    break

        if real_cur_val <= 0:
            print(f"  ❌ [Elendi - Ürün Sayfasında Fiyat Yok]: {deal['title'][:40]}")
            return None

        if real_cur_val > MAX_PRICE_TL:
            print(f"  ❌ [Elendi - Pahalı Ürün ({format_tl(real_cur_val)} > {format_tl(MAX_PRICE_TL)})]: {deal['title'][:40]}")
            return None

        real_old_val = 0.0
        for old_sel in [
            "#corePriceDisplay_desktop_feature_div .basisPrice .a-offscreen",
            "#corePriceDisplay_desktop_feature_div .basisPrice",
            "#apex_desktop .a-text-price .a-offscreen",
            "#apex_desktop .a-text-price"
        ]:
            oloc = page.locator(old_sel).first
            if oloc.count():
                otxt = oloc.inner_text().strip().split("\n")[0]
                oval = parse_price(otxt)
                if oval > real_cur_val:
                    real_old_val = oval
                    break

        if real_old_val <= real_cur_val:
            print(f"  ❌ [Elendi - Ürün Sayfasında İndirim Yok ({format_tl(real_cur_val)})]: {deal['title'][:45]}")
            return None

        real_disc = int(round((real_old_val - real_cur_val) / real_old_val * 100))
        if not (MIN_DISCOUNT_PERCENT <= real_disc <= 85):
            print(f"  ❌ [Elendi - Gerçek İndirim Yetersiz (%{real_disc})]: {deal['title'][:45]}")
            return None

        asin = deal.get("asin") or ""
        mem_info = {"is_fake_markup": False, "dropped_from_memory": False}
        if price_db is not None and asin:
            mem_info = check_and_record_price_memory(price_db, asin, real_cur_val, deal["title"])
            if mem_info["is_fake_markup"]:
                print(f"  ❌ [Elendi - Sahte İndirim Yakalandı! Radar Hafızasında {format_tl(mem_info['prev_min'])} İdi, Şimdi {format_tl(real_cur_val)}]: {deal['title'][:40]}")
                return None

        lowest_days = deal.get("deal_info", {}).get("lowest_days", 0)
        try:
            m_low = re.search(r'(\d+)\s*günün en düşük fiyat', core_price_text.lower())
            if m_low:
                lowest_days = max(lowest_days, int(m_low.group(1)))
            elif "en düşük fiyat" in core_price_text.lower():
                lowest_days = max(lowest_days, 30)
        except Exception:
            pass

        official_low_badge = ""
        if lowest_days >= 180:
            official_low_badge = f"Son {lowest_days} Günün En Düşük Fiyatı!"
        elif lowest_days >= 60:
            official_low_badge = f"Son {lowest_days} Günün Dip Fiyatı!"
        elif lowest_days >= 30:
            official_low_badge = "Son 30 Günün En Düşük Fiyatı!"

        rating_val = 0.0
        rating_str = ""
        reviews_str = ""
        try:
            pop = page.locator("#acrPopover").first
            if pop.count():
                r_txt = (pop.get_attribute("title") or pop.inner_text() or "").strip()
                m_r = re.search(r'([0-9][,\.][0-9])', r_txt)
                if m_r:
                    rating_val = float(m_r.group(1).replace(",", "."))
                    rating_str = f"{rating_val:.1f}/5"
            rev_el = page.locator("#acrCustomerReviewText").first
            if rev_el.count():
                rv_raw = rev_el.inner_text().strip()
                m_rv = re.search(r'([0-9\.,]+)', rv_raw)
                if m_rv:
                    reviews_str = m_rv.group(1)
        except Exception:
            pass

        if 0 < rating_val < MIN_RATING:
            print(f"  ❌ [Elendi - Düşük Yıldız Puanı ({rating_val}/5)]: {deal['title'][:45]}")
            return None

        real_savings = real_old_val - real_cur_val
        viral = detect_viral_profile(
            deal["title"],
            real_disc,
            real_savings,
            real_cur_val,
            rating=rating_val,
            is_amazon_seller=is_amazon_seller,
            constraints=constraints
        )

        if viral["require_amazon_seller"] and not is_amazon_seller:
            print(f"  ❌ [Elendi - Market Ürününde Satıcı Amazon.com.tr Değil]: {deal['title'][:45]}")
            return None

        unit_info = calculate_unit_price_info(deal["title"], real_cur_val, core_price_text=core_price_text)
        unit_str = unit_info["unit_str"]
        is_truly_market_cheaper = unit_info["is_truly_market_cheaper"] and is_amazon_seller and real_disc >= 18

        sales_badge = ""
        try:
            sp_el = page.locator("#social-proofing-faceout-title-tk_bought").first
            if sp_el.count():
                sp_txt = sp_el.inner_text().replace("\xa0", " ").strip()
                m_sp = re.search(r'([0-9\.,]+\s*B?\+?)', sp_txt)
                if m_sp:
                    sales_badge = f"Geçen ay {m_sp.group(1).strip()}+ satıldı"
                elif "satın alındı" in sp_txt.lower():
                    sales_badge = sp_txt
            if not sales_badge:
                bs_el = page.locator(".p13n-best-seller-badge, #zeitgeistBadge_feature_div").first
                if bs_el.count() and "çok satan" in bs_el.inner_text().lower():
                    sales_badge = "Amazon Çok Satan #1"
        except Exception:
            pass

        coupon_text = ""
        try:
            cp_el = page.locator("#promoPriceBlockMessage_feature_div, .promoPriceBlockMessage").first
            if cp_el.count():
                cp_raw = cp_el.inner_text().replace("\xa0", " ").strip()
                m_nakit = re.search(r'(\d+\s*TL\'?lik\s*Alışverişe\s*\d+\s*TL\s*Nakit\s*İade)', cp_raw, re.I)
                m_coklu = re.search(r'(\d+\s*TL\s*seçili\s*ürün\s*satın\s*aldığınızda\s*%\d+\s*tasarruf)', cp_raw, re.I)
                m_alode = re.search(r'(\d+\s*al\s*\d+\s*öde)', cp_raw, re.I)
                if m_nakit:
                    coupon_text = f"Ek Kampanya: {m_nakit.group(1)}"
                elif m_alode:
                    coupon_text = f"Çoklu Alım: {m_alode.group(1).upper()}"
                elif m_coklu:
                    coupon_text = "Çoklu Alımda Sepette +%10 Ek İndirim!"
                elif "kupon" in cp_raw.lower():
                    coupon_text = "Sayfada Ek Kupon İndirimi Var!"
        except Exception:
            pass

        try:
            main_img = page.locator("#landingImage").first
            if main_img.count():
                hi_res = main_img.get_attribute("data-old-hires") or main_img.get_attribute("src") or ""
                if hi_res and hi_res.startswith("http"):
                    deal["image_url"] = hi_res
        except Exception:
            pass

        clean_cur_price = format_tl(real_cur_val)
        clean_old_price = format_tl(real_old_val)
        savings_str = format_tl(real_savings)

        if sales_badge:
            viral["virality_score"] += 45
        if coupon_text:
            viral["virality_score"] += 40
        if unit_str:
            viral["virality_score"] += 35
        if is_truly_market_cheaper:
            viral["virality_score"] += 60
        if lowest_days >= 180:
            viral["virality_score"] += 185
        elif lowest_days >= 90:
            viral["virality_score"] += 135
        elif lowest_days >= 30:
            viral["virality_score"] += 95
        if mem_info.get("dropped_from_memory"):
            viral["virality_score"] += 70
        # Pahalı kartlık/cüzdan/anahtarlık (>750 TL) yerine geniş kitle ürünü (mont, ayakkabı, termos, teknoloji) önceliklendir
        if real_cur_val > 750 and any(acc in t_low for acc in ["kartlık", "cüzdan", "anahtarlık", "cc holder", "card holder"]):
            viral["virality_score"] -= 180

        deal["virality_score"] = viral["virality_score"]
        deal["cur_val"] = real_cur_val
        deal["summary"] = f"{deal['title']} Amazon Türkiye'de %{real_disc} indirimle {clean_cur_price} fiyata düştü."
        deal["deal_info"].update({
            "category": viral["category"],
            "category_tag": viral["category_tag"],
            "category_emoji": viral["category_emoji"],
            "brand_tag": viral["brand_tag"],
            "brand_key": viral["brand_key"],
            "is_hero_brand": viral["is_hero_brand"],
            "is_basket_filler": viral["is_basket_filler"],
            "is_brand_on_cooldown": viral["is_brand_on_cooldown"],
            "price": clean_cur_price,
            "price_val": real_cur_val,
            "old_price": clean_old_price,
            "savings_tl": int(round(real_savings)),
            "savings_str": savings_str,
            "discount": f"-%{real_disc}",
            "discount_percent": real_disc,
            "rating_str": rating_str,
            "reviews_str": reviews_str,
            "sales_badge": low_stock_badge or sales_badge,
            "coupon_text": coupon_text,
            "unit_str": unit_str,
            "is_amazon_seller": is_amazon_seller,
            "is_truly_market_cheaper": is_truly_market_cheaper,
            "lowest_days": lowest_days,
            "official_low_badge": official_low_badge,
        })
        role_tag = "🛒 [2. Link / Kasa Yanı]" if viral["is_basket_filler"] else "🌟 [Vitrin Adayı]"
        extra = f" | {unit_str}" if unit_str else ""
        if official_low_badge:
            extra += f" | 🏆 {official_low_badge}"
        elif rating_str:
            extra += f" | ⭐ {rating_str}"
        print(f"  ✅ {role_tag} [{deal['virality_score']} Puan]: {deal['title'][:34]} | {clean_old_price} -> {clean_cur_price} (-%{real_disc}){extra}")
        return deal
    except Exception as e:
        print(f"  ⚠️ Ürün doğrulama hatası ({url}): {e}")
        return None


def collect_cards_from_page(
    page,
    seen_asins: set,
    posted_slugs: set,
    raw_candidates: list,
    forced_hint: str = "",
    price_db: Dict[str, Dict] = None,
    constraints: Dict = None
):
    """Sayfadaki üstü çizili indirimli ürün kartlarını tarayıp uygun fiyatlı adayları havuza ekler."""
    strike_els = page.locator('.a-price[data-a-strike="true"]').all()
    added = 0
    for s_el in strike_els:
        try:
            parent = s_el.locator('xpath=ancestor::div[@data-asin and string-length(@data-asin)=10]').first
            if not parent.count():
                parent = s_el.locator('xpath=ancestor::div[@data-testid="product-card" or contains(@class, "ProductCard") or contains(@class, "DealCard") or contains(@class, "DealGridItem") or contains(@class, "a-cardui")]').first
            if not parent.count():
                parent = s_el.locator('xpath=ancestor::div[4]')

            item_text = parent.inner_text().strip()

            old_price_raw = s_el.inner_text().strip().split("\n")[0]
            cur_price_el = parent.locator('.a-price:not([data-a-strike="true"])').first
            cur_price_raw = cur_price_el.inner_text().strip().split("\n")[0] if cur_price_el.count() else ""

            old_val = parse_price(old_price_raw)
            cur_val = parse_price(cur_price_raw)

            if old_val > cur_val > 0:
                disc_percent = int(round((old_val - cur_val) / old_val * 100))
                savings_tl = max(0.0, old_val - cur_val)
            else:
                continue

            if cur_val > MAX_PRICE_TL or cur_val < 35.0:
                continue

            if not (MIN_DISCOUNT_PERCENT <= disc_percent <= 85):
                continue

            asin = parent.get_attribute("data-asin") if parent.count() else None
            if not asin or len(asin) != 10:
                link_el = parent.locator('a[href*="/dp/"]').first
                if not link_el.count():
                    continue
                href = link_el.get_attribute("href") or ""
                asin_match = re.search(r'/dp/([A-Z0-9]{10})', href)
                asin = asin_match.group(1) if asin_match else None

            if not asin or asin in seen_asins:
                continue

            lowest_days = 0
            m_low = re.search(r'(\d+)\s*günün en düşük fiyat', item_text.lower())
            if m_low:
                lowest_days = int(m_low.group(1))
            elif "en düşük fiyat" in item_text.lower() or "30-day-low" in forced_hint:
                lowest_days = 30

            h2_el = parent.locator("h2").first
            if h2_el.count() and len(h2_el.inner_text().strip()) > 10:
                prod_title = clean_product_title(h2_el.inner_text().strip())
            else:
                lines = [
                    l.strip() for l in item_text.split("\n")
                    if l.strip() and len(l.strip()) > 14
                    and "%" not in l and "TL" not in l
                    and "gün" not in l.lower() and "fırsat" not in l.lower()
                    and "çok satan" not in l.lower()
                ]
                prod_title = clean_product_title(lines[0]) if lines else f"Amazon {forced_hint} Ürünü".strip()

            if any(b_kw in prod_title.lower() for b_kw in BANNED_KEYWORDS):
                continue

            if price_db is not None:
                mem = check_and_record_price_memory(price_db, asin, cur_val, prod_title)
                if mem["is_fake_markup"]:
                    continue

            seen_asins.add(asin)

            clean_url = f"https://www.amazon.com.tr/dp/{asin}"
            affiliate_url = attach_affiliate_link(clean_url)

            img_el = parent.locator("img").first
            img_src = img_el.get_attribute("src") if img_el.count() else ""
            if not img_src or "data:image" in img_src:
                continue
            hd_img = re.sub(r'\._AC_SR\d+,\d+_\.', '._AC_SL1500_.', img_src)
            hd_img = re.sub(r'\._AC_UL\d+_SR\d+,\d+_\.', '._AC_SL1500_.', hd_img)

            slug = re.sub(r'[^a-zA-Z0-9]+', '-', prod_title.lower()).strip('-')[:50]
            if not slug or "amazon-" in slug:
                slug = f"amazon-deal-{asin.lower()}"

            if slug in posted_slugs or any(asin.lower() in s.lower() for s in posted_slugs if s):
                continue

            viral = detect_viral_profile(
                f"{prod_title} {forced_hint}",
                disc_percent,
                savings_tl,
                cur_val,
                constraints=constraints
            )
            if lowest_days >= 90:
                viral["virality_score"] += 110
            elif lowest_days >= 30:
                viral["virality_score"] += 75

            clean_cur_price = format_tl(cur_val)
            clean_old_price = format_tl(old_val)
            savings_str = format_tl(savings_tl)

            raw_candidates.append({
                "asin": asin,
                "title": prod_title,
                "cur_val": cur_val,
                "summary": f"{prod_title} Amazon Türkiye'de %{disc_percent} indirimle {clean_cur_price} fiyata düştü.",
                "link": affiliate_url,
                "image_url": hd_img,
                "virality_score": viral["virality_score"],
                "slug": slug,
                "deal_info": {
                    "store": "AMAZON TR",
                    "store_emoji": "🛒",
                    "category": viral["category"],
                    "category_tag": viral["category_tag"],
                    "category_emoji": viral["category_emoji"],
                    "category_color": "#F59E0B",
                    "brand_tag": viral["brand_tag"],
                    "brand_key": viral["brand_key"],
                    "is_hero_brand": viral["is_hero_brand"],
                    "is_basket_filler": viral["is_basket_filler"],
                    "is_brand_on_cooldown": viral["is_brand_on_cooldown"],
                    "price": clean_cur_price,
                    "price_val": cur_val,
                    "old_price": clean_old_price,
                    "savings_tl": int(round(savings_tl)),
                    "savings_str": savings_str,
                    "discount": f"-%{disc_percent}",
                    "discount_percent": disc_percent,
                    "rating_str": "",
                    "reviews_str": "",
                    "sales_badge": "",
                    "coupon_text": "",
                    "unit_str": "",
                    "is_amazon_seller": True,
                    "is_truly_market_cheaper": False,
                    "lowest_days": lowest_days,
                    "official_low_badge": "",
                }
            })
            added += 1
        except Exception:
            continue
    return added


def pick_primary_and_second_deal(verified_list: List[Dict], constraints: Dict = None) -> tuple:
    """
    Süpermarket Vitrini Seçicisi:
    - 1. Ürün (Ana Tweet / Vitrin):
      * ASLA Kasa Yanı (diş ipi, sıvı sabun, ruj, soğuk çay vb.) olamaz!
      * Son 8 paylaşımda kullanılan markalardan (is_brand_on_cooldown) olamaz!
      * En yüksek puanlı Vitrin Ürünü seçilir.
    - 2. Ürün (İlk Yorumdaki Çapraz Satış & Görsel Alt Şerit):
      * Öncelikle 50-300 TL arası Kasa Yanı / Sepet Tamamlayıcı (veya farklı kategoriden ucuz) fırsat seçilir!
    """
    if not verified_list:
        return None, None

    hero_candidates = [
        d for d in verified_list
        if not d["deal_info"].get("is_basket_filler")
        and not d["deal_info"].get("is_brand_on_cooldown")
    ]
    if not hero_candidates:
        hero_candidates = [d for d in verified_list if not d["deal_info"].get("is_basket_filler")]
    if not hero_candidates:
        hero_candidates = verified_list

    hero_candidates.sort(key=lambda x: x.get("virality_score", 0), reverse=True)
    primary = hero_candidates[0]
    p_slug = primary.get("slug")
    p_brand = primary["deal_info"].get("brand_key", "")
    p_cat = primary["deal_info"].get("category", "")

    others = [
        d for d in verified_list
        if d.get("slug") != p_slug and d["deal_info"].get("brand_key") != p_brand
    ]
    if not others:
        others = [d for d in verified_list if d.get("slug") != p_slug]
    if not others:
        return primary, None

    # 2. Fırsat için öncelik: Kasa yanı / ucuz sepet tamamlayıcı (<= 350 TL) ürünler!
    cheap_fillers = [
        d for d in others
        if d["deal_info"].get("is_basket_filler") or float(d["deal_info"].get("price_val", 9999)) <= 350.0
    ]
    if cheap_fillers:
        cheap_fillers.sort(key=lambda x: x["deal_info"].get("discount_percent", 0), reverse=True)
        return primary, cheap_fillers[0]

    diff_cat = [d for d in others if d["deal_info"].get("category") != p_cat]
    if diff_cat:
        return primary, diff_cat[0]
    return primary, others[0]


def pick_complementary_second_deal(primary_deal: Dict, verified_list: List[Dict]) -> Optional[Dict]:
    """Geriye dönük uyumluluk için 2. fırsat seçici."""
    _, second = pick_primary_and_second_deal([primary_deal] + [d for d in verified_list if d.get("slug") != primary_deal.get("slug")])
    return second


def build_balanced_verification_queue(raw_candidates: List[Dict]) -> List[Dict]:
    """
    Ürün sayfasına (/dp/ASIN) girilecek aday kuyruğunu çeşitlendirir:
    - Aynı markadan en fazla 1 Vitrin adayı, aynı kategoriden en fazla 3 Vitrin adayı alır (İlk 11 sıra).
    - Son 4 sıraya ise özellikle 50-300 TL arası 'Sepet Tamamlayıcı (2. Link)' adaylarını koyar.
    """
    sorted_all = sorted(raw_candidates, key=lambda x: x.get("virality_score", 0), reverse=True)
    hero_queue = []
    filler_queue = []
    used_brands = set()
    cat_counts = {}

    for cand in sorted_all:
        info = cand.get("deal_info", {})
        b_key = info.get("brand_key", "genel")
        cat = info.get("category", "GENEL")
        is_filler = info.get("is_basket_filler", False)
        on_cd = info.get("is_brand_on_cooldown", False)

        if is_filler:
            if len(filler_queue) < 4 and b_key not in used_brands:
                filler_queue.append(cand)
                used_brands.add(b_key)
            continue

        if on_cd:
            continue

        if b_key in used_brands:
            continue
        if cat_counts.get(cat, 0) >= 3:
            continue

        hero_queue.append(cand)
        used_brands.add(b_key)
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if len(hero_queue) >= 11:
            break

    # Eğer hero_queue az kaldıysa kalanlardan tamamla
    if len(hero_queue) < 6:
        for cand in sorted_all:
            if cand not in hero_queue and cand not in filler_queue:
                hero_queue.append(cand)
                if len(hero_queue) >= 8:
                    break

    return hero_queue + filler_queue[:4]


def fetch_live_amazon_deals(posted_slugs: set = None, history: list = None) -> List[Dict]:
    """
    Amazon Türkiye'den Goldbox Kategori Balonları + Teknoloji, Moda, Mutfak, Market ve Temizlik
    kategorilerini tarar; Vitrin Mıknatısı (1. Ürün) ve Kasa Yanı (2. Ürün) adaylarını doğrular.
    """
    raw_candidates = []
    verified_deals = []
    seen_asins = set()
    posted_slugs = posted_slugs or set()
    price_db = load_price_db()
    constraints = get_recent_post_constraints(history)

    if constraints["recent_brands"]:
        print(f"🛡️ [Anti-Spam Marka Kilidi] Son 8 paylaşımdaki markalar bloke edildi: {', '.join(sorted(constraints['recent_brands']))}")
    if constraints["last_category"]:
        print(f"🔄 [Kategori Rotasyonu] Son paylaşılan kategori: {constraints['last_category']} (Bu döngüde farklı kategoriye öncelik verilecek)")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="tr-TR",
                viewport={"width": 1400, "height": 900}
            )
            page = ctx.new_page()

            # 1. Goldbox Ana Sayfa + Resmi Kategori ve Dip Fiyat Balonları
            print("🛒 [1/5] Amazon TR Günün Fırsatları ve Kategori/Dip Fiyat Balonları taranıyor...")
            try:
                page.goto("https://www.amazon.com.tr/gp/goldbox", wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(2000)
                for _ in range(3):
                    collect_cards_from_page(page, seen_asins, posted_slugs, raw_candidates, price_db=price_db, constraints=constraints)
                    page.mouse.wheel(0, 1800)
                    page.wait_for_timeout(900)

                goldbox_bubbles = [
                    ("filter-bubble-deals-collection-30-day-low", "30-day-low"),
                    ("filter-bubble-deals-collection-electronics", "kulaklık teknoloji"),
                    ("filter-bubble-deals-collection-computers", "mouse klavye ssd"),
                    ("filter-bubble-deals-collection-kitchen", "mutfak termos"),
                    ("filter-bubble-deals-collection-fashion-apparel", "tişört pantolon giyim"),
                    ("filter-bubble-deals-collection-fashion-shoes", "spor ayakkabı"),
                    ("filter-bubble-deals-collection-grocery", "kahve market"),
                    ("filter-bubble-deals-collection-health-and-personal-care", "deterjan temizlik kişisel bakım"),
                    ("filter-bubble-deals-collection-deals-under-xx", "market mutfak"),
                ]
                for tid, hint in goldbox_bubbles:
                    btn = page.locator(f'button[data-testid="{tid}"]').first
                    if btn.count():
                        try:
                            btn.evaluate("el => el.click()")
                            page.wait_for_timeout(1350)
                            collect_cards_from_page(page, seen_asins, posted_slugs, raw_candidates, forced_hint=hint, price_db=price_db, constraints=constraints)
                            page.mouse.wheel(0, 1600)
                            page.wait_for_timeout(850)
                            collect_cards_from_page(page, seen_asins, posted_slugs, raw_candidates, forced_hint=hint, price_db=price_db, constraints=constraints)
                        except Exception:
                            pass
            except Exception as e:
                print(f"  ⚠️ Goldbox tarama uyarısı: {e}")

            # 2. Yüksek Görüntülenmeli Vitrin + Kasa Yanı Kategori Sayfaları
            CategorySources = [
                ("⚡ [2/5] Teknoloji, Oyuncu Ekipmanı & Aksesuar İndirimleri", "https://www.amazon.com.tr/s?i=computers&rh=p_n_pct-off-with-tax%3A15-&s=popularity-rank", "teknoloji aksesuar"),
                ("🍳 [3/5] Mutfak, Termos & Ev Gereçleri İndirimleri", "https://www.amazon.com.tr/s?i=kitchen&rh=p_n_pct-off-with-tax%3A15-&s=popularity-rank", "mutfak"),
                ("👕 [4/5] Moda, Giyim & Spor Ayakkabı İndirimleri", "https://www.amazon.com.tr/s?i=fashion&rh=p_n_pct-off-with-tax%3A20-&s=popularity-rank", "giyim ayakkabı"),
                ("☕ [5/5] Kahve, Deterjan & Süpermarket Çok Satanlar", "https://www.amazon.com.tr/s?i=grocery&s=popularity-rank", "kahve market"),
            ]
            for label, url, hint in CategorySources:
                print(f"{label} taranıyor...")
                try:
                    page.wait_for_timeout(750)
                    page.goto(url, wait_until="domcontentloaded", timeout=22000)
                    page.wait_for_timeout(1350)
                    collect_cards_from_page(page, seen_asins, posted_slugs, raw_candidates, forced_hint=hint, price_db=price_db, constraints=constraints)
                except Exception as e:
                    print(f"  ⚠️ {label} uyarısı: {e}")

            print(f"  • Toplam {len(raw_candidates)} adet uygun fiyatlı (<4.500 TL) aday fırsat bulundu (Fiyat Hafızası: {len(price_db)} ürün).")

            verification_queue = build_balanced_verification_queue(raw_candidates)
            print(f"🔍 Çeşitlendirilmiş {len(verification_queue)} adayın ürün sayfalarında (/dp/ASIN) satıcı, birim fiyat ve dip fiyat damgası doğrulanıyor...")

            hero_verified_count = 0
            filler_verified_count = 0
            for cand in verification_queue:
                verified = verify_product_page_price(page, cand, price_db=price_db, constraints=constraints)
                if verified:
                    verified_deals.append(verified)
                    if verified["deal_info"].get("is_basket_filler"):
                        filler_verified_count += 1
                    else:
                        hero_verified_count += 1
                    # En az 3 Vitrin Ürünü + 1 Kasa Yanı (veya toplam 5 doğrulanmış ürün) bulunca dur
                    if (hero_verified_count >= 3 and filler_verified_count >= 1) or len(verified_deals) >= 5:
                        break

            browser.close()
    except Exception as e:
        print(f"⚠️ Amazon Canlı Fırsat Motoru Hatası: {e}")

    save_price_db(price_db)
    verified_deals.sort(key=lambda x: x["virality_score"], reverse=True)
    return verified_deals


def fetch_deal_articles(feed_urls: List[str] = None, posted_slugs: set = None, history: list = None) -> List[Dict]:
    print("🛒 Amazon TR Vitrin (Teknoloji, Mutfak, Giyim) + Kasa Yanı (Market, Kahve, Temizlik) Fırsatları taranıyor...")
    deals = fetch_live_amazon_deals(posted_slugs=posted_slugs, history=history)
    print(f"  • Amazon TR'den ürün sayfasında birebir doğrulanmış {len(deals)} adet fırsat hazır.")
    return deals
