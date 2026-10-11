"""Завдання №161: безпечний розбір XML (XXE: CWE-611, billion laughs: CWE-776).

XML дозволяє в `<!DOCTYPE ...>` оголошувати СУТНОСТІ: зовнішні (`<!ENTITY x SYSTEM "file:///etc/passwd">`, парсер
прочитає файл чи піде в мережу) і вкладені (`lol9` розкривається в мільярди рядків). Коли XML приходить від
користувача (SAML, SOAP, завантажений документ), його не можна віддавати парсеру «як є».

`parse_xml_safely(data, *, max_bytes=1_000_000, max_depth=50, max_nodes=10_000) -> xml.etree.ElementTree.Element`
    * `data` це bytes або str (str кодується в UTF-8); інший тип: TypeError;
    * довжина в БАЙТАХ більша за `max_bytes`: `TooLarge` ДО будь-якого розбору;
    * будь-яке оголошення DOCTYPE (а отже будь-яке оголошення сутностей, зовнішній DTD, параметричні сутності)
      це `UnsafeXML`. Це не залежить від кодування документа (UTF-16 теж). Рядок `<!DOCTYPE` усередині коментаря
      чи CDATA НЕ є оголошенням: такий документ розбирається нормально;
    * глибина вкладеності більша за `max_depth` (корінь має глибину 1) або кількість елементів більша за `max_nodes`:
      `TooLarge`; перевірка йде ПІД ЧАС розбору й зупиняє його одразу (документ із мільйоном вкладених елементів
      не повинен ні рахуватись повністю, ні давати RecursionError);
    * порожній вхід, неправильна розмітка, невизначена сутність (`&foo;`), зайве після кореня: `MalformedXML`
      (не `ParseError` і не `ExpatError`);
    * стандартні сутності (`&lt; &gt; &amp; &quot; &apos;`) і числові (`&#65;`) працюють; коментарі та
      інструкції обробки дозволені й до дерева не потрапляють;
    * простори імен як у ElementTree: тег `{uri}name`, атрибути так само;
    * жодних звернень до файлової системи й мережі.
Усі три помилки це підкласи ValueError.
"""
import xml.etree.ElementTree as ET


class UnsafeXML(ValueError):
    pass


class TooLarge(ValueError):
    pass


class MalformedXML(ValueError):
    pass


def parse_xml_safely(data, *, max_bytes: int = 1_000_000, max_depth: int = 50, max_nodes: int = 10_000) -> ET.Element:
    raise NotImplementedError
