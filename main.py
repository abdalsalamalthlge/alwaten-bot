import telebot
from telebot import types
import sqlite3
import os

TOKEN = "8299747184:AAHugmlEBT3VUozjE8mv2141h2lE4yE3d0E"
ADMIN_ID = 8213405271

bot = telebot.TeleBot(TOKEN)

state = {}
temp = {}

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

# ===== الدفع =====
PAYMENT_METHODS = {
    "شام كاش": "5fbc30de0764cfc28d9341e2835b7731",
    "سيريتل كاش": "963932080655"
}

# ===== START =====
@bot.message_handler(commands=['start'])
def start(message):
    cursor.execute("SELECT name FROM categories")
    cats = cursor.fetchall()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for c in cats:
        markup.add(c[0])

    markup.add("💳 طرق الدفع")

    if message.chat.id == ADMIN_ID:
        markup.add("⚙️ لوحة التحكم")

    state[message.chat.id] = "category"
    bot.send_message(message.chat.id, "🎮 اختر الفئة:", reply_markup=markup)

# ===== لوحة التحكم =====
@bot.message_handler(func=lambda m: m.text == "⚙️ لوحة التحكم")
def admin_panel(message):
    if message.chat.id != ADMIN_ID:
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 الطلبات")
    markup.add("➕ إضافة فئة", "🗑 حذف فئة")
    markup.add("➕ إضافة منتج", "🗑 حذف منتج")
    markup.add("✏️ تعديل فئة", "💰 تعديل سعر")
    markup.add("🔙 رجوع")

    state[message.chat.id] = "admin"
    bot.send_message(message.chat.id, "⚙️ لوحة التحكم:", reply_markup=markup)

# ===== عرض المنتجات =====
@bot.message_handler(func=lambda m: state.get(m.chat.id) == "category")
def category(message):

    if message.text == "💳 طرق الدفع":
        txt = ""
        for k,v in PAYMENT_METHODS.items():
            txt += f"{k}: {v}\n"
        bot.send_message(message.chat.id, txt)
        return

    cursor.execute("SELECT name, price FROM products WHERE category=?", (message.text,))
    items = cursor.fetchall()

    if not items:
        bot.send_message(message.chat.id, "❌ لا يوجد منتجات")
        return

    markup = types.InlineKeyboardMarkup()
    for name, price in items:
        markup.add(types.InlineKeyboardButton(text=f"{name} - {price}", callback_data=f"buy_{name}"))

    bot.send_message(message.chat.id, "💰 اختر:", reply_markup=markup)

# ===== شراء =====
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def buy(call):
    name = call.data.replace("buy_", "")

    cursor.execute("SELECT price, category FROM products WHERE name=?", (name,))
    data = cursor.fetchone()

    temp[call.message.chat.id] = {
        "product": name,
        "price": data[0],
        "cat": data[1]
    }

    state[call.message.chat.id] = "id"
    bot.send_message(call.message.chat.id, "🆔 أرسل ID:")

# ===== ID =====
@bot.message_handler(func=lambda m: state.get(m.chat.id) == "id")
def get_id(message):
    temp[message.chat.id]["id"] = message.text
    state[message.chat.id] = "payment"

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for p in PAYMENT_METHODS:
        markup.add(p)

    bot.send_message(message.chat.id, "💳 اختر الدفع:", reply_markup=markup)

# ===== الدفع =====
@bot.message_handler(func=lambda m: state.get(m.chat.id) == "payment")
def payment(message):
    if message.text not in PAYMENT_METHODS:
        return

    temp[message.chat.id]["payment"] = message.text
    state[message.chat.id] = "photo"

    num = PAYMENT_METHODS[message.text]

    bot.send_message(message.chat.id, f"ادفع هنا:\n{num}\nثم أرسل صورة")

# ===== الطلب =====
@bot.message_handler(content_types=['photo'])
def photo(message):
    data = temp.get(message.chat.id)
    if not data:
        return

    cursor.execute("INSERT INTO orders (user_id,data,status) VALUES (?,?,?)",
                   (message.chat.id,str(data),"pending"))
    conn.commit()

    oid = cursor.lastrowid

    txt = f"طلب #{oid}\n{data}"

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("قبول", callback_data=f"accept_{oid}"),
        types.InlineKeyboardButton("رفض", callback_data=f"reject_{oid}")
    )

    bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=txt, reply_markup=markup)
    bot.send_message(message.chat.id, "✔ تم إرسال طلبك")

    temp.pop(message.chat.id)
    state.pop(message.chat.id)

# ===== إدارة الطلب =====
@bot.callback_query_handler(func=lambda call: "_" in call.data)
def admin_actions(call):
    action, oid = call.data.split("_")
    oid = int(oid)

    cursor.execute("SELECT user_id FROM orders WHERE id=?", (oid,))
    user = cursor.fetchone()[0]

    if action == "accept":
        bot.send_message(user, "✅ تم القبول")
    elif action == "reject":
        bot.send_message(user, "❌ تم الرفض")

