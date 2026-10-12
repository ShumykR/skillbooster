"""Завдання №114: Notification service: пріоритети, дедуплікація, тихі години, ретраї та fallback між каналами.

NotificationService(clock, senders, *, max_attempts=3, backoff_base=10, dedupe_window=300)
    senders: {канал: send(user, kind, payload)}; send кидає виняток при невдачі. clock() повертає секунди.
    .set_preferences(user, *, channels=("push", "email"), muted_kinds=(), quiet_hours=None)
        channels: порядок каналів (перший основний, решта fallback); канал, якого немає в senders, або порожній список: ValueError.
        muted_kinds: типи повідомлень, які користувач вимкнув. quiet_hours = (start, end): години UTC 0..23, у яких не турбувати;
        діапазон може переходити через північ (22, 7). start == end або година поза 0..23: ValueError. Година = int(now // 3600) % 24;
        у тихих годинах start <= година < end (або година >= start чи година < end, якщо start > end).
        Користувач без налаштувань має channels ("push", "email"), без muted і quiet_hours.
    .submit(user, kind, payload, *, priority="normal", dedupe_key=None) -> dict
        priority: "critical" < "high" < "normal" < "low" за важливістю; інше: ValueError.
        Результат {"id": номер або None, "status": "queued" | "duplicate" | "muted"}:
          * dedupe_key задано і для (user, dedupe_key) прийняте повідомлення було менше ніж dedupe_window секунд тому
            (відлік від ПЕРШОГО прийнятого, дублікати вікно не продовжують): "duplicate", id None;
          * kind у muted_kinds користувача і priority не "critical": "muted", id None (critical вимкнути не можна);
          * інакше "queued", id = 1, 2, ... (лічильник лише для прийнятих). Перевірка дублікатів іде ПЕРЕД перевіркою muted,
            але вимкнене (muted) повідомлення вікно дедуплікації не відкриває.
    .dispatch() -> list[dict]
        Обробляє повідомлення з available_at <= clock(), порядок: (важливість, available_at, id); кожне не більше одного разу за
        виклик. Повідомлення не-critical пропускаються (лишаються в черзі, подій немає), якщо зараз тихі години користувача.
        Спроба: senders[канал](user, kind, payload). Події {"id", "status", "channel", "attempt"}:
          успіх: "sent" (attempt = номер спроби на цьому каналі, з 1);
          невдача, спроб на каналі < max_attempts: "retry", available_at = clock() + backoff_base * 2 ** (attempt - 1);
          невдача на останній спробі й є наступний канал: "fallback" (channel = канал, що вичерпався), далі наступний канал із
          спроби 1 і available_at = clock();
          невдача на останній спробі останнього каналу: "failed".
    .status(id) -> "queued" | "sent" | "failed"       невідомий id: KeyError.
    .sent -> list[tuple[int, str]]                    (id, канал) у порядку успішних відправлень.
"""

PRIORITIES = ("critical", "high", "normal", "low")


class NotificationService:
    def __init__(self, clock, senders: dict, *, max_attempts: int = 3, backoff_base: float = 10, dedupe_window: float = 300) -> None:
        raise NotImplementedError

    def set_preferences(self, user: str, *, channels=("push", "email"), muted_kinds=(), quiet_hours=None) -> None:
        raise NotImplementedError

    def submit(self, user: str, kind: str, payload, *, priority: str = "normal", dedupe_key: str | None = None) -> dict:
        raise NotImplementedError

    def dispatch(self) -> list[dict]:
        raise NotImplementedError

    def status(self, notification_id: int) -> str:
        raise NotImplementedError

    @property
    def sent(self) -> list[tuple[int, str]]:
        raise NotImplementedError
