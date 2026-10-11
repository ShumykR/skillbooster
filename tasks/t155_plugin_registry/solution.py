"""Завдання №155: Factory + автореєстрація плагінів через `__init_subclass__`.

Замість `if fmt == "csv": ... elif fmt == "json": ...` кожен плагін сам оголошує себе одним рядком у `class`.

    class Exporter(Registered): ...                  # ПРЯМИЙ нащадок Registered це корінь НОВОГО реєстру
    class CsvExporter(Exporter, key="csv"): ...      # нащадок з key= потрапляє в реєстр свого кореня
    class Importer(Registered): ...                  # інший корінь: окремий реєстр
    Exporter.create("csv", sep=";")                  # -> CsvExporter(sep=";")

Правила `Registered`:
    * корінь (прямий нащадок `Registered`) отримує власний порожній реєстр; самого `Registered` у реєстрах немає;
    * клас з `key=` (на будь-якій глибині нащадків кореня) реєструється під цим ключем у реєстрі кореня;
      клас без `key=` НЕ реєструється (абстрактна проміжна ланка), але його нащадки можуть мати власні ключі;
    * ключ це непорожній рядок, інакше TypeError; той самий ключ двічі в одному корені: ValueError
      (клас при цьому НЕ створюється, реєстр не змінюється); в різних коренях ключі незалежні;
    * `Root.create(key, *args, **kwargs)` повертає `registered_class(*args, **kwargs)`; доступний на корені й
      на будь-якому нащадку (завжди шукає в реєстрі кореня);
    * `Root.get(key)` повертає клас; невідомий ключ: `UnknownKey` (підклас KeyError), у повідомленні
      перелічено доступні ключі (відсортовані);
    * `Root.keys()` повертає відсортований список ключів;
    * інші іменовані аргументи класу (`class X(Root, key="a", color="red")`) передаються далі в
      `super().__init_subclass__`, тож кооперативне множинне успадкування не ламається;
    * реєстри не спільні між кореневими класами і не «протікають» через `Registered`.
"""


class UnknownKey(KeyError):
    pass


class Registered:
    def __init_subclass__(cls, *, key=None, **kwargs):
        raise NotImplementedError

    @classmethod
    def create(cls, key, *args, **kwargs):
        raise NotImplementedError

    @classmethod
    def get(cls, key):
        raise NotImplementedError

    @classmethod
    def keys(cls) -> list[str]:
        raise NotImplementedError
