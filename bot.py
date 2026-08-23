import re

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from sqlalchemy import select, func

from config import get_settings
from session import SessionLocal
from entities import (
    Campaign,
    Prospect,
    Order,
    OutreachMessage,
    Payment,
)
from campaigns import CampaignService


settings = get_settings()
campaign_service = CampaignService()


def allowed(update: Update) -> bool:
    return bool(
        settings.TELEGRAM_CHAT_ID
        and update.effective_chat
        and str(update.effective_chat.id)
        == str(settings.TELEGRAM_CHAT_ID)
    )


def panel():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("HUNT", callback_data="hunt"),
            InlineKeyboardButton("PAUSE", callback_data="pause"),
        ],
        [
            InlineKeyboardButton("RESUME", callback_data="resume"),
            InlineKeyboardButton("STOP", callback_data="stop"),
        ],
        [
            InlineKeyboardButton("STATUS", callback_data="status"),
            InlineKeyboardButton("LEADS", callback_data="leads"),
        ],
        [
            InlineKeyboardButton("ORDERS", callback_data="orders"),
            InlineKeyboardButton("REVENUE", callback_data="revenue"),
        ],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    await update.message.reply_text(
        "PIXEL PULSE STUDIO\n"
        "━━━━━━━━━━━━━━━━\n"
        "🤖 Agent: READY\n\n"
        "Use /hunt 100\n"
        "Use /hunt 500 7d\n"
        "Use /status for the dashboard.",
        reply_markup=panel(),
    )


async def hunt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    args = context.args

    target = (
        int(args[0])
        if args and args[0].isdigit()
        else 100
    )

    days = 1

    if len(args) > 1:
        match = re.match(
            r"(\d+)([dw])",
            args[1].lower()
        )

        if match:
            number = int(match.group(1))
            unit = match.group(2)

            days = number * 7 if unit == "w" else number

    db = SessionLocal()

    try:
        campaign = campaign_service.create(
            db,
            "Telegram Hunt",
            target,
            days,
        )

        await update.message.reply_text(
            f"CAMPAIGN CREATED\n\n"
            f"Campaign: {campaign.campaign_id}\n"
            f"Target: {target}\n"
            f"Duration: {days} day(s)\n"
            f"Daily target: ~{campaign.daily_limit}\n"
            f"Status: READY\n\n"
            f"Use /resume {campaign.campaign_id} to start."
        )

    finally:
        db.close()


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    db = SessionLocal()

    try:
        campaign = db.scalar(
            select(Campaign)
            .where(Campaign.status == "RUNNING")
            .order_by(Campaign.created_at.desc())
        )

        prospects = (
            db.scalar(select(func.count(Prospect.id)))
            or 0
        )

        outreach = (
            db.scalar(select(func.count(OutreachMessage.id)))
            or 0
        )

        orders = (
            db.scalar(
                select(func.count(Order.id))
                .where(
                    Order.status.in_([
                        "PAID",
                        "IN_PRODUCTION",
                        "QC",
                        "READY",
                    ])
                )
            )
            or 0
        )

        revenue = (
            db.scalar(
                select(func.sum(Payment.amount))
                .where(Payment.status == "PAID")
            )
            or 0
        )

        await update.message.reply_text(
            "PIXEL PULSE STUDIO\n"
            "━━━━━━━━━━━━━━━━\n"
            f"🤖 Agent: {'🟢 RUNNING' if campaign else '⚪ IDLE'}\n"
            f"🎯 Active Campaign: "
            f"{campaign.name if campaign else 'None'}\n"
            f"📊 Prospects: {prospects}\n"
            f"📤 Outreach: {outreach}\n"
            f"💳 Orders: {orders}\n"
            f"💰 Revenue: ${float(revenue):.2f}",
            reply_markup=panel(),
        )

    finally:
        db.close()


