import asyncio
import os
from sqlalchemy import select
from app.core.logging import events
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import Campaign, Order, Prospect
from app.services.campaigns import CampaignService

s = get_settings()
cs = CampaignService()


def build_bot():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return None
    try:
        from telegram.ext import Application
        return Application.builder().token(token).build()
    except Exception as e:
        events.event("ERROR", component="telegram_init", error=str(e))
        return None


def allowed(update):
    allowed_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
    return bool(allowed_id and update.effective_chat and str(update.effective_chat.id) == str(allowed_id))


def fmt_order(o):
    return f"{o.order_id} — {o.package} — {o.currency} {o.amount:.2f} — {o.status}"


async def run_bot():
    from telegram.ext import CommandHandler
    bot = build_bot()
    if bot is None:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    async def start(update, context):
        if not allowed(update): return
        await update.message.reply_text(
            "Pixel Pulse Studio is online.\n\n"
            "Commands:\n"
            "/status\n/campaigns\n/prospects\n/orders\n"
            "/neworder STARTER|Name|Company|email|PROSPECT_ID\n"
            "/order ORDER_ID\n/generate ORDER_ID"
        )

    async def status(update, context):
        if not allowed(update): return
        db = SessionLocal()
        try:
            running = db.scalar(select(Campaign).where(Campaign.status == "RUNNING").order_by(Campaign.created_at.desc()))
            orders = db.scalars(select(Order).order_by(Order.created_at.desc()).limit(5)).all()
            prospects = db.scalars(select(Prospect).order_by(Prospect.created_at.desc()).limit(5)).all()
            text = f"Agent: {'RUNNING' if running else 'IDLE'}\n"
            text += f"Campaign: {running.campaign_id if running else 'None'}\n\nRecent prospects:\n"
            text += "\n".join(f"{p.id}. {p.company_name} — {p.service_match} — score {p.qualification_score}" for p in prospects) or "None"
            text += "\n\nRecent orders:\n" + ("\n".join(fmt_order(o) for o in orders) or "No orders found.")
            await update.message.reply_text(text)
        finally:
            db.close()

    async def campaigns(update, context):
        if not allowed(update): return
        db = SessionLocal()
        try:
            rows = db.scalars(select(Campaign).order_by(Campaign.created_at.desc()).limit(10)).all()
            await update.message.reply_text("\n".join(f"{c.campaign_id} | {c.status} | {c.name} | {c.remaining_prospects} remaining" for c in rows) or "No campaigns found.")
        finally:
            db.close()

    async def prospects(update, context):
        if not allowed(update): return
        db = SessionLocal()
        try:
            rows = db.scalars(select(Prospect).order_by(Prospect.created_at.desc()).limit(10)).all()
            await update.message.reply_text("Recent prospects:\n" + ("\n".join(f"{p.id}. {p.company_name} — {p.service_match} — score {p.qualification_score}" for p in rows) or "None"))
        finally:
            db.close()

    async def orders(update, context):
        if not allowed(update): return
        db = SessionLocal()
        try:
            rows = db.scalars(select(Order).order_by(Order.created_at.desc()).limit(10)).all()
            await update.message.reply_text("Recent orders:\n" + ("\n".join(fmt_order(o) for o in rows) or "No orders found."))
        finally:
            db.close()

    async def neworder(update, context):
        if not allowed(update): return
        raw = " ".join(context.args).strip()
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < 4:
            await update.message.reply_text("Usage:\n/neworder STARTER|Name|Company|email|PROSPECT_ID\n\nPackages: STARTER, PROFESSIONAL, PREMIUM")
            return
        package, name, company, email = [p for p in parts[:4]]
        prospect_id = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else None
        package = package.upper()
        prices = {"STARTER": s.STARTER_PRICE, "PROFESSIONAL": s.PROFESSIONAL_PRICE, "PREMIUM": s.PREMIUM_PRICE}
        if package not in prices:
            await update.message.reply_text("Invalid package. Use STARTER, PROFESSIONAL, or PREMIUM.")
            return
        db = SessionLocal()
        try:
            from app.models.entities import Customer, Payment
            import uuid
            from app.services.flutterwave import FlutterwaveService
            cust = Customer(name=name, company_name=company, email=email, prospect_id=prospect_id)
            db.add(cust); db.flush()
            o = Order(order_id="PPS-ORD-" + uuid.uuid4().hex[:12].upper(), customer_id=cust.id, prospect_id=prospect_id, package=package, amount=prices[package], currency=s.SERVICE_CURRENCY, status="PENDING")
            db.add(o); db.flush()
            ref = "PPS-" + o.order_id + "-" + uuid.uuid4().hex[:6].upper()
            pay = Payment(payment_id="PAY-" + uuid.uuid4().hex[:10], order_id=o.id, reference=ref, amount=o.amount, currency=o.currency)
            db.add(pay); db.commit()
            try:
                result = await FlutterwaveService().create_payment(ref, o.amount, o.currency, email, name, o.order_id)
                pay.payment_url = result.get("link")
                db.commit()
            except Exception as e:
                db.rollback()
                await update.message.reply_text(f"Order created but payment link failed:\n{o.order_id}\n{e}")
                return
            await update.message.reply_text(f"ORDER CREATED\n\nOrder: {o.order_id}\nPackage: {package}\nAmount: {o.currency} {o.amount:.2f}\nStatus: {o.status}\n\nPayment link:\n{pay.payment_url or 'Not returned'}")
        finally:
            db.close()

    async def order(update, context):
        if not allowed(update): return
        oid = context.args[0] if context.args else None
        if not oid:
            await update.message.reply_text("Usage: /order PPS-ORD-XXXXXXXXXXXX")
            return
        db = SessionLocal()
        try:
            o = db.scalar(select(Order).where(Order.order_id == oid))
            await update.message.reply_text(fmt_order(o) if o else "Order not found.")
        finally:
            db.close()

    async def generate(update, context):
        if not allowed(update): return
        oid = context.args[0] if context.args else None
        if not oid:
            await update.message.reply_text("Usage: /generate PPS-ORD-XXXXXXXXXXXX")
            return
        db = SessionLocal()
        try:
            o = db.scalar(select(Order).where(Order.order_id == oid))
            if not o:
                await update.message.reply_text("Order not found.")
                return
            if o.status not in ("PAID", "IN_PRODUCTION", "QC", "READY"):
                await update.message.reply_text(f"Order is {o.status}. Payment must be verified before presentation generation.")
                return
            from app.services.presentation import PresentationService
            project = PresentationService().generate(db, o.id)
            await update.message.reply_text(f"PRESENTATION GENERATED\nOrder: {oid}\nStatus: {project.status}\nSlides: {len(project.strategy_json.get('slides', []))}")
        except Exception as e:
            await update.message.reply_text(f"Generation failed: {e}")
        finally:
            db.close()

    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CommandHandler("status", status))
    bot.add_handler(CommandHandler("campaigns", campaigns))
    bot.add_handler(CommandHandler("prospects", prospects))
    bot.add_handler(CommandHandler("orders", orders))
    bot.add_handler(CommandHandler("neworder", neworder))
    bot.add_handler(CommandHandler("order", order))
    bot.add_handler(CommandHandler("generate", generate))

    await bot.initialize()
    await bot.bot.delete_webhook(drop_pending_updates=True)
    await bot.start()
    await bot.updater.start_polling(drop_pending_updates=True)
    try:
        await asyncio.Event().wait()
    finally:
        await bot.updater.stop(); await bot.stop(); await bot.shutdown()


def main():
    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
