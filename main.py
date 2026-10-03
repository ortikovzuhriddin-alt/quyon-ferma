import os
import io
import json
import sqlite3
from datetime import datetime
from aiohttp import web
import aiohttp_cors
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import google.generativeai as genai

# --- SOZLAMALAR ---
BOT_TOKEN = "8863745035:AAE8g1tqu8VFzP4EuHhb-wtoRkzdqaFcQKs"
GEMINI_API_KEY = "AQ.Ab8RN6Krz4oeWkqqC1Rf1SKaWEBakHtZRQqZe8uR05JDsH_04w"
DB_FILE = "quyonlar.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Google Gemini sozlamasi
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-flash')

class QuyonQoshishFSM(StatesGroup):
    nom = State()
    zot = State()
    yangi_zot_nomi = State()
    jinsi = State()
    yoshi = State()
    narx = State()

class RasxodFSM(StatesGroup):
    turi = State()
    izoh = State()
    summa = State()

class QuyonSotishFSM(StatesGroup):
    quyon_id = State()
    summa = State()

class AIVeterinarFSM(StatesGroup):
    savol = State()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS quyonlar (
            id TEXT PRIMARY KEY,
            nom TEXT,
            zot TEXT,
            olinganFerma TEXT,
            jinsi TEXT,
            yoshi TEXT,
            olinganSumma REAL,
            kelganSana TEXT,
            qoshilganSana TEXT,
            holati TEXT,
            sotilganSana TEXT,
            sotilganSumma REAL,
            olganSana TEXT,
            vaqt TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS xarajatlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            turi TEXT,
            izoh TEXT,
            summa REAL,
            sana TEXT,
            vaqt TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_next_quyon_id():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM quyonlar")
    rows = c.fetchall()
    conn.close()
    max_num = 0
    for r in rows:
        val = r[0]
        if val and str(val).startswith("Q-"):
            try:
                n = int(str(val).replace("Q-", ""))
                if n > max_num:
                    max_num = n
            except:
                pass
    return f"Q-{str(max_num + 1).zfill(3)}"

def asosiy_menyu():
    kb = [
        [KeyboardButton(text="➕ Quyon"), KeyboardButton(text="💸 Rasxod")],
        [KeyboardButton(text="💰 Sotish"), KeyboardButton(text="📊 Kassa")],
        [KeyboardButton(text="🤖 AI Maslahatchi"), KeyboardButton(text="🐰 Quyonlar")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def bekor_qilish_knopka():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)

def rasxod_turlari_knopka():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🌾 Yem (Granula/Arpa)"), KeyboardButton(text="🌿 Xashak (Beda/Somon)")],
        [KeyboardButton(text="💊 Dori / Vaksina"), KeyboardButton(text="🪵 Katak / Jihoz")],
        [KeyboardButton(text="📦 Boshqa rasxod")],
        [KeyboardButton(text="❌ Bekor qilish")]
    ], resize_keyboard=True)

def jins_knopka():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Samka (Urg'ochi)"), KeyboardButton(text="Samis (Erkak)")],
        [KeyboardButton(text="❌ Bekor qilish")]
    ], resize_keyboard=True)

def zot_knopka():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Rex Trikalor"), KeyboardButton(text="Kaliforniya")],
        [KeyboardButton(text="Flandr"), KeyboardButton(text="Yangi Zelandiya")],
        [KeyboardButton(text="Rizen"), KeyboardButton(text="Jaydari")],
        [KeyboardButton(text="➕ Yangi zot yozish...")],
        [KeyboardButton(text="❌ Bekor qilish")]
    ], resize_keyboard=True)

