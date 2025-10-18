# -------------------------------------------------------------------------------------
# name        : bb_utils.py
# created     : 16.10.2025 05:45
# description : Фасадные функции для удобного форматирования
# -------------------------------------------------------------------------------------

from typing import Union, List, Any
from bb_fmt import _formatter


def fmt(value: Any, **kwargs) -> str:
    """
    Универсальная функция форматирования данных

    Args:
        value: значение для форматирования (любой тип)
        **kwargs: параметры форматирования

    Returns:
        Отформатированная строка

    Examples:
        >>> fmt(1000000)
        '1 000 000'
        >>> fmt("2023-12-25")
        '25-12-2023'
        >>> fmt(0.15, format_type='%')
        '15,0%'
        >>> fmt(1500000, currency='USD')
        '$1,500,000.00'
    """
    return _formatter.format(value, **kwargs)


def fmt_currency(amount: Union[int, float, str], currency: str = 'RUB', **kwargs) -> str:
    """
    Форматирование валюты (удобный алиас)

    Args:
        amount: денежная сумма
        currency: код валюты (RUB, USD, EUR, GBP, CNY)
        **kwargs: дополнительные параметры форматирования

    Returns:
        Отформатированная денежная сумма

    Examples:
        >>> fmt_currency(1500000)
        '1 500 000,00 ₽'
        >>> fmt_currency(1500000, 'USD')
        '$1,500,000.00'
    """
    if amount == 'show':
        return _formatter._generate_help('fmt_currency')
    return fmt(amount, currency=currency, **kwargs)


def fmt_date(date_str: str, format: str = 'dd-mm-yyyy', **kwargs) -> str:
    """
    Форматирование даты (удобный алиас)

    Args:
        date_str: дата в формате YYYY-MM-DD
        format: формат вывода даты
        **kwargs: дополнительные параметры форматирования

    Returns:
        Отформатированная дата

    Examples:
        >>> fmt_date("2023-12-25")
        '25-12-2023'
        >>> fmt_date("2023-12-25", "dd.mm.yyyy")
        '25.12.2023'
    """
    if date_str == 'show':
        return _formatter._generate_help('fmt_date')
    return fmt(date_str, format_type='date', date_format=format, **kwargs)


def fmt_number(number: Union[int, float, str], **kwargs) -> str:
    """
    Форматирование числа (удобный алиас)

    Args:
        number: число для форматирования
        **kwargs: дополнительные параметры форматирования

    Returns:
        Отформатированное число

    Examples:
        >>> fmt_number(1000000)
        '1 000 000'
        >>> fmt_number(1234567.89)
        '1 234 567,89'
    """
    if number == 'show':
        return _formatter._generate_help('fmt_number')
    return fmt(number, format_type='financial', **kwargs)


def fmt_list(items: List, separator: str = ', ', **kwargs) -> str:
    """
    Форматирование списка (удобный алиас)

    Args:
        items: список для форматирования
        separator: разделитель элементов
        **kwargs: дополнительные параметры форматирования

    Returns:
        Отформатированная строка списка

    Examples:
        >>> fmt_list([1, 2, 3])
        '1, 2, 3'
        >>> fmt_list([1, 2, 3], ' - ')
        '1 - 2 - 3'
    """
    if items == 'show':
        return _formatter._generate_help('fmt_list')
    return fmt(items, array_separator=separator, **kwargs)


# Дополнительные специализированные функции
def fmt_percentage(value: Union[float, str], decimal_places: int = 1, **kwargs) -> str:
    """
    Форматирование процентов (удобный алиас)

    Args:
        value: процентное значение (0.15 для 15%)
        decimal_places: количество знаков после запятой
        **kwargs: дополнительные параметры форматирования

    Returns:
        Отформатированный процент

    Examples:
        >>> fmt_percentage(0.1567)
        '15,7%'
        >>> fmt_percentage(0.15, decimal_places=0)
        '15%'
    """
    if value == 'show':
        return "fmt_percentage(value, decimal_places=1) - форматирование процентов"
    return fmt(value, format_type='%', decimal_places=decimal_places, **kwargs)