# ===== عرض الطلبات =====
@bot.message_handler(func=lambda m: m.text == "📊 الطلبات" and m.chat.id == ADMIN_ID)
def show_orders(message):
    cursor.execute("SELECT * FROM orders")
    orders = cursor.fetchall()

    if not orders:
        bot.send_message(message.chat.id, "❌ لا يوجد طلبات")
        return

    text = ""
    for o in orders:
        text += f"\n#{o[0]} - {o[3]}\n{o[2]}\n"

    bot.send_message(message.chat.id, text)

# ===== إضافة فئة =====
@bot.message_handler(func=lambda m: m.text == "➕ إضافة فئة" and m.chat.id == ADMIN_ID)
def add_cat(message):
    state[message.chat.id] = "add_cat"
    bot.send_message(message.chat.id, "اسم الفئة:")

@bot.message_handler(func=lambda m: state.get(m.chat.id) == "add_cat")
def save_cat(message):
    cursor.execute("INSERT INTO categories VALUES (?)", (message.text,))
    conn.commit()
    state[message.chat.id] = "admin"
    bot.send_message(message.chat.id, "✔ تم")

# ===== حذف فئة =====
@bot.message_handler(func=lambda m: m.text == "🗑 حذف فئة" and m.chat.id == ADMIN_ID)
def del_cat(message):
    cursor.execute("SELECT name FROM categories")
    cats = cursor.fetchall()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for c in cats:
        markup.add(c[0])

    state[message.chat.id] = "del_cat"
    bot.send_message(message.chat.id, "اختر:", reply_markup=markup)

@bot.message_handler(func=lambda m: state.get(m.chat.id) == "del_cat")
def confirm_del(message):
    cursor.execute("DELETE FROM categories WHERE name=?", (message.text,))
    cursor.execute("DELETE FROM products WHERE category=?", (message.text,))
    conn.commit()
    bot.send_message(message.chat.id, "✔ تم")
    state[message.chat.id] = "admin"

# ===== إضافة منتج =====
@bot.message_handler(func=lambda m: m.text == "➕ إضافة منتج" and m.chat.id == ADMIN_ID)
def add_prod(message):
    state[message.chat.id] = "prod_cat"
    bot.send_message(message.chat.id, "اسم الفئة:")

@bot.message_handler(func=lambda m: state.get(m.chat.id) == "prod_cat")
def prod_cat(message):
    temp[message.chat.id] = {"cat": message.text}
    state[message.chat.id] = "prod_name"
    bot.send_message(message.chat.id, "اسم المنتج:")

@bot.message_handler(func=lambda m: state.get(m.chat.id) == "prod_name")
def prod_name(message):
    temp[message.chat.id]["name"] = message.text
    state[message.chat.id] = "prod_price"
    bot.send_message(message.chat.id, "السعر:")

@bot.message_handler(func=lambda m: state.get(m.chat.id) == "prod_price")
def prod_price(message):
    d = temp[message.chat.id]
    cursor.execute("INSERT INTO products VALUES (?,?,?)", (d["cat"], d["name"], message.text))
    conn.commit()
    bot.send_message(message.chat.id, "✔ تم")
    state[message.chat.id] = "admin"

# ===== حذف منتج =====
@bot.message_handler(func=lambda m: m.text == "🗑 حذف منتج" and m.chat.id == ADMIN_ID)
def del_prod(message):
    cursor.execute("SELECT name FROM products")
    prods = cursor.fetchall()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for p in prods:
        markup.add(p[0])

    state[message.chat.id] = "del_prod"
    bot.send_message(message.chat.id, "اختر:", reply_markup=markup)

@bot.message_handler(func=lambda m: state.get(m.chat.id) == "del_prod")
def confirm_del_prod(message):
    cursor.execute("DELETE FROM products WHERE name=?", (message.text,))
    conn.commit()
    bot.send_message(message.chat.id, "✔ تم")
    state[message.chat.id] = "admin"

# ===== تعديل السعر =====
@bot.message_handler(func=lambda m: m.text == "💰 تعديل سعر" and m.chat.id == ADMIN_ID)
def edit_price(message):
    cursor.execute("SELECT name FROM products")
    prods = cursor.fetchall()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for p in prods:
        markup.add(p[0])

    state[message.chat.id] = "edit_price"
    bot.send_message(message.chat.id, "اختر المنتج:", reply_markup=markup)

@bot.message_handler(func=lambda m: state.get(m.chat.id) == "edit_price")
def new_price(message):
    temp[message.chat.id] = {"prod": message.text}
    state[message.chat.id] = "new_price"
    bot.send_message(message.chat.id, "السعر الجديد:")

@bot.message_handler(func=lambda m: state.get(m.chat.id) == "new_price")
def save_price(message):
    cursor.execute("UPDATE products SET price=? WHERE name=?", (message.text, temp[message.chat.id]["prod"]))
    conn.commit()
    bot.send_message(message.chat.id, "✔ تم تحديث السعر")
    state[message.chat.id] = "admin"

print("Bot running...")
bot.infinity_polling()
