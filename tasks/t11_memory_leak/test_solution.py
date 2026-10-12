import gc
import tracemalloc

from solution import EventBus, ThumbnailService

PAYLOAD = bytes(range(256)) * 40  # ~10 КБ на запит


def traced_growth(service, warmup=500, measured=3000):
    """Зростання пам'яті Python між warmup-го та останнім запитом, байт."""
    gc.collect()
    tracemalloc.start()
    try:
        for i in range(warmup):
            service.handle(i, i % 7, 64, PAYLOAD)
        gc.collect()
        before = tracemalloc.get_traced_memory()[0]
        for i in range(warmup, warmup + measured):
            service.handle(i, i % 7, 64, PAYLOAD)
        gc.collect()
        return tracemalloc.get_traced_memory()[0] - before
    finally:
        tracemalloc.stop()


def test_memory_does_not_grow_with_number_of_requests():
    growth = traced_growth(ThumbnailService(EventBus()))
    assert growth < 200_000, f"+{growth // 1024} КБ за 3000 запитів: десь лишається посилання на кожен запит"


def test_no_subscriptions_left_after_request():
    bus = EventBus()
    service = ThumbnailService(bus)
    for i in range(50):
        service.handle(i, i, 32, PAYLOAD)
    assert bus.listener_count() == 0


def test_subscription_is_removed_even_if_a_listener_fails():
    bus = EventBus()
    service = ThumbnailService(bus)
    bus.subscribe(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        service.handle(1, 1, 32, PAYLOAD)
    except RuntimeError:
        pass
    assert bus.listener_count() == 1  # лишився тільки чужий підписник, не підписка запиту


def test_cache_is_shared_between_requests_of_same_user_and_size():
    service = ThumbnailService(EventBus())
    first = service.handle(1, 7, 64, PAYLOAD)
    again = service.handle(2, 7, 64, PAYLOAD)
    assert again == first
    assert service.compute_count == 1
    service.handle(3, 7, 32, PAYLOAD)  # інший розмір: новий розрахунок
    assert service.compute_count == 2


def test_cache_is_bounded_and_evicts_least_recently_used():
    service = ThumbnailService(EventBus(), cache_size=3)
    for user in (1, 2, 3):
        service.handle(user, user, 16, PAYLOAD)
    service.handle(10, 1, 16, PAYLOAD)  # користувач 1 знову «свіжий»
    service.handle(11, 4, 16, PAYLOAD)  # витісняє користувача 2
    assert service.cache_len() == 3
    computed = service.compute_count
    service.handle(12, 1, 16, PAYLOAD)
    service.handle(13, 3, 16, PAYLOAD)
    assert service.compute_count == computed, "1 і 3 мали лишитись у кеші"
    service.handle(14, 2, 16, PAYLOAD)
    assert service.compute_count == computed + 1, "2 мав бути витіснений"
