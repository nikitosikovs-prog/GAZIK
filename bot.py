import logging
import random
import sqlite3
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes
from aiohttp import web
import threading
import asyncio

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8659068385:AAGczzHbQ1U7KVtY0h7g8hz8D9_RzVMaoio"
WEBAPP_URL = "http://localhost:8080"  # потом заменишь на serveo/ngrok
PORT = 8080

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('casino.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, 
                  name TEXT,
                  balance INTEGER DEFAULT 1000,
                  games INTEGER DEFAULT 0,
                  wins INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()
    print("✅ База данных готова")


def get_user(user_id):
    conn = sqlite3.connect('casino.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (id, name) VALUES (?, ?)",
                  (user_id, f"Player{user_id}"))
        conn.commit()
        balance = 1000
        games = 0
        wins = 0
    else:
        balance = user[2]
        games = user[3]
        wins = user[4]
    conn.close()
    return {"balance": balance, "games": games, "wins": wins}


def update_balance(user_id, new_balance):
    conn = sqlite3.connect('casino.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance=? WHERE id=?", (new_balance, user_id))
    conn.commit()
    conn.close()


def update_stats(user_id, win_amount):
    conn = sqlite3.connect('casino.db')
    c = conn.cursor()
    c.execute("UPDATE users SET games=games+1, wins=wins+? WHERE id=?",
              (1 if win_amount > 0 else 0, user_id))
    conn.commit()
    conn.close()


# ========== БОТ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = get_user(user.id)

    keyboard = [[InlineKeyboardButton(
        "🐸 ЗАПУСТИТЬ PEPE CASINO",
        web_app=WebAppInfo(url=f"{WEBAPP_URL}/")
    )]]

    await update.message.reply_text(
        f"🐸 **PEPE CASINO** 🐸\n\n"
        f"💰 Баланс: {user_data['balance']} GC\n"
        f"🎮 Сыграно: {user_data['games']}\n"
        f"🏆 Побед: {user_data['wins']}\n\n"
        f"👇 Нажми кнопку чтобы войти!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


# ========== СЛОТ TATTOO HORSES ==========
class TattooHorsesSlot:
    def __init__(self):
        self.symbols = {
            'gold_horse': {'name': '🐎 Золотой конь', 'mult': 5, 'emoji': '🐎✨'},
            'silver_horse': {'name': '🐎 Серебряный конь', 'mult': 3, 'emoji': '🐎⭐'},
            'bronze_horse': {'name': '🐎 Бронзовый конь', 'mult': 2, 'emoji': '🐎'},
            'horseshoe': {'name': '👑 Подкова', 'mult': 'wild', 'emoji': '👑'},
            'skull': {'name': '💀 Череп', 'mult': 'scatter', 'emoji': '💀'},
            'fire': {'name': '🔥 Пламя', 'mult': 'bonus', 'emoji': '🔥'}
        }

    def spin(self, bet):
        # Генерируем 5x3 поле
        reels = []
        for _ in range(5):
            col = []
            for _ in range(3):
                sym = random.choice(list(self.symbols.keys()))
                col.append(sym)
            reels.append(col)

        # Проверяем выигрыш
        win_multiplier = self.check_win(reels)
        win_amount = int(bet * win_multiplier)

        return {
            'reels': reels,
            'win_multiplier': win_multiplier,
            'win_amount': win_amount
        }

    def check_win(self, reels):
        # Простая проверка (для демо)
        mult = 0
        # Проверяем горизонтальные линии
        for row in range(3):
            symbols = [reels[col][row] for col in range(5)]
            if all(s == symbols[0] for s in symbols):
                if symbols[0] == 'gold_horse':
                    mult += 5
                elif symbols[0] == 'silver_horse':
                    mult += 3
                elif symbols[0] == 'bronze_horse':
                    mult += 2
                elif symbols[0] == 'horseshoe':
                    mult += 10
        return mult


# ========== API ДЛЯ МИНИ-АПП ==========
async def handle_index(request):
    return web.FileResponse('templates/index.html')


async def handle_user(request):
    user_id = int(request.query.get('user_id', 0))
    user = get_user(user_id)
    return web.json_response(user)


async def handle_slot_spin(request):
    data = await request.json()
    user_id = data['user_id']
    bet = data['bet']

    user = get_user(user_id)
    if user['balance'] < bet:
        return web.json_response({'success': False, 'error': 'Недостаточно средств'})

    slot = TattooHorsesSlot()
    result = slot.spin(bet)

    new_balance = user['balance'] - bet + result['win_amount']
    update_balance(user_id, new_balance)
    update_stats(user_id, result['win_amount'])

    return web.json_response({
        'success': True,
        'reels': result['reels'],
        'win_amount': result['win_amount'],
        'new_balance': new_balance
    })


# ========== ЗАПУСК ==========
async def start_server():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/api/user', handle_user)
    app.router.add_post('/api/slot/spin', handle_slot_spin)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', PORT)
    await site.start()
    print(f"✅ Сервер: http://localhost:{PORT}")


def run_bot():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("✅ Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    threading.Thread(target=lambda: asyncio.run(start_server())).start()
    run_bot()