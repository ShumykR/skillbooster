"""Завдання №62: GDPR: експорт і видалення даних користувача.

`db` це словник таблиць (списки словників):
  users(id, email, name, phone, password_hash, ...), addresses(id, user_id, street, city),
  orders(id, user_id, amount, currency, created_at, email, shipping_name, shipping_address, invoice_number),
  messages(id, author_id, to_user_id, text), audit_log(id, user_id, action, ip, at),
  deletion_requests(pseudonym, at).
Поля, що починаються з "_" (внутрішні нотатки), і SECRET_FIELDS це не дані для видачі.

export_user_data(db, user_id) -> dict   (право доступу, ст. 15)
    UserNotFound, якщо такого користувача немає. Результат придатний для json.dumps:
    {"user": {...}, "addresses": [...], "orders": [...], "messages": [...], "audit_log": [...]}
    * "user": рядок користувача; "addresses", "orders", "audit_log": рядки з його `user_id`;
      "messages": лише ті, де він автор (`author_id`); листи ІНШИХ людей до нього це їхні персональні дані;
    * без полів на "_" та з SECRET_FIELDS; це копії, db не змінюється; чужі дані не потрапляють.

delete_user(db, user_id, *, pepper, now) -> dict   (право на забуття, ст. 17)
    pseudonym = "deleted-" + перші 12 hex SHA-256(f"{pepper}:{user_id}") (стабільний, але без `pepper` не відновлюється).
    * якщо в `deletion_requests` уже є цей pseudonym: нічого не робить, повертає {"status": "already_deleted"};
      інакше якщо користувача немає: UserNotFound;
    * ВИДАЛЯЄ: рядок users, усі addresses, усі messages, де він автор;
    * ЗБЕРІГАЄ, але знеособлює (закон вимагає зберігати бухгалтерські записи): orders (user_id := pseudonym;
      email, shipping_name, shipping_address := None; сума, валюта, дата, invoice_number лишаються);
      audit_log (user_id := pseudonym, ip := None); messages від інших людей до нього (to_user_id := pseudonym);
    * додає в `deletion_requests` {"pseudonym": ..., "at": now} без персональних даних (ні email, ні user_id);
    * повертає {"status": "deleted", "pseudonym": ..., "removed": {"users": n, "addresses": n, "messages": n},
      "anonymized": {"orders": n, "audit_log": n, "messages_received": n}};
    * дані інших користувачів не змінюються.
"""
import hashlib  # noqa: F401

SECRET_FIELDS = {"password_hash", "totp_secret"}


class UserNotFound(Exception):
    pass


def export_user_data(db: dict, user_id: int) -> dict:
    raise NotImplementedError


def delete_user(db: dict, user_id: int, *, pepper: str, now: float) -> dict:
    raise NotImplementedError
