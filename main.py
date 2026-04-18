import telebot
from telebot import types
import sqlite3
import os

TOKEN = "8299747184:AAHugmlEBT3VUozjE8mv2141h2lE4yE3d0E"
ADMIN_ID = 8213405271

bot = telebot.TeleBot(TOKEN)

state = {}
temp = {}

# ===== مجلد الصور =====
if not os.path.exists("payments"):
    os.makedirs("payments")

# ===== DATABASE =====
conn = sqlite3.connect("store.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS categories (name TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS products (category TEXT, name TEXT, price TEXT)")
cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
data TEXT,
status TEXT
)
""")
conn.commit()

# ===== طرق الدفع =====
PAYMENT_METHODS = {
    "شام كاش": "5fbc30de0764cfc28d9341e2835b7731",
    "سيريتل كاش": "963932080655"
}

SUPPORT = "https://t.me/alwaten_digital"

# ===== START =====
@bot.message_handler(commands=['start'])
def start(message):

    cursor.execute("SELECT name FROM categories")
    cats = cursor.fetchall()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    for c in cats:
        markup.add(c[0])

    markup.add("💳 طرق الدفع", "🆘 الدعم")

    if message.chat.id == ADMIN_ID:
        markup.add("⚙️ لوحة التحكم")

    state[message.chat.id] = "category"
    bot.send_message(message.chat.id, "🎮 اختر الفئة:", reply_markup=markup)

# ===== لوحة التحكم =====
@bot.message_handler(func=lambda m: m.text == "⚙️ لوحة التحكم")
def admin_panel(message):
    if message.chat.id != ADMIN_ID:
        return

    state[message.chat.id] = "admin"

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📂 عرض الفئات")
    markup.add("➕ إضافة فئة", "🗑 حذف فئة")
    markup.add("➕ إضافة منتج", "🗑 حذف منتج")
    markup.add("✏️ تعديل فئة")
    markup.add("🔙 رجوع")

    bot.send_message(message.chat.id, "⚙️ لوحة التحكم:", reply_markup=markup)

# ===== رجوع =====
@bot.message_handler(func=lambda m: m.text == "🔙 رجوع")
def back(message):
    state[message.chat.id] = "category"
    start(message)

# ===== عرض المنتجات =====
@bot.message_handler(func=lambda m: state.get(m.chat.id) == "category")
def category(message):

    if message.text == "💳 طرق الدفع":
        text = "💳 طرق الدفع:\n"
        for k, v in PAYMENT_METHODS.items():
            text += f"\n{k}: {v}"
        bot.send_message(message.chat.id, text)
        return

    if message.text == "🆘 الدعم":
        bot.send_message(message.chat.id, SUPPORT)
        return

    cursor.execute("SELECT name, price FROM products WHERE category=?", (message.text,))
    items = cursor.fetchall()

    if not items:
        bot.send_message(message.chat.id, "❌ لا يوجد منتجات")
        return

    markup = types.InlineKeyboardMarkup()
    for name, price in items:
        markup.add(types.InlineKeyboardButton(
            text=f"{name} - {price}",
            callback_data=f"buy_{name}"
        ))

    bot.send_message(message.chat.id, "💰 اختر المنتج:", reply_markup=markup)

# ===== شراء =====
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def buy(call):

    name = call.data.replace("buy_", "")

    cursor.execute("SELECT price, category FROM products WHERE name=?", (name,))
    data = cursor.fetchone()

    if not data:
        return

    price, cat = data

    temp[call.message.chat.id] = {
        "product": name,
        "price": price,
        "cat": cat
    }

    state[call.message.chat.id] = "id"

    bot.send_message(call.message.chat.id, f"""
🛒 المنتج: {name}
💵 السعر: {price}

🆔 أرسل ID الحساب
""")

# ===== ID =====
@bot.message_handler(func=lambda m: state.get(m.chat.id) == "id")
def get_id(message):
    temp[message.chat.id]["id"] = message.text
    state[message.chat.id] = "payment"

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for p in PAYMENT_METHODS:
        markup.add(p)

    bot.send_message(message.chat.id, "💳 اختر طريقة الدفع:", reply_markup=markup)

# ===== الدفع =====
@bot.message_handler(func=lambda m: state.get(m.chat.id) == "payment")
def payment(message):

    if message.text not in PAYMENT_METHODS:
        return

    temp[message.chat.id]["payment"] = message.text
    state[message.chat.id] = "photo"

    num = PAYMENT_METHODS[message.text]

    text = f"""