async def campaigns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    db = SessionLocal()

    try:
        rows = db.scalars(
            select(Campaign)
            .order_by(Campaign.created_at.desc())
            .limit(10)
        ).all()

        if not rows:
            await update.message.reply_text(
                "No campaigns."
            )
            return

        text = "\n".join(
            f"{c.campaign_id} — "
            f"{c.status} — "
            f"{c.completed_prospects}/"
            f"{c.target_prospects}"
            for c in rows
        )

        await update.message.reply_text(text)

    finally:
        db.close()


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    campaign_id = (
        context.args[0]
        if context.args
        else None
    )

    db = SessionLocal()

    try:
        if campaign_id:
            campaign = campaign_service.set_status(
                db,
                campaign_id,
                "RUNNING",
            )
        else:
            campaign = db.scalar(
                select(Campaign)
                .where(Campaign.status == "PAUSED")
                .order_by(Campaign.created_at.desc())
            )

            if campaign:
                campaign.status = "RUNNING"
                db.commit()

        await update.message.reply_text(
            f"Campaign {campaign.campaign_id} is RUNNING."
            if campaign
            else "No paused campaign found."
        )

    finally:
        db.close()


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    db = SessionLocal()

    try:
        campaign = db.scalar(
            select(Campaign)
            .where(Campaign.status == "RUNNING")
            .order_by(Campaign.created_at.desc())
        )

        if campaign:
            campaign.status = "PAUSED"
            db.commit()

        await update.message.reply_text(
            f"Paused {campaign.campaign_id}."
            if campaign
            else "No running campaign."
        )

    finally:
        db.close()


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    db = SessionLocal()

    try:
        campaigns = db.scalars(
            select(Campaign)
            .where(Campaign.status == "RUNNING")
        ).all()

        for campaign in campaigns:
            campaign.status = "STOPPED"

        db.commit()

        await update.message.reply_text(
            "Prospecting and outreach stopped.\n"
            "Existing paid orders remain intact."
        )

    finally:
        db.close()


async def emergency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    db = SessionLocal()

    try:
        campaigns = db.scalars(
            select(Campaign)
            .where(Campaign.status == "RUNNING")
        ).all()

        for campaign in campaigns:
            campaign.status = "PAUSED"

        db.commit()

        await update.message.reply_text(
            "🚨 EMERGENCY STOP ACTIVE\n\n"
            "Prospecting stopped.\n"
            "Outreach stopped.\n"
            "Follow-ups stopped.\n"
            "New payment requests stopped.\n\n"
            "Paid orders are untouched."
        )

    finally:
        db.close()


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /cancel <campaign_id>"
        )
        return

    campaign_id = context.args[0]

    db = SessionLocal()

    try:
        campaign = campaign_service.set_status(
            db,
            campaign_id,
            "CANCELLED",
        )

        await update.message.reply_text(
            f"Cancelled {campaign_id}."
            if campaign
            else "Campaign not found."
        )

    finally:
        db.close()


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /restart <campaign_id>"
        )
        return

    campaign_id = context.args[0]

    db = SessionLocal()

    try:
        campaign = campaign_service.set_status(
            db,
            campaign_id,
            "RUNNING",
        )

        await update.message.reply_text(
            f"Restarted {campaign_id}."
            if campaign
            else "Campaign not found."
        )

    finally:
        db.close()


async def leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    db = SessionLocal()

    try:
        rows = db.scalars(
            select(Prospect)
            .where(
                Prospect.qualification_score
                >= settings.MIN_QUALIFICATION_SCORE
            )
            .order_by(Prospect.created_at.desc())
            .limit(10)
        ).all()

        if not rows:
            await update.message.reply_text(
                "No qualified leads yet."
            )
            return

        text = "\n".join(
            f"{p.id}. {p.company_name} — "
            f"{p.service_match} — "
            f"{p.qualification_score}/100"
            for p in rows
        )

        await update.message.reply_text(text)

    finally:
        db.close()


async def orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    db = SessionLocal()

    try:
        rows = db.scalars(
            select(Order)
            .order_by(Order.created_at.desc())
            .limit(10)
        ).all()

        if not rows:
            await update.message.reply_text(
                "No orders yet."
            )
            return

        text = "\n".join(
            f"{o.order_id} — "
            f"{o.package} — "
            f"{o.currency} {o.amount:.2f} — "
            f"{o.status}"
            for o in rows
        )

        await update.message.reply_text(text)

    finally:
        db.close()


