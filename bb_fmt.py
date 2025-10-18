# -------------------------------------------------------------------------------------
# name        : bb_fmt.py
# created     : 16.10.2025 05:45
# description : Базовая логика универсального форматирования данных (Python)
# -------------------------------------------------------------------------------------

import re
from datetime import datetime, date
from typing import Union, Optional, List, Any, Dict
from decimal import Decimal, InvalidOperation


class UniversalFormatter:
    """
    Универсальный форматировщик данных с расширенными возможностями
    """

    def __init__(self):
        self.supported_currencies = {
            'RUB': {'symbol': '₽', 'format': '{amount} {symbol}', 'position': 'after'},
            'USD': {'symbol': '$', 'format': '{symbol}{amount}', 'position': 'before'},
            'EUR': {'symbol': '€', 'format': '{symbol}{amount}', 'position': 'before'},
            'GBP': {'symbol': '£', 'format': '{symbol}{amount}', 'position': 'before'},
            'CNY': {'symbol': '¥', 'format': '{symbol}{amount}', 'position': 'before'},
        }

        self.phone_formats = {
            'ru': '+7 ({xxx}) {yyy}-{zz}-{aa}',
            'us': '+1 ({xxx}) {yyy}-{zzzz}',
            'eu': '+{cc} {xxx} {yyyyyy}',
            'international': '+{cc} {number}'
        }

    def format(
            self,
            value: Any,
            format_type: Optional[str] = None,
            # Числовые форматы
            financial_separator: str = ' ',
            decimal_separator: str = ',',
            decimal_places: Optional[int] = None,
            # Форматы даты/времени
            date_format: str = 'dd-mm-yyyy',
            time_format: str = 'HH:MM:SS',
            datetime_format: str = 'dd-mm-yyyy HH:MM:SS',
            # Валютные форматы
            currency: Optional[str] = None,
            currency_format: Optional[str] = None,
            # Текстовые форматы
            text_case: Optional[str] = None,
            text_trim: bool = False,
            text_max_length: Optional[int] = None,
            # Форматы массивов
            array_separator: str = ', ',
            array_prefix: str = '',
            array_suffix: str = '',
            # Специальные форматы
            phone_format: Optional[str] = None,
            boolean_format: str = 'true_false',
            null_value: str = '',
            # Проценты
            percent_format: str = 'symbol',
            # Дополнительные опции
            strip_html: bool = False,
            escape_special: bool = False,
            custom_format: Optional[str] = None
    ) -> str:
        """
        Универсальное форматирование данных
        """

        # Обработка команды help
        if value == 'show':
            return self._generate_help('fmt')

        # Обработка пустых значений
        if value is None:
            return null_value

        # Синоним для percentage
        if format_type == '%':
            format_type = 'percentage'

        # Определение типа данных
        if format_type is None or format_type == 'auto':
            format_type = self._detect_format_type(value)

        # Применение кастомного формата если указан
        if custom_format:
            return self._apply_custom_format(value, custom_format)

        # Форматирование в зависимости от типа
        if format_type == 'array':
            return self._format_array(value, **self._get_format_kwargs(locals()))
        elif format_type == 'date':
            return self._format_date(value, date_format)
        elif format_type == 'time':
            return self._format_time(value, time_format)
        elif format_type == 'datetime':
            return self._format_datetime(value, datetime_format)
        elif format_type == 'financial':
            return self._format_financial(value, financial_separator, decimal_separator, decimal_places)
        elif format_type == 'currency':
            return self._format_currency(value, currency, currency_format)
        elif format_type == 'percentage':
            return self._format_percentage(value, percent_format, decimal_places)
        elif format_type == 'phone':
            return self._format_phone(value, phone_format)
        elif format_type == 'boolean':
            return self._format_boolean(value, boolean_format)
        elif format_type == 'text':
            return self._format_text(value, text_case, text_trim, text_max_length, strip_html, escape_special)
        else:
            return self._format_unknown(value)

    def _detect_format_type(self, value: Any) -> str:
        """Определяет тип данных для автоматического форматирования"""

        if isinstance(value, (list, tuple)):
            return 'array'
        elif isinstance(value, datetime):
            return 'datetime'
        elif isinstance(value, date):
            return 'date'
        elif isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, (int, float, Decimal)):
            if 0 <= float(value) <= 1:
                return 'percentage'
            return 'financial'
        elif isinstance(value, str):
            if self._is_date_string(value):
                return 'date'
            elif self._is_datetime_string(value):
                return 'datetime'
            elif self._is_phone_number(value):
                return 'phone'
            elif self._is_currency_string(value):
                return 'currency'
            elif value.lower() in ('true', 'false', 'yes', 'no', '1', '0'):
                return 'boolean'
            elif self._is_numeric_string(value):
                return 'financial'
            else:
                return 'text'
        else:
            return 'unknown'

    def _format_financial(
            self,
            number: Union[str, int, float],
            thousands_sep: str = ' ',
            decimal_sep: str = ',',
            decimal_places: Optional[int] = None
    ) -> str:
        """Расширенное форматирование чисел с поддержкой любых разделителей"""

        try:
            # Преобразуем в число
            if isinstance(number, str):
                # Очищаем число от любых существующих разделителей
                clean_number = re.sub(r'[^\d\.\-]', '', number)
                # Заменяем запятую на точку для корректного преобразования
                clean_number = clean_number.replace(',', '.')
                num_value = Decimal(clean_number)
            else:
                num_value = Decimal(str(number))

            # Автоматическое определение количества знаков после запятой
            if decimal_places is None:
                if num_value == num_value.to_integral():
                    decimal_places = 0
                else:
                    decimal_places = min(abs(num_value.as_tuple().exponent), 6)

            # Форматирование с поддержкой любых разделителей
            if decimal_places == 0:
                formatted = f"{int(num_value):,}".replace(',', 'TEMP_THOUSANDS')
                formatted = formatted.replace('TEMP_THOUSANDS', thousands_sep)
            else:
                format_string = f"{{:,.{decimal_places}f}}"
                formatted = format_string.format(float(num_value))
                formatted = formatted.replace(',', 'TEMP_THOUSANDS').replace('.', 'TEMP_DECIMAL')
                formatted = formatted.replace('TEMP_THOUSANDS', thousands_sep).replace('TEMP_DECIMAL', decimal_sep)

            return formatted

        except (ValueError, InvalidOperation, TypeError):
            return str(number)

    def _format_currency(
            self,
            value: Union[str, int, float],
            currency_code: Optional[str] = None,
            currency_format: Optional[str] = None
    ) -> str:
        """Форматирование валюты"""

        try:
            amount = Decimal(str(value))

            if currency_code and currency_code.upper() in self.supported_currencies:
                currency = self.supported_currencies[currency_code.upper()]

                if currency_format:
                    format_template = currency_format
                else:
                    format_template = currency['format']

                formatted_amount = self._format_financial(amount, decimal_places=2)

                return format_template.format(
                    symbol=currency['symbol'],
                    amount=formatted_amount,
                    code=currency_code.upper()
                )
            else:
                return self._format_financial(amount, decimal_places=2)

        except (ValueError, InvalidOperation):
            return str(value)

    def _format_percentage(
            self,
            value: Union[str, int, float],
            percent_format: str = 'symbol',
            decimal_places: Optional[int] = None
    ) -> str:
        """Форматирование процентов"""

        try:
            number = Decimal(str(value)) * 100

            if decimal_places is None:
                decimal_places = 1

            formatted_number = self._format_financial(number, decimal_places=decimal_places)

            if percent_format == 'symbol':
                return f"{formatted_number}%"
            elif percent_format == 'word':
                return f"{formatted_number} percent"
            else:
                return formatted_number

        except (ValueError, InvalidOperation):
            return str(value)

    def _format_phone(self, phone: str, phone_format: Optional[str] = None) -> str:
        """Форматирование телефонных номеров"""

        clean_phone = re.sub(r'[^\d+]', '', phone)

        if phone_format and phone_format in self.phone_formats:
            format_template = self.phone_formats[phone_format]
        else:
            if clean_phone.startswith('+7') or clean_phone.startswith('7'):
                format_template = self.phone_formats['ru']
            elif clean_phone.startswith('+1') or clean_phone.startswith('1'):
                format_template = self.phone_formats['us']
            else:
                format_template = self.phone_formats['international']

        if format_template == self.phone_formats['ru']:
            if len(clean_phone) >= 11:
                if clean_phone.startswith('+7'):
                    part1 = clean_phone[2:5]  # 916
                    part2 = clean_phone[5:8]  # 123
                    part3 = clean_phone[8:10]  # 45
                    part4 = clean_phone[10:12]  # 67
                else:
                    part1 = clean_phone[1:4]  # 916
                    part2 = clean_phone[4:7]  # 123
                    part3 = clean_phone[7:9]  # 45
                    part4 = clean_phone[9:11]  # 67
                return f"+7 ({part1}) {part2}-{part3}-{part4}"

        return clean_phone

    def _format_boolean(self, value: Any, boolean_format: str = 'true_false') -> str:
        """Форматирование булевых значений"""

        bool_value = bool(value)

        formats = {
            'true_false': ('true', 'false'),
            'yes_no': ('yes', 'no'),
            '10': ('1', '0'),
            'on_off': ('on', 'off'),
            'enabled_disabled': ('enabled', 'disabled'),
            'ru': ('да', 'нет'),
            'checkmark': ('✓', '✗')
        }

        true_str, false_str = formats.get(boolean_format, ('true', 'false'))
        return true_str if bool_value else false_str

    def _format_text(
            self,
            text: str,
            text_case: Optional[str] = None,
            text_trim: bool = False,
            text_max_length: Optional[int] = None,
            strip_html: bool = False,
            escape_special: bool = False
    ) -> str:
        """Форматирование текста"""

        result = str(text)

        if strip_html:
            result = re.sub(r'<[^>]+>', '', result)

        if escape_special:
            result = result.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        if text_trim:
            result = result.strip()

        if text_case == 'lower':
            result = result.lower()
        elif text_case == 'upper':
            result = result.upper()
        elif text_case == 'title':
            result = result.title()
        elif text_case == 'capitalize':
            result = result.capitalize()

        if text_max_length and len(result) > text_max_length:
            result = result[:text_max_length - 3] + '...'

        return result

    def _format_array(
            self,
            array: Union[List, tuple],
            array_separator: str = ', ',
            array_prefix: str = '',
            array_suffix: str = '',
            **format_kwargs
    ) -> str:
        """Форматирование массивов"""

        formatted_items = []
        for item in array:
            formatted_item = self.format(item, **format_kwargs)
            formatted_items.append(formatted_item)

        result = array_separator.join(formatted_items)
        return f"{array_prefix}{result}{array_suffix}"

    def _is_date_string(self, value: str) -> bool:
        """Проверяет, является ли строка датой"""
        patterns = [
            r'^\d{4}-\d{2}-\d{2}$',
            r'^\d{2}\.\d{2}\.\d{4}$',
            r'^\d{2}/\d{2}/\d{4}$',
        ]
        return any(re.match(pattern, value) for pattern in patterns)

    def _is_datetime_string(self, value: str) -> bool:
        """Проверяет, является ли строка датой-временем"""
        patterns = [
            r'^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}$',
            r'^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}$',
            r'^\d{2}\.\d{2}\.\d{4}[T\s]\d{2}:\d{2}:\d{2}$',
            r'^\d{2}\/\d{2}\/\d{4}[T\s]\d{2}:\d{2}:\d{2}$',
            r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$',
            r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$',
        ]
        return any(re.match(pattern, value) for pattern in patterns)

    def _is_phone_number(self, value: str) -> bool:
        """Проверяет, является ли строка телефонным номером"""
        clean_value = re.sub(r'[^\d+]', '', value)
        return len(clean_value) >= 10 and clean_value.replace('+', '').isdigit()

    def _is_currency_string(self, value: str) -> bool:
        """Проверяет, является ли строка валютой"""
        currency_symbols = ['$', '€', '£', '¥', '₽', '₹']
        return any(symbol in value for symbol in currency_symbols)

    def _is_numeric_string(self, value: str) -> bool:
        """Проверяет, является ли строка числом"""
        try:
            clean_value = value.replace(' ', '').replace(',', '.').replace("'", "")
            float(clean_value)
            return True
        except ValueError:
            return False

    def _apply_custom_format(self, value: Any, custom_format: str) -> str:
        """Применяет пользовательский формат"""
        try:
            return custom_format.format(value=value)
        except:
            return str(value)

    def _format_date(self, date_str: str, output_format: str) -> str:
        """Форматирует дату"""
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')

            format_mapping = {
                'dd-mm-yyyy': '%d-%m-%Y',
                'dd.mm.yyyy': '%d.%m.%Y',
                'dd/mm/yyyy': '%d/%m/%Y',
                'mm-dd-yyyy': '%m-%d-%Y',
                'mm.dd.yyyy': '%m.%d.%Y',
                'mm/dd/yyyy': '%m/%d/%Y',
                'yyyy-mm-dd': '%Y-%m-%d',
                'dd-mm-yy': '%d-%m-%y',
                'dd.mm.yy': '%d.%m.%y',
                'full': '%d %B %Y',
                'short': '%d %b %Y',
                'iso': '%Y-%m-%d',
            }

            if output_format in format_mapping:
                return date_obj.strftime(format_mapping[output_format])
            else:
                return date_obj.strftime(output_format)

        except ValueError:
            return date_str

    def _format_time(self, time_str: str, output_format: str) -> str:
        """Форматирует время"""
        return time_str

    def _format_datetime(self, datetime_str: str, output_format: str) -> str:
        """Форматирует дату и время"""
        try:
            # Пробуем разные форматы ввода
            formats_to_try = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M',
                '%d.%m.%Y %H:%M:%S',
                '%d/%m/%Y %H:%M:%S'
            ]

            datetime_obj = None
            for fmt_str in formats_to_try:
                try:
                    datetime_obj = datetime.strptime(datetime_str, fmt_str)
                    break
                except ValueError:
                    continue

            if datetime_obj is None:
                return datetime_str

            # Маппинг пользовательских форматов на стандартные strftime форматы
            format_mapping = {
                'dd-mm-yyyy HH:MM:SS': '%d-%m-%Y %H:%M:%S',
                'dd.mm.yyyy HH:MM:SS': '%d.%m.%Y %H:%M:%S',
                'dd/mm/yyyy HH:MM:SS': '%d/%m/%Y %H:%M:%S',
                'yyyy-mm-dd HH:MM:SS': '%Y-%m-%d %H:%M:%S',
                'dd-mm-yyyy HH:MM': '%d-%m-%Y %H:%M',
                'dd.mm.yyyy HH:MM': '%d.%m.%Y %H:%M',
                'dd/mm/yyyy HH:MM': '%d/%m/%Y %H:%M',
                'yyyy-mm-dd HH:MM': '%Y-%m-%d %H:%M',
                'dd-mm-yy HH:MM:SS': '%d-%m-%y %H:%M:%S',
                'dd.mm.yy HH:MM:SS': '%d.%m.%y %H:%M:%S',
                'full': '%d %B %Y %H:%M:%S',
                'short': '%d %b %Y %H:%M:%S',
                'iso': '%Y-%m-%d %H:%M:%S',
            }

            if output_format in format_mapping:
                return datetime_obj.strftime(format_mapping[output_format])
            else:
                # Заменяем пользовательские плейсхолдеры на стандартные
                custom_format = output_format
                custom_format = custom_format.replace('dd', '%d')
                custom_format = custom_format.replace('mm', '%m')
                custom_format = custom_format.replace('yyyy', '%Y')
                custom_format = custom_format.replace('yy', '%y')
                custom_format = custom_format.replace('HH', '%H')
                custom_format = custom_format.replace('MM', '%M')
                custom_format = custom_format.replace('SS', '%S')
                custom_format = custom_format.replace('MMMM', '%B')
                custom_format = custom_format.replace('MMM', '%b')

                return datetime_obj.strftime(custom_format)

        except ValueError:
            return datetime_str

    def _format_unknown(self, value: Any) -> str:
        """Форматирование неизвестного типа"""
        return str(value)

    def _get_format_kwargs(self, local_vars: Dict) -> Dict:
        """Извлекает только нужные параметры форматирования"""
        exclude_keys = ['self', 'value', 'format_type', 'custom_format']
        return {k: v for k, v in local_vars.items() if k not in exclude_keys and not k.startswith('_')}

    def _generate_help(self, function_name: str) -> str:
        """Генерирует справку по функциям"""

        help_content = {
            'fmt': """
            <div class="function-help">
                <h1>Функция fmt() - Универсальное форматирование</h1>
                <p>Форматирует любые типы данных: числа, даты, текст, массивы, валюты и т.д.</p>

                <h2>Параметры:</h2>
                <table border="1" style="border-collapse: collapse; width: 100%;">
                    <tr><th>Параметр</th><th>Тип</th><th>По умолчанию</th><th>Описание</th></tr>
                    <tr><td>value</td><td>Any</td><td>-</td><td>Значение для форматирования</td></tr>
                    <tr><td>format_type</td><td>str</td><td>auto</td><td>Тип форматирования: auto, date, datetime, financial, currency, %, phone, boolean, text, array</td></tr>
                    <tr><td>financial_separator</td><td>str</td><td>' '</td><td>Разделитель тысяч (можно использовать любой символ: ' ', ',', '.', '`', "'", etc.)</td></tr>
                    <tr><td>decimal_separator</td><td>str</td><td>','</td><td>Десятичный разделитель (можно использовать любой символ: ',', '.', etc.)</td></tr>
                    <tr><td>decimal_places</td><td>int</td><td>None</td><td>Количество знаков после запятой</td></tr>
                    <tr><td>date_format</td><td>str</td><td>dd-mm-yyyy</td><td>Формат даты</td></tr>
                    <tr><td>datetime_format</td><td>str</td><td>dd-mm-yyyy HH:MM:SS</td><td>Формат даты и времени</td></tr>
                    <tr><td>currency</td><td>str</td><td>None</td><td>Код валюты: RUB, USD, EUR, GBP, CNY</td></tr>
                    <tr><td>text_case</td><td>str</td><td>None</td><td>Регистр: lower, upper, title, capitalize</td></tr>
                    <tr><td>array_separator</td><td>str</td><td>', '</td><td>Разделитель элементов массива</td></tr>
                    <tr><td>boolean_format</td><td>str</td><td>true_false</td><td>Формат булевых значений</td></tr>
                    <tr><td>percent_format</td><td>str</td><td>symbol</td><td>Формат процентов: symbol, word, none</td></tr>
                </table>

                <h2>Примеры:</h2>
                <pre>
fmt(1000000)                      # "1 000 000"
fmt(1200140, financial_separator='`', decimal_separator='.', decimal_places=2)  # "1`200`140.00"
fmt("2023-12-25")                 # "25-12-2023"  
fmt("2023-12-25 15:23:21")        # "25-12-2023 15:23:21"
fmt(0.15, format_type='%')        # "15,0%"
fmt(1500000, currency='USD')      # "$1,500,000.00"
fmt([1, 2, 3], array_separator=' - ')  # "1 - 2 - 3"
                </pre>
            </div>
            """
        }

        return help_content.get(function_name, f"<h1>Справка не найдена для функции: {function_name}</h1>")


# Создаем глобальный экземпляр форматировщика
_formatter = UniversalFormatter()