@dp.message(F.text.contains("Bekor qilish"), StateFilter("*"))
async def bekor_qilish(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Amal bekor qilindi.", reply_markup=asosiy_menyu())

@dp.message(Command("start"), StateFilter("*"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Assalomu alaykum! 🐰 Quyon fermasi tizimi online serverda ishlamoqda.", reply_markup=asosiy_menyu())

# --- 1. AI MASLAHATCHI ---
@dp.message(F.text.contains("AI Maslahatchi"), StateFilter("*"))
async def start_ai_maslahat(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(AIVeterinarFSM.savol)
    matn = "🤖 **Google Gemini Quyonchilik Maslahatchisi**\n\nSavolingizni yozing yoki quyon rasmini yuboring:"
    await message.answer(matn, reply_markup=bekor_qilish_knopka(), parse_mode="Markdown")

@dp.message(AIVeterinarFSM.savol, F.photo)
async def ai_savol_rasm(message: types.Message, state: FSMContext):
    await message.answer("⏳ Rasm tahlil qilinmoqda...")
    try:
        photo = message.photo[-1]
        file_io = io.BytesIO()
        await bot.download(photo, destination=file_io)
        img_bytes = file_io.getvalue()

        izoh = message.caption or "Ushbu quyonning sog'lig'i va holatini tahlil qilib, amaliy tavsiya ber."
        prompt = f"Sen quyonchilik bo'yicha tajribali veterinar mutaxassisissan. Qisqa, tushunarli va amaliy davolash/parvarish tavsiyasini ber: {izoh}"
        
        image_part = {"mime_type": "image/jpeg", "data": img_bytes}
        response = ai_model.generate_content([prompt, image_part])
        await message.answer(f"🤖 **Maslahat:**\n\n{response.text}", reply_markup=asosiy_menyu())
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {str(e)}", reply_markup=asosiy_menyu())
    await state.clear()

@dp.message(AIVeterinarFSM.savol, F.text)
async def ai_savol_matn(message: types.Message, state: FSMContext):
    savol = message.text.strip()
    await message.answer("⏳ Javob tayyorlanmoqda...")
    prompt = f"Sen quyonchilik bo'yicha tajribali veterinar mutaxassisissan. O'zbekistondagi iqlim va sharoitni hisobga olib, quyidagi savolga amaliy va aniq tavsiya ber: {savol}"
    try:
        response = ai_model.generate_content(prompt)
        await message.answer(f"🤖 **Maslahat:**\n\n{response.text}", reply_markup=asosiy_menyu())
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {str(e)}", reply_markup=asosiy_menyu())
    await state.clear()

# --- 2. SOTISH BO'LIMI ---
@dp.message(F.text == "💰 Sotish", StateFilter("*"))
async def start_sotish(message: types.Message, state: FSMContext):
    await state.clear()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, nom, zot FROM quyonlar WHERE holati = 'tirik' OR holati IS NULL")
    rows = c.fetchall()
    conn.close()

    if not rows:
        await message.answer("Sotish uchun tirik quyon topilmadi.", reply_markup=asosiy_menyu())
        return

    royxat_matni = "\n".join([f"• `{r[0]}` — {r[1]} ({r[2]})" for r in rows[:20]])
    await state.set_state(QuyonSotishFSM.quyon_id)
    await message.answer(
        f"💰 **Quyon sotish**\n\nMavjud quyonlar:\n{royxat_matni}\n\nSotilgan quyonning **ID raqamini** yozing (masalan: `Q-001`):",
        reply_markup=bekor_qilish_knopka(),
        parse_mode="Markdown"
    )

@dp.message(QuyonSotishFSM.quyon_id)
async def sotish_id(message: types.Message, state: FSMContext):
    q_id = message.text.strip().upper()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, nom FROM quyonlar WHERE UPPER(id) = ? AND (holati = 'tirik' OR holati IS NULL)", (q_id,))
    quyon = c.fetchone()
    conn.close()

    if not quyon:
        await message.answer("Bunday ID li tirik quyon topilmadi. Qaytadan kiriting (yoki Bekor qilishni bosing):")
        return

    await state.update_data(quyon_id=quyon[0], quyon_nom=quyon[1])
    await state.set_state(QuyonSotishFSM.summa)
    await message.answer(f"🐰 Tanlandi: **{quyon[1]}** (`{quyon[0]}`).\n\nNecha pulga sotildi? (summani so'mda kiriting):", reply_markup=bekor_qilish_knopka(), parse_mode="Markdown")

@dp.message(QuyonSotishFSM.summa)
async def sotish_summa(message: types.Message, state: FSMContext):
    try:
        summa = float(message.text.strip().replace(" ", "").replace(",", ""))
    except ValueError:
        await message.answer("Summani raqamda kiriting:")
        return

    data = await state.get_data()
    q_id = data['quyon_id']
    bugun_sana = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE quyonlar 
        SET holati = 'sotilgan', sotilganSana = ?, sotilganSumma = ?
        WHERE id = ?
    ''', (bugun_sana, summa, q_id))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(
        f"✅ Muvaffaqiyatli sotildi!\n🐰 Quyon: {data['quyon_nom']} (`{q_id}`)\n💵 Sotilgan summa: {summa:,.0f} so'm",
        reply_markup=asosiy_menyu(),
        parse_mode="Markdown"
    )

# --- 3. QUYON QO'SHISH ---
@dp.message(F.text == "➕ Quyon", StateFilter("*"))
async def start_quyon_qoshish(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(QuyonQoshishFSM.nom)
    await message.answer("🐰 Quyonning laqabini kiriting:", reply_markup=bekor_qilish_knopka())

@dp.message(QuyonQoshishFSM.nom)
async def qoshish_nom(message: types.Message, state: FSMContext):
    await state.update_data(nom=message.text.strip())
    await state.set_state(QuyonQoshishFSM.zot)
    await message.answer("🧬 Zotini tanlang:", reply_markup=zot_knopka())

@dp.message(QuyonQoshishFSM.zot)
async def qoshish_zot(message: types.Message, state: FSMContext):
    matn = message.text.strip()
    if "Yangi zot yozish" in matn:
        await state.set_state(QuyonQoshishFSM.yangi_zot_nomi)
        await message.answer("✍️️ Yangi zot nomini yozing:", reply_markup=bekor_qilish_knopka())
        return
    await state.update_data(zot=matn)
    await state.set_state(QuyonQoshishFSM.jinsi)
    await message.answer("⚧ Jinsini tanlang:", reply_markup=jins_knopka())

@dp.message(QuyonQoshishFSM.yangi_zot_nomi)
async def qoshish_yangi_zot_nomi(message: types.Message, state: FSMContext):
    await state.update_data(zot=message.text.strip())
    await state.set_state(QuyonQoshishFSM.jinsi)
    await message.answer("⚧ Jinsini tanlang:", reply_markup=jins_knopka())

@dp.message(QuyonQoshishFSM.jinsi)
async def qoshish_jinsi(message: types.Message, state: FSMContext):
    await state.update_data(jinsi=message.text.strip())
    await state.set_state(QuyonQoshishFSM.yoshi)
    await message.answer("🎂 Yoshi (masalan: 5 oylik):", reply_markup=bekor_qilish_knopka())

@dp.message(QuyonQoshishFSM.yoshi)
async def qoshish_yoshi(message: types.Message, state: FSMContext):
    await state.update_data(yoshi=message.text.strip())
    await state.set_state(QuyonQoshishFSM.narx)
    await message.answer("💵 Olingan narxini kiriting (so'mda):", reply_markup=bekor_qilish_knopka())

@dp.message(QuyonQoshishFSM.narx)
async def qoshish_narx(message: types.Message, state: FSMContext):
    try:
        narx = float(message.text.strip().replace(" ", "").replace(",", ""))
    except ValueError:
        await message.answer("Faqat raqam kiriting:")
        return

    data = await state.get_data()
    yangi_id = get_next_quyon_id()
    bugun_sana = datetime.now().strftime("%Y-%m-%d")
    hozirgi_vaqt = datetime.now().isoformat()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO quyonlar (id, nom, zot, olinganFerma, jinsi, yoshi, olinganSumma, kelganSana, qoshilganSana, holati, sotilganSana, sotilganSumma, olganSana, vaqt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (yangi_id, data['nom'], data['zot'], "Ishxona", data['jinsi'], data['yoshi'], narx, bugun_sana, None, "tirik", None, 0, None, hozirgi_vaqt))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(f"✅ Saqlandi! ID: `{yangi_id}` | Laqabi: {data['nom']}", reply_markup=asosiy_menyu(), parse_mode="Markdown")

# --- 4. RASXOD ---
@dp.message(F.text == "💸 Rasxod", StateFilter("*"))
async def start_rasxod(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(RasxodFSM.turi)
    await message.answer("💸 Xarajat turi:", reply_markup=rasxod_turlari_knopka())

@dp.message(RasxodFSM.turi)
async def rasxod_turi(message: types.Message, state: FSMContext):
    await state.update_data(turi=message.text.strip())
    await state.set_state(RasxodFSM.izoh)
    await message.answer("📝 Xarajat tafsiloti (masalan: 1 qop yem):", reply_markup=bekor_qilish_knopka())

@dp.message(RasxodFSM.izoh)
async def rasxod_izoh(message: types.Message, state: FSMContext):
    await state.update_data(izoh=message.text.strip())
    await state.set_state(RasxodFSM.summa)
    await message.answer("💵 Summasi (so'mda):", reply_markup=bekor_qilish_knopka())

@dp.message(RasxodFSM.summa)
async def rasxod_summa(message: types.Message, state: FSMContext):
    try:
        summa = float(message.text.strip().replace(" ", "").replace(",", ""))
    except ValueError:
        await message.answer("Summani raqamda kiriting:")
        return

    data = await state.get_data()
    bugun_sana = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO xarajatlar (turi, izoh, summa, sana, vaqt) VALUES (?, ?, ?, ?, ?)',
              (data['turi'], data['izoh'], summa, bugun_sana, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(f"✅ Xarajat saqlandi: {summa:,.0f} so'm", reply_markup=asosiy_menyu())

# --- 5. KASSA VA RO'YXAT ---
@dp.message(F.text == "📊 Kassa", StateFilter("*"))
async def hisobot_kassa(message: types.Message, state: FSMContext):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(olinganSumma) FROM quyonlar WHERE holati = 'tirik' OR holati IS NULL")
    tirik = c.fetchone()
    c.execute("SELECT SUM(sotilganSumma) FROM quyonlar WHERE holati = 'sotilgan'")
    sotuv = c.fetchone()[0] or 0
    c.execute("SELECT SUM(summa) FROM xarajatlar")
    rasxod = c.fetchone()[0] or 0
    conn.close()

    matn = (
        f"📊 **Kassa hisoboti:**\n\n"
        f"🐰 Tirik quyonlar: {tirik[0] or 0} ta\n"
        f"💰 Jami sotuv: +{sotuv:,.0f} so'm\n"
        f"🌾 Jami rasxod: -{rasxod:,.0f} so'm\n"
        f"📈 Sof kassa: {(sotuv - rasxod):,.0f} so'm"
    )
    await message.answer(matn, reply_markup=asosiy_menyu(), parse_mode="Markdown")

@dp.message(F.text == "🐰 Quyonlar", StateFilter("*"))
async def quyonlar_royxat(message: types.Message, state: FSMContext):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, nom, zot FROM quyonlar WHERE holati = 'tirik' OR holati IS NULL")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await message.answer("Hozircha tirik quyon yo'q.", reply_markup=asosiy_menyu())
        return
    txt = "🐰 **Tirik quyonlar:**\n\n" + "\n".join([f"• `{r[0]}` — {r[1]} ({r[2]})" for r in rows[:30]])
    await message.answer(txt, reply_markup=asosiy_menyu(), parse_mode="Markdown")

# --- VEB / APK UCHUN API ---
async def ai_handler(request):
    try:
        data = await request.json()
        savol = data.get("savol", "").strip()
        if not savol:
            return web.json_response({"status": "error", "message": "Savol kiritilmadi"}, status=400)
        prompt = f"Sen quyonchilik veterinari mutaxassisissan. Qisqa va aniq tavsiya ber: {savol}"
        response = ai_model.generate_content(prompt)
        return web.json_response({"status": "ok", "javob": response.text})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def sync_handler(request):
    try:
        data = await request.json()
        quyonlar = data.get("quyonlar", [])
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        for q in quyonlar:
            c.execute('''
                INSERT OR REPLACE INTO quyonlar (id, nom, zot, olinganFerma, jinsi, yoshi, olinganSumma, kelganSana, qoshilganSana, holati, sotilganSana, sotilganSumma, olganSana, vaqt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (q.get("id"), q.get("nom"), q.get("zot"), q.get("olinganFerma", "APK"), q.get("jinsi"), q.get("yoshi"), q.get("olinganSumma", 0), q.get("kelganSana"), q.get("qoshilganSana"), q.get("holati", "tirik"), q.get("sotilganSana"), q.get("sotilganSumma", 0), q.get("olganSana"), q.get("vaqt", datetime.now().isoformat())))
        conn.commit()
        conn.close()
        return web.json_response({"status": "ok", "message": f"{len(quyonlar)} ta saqlandi"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def start_server():
    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")})
    cors.add(cors.add(app.router.add_resource("/api/sync")).add_route("POST", sync_handler))
    cors.add(cors.add(app.router.add_resource("/api/ai")).add_route("POST", ai_handler))
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    init_db()
    await start_server()
    print("Bot va server ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