def fmt_phone(phone: str, phone_format: str = 'auto', **kwargs) -> str:
    """
    Форматирование телефонного номера (удобный алиас)

    Args:
        phone: номер телефона
        phone_format: формат телефона (auto, ru, us, eu, international)
        **kwargs: дополнительные параметры форматирования

    Returns:
        Отформатированный номер телефона

    Examples:
        >>> fmt_phone('+79161234567')
        '+7 (916) 123-45-67'
        >>> fmt_phone('+441234567890', 'international')
        '+44 1234567890'
    """
    if phone == 'show':
        return "fmt_phone(phone, phone_format='auto') - форматирование телефонных номеров"
    return fmt(phone, format_type='phone', phone_format=phone_format, **kwargs)


def fmt_boolean(value: Any, boolean_format: str = 'true_false', **kwargs) -> str:
    """
    Форматирование булевых значений (удобный алиас)

    Args:
        value: булево значение
        boolean_format: формат вывода (true_false, yes_no, 10, ru, checkmark)
        **kwargs: дополнительные параметры форматирования

    Returns:
        Отформатированное булево значение

    Examples:
        >>> fmt_boolean(True)
        'true'
        >>> fmt_boolean(False, 'ru')
        'нет'
        >>> fmt_boolean(1, 'checkmark')
        '✓'
    """
    if value == 'show':
        return "fmt_boolean(value, boolean_format='true_false') - форматирование булевых значений"
    return fmt(value, format_type='boolean', boolean_format=boolean_format, **kwargs)


# Функция для пакетного форматирования
def fmt_batch(values: List[Any], **kwargs) -> List[str]:
    """
    Пакетное форматирование списка значений

    Args:
        values: список значений для форматирования
        **kwargs: параметры форматирования (применяются ко всем значениям)

    Returns:
        Список отформатированных строк

    Examples:
        >>> fmt_batch([1000, '2023-12-25', 0.15])
        ['1 000', '25-12-2023', '15,0%']
    """
    return [fmt(value, **kwargs) for value in values]


# Демонстрация работы
if __name__ == "__main__":
    print("=== ДЕМОНСТРАЦИЯ РАБОТЫ BB_UTILS ===")

    # Основные примеры
    print("Основные функции:")
    print(f"fmt(1000000): {fmt(1000000)}")
    print(f"fmt('2023-12-25'): {fmt('2023-12-25')}")
    print(f"fmt(0.15, format_type='%'): {fmt(0.15, format_type='%')}")

    print("\nСпециализированные функции:")
    print(f"fmt_currency(1500000, 'USD'): {fmt_currency(1500000, 'USD')}")
    print(f"fmt_date('2023-12-25', 'dd.mm.yyyy'): {fmt_date('2023-12-25', 'dd.mm.yyyy')}")
    print(f"fmt_number(1234567.89): {fmt_number(1234567.89)}")
    print(f"fmt_list([1, 2, 3], ' - '): {fmt_list([1, 2, 3], ' - ')}")

    print("\nДополнительные функции:")
    print(f"fmt_percentage(0.1567): {fmt_percentage(0.1567)}")
    print(f"fmt_phone('+79161234567'): {fmt_phone('+79161234567')}")
    print(f"fmt_boolean(True, 'ru'): {fmt_boolean(True, 'ru')}")

    print("\nПакетное форматирование:")
    mixed_data = [1000, "2023-12-25", 0.15, True, "+79161234567"]
    formatted_batch = fmt_batch(mixed_data)
    print(f"Исходные: {mixed_data}")
    print(f"Форматированные: {formatted_batch}")

    print("\nСправка:")
    print("Для получения справки используйте:")
    print("fmt('show') - справка по основной функции")
    print("fmt_currency('show') - справка по форматированию валют")
    print("fmt_date('show') - справка по форматированию дат")