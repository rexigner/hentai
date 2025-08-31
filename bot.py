import asyncio
import aiohttp
import random
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LabeledPrice,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
)

TOKEN = "8405888483:AAE5KuD2lVpunJDvYek909Sc2xyKTQ6B42k"
PHOTO_API_URL = "https://api.waifu.pics/nsfw/waifu"
PAYMENT_PROVIDER_TOKEN = ""  # Usually empty for Telegram Stars payments

SEXY_SENTENCES = [
    "Feeling naughty? 😈",
    "Hot and fresh just for you 🔥",
    "Can’t stop staring… 👀",
    "Spice up your day! 🌶️",
    "Pure temptation 😘",
    "Your daily dose of desire 💋",
    "Sizzling and stunning 🔥",
    "Unleash your fantasies 😏",
]

user_jobs = {}
user_counters = {}
user_payment_status = {}
payment_pending = {}  # Tracks if user has been prompted and not paid yet
session = None  # aiohttp ClientSession shared


async def fetch_image(url):
    global session
    if session is None:
        session = aiohttp.ClientSession()
    try:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("url")
            else:
                print(f"Failed to fetch from {url}, status {response.status}")
                return None
    except Exception as e:
        print(f"Exception in fetch_image: {e}")
        return None


async def send_photo(chat_id, context: ContextTypes.DEFAULT_TYPE):
    # Check payment status and limits
    paid_until = user_payment_status.get(chat_id)
    now = datetime.utcnow()

    # If payment is pending and not paid, do not send photo repeatedly
    if payment_pending.get(chat_id, False):
        return

    if paid_until is None or now > paid_until:  # No valid payment
        if user_counters.get(chat_id, 0) >= 15:
            if not payment_pending.get(chat_id, False):
                await prompt_payment_options(chat_id, context)
                payment_pending[chat_id] = True
            return

    image_url = await fetch_image(PHOTO_API_URL)
    if not image_url:
        await context.bot.send_message(chat_id, "Sorry, no image available right now.")
        return
    caption = random.choice(SEXY_SENTENCES)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("More", callback_data="more"),
                InlineKeyboardButton("Stop", callback_data="stop"),
            ]
        ]
    )
    try:
        await context.bot.send_photo(chat_id=chat_id, photo=image_url, caption=caption, reply_markup=keyboard)
        user_counters[chat_id] = user_counters.get(chat_id, 0) + 1
    except Exception as e:
        print(f"Failed to send photo: {e}")
        await context.bot.send_message(chat_id, "Failed to send image. Try again later.")


async def prompt_payment_options(chat_id, context):
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Pay 10 Stars (1 Day Access)", callback_data="pay_1day"),
            ],
            [
                InlineKeyboardButton("Pay 70 Stars (1 Week Access)", callback_data="pay_1week"),
            ],
        ]
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text="You've reached 15 photos. Please choose a payment option to continue receiving pictures:",
        reply_markup=keyboard,
    )


async def send_invoice(chat_id, context, option):
    if option == "1day":
        prices = [LabeledPrice(label="10 Telegram Stars for 1 Day", amount=10)]
        title = "Unlock 1 Day Access"
        description = "Pay 10 Telegram Stars to unlock picture access for 1 day."
        payload = "payment_1day"
    else:
        prices = [LabeledPrice(label="70 Telegram Stars for 1 Week", amount=70)]
        title = "Unlock 1 Week Access"
        description = "Pay 70 Telegram Stars to unlock picture access for 1 week."
        payload = "payment_1week"

    await context.bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency="XTR",
        prices=prices,
        is_flexible=False,
        start_parameter="get_pictures",
    )


async def send_photo_periodically(chat_id, context, interval):
    while user_jobs.get(chat_id, False):
        await send_photo(chat_id, context)
        await asyncio.sleep(interval)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    paid_until = user_payment_status.get(chat_id)
    now = datetime.utcnow()

    if payment_pending.get(chat_id, False):
        await update.message.reply_text(
            "You must complete payment to continue receiving pictures. Please choose a payment option in the chat."
        )
        return

    if paid_until is None or now > paid_until:
        if user_counters.get(chat_id, 0) >= 15:
            await prompt_payment_options(chat_id, context)
            payment_pending[chat_id] = True
            return

    image_url = await fetch_image(PHOTO_API_URL)
    if image_url:
        await context.bot.send_photo(chat_id=chat_id, photo=image_url, caption="Hey sexy")
    else:
        await update.message.reply_text("Hey sexy")

    keyboard = [
        [InlineKeyboardButton("Every 10 seconds", callback_data="interval_10")],
        [InlineKeyboardButton("Every 5 seconds", callback_data="interval_5")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose how often you want to receive pictures:", reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    await query.answer()

    if query.data == "pay_1day":
        await send_invoice(chat_id, context, "1day")
        return
    elif query.data == "pay_1week":
        await send_invoice(chat_id, context, "1week")
        return

    if query.data == "start":

        if payment_pending.get(chat_id, False):
            await context.bot.send_message(
                chat_id,
                "You must pay first to receive pictures. Please choose a payment option.",
            )
            return

        if user_jobs.get(chat_id, False):
            await context.bot.send_message(chat_id, "Already running.")
            return

        paid_until = user_payment_status.get(chat_id)
        now = datetime.utcnow()
        if (paid_until is None or now > paid_until) and user_counters.get(chat_id, 0) >= 15:
            payment_pending[chat_id] = True
            await prompt_payment_options(chat_id, context)
            return

        interval = user_jobs.get(f"{chat_id}_interval", 10)
        user_jobs[chat_id] = True
        await context.bot.send_message(chat_id, f"Started sending photos every {interval} seconds. Use buttons to control.")
        context.application.create_task(send_photo_periodically(chat_id, context, interval))

    elif query.data == "more":
        if user_jobs.get(chat_id, False):
            await send_photo(chat_id, context)
        else:
            await context.bot.send_message(chat_id, "Press start first!")

    elif query.data == "stop":
        if user_jobs.get(chat_id, False):
            user_jobs[chat_id] = False
            await context.bot.send_message(chat_id, "Stopped sending images. Send /start to control again.")
        else:
            await context.bot.send_message(chat_id, "No active session to stop.")

    elif query.data in ["interval_10", "interval_5"]:
        interval = 10 if query.data == "interval_10" else 5
        user_jobs[f"{chat_id}_interval"] = interval

        keyboard = [
            [InlineKeyboardButton("Start", callback_data="start")],
            [InlineKeyboardButton("Stop", callback_data="stop")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=f"Interval set to every {interval} seconds. Use Start or Stop buttons below:", reply_markup=reply_markup)


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    payload = update.message.successful_payment.invoice_payload
    now = datetime.utcnow()

    if payload == "payment_1day":
        user_payment_status[chat_id] = now + timedelta(days=1)
    elif payload == "payment_1week":
        user_payment_status[chat_id] = now + timedelta(weeks=1)
    else:
        user_payment_status[chat_id] = now + timedelta(days=1)

    user_counters[chat_id] = 0
    payment_pending[chat_id] = False
    await context.bot.send_message(chat_id, "✅ Payment received! You can now receive pictures. Use /start to begin.")


def main():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    print("Bot started, send /start to chat with buttons.")
    application.run_polling()


if __name__ == "__main__":
    main()