💳 {message.text}
📱 رقم الدفع:
{num}

📌 ادفع ثم أرسل صورة
"""

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📋 نسخ الرقم", callback_data=f"copy_{num}"))

    bot.send_message(message.chat.id, text, reply_markup=markup)

# ===== نسخ الرقم =====
@bot.callback_query_handler(func=lambda call: call.data.startswith("copy_"))
def copy(call):
    num = call.data.replace("copy_", "")
    bot.answer_callback_query(call.id, f"{num}", show_alert=True)

# ===== استلام الطلب =====
@bot.message_handler(content_types=['photo'])
def photo(message):

    data = temp.get(message.chat.id)
    if not data:
        return

    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded = bot.download_file(file_info.file_path)

    path = f"payments/{message.chat.id}_{message.message_id}.jpg"

    with open(path, "wb") as f:
        f.write(downloaded)

    cursor.execute(
        "INSERT INTO orders (user_id, data, status) VALUES (?, ?, ?)",
        (message.chat.id, str(data), "pending")
    )
    conn.commit()

    oid = cursor.lastrowid

    text = f"""
📦 طلب #{oid}

👤 @{message.from_user.username}

🎮 {data['cat']}
📦 {data['product']}
💵 {data['price']}
🆔 {data['id']}
💳 {data['payment']}
"""

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ قبول", callback_data=f"accept_{oid}"),
        types.InlineKeyboardButton("❌ رفض", callback_data=f"reject_{oid}")
    )
    markup.add(
        types.InlineKeyboardButton("⏳ تنفيذ", callback_data=f"process_{oid}"),
        types.InlineKeyboardButton("📦 تم", callback_data=f"done_{oid}")
    )

    bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=text, reply_markup=markup)
    bot.send_message(message.chat.id, f"✔ تم إرسال طلبك رقم #{oid}")

    temp.pop(message.chat.id)
    state.pop(message.chat.id)

# ===== تحديث الطلب =====
@bot.callback_query_handler(func=lambda call: "_" in call.data)
def admin_actions(call):

    action, oid = call.data.split("_")
    oid = int(oid)

    cursor.execute("SELECT user_id FROM orders WHERE id=?", (oid,))
    user = cursor.fetchone()
    if not user:
        return

    uid = user[0]

    if action == "accept":
        bot.send_message(uid, "✅ تم قبول طلبك")
    elif action == "reject":
        bot.send_message(uid, "❌ تم رفض الطلب")
    elif action == "process":
        bot.send_message(uid, "⏳ طلبك قيد التنفيذ")
    elif action == "done":
        bot.send_message(uid, "📦 تم التسليم 🎉")

    bot.answer_callback_query(call.id, "تم")

# ===== إضافة فئة =====
@bot.message_handler(func=lambda m: m.text == "➕ إضافة فئة" and state.get(m.chat.id) == "admin")
def add_cat(message):
    state[message.chat.id] = "add_cat"
    bot.send_message(message.chat.id, "اسم الفئة؟")

@bot.message_handler(func=lambda m: state.get(m.chat.id) == "add_cat")
def save_cat(message):
    cursor.execute("INSERT INTO categories VALUES (?)", (message.text,))
    conn.commit()
    state[message.chat.id] = "admin"
    bot.send_message(message.chat.id, "✔ تم")

# ===== حذف فئة =====
@bot.message_handler(func=lambda m: m.text == "🗑 حذف فئة" and state.get(m.chat.id) == "admin")
def delete_cat(message):

    cursor.execute("SELECT name FROM categories")
    cats = cursor.fetchall()

    if not cats:
        bot.send_message(message.chat.id, "❌ لا يوجد فئات")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for c in cats:
        markup.add(c[0])

    markup.add("🔙 رجوع")

    state[message.chat.id] = "del_cat"
    bot.send_message(message.chat.id, "📂 اختر الفئة:", reply_markup=markup)

@bot.message_handler(func=lambda m: state.get(m.chat.id) == "del_cat")
def confirm_del_cat(message):

    if message.text == "🔙 رجوع":
        state[message.chat.id] = "admin"
        return

    cursor.execute("DELETE FROM categories WHERE name=?", (message.text,))
    cursor.execute("DELETE FROM products WHERE category=?", (message.text,))
    conn.commit()

    bot.send_message(message.chat.id, "✔ تم حذف الفئة")
    state[message.chat.id] = "admin"

# ===== تشغيل =====
print("Bot running...")
bot.infinity_polling()