async def revenue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    db = SessionLocal()

    try:
        total = (
            db.scalar(
                select(func.sum(Payment.amount))
                .where(Payment.status == "PAID")
            )
            or 0
        )

        await update.message.reply_text(
            f"Verified revenue: ${float(total):.2f}"
        )

    finally:
        db.close()


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    db = SessionLocal()

    try:
        discovered = (
            db.scalar(select(func.count(Prospect.id)))
            or 0
        )

        qualified = (
            db.scalar(
                select(func.count(Prospect.id))
                .where(Prospect.status == "QUALIFIED")
            )
            or 0
        )

        outreach = (
            db.scalar(
                select(func.count(OutreachMessage.id))
                .where(
                    OutreachMessage.direction == "outbound"
                )
            )
            or 0
        )

        replies = (
            db.scalar(
                select(func.count(OutreachMessage.id))
                .where(
                    OutreachMessage.direction == "inbound"
                )
            )
            or 0
        )

        payments = (
            db.scalar(
                select(func.count(Payment.id))
                .where(Payment.status == "PAID")
            )
            or 0
        )

        orders = (
            db.scalar(select(func.count(Order.id)))
            or 0
        )

        completed = (
            db.scalar(
                select(func.count(Order.id))
                .where(Order.status == "DELIVERED")
            )
            or 0
        )

        total = (
            db.scalar(
                select(func.sum(Payment.amount))
                .where(Payment.status == "PAID")
            )
            or 0
        )

        await update.message.reply_text(
            f"Prospects discovered: {discovered}\n"
            f"Prospects qualified: {qualified}\n"
            f"Outreach sent: {outreach}\n"
            f"Replies: {replies}\n"
            f"Payments: {payments}\n"
            f"Orders: {orders}\n"
            f"Completed orders: {completed}\n"
            f"Revenue: ${float(total):.2f}"
        )

    finally:
        db.close()


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    await update.message.reply_text(
        f"Currency: {settings.SERVICE_CURRENCY}\n"
        f"Starter: ${settings.STARTER_PRICE}\n"
        f"Professional: ${settings.PROFESSIONAL_PRICE}\n"
        f"Premium: ${settings.PREMIUM_PRICE}\n"
        f"Daily prospects: {settings.MAX_DAILY_PROSPECTS}\n"
        f"Daily outreach: {settings.MAX_DAILY_OUTREACH}\n"
        f"Hourly outreach: {settings.MAX_HOURLY_OUTREACH}\n"
        f"Qualification threshold: "
        f"{settings.MIN_QUALIFICATION_SCORE}\n"
        f"TEST_MODE: {settings.TEST_MODE}\n"
        f"FULL_AUTO: {settings.FULL_AUTO}"
    )


async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    await update.message.reply_text(
        "🟢 Pixel Pulse Studio API is configured.\n"
        "Use /api/health for the health check."
    )


async def natural(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return

    text = (update.message.text or "").lower()

    if "emergency" in text or "stop everything" in text:
        return await emergency(update, context)

    if "pause" in text:
        return await pause(update, context)

    if "resume" in text:
        return await resume(update, context)

    match = re.search(
        r"(?:find|hunt)\s+(\d+)"
        r"(?:\s+prospects)?"
        r"(?:\s+over\s+(\d+)\s*"
        r"(day|days|week|weeks))?",
        text,
    )

    if match:
        target = match.group(1)
        number = int(match.group(2) or 1)

        days = (
            number * 7
            if "week" in (match.group(3) or "")
            else number
        )

        context.args = [
            target,
            f"{days}d",
        ]

        return await hunt(update, context)

    await update.message.reply_text(
        'Try: "find 500 prospects over 7 days", '
        '"pause everything", "resume", or "stop hunting".'
    )


def build_bot():
    if not settings.TELEGRAM_BOT_TOKEN:
        return None

    application = (
        Application
        .builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("hunt", hunt)
    )

    application.add_handler(
        CommandHandler("status", status)
    )

    application.add_handler(
        CommandHandler("campaigns", campaigns)
    )

    application.add_handler(
        CommandHandler("resume", resume)
    )

    application.add_handler(
        CommandHandler("pause", pause)
    )

    application.add_handler(
        CommandHandler("stop", stop)
    )

    application.add_handler(
        CommandHandler("cancel", cancel)
    )

    application.add_handler(
        CommandHandler("restart", restart)
    )

    application.add_handler(
        CommandHandler("leads", leads)
    )

    application.add_handler(
        CommandHandler("orders", orders_cmd)
    )

    application.add_handler(
        CommandHandler("revenue", revenue)
    )

    application.add_handler(
        CommandHandler("stats", stats)
    )

    application.add_handler(
        CommandHandler("settings", settings_cmd)
    )

    application.add_handler(
        CommandHandler("health", health_cmd)
    )

    application.add_handler(
        CommandHandler(
            "emergency_stop",
            emergency,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            natural,
        )
    )

    return application
