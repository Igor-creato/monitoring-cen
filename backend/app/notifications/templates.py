from decimal import Decimal, InvalidOperation

from app.notifications.base import NotificationMessage


def render_price_alert(payload: dict) -> NotificationMessage:
    title = payload.get("title") or "Товар"
    currency = payload.get("currency") or ""
    current_price = _format_price(payload.get("current_price"), currency)
    target_price = _format_price(payload.get("target_price"), currency)
    previous_price = _format_price(payload.get("previous_price"), currency)
    url = payload.get("url") or ""

    subject = f"Цена достигла цели: {current_price}"
    lines = [
        f"{title}",
        "",
        f"Текущая цена: {current_price}",
        f"Целевая цена: {target_price}",
    ]
    if previous_price is not None:
        lines.append(f"Предыдущая цена: {previous_price}")
    if url:
        lines.extend(["", f"Ссылка: {url}"])

    return NotificationMessage(
        subject=subject,
        text="\n".join(lines),
        recipient=payload.get("recipient_email") or payload.get("recipient"),
        metadata=payload,
    )


def render_notification(payload: dict) -> NotificationMessage:
    notification_type = payload.get("notification_type")
    if notification_type in {None, "target_reached", "price_drop", "price_changed"}:
        return render_price_alert(payload)

    return NotificationMessage(
        subject="Уведомление мониторинга цен",
        text=str(payload),
        recipient=payload.get("recipient_email") or payload.get("recipient"),
        metadata=payload,
    )


def _format_price(value: object, currency: str) -> str | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        amount_text = str(value)
    else:
        amount_text = f"{amount:,.2f}".replace(",", " ")
        if amount == amount.to_integral_value():
            amount_text = f"{amount:,.0f}".replace(",", " ")

    return f"{amount_text} {currency}".strip()
