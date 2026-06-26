"""
Unit-тесты для parser.py: парсинг заголовка и транзакций выписки СберБанка.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import unittest
from decimal import Decimal

from parse import (
    StatementHeader, Transaction,
    _parse_russian_number,
    _extract_card_number,
    _convert_date,
    parse_header,
    parse_transactions_page,
    parse_all,
)


class TestParseRussianNumber(unittest.TestCase):
    """Тесты для _parse_russian_number."""

    # --- Зачисления (со знаком + или is_debit=False) ---

    def test_credit_with_plus(self):
        """Зачисление с явным +."""
        self.assertEqual(
            _parse_russian_number('+35 910,00', is_debit=False),
            Decimal('35910.00')
        )

    def test_credit_no_sign(self):
        """Без знака, is_debit=False — положительное."""
        self.assertEqual(
            _parse_russian_number('58 494,52', is_debit=False),
            Decimal('58494.52')
        )

    def test_credit_with_thousands(self):
        """Число с пробелами-разделителями тысяч."""
        self.assertEqual(
            _parse_russian_number('+2 281 162,83', is_debit=False),
            Decimal('2281162.83')
        )

    def test_credit_zero(self):
        """Нулевое зачисление."""
        self.assertEqual(
            _parse_russian_number('+0,00', is_debit=False),
            Decimal('0.00')
        )

    def test_credit_no_decimals(self):
        """Целое число без дробной части."""
        self.assertEqual(
            _parse_russian_number('+100', is_debit=False),
            Decimal('100')
        )

    # --- Списания (без знака + is_debit=True) ---

    def test_debit_no_sign(self):
        """Списание без знака — отрицательное."""
        self.assertEqual(
            _parse_russian_number('1 500,00', is_debit=True),
            Decimal('-1500.00')
        )

    def test_debit_minus_sign(self):
        """Списание с явным минусом."""
        self.assertEqual(
            _parse_russian_number('-7 000,00', is_debit=True),
            Decimal('-7000.00')
        )

    def test_debit_large(self):
        """Большое списание."""
        self.assertEqual(
            _parse_russian_number('2 272 504,13', is_debit=True),
            Decimal('-2272504.13')
        )

    # --- is_debit игнорируется при явном знаке ---

    def test_debit_with_plus_is_debit_true(self):
        """Явный + переопределяет is_debit=True."""
        self.assertEqual(
            _parse_russian_number('+100,00', is_debit=True),
            Decimal('100.00')
        )

    def test_credit_with_minus_is_debit_false(self):
        """Явный - переопределяет is_debit=False."""
        self.assertEqual(
            _parse_russian_number('-100,00', is_debit=False),
            Decimal('-100.00')
        )

    # --- Нестандартные пробелы ---

    def test_non_breaking_space(self):
        """Неразрывный пробел (\\u00a0) должен обрабатываться."""
        self.assertEqual(
            _parse_russian_number('35\u00a0910,00', is_debit=True),
            Decimal('-35910.00')
        )

    def test_mixed_spaces(self):
        """Смешанные обычные и неразрывные пробелы."""
        self.assertEqual(
            _parse_russian_number('+2\u00a0281 162,83', is_debit=False),
            Decimal('2281162.83')
        )

    # --- Граничные случаи ---

    def test_empty_string(self):
        """Пустая строка — 0."""
        self.assertEqual(
            _parse_russian_number('', is_debit=True),
            Decimal('0')
        )

    def test_invalid_string(self):
        """Невалидная строка — 0 (InvalidOperation)."""
        self.assertEqual(
            _parse_russian_number('abc', is_debit=False),
            Decimal('0')
        )

    def test_tiny_amount(self):
        """Очень маленькая сумма."""
        self.assertEqual(
            _parse_russian_number('+0,01', is_debit=False),
            Decimal('0.01')
        )

    def test_balance_default(self):
        """Остаток (is_debit=False) — всегда положительный."""
        self.assertEqual(
            _parse_russian_number('31 243,22', is_debit=False),
            Decimal('31243.22')
        )


class TestExtractCardNumber(unittest.TestCase):
    """Тесты для _extract_card_number."""

    def test_card_8340(self):
        """Номер карты ****8340."""
        self.assertEqual(
            _extract_card_number('Заработная плата. Операция по карте ****8340'),
            '****8340'
        )

    def test_card_8660(self):
        """Номер счёта ****8660."""
        self.assertEqual(
            _extract_card_number('SBERBANK ONL@IN KARTA-VKLAD. Операция по счету ****8660'),
            '****8660'
        )

    def test_no_card(self):
        """Нет номера карты."""
        self.assertEqual(
            _extract_card_number('YANDEX.GO MOSKVA RUS'),
            ''
        )

    def test_empty_string(self):
        """Пустая строка."""
        self.assertEqual(_extract_card_number(''), '')

    def test_multiple_cards_first(self):
        """При нескольких номерах — первый."""
        self.assertEqual(
            _extract_card_number('****8340 и ****8660'),
            '****8340'
        )


class TestConvertDate(unittest.TestCase):
    """Тесты для _convert_date."""

    def test_normal(self):
        """Обычная дата."""
        self.assertEqual(_convert_date('13.01.2023'), '2023-01-13')

    def test_first_january(self):
        """1 января."""
        self.assertEqual(_convert_date('01.01.2023'), '2023-01-01')

    def test_thirty_first(self):
        """31 декабря."""
        self.assertEqual(_convert_date('31.12.2023'), '2023-12-31')

    def test_leap_year(self):
        """Високосный год."""
        self.assertEqual(_convert_date('29.02.2024'), '2024-02-29')


class TestParseHeader(unittest.TestCase):
    """Тесты для parse_header."""

    def _make_realistic_header_lines(self):
        """Строки, имитирующие первую страницу реальной выписки СберБанка."""
        return [
            'Выписка по платёжному счёту',
            'Владелец счёта',
            'Иванов Иван Петрович',
            'Номер счёта 40817 810 7 3812 1234567 Пополнение 2 281 162,83',
            'Списание 2 272 504,13',
            'Российский рубль (Россия), RUR',
            'За период 01.12.2022 — 29.05.2023',
            'Остаток на 01.12.2022 22 584,52',
            'Остаток на 29.05.2023 8 387,17',
            'Дата операции Время Категория Сумма Остаток',
            'и код авторизации',
            'операции2',
        ]

    def test_full_header(self):
        """Полный заголовок со всеми полями."""
        lines = self._make_realistic_header_lines()
        header = parse_header(lines)

        self.assertIsNotNone(header)
        self.assertEqual(header.owner_name, 'Иванов Иван Петрович')
        self.assertEqual(header.account_number, '40817 810 7 3812 1234567')
        self.assertEqual(header.currency, 'RUB')
        self.assertEqual(header.period_start, '2022-12-01')
        self.assertEqual(header.period_end, '2023-05-29')
        self.assertEqual(header.opening_balance, Decimal('22584.52'))
        self.assertEqual(header.closing_balance, Decimal('8387.17'))
        self.assertEqual(header.total_deposits, Decimal('2281162.83'))
        self.assertEqual(header.total_withdrawals, Decimal('2272504.13'))

    def test_header_empty_lines(self):
        """Пустой список — все поля пустые/нулевые."""
        header = parse_header([])
        self.assertIsNotNone(header)
        self.assertEqual(header.owner_name, '')
        self.assertEqual(header.opening_balance, Decimal('0'))
        self.assertEqual(header.closing_balance, Decimal('0'))

    def test_header_minimal(self):
        """Минимальный заголовок — только обязательные поля."""
        lines = [
            'Владелец счёта',
            'Иванов Иван',
            'Остаток на 01.01.2023 100,00',
        ]
        header = parse_header(lines)
        self.assertEqual(header.owner_name, 'Иванов Иван')
        self.assertEqual(header.opening_balance, Decimal('100.00'))
        self.assertEqual(header.closing_balance, Decimal('100.00'))  # только один остаток
        self.assertEqual(header.total_deposits, Decimal('0'))
        self.assertEqual(header.total_withdrawals, Decimal('0'))

    def test_header_no_ruble(self):
        """Без 'Российский рубль' — валюта пустая."""
        lines = self._make_realistic_header_lines()
        # Удаляем строку с валютой
        lines = [l for l in lines if 'Российский рубль' not in l]
        header = parse_header(lines)
        self.assertEqual(header.currency, '')

    def test_header_no_deposit_withdrawal(self):
        """Без строк Пополнение/Списание — нули."""
        lines = [
            'Владелец счёта',
            'Тест',
            'Остаток на 01.01.2023 100,00',
            'Остаток на 31.01.2023 200,00',
        ]
        header = parse_header(lines)
        self.assertEqual(header.total_deposits, Decimal('0'))
        self.assertEqual(header.total_withdrawals, Decimal('0'))

    def test_header_no_period(self):
        """Без периода — пустые строки."""
        lines = [
            'Владелец счёта',
            'Тест',
        ]
        header = parse_header(lines)
        self.assertEqual(header.period_start, '')
        self.assertEqual(header.period_end, '')

    def test_header_deposit_withdrawal_on_separate_lines(self):
        """Пополнение и Списание на отдельных строках."""
        lines = [
            'Номер счёта 40817 810 7 3812 1234567',
            'Пополнение 2 281 162,83',
            'Списание 2 272 504,13',
        ]
        header = parse_header(lines)
        self.assertEqual(header.total_deposits, Decimal('2281162.83'))
        self.assertEqual(header.total_withdrawals, Decimal('2272504.13'))


class TestParseTransactionsPage(unittest.TestCase):
    """Тесты для parse_transactions_page."""

    # --- Помощники для построения тестовых страниц ---

    def _make_page(self, transactions_body: list[str]) -> list[str]:
        """Собирает страницу с заголовком таблицы и транзакциями."""
        lines = [
            'Дата операции Время Категория Сумма Остаток',
            'и код авторизации',
            'операции2',
        ]
        lines.extend(transactions_body)
        return lines

    def test_single_credit(self):
        """Одна транзакция зачисления."""
        lines = self._make_page([
            '13.01.2023 08:33 Прочие операции +35 910,00 58 494,52',
            '13.01.2023 258766 Заработная плата. Операция по карте ****8340',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.date_operation, '2023-01-13')
        self.assertEqual(t.operation_time, '08:33')
        self.assertEqual(t.date_processing, '2023-01-13')
        self.assertEqual(t.auth_code, '258766')
        self.assertEqual(t.category, 'Прочие операции')
        self.assertEqual(t.description, 'Заработная плата. Операция по карте ****8340')
        self.assertEqual(t.amount_rub, Decimal('35910.00'))
        self.assertEqual(t.balance, Decimal('58494.52'))
        self.assertEqual(t.card_account, '****8340')
        self.assertEqual(t.currency_code, '')
        self.assertIsNone(t.amount_currency)

    def test_single_debit(self):
        """Одна транзакция списания."""
        lines = self._make_page([
            '16.05.2023 02:24 Прочие операции 99,00 15 387,17',
            '16.05.2023 212212 MOBILE BANK: KOMISSIYA. Операция по карте ****8660',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        # Без знака + → списание (отрицательное)
        self.assertEqual(t.amount_rub, Decimal('-99.00'))
        self.assertEqual(t.balance, Decimal('15387.17'))
        self.assertEqual(t.card_account, '****8660')

    def test_multiple_transactions(self):
        """Несколько транзакций подряд."""
        lines = self._make_page([
            '13.01.2023 08:33 Прочие операции +35 910,00 58 494,52',
            '13.01.2023 258766 Заработная плата. Операция по карте ****8340',
            '16.05.2023 02:24 Прочие операции 99,00 15 387,17',
            '16.05.2023 212212 MOBILE BANK: KOMISSIYA. Операция по карте ****8660',
            '04.05.2023 14:41 Перевод с карты 1 500,00 15 486,17',
            '04.05.2023 799769 Перевод для Т. Софья Евгеньевна. Операция по карте',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 3)

        # Первая — зачисление
        self.assertEqual(txns[0].amount_rub, Decimal('35910.00'))
        self.assertEqual(txns[0].card_account, '****8340')

        # Вторая — списание
        self.assertEqual(txns[1].amount_rub, Decimal('-99.00'))
        self.assertEqual(txns[1].card_account, '****8660')

        # Третья — списание без номера карты
        self.assertEqual(txns[2].amount_rub, Decimal('-1500.00'))
        self.assertEqual(txns[2].card_account, '')

    def test_rsd_transaction(self):
        """Транзакция в RSD (иностранная валюта)."""
        lines = self._make_page([
            '02.03.2023 07:16 Покупка 1 972,09 10 582,74',
            '01.03.2023 558492 YANDEX.GO MOSKVA RUS 2 331,00 RSD',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.amount_rub, Decimal('-1972.09'))  # списание
        self.assertEqual(t.balance, Decimal('10582.74'))
        self.assertEqual(t.currency_code, 'RSD')
        self.assertEqual(t.amount_currency, Decimal('2331.00'))
        # RSD убран из описания
        self.assertNotIn('RSD', t.description)
        self.assertIn('YANDEX.GO MOSKVA RUS', t.description)

    def test_eur_two_token_amount(self):
        """EUR с 2-токен суммой (1 500,00 EUR)."""
        lines = self._make_page([
            '15.04.2023 10:30 Покупка 3 000,00 10 000,00',
            '15.04.2023 123456 PAYPAL *SERVICE IRELAND 1 500,00 EUR',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'EUR')
        self.assertEqual(t.amount_currency, Decimal('1500.00'))
        self.assertIn('PAYPAL *SERVICE IRELAND', t.description)
        self.assertNotIn('EUR', t.description)
        self.assertNotIn('1 500,00', t.description)

    def test_eur_negative_two_token_amount(self):
        """Отрицательная EUR с 2-токен суммой (-500,00 EUR) — возврат."""
        lines = self._make_page([
            '15.04.2023 10:30 Покупка +3 000,00 13 000,00',
            '15.04.2023 123456 AMAZON.DE -500,00 EUR',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'EUR')
        self.assertEqual(t.amount_currency, Decimal('-500.00'))
        self.assertEqual(t.description, 'AMAZON.DE')

    def test_eur_negative_single_token_amount(self):
        """Отрицательная EUR с 1-токен суммой (-99,95 EUR) — возврат."""
        lines = self._make_page([
            '16.04.2023 11:00 Покупка +500,00 10 000,00',
            '16.04.2023 654321 STEAM GAMES.COM -99,95 EUR',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'EUR')
        self.assertEqual(t.amount_currency, Decimal('-99.95'))
        self.assertEqual(t.description, 'STEAM GAMES.COM')

    def test_eur_single_token_amount(self):
        """EUR с 1-токен суммой (99,95 EUR)."""
        lines = self._make_page([
            '16.04.2023 11:00 Покупка 500,00 9 500,00',
            '16.04.2023 654321 STEAM GAMES.COM 99,95 EUR',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'EUR')
        self.assertEqual(t.amount_currency, Decimal('99.95'))
        self.assertIn('STEAM GAMES.COM', t.description)

    def test_eur_round_amount(self):
        """EUR с круглой суммой (50,00 EUR)."""
        lines = self._make_page([
            '17.04.2023 12:00 Покупка 200,00 9 300,00',
            '17.04.2023 111111 AMAZON.DE 50,00 EUR',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'EUR')
        self.assertEqual(t.amount_currency, Decimal('50.00'))
        self.assertEqual(t.description, 'AMAZON.DE')

    # --- USD ---

    def test_usd_two_token_amount(self):
        """USD с 2-токен суммой (2 500,00 USD)."""
        lines = self._make_page([
            '18.04.2023 13:00 Покупка 5 000,00 15 000,00',
            '18.04.2023 222222 AWS AMAZON.COM 2 500,00 USD',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'USD')
        self.assertEqual(t.amount_currency, Decimal('2500.00'))
        self.assertIn('AWS AMAZON.COM', t.description)
        self.assertNotIn('USD', t.description)

    def test_usd_single_token_amount(self):
        """USD с 1-токен суммой (9,99 USD)."""
        lines = self._make_page([
            '19.04.2023 14:00 Покупка 350,00 14 650,00',
            '19.04.2023 333333 APPLE.COM/BILL 9,99 USD',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'USD')
        self.assertEqual(t.amount_currency, Decimal('9.99'))
        self.assertEqual(t.description, 'APPLE.COM/BILL')

    # --- GBP ---

    def test_gbp_two_token_amount(self):
        """GBP с 2-токен суммой (1 200,00 GBP)."""
        lines = self._make_page([
            '20.04.2023 15:00 Покупка 4 000,00 11 000,00',
            '20.04.2023 444444 SPOTIFY UK 1 200,00 GBP',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'GBP')
        self.assertEqual(t.amount_currency, Decimal('1200.00'))
        self.assertNotIn('GBP', t.description)

    def test_gbp_single_token_amount(self):
        """GBP с 1-токен суммой (45,50 GBP)."""
        lines = self._make_page([
            '21.04.2023 16:00 Покупка 200,00 10 800,00',
            '21.04.2023 555555 NETFLIX.COM 45,50 GBP',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'GBP')
        self.assertEqual(t.amount_currency, Decimal('45.50'))
        self.assertEqual(t.description, 'NETFLIX.COM')

    # --- CHF ---

    def test_chf_two_token_amount(self):
        """CHF с 2-токен суммой (3 000,00 CHF)."""
        lines = self._make_page([
            '22.04.2023 17:00 Покупка 6 000,00 5 000,00',
            '22.04.2023 666666 SWISSPOST ZURICH 3 000,00 CHF',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'CHF')
        self.assertEqual(t.amount_currency, Decimal('3000.00'))
        self.assertNotIn('CHF', t.description)

    def test_chf_single_token_amount(self):
        """CHF с 1-токен суммой (150,00 CHF)."""
        lines = self._make_page([
            '23.04.2023 18:00 Покупка 750,00 4 250,00',
            '23.04.2023 777777 RECHNUNG.CH 150,00 CHF',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'CHF')
        self.assertEqual(t.amount_currency, Decimal('150.00'))
        self.assertEqual(t.description, 'RECHNUNG.CH')

    # --- JPY (без копеек — целые числа) ---

    def test_jpy_two_token_with_decimals(self):
        """JPY с 2-токен суммой и ,00 (5 000,00 JPY)."""
        lines = self._make_page([
            '24.04.2023 19:00 Покупка 3 000,00 12 000,00',
            '24.04.2023 888888 AMAZON.CO.JP 5 000,00 JPY',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'JPY')
        self.assertEqual(t.amount_currency, Decimal('5000.00'))
        self.assertEqual(t.description, 'AMAZON.CO.JP')

    def test_jpy_two_token_whole(self):
        """JPY с 2-токен целой суммой без ,00 (5 000 JPY)."""
        lines = self._make_page([
            '25.04.2023 20:00 Покупка 2 500,00 9 500,00',
            '25.04.2023 999999 MERCARI.JP 5 000 JPY',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'JPY')
        self.assertEqual(t.amount_currency, Decimal('5000'))
        self.assertEqual(t.description, 'MERCARI.JP')

    def test_jpy_single_token_whole(self):
        """JPY с 1-токен целой суммой без ,00 (1500 JPY)."""
        lines = self._make_page([
            '26.04.2023 21:00 Покупка 800,00 8 700,00',
            '26.04.2023 101010 UNIQLO.JP 1500 JPY',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'JPY')
        self.assertEqual(t.amount_currency, Decimal('1500'))
        self.assertEqual(t.description, 'UNIQLO.JP')

    def test_jpy_large_whole(self):
        """JPY с большой целой суммой (12000 JPY — 5 цифр)."""
        lines = self._make_page([
            '27.04.2023 22:00 Покупка 5 000,00 5 000,00',
            '27.04.2023 121212 TOKYO STORE 12000 JPY',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'JPY')
        self.assertEqual(t.amount_currency, Decimal('12000'))
        self.assertEqual(t.description, 'TOKYO STORE')

    def test_rsd_negative_whole_amount(self):
        """Отрицательная RSD без копеек (-2 331 RSD) — возврат в валюте."""
        lines = self._make_page([
            '17.04.2023 12:00 Покупка +1 500,00 11 500,00',
            '17.04.2023 111111 YANDEX.GO -2 331 RSD',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'RSD')
        self.assertEqual(t.amount_currency, Decimal('-2331'))
        self.assertEqual(t.description, 'YANDEX.GO')

    def test_rsd_single_token_amount(self):
        """RSD с однострочной суммой (например 187,00 RSD)."""

        lines = self._make_page([
            '15.04.2023 10:30 Покупка 500,00 5 000,00',
            '15.04.2023 123456 TEST DESCRIPTION 187,00 RSD',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.currency_code, 'RSD')
        self.assertEqual(t.amount_currency, Decimal('187.00'))
        self.assertIn('TEST DESCRIPTION', t.description)
        self.assertNotIn('RSD', t.description)
        self.assertNotIn('187,00', t.description)

    def test_multi_line_description(self):
        """Описание продолжается на следующей строке."""
        lines = self._make_page([
            '13.01.2023 08:33 Прочие операции +35 910,00 58 494,52',
            '13.01.2023 258766 Заработная плата.',
            'Операция по карте ****8340',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertIn('Заработная плата.', t.description)
        self.assertIn('Операция по карте ****8340', t.description)
        # Номер карты из продолжения
        self.assertEqual(t.card_account, '****8340')

    def test_skip_boilerplate_lines(self):
        """Служебные строки между транзакциями пропускаются."""
        lines = self._make_page([
            '13.01.2023 08:33 Прочие операции +35 910,00 58 494,52',
            '13.01.2023 258766 Заработная плата.',
            '* Продолжение на следующей странице',
            '16.05.2023 02:24 Прочие операции 99,00 15 387,17',
            '16.05.2023 212212 MOBILE BANK: KOMISSIYA. Операция по карте ****8660',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 2)

    def test_empty_page(self):
        """Пустая страница (без транзакций)."""
        lines = [
            'Дата операции Время Категория Сумма Остаток',
            'и код авторизации',
            'операции2',
            'Продолжение на следующей странице',
        ]
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 0)

    def test_no_table_header(self):
        """Страница без заголовка таблицы."""
        lines = [
            '13.01.2023 08:33 Прочие операции +35 910,00 58 494,52',
            '13.01.2023 258766 Заработная плата.',
        ]
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)

    def test_transaction_without_card(self):
        """Транзакция без номера карты."""
        lines = self._make_page([
            '04.05.2023 14:41 Перевод с карты 1 500,00 15 486,17',
            '04.05.2023 799769 Перевод для Т. Софья Евгеньевна',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.card_account, '')
        self.assertEqual(t.amount_rub, Decimal('-1500.00'))

    def test_large_amount_no_plus(self):
        """Большая сумма без знака + — списание."""
        lines = self._make_page([
            '01.12.2022 10:00 Покупка 2 500,00 20 084,52',
            '01.12.2022 111111 TEST',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.amount_rub, Decimal('-2500.00'))
        self.assertEqual(t.balance, Decimal('20084.52'))

    def test_transaction_with_6_digit_code(self):
        """Код авторизации ровно 6 цифр."""
        lines = self._make_page([
            '30.04.2023 11:06 Прочие операции +7 517,00 19 512,39',
            '30.04.2023 361371 Заработная плата. Операция по карте ****8660',
        ])
        txns = parse_transactions_page(lines)
        self.assertEqual(len(txns), 1)
        t = txns[0]
        self.assertEqual(t.auth_code, '361371')
        self.assertEqual(t.amount_rub, Decimal('7517.00'))
        self.assertEqual(t.card_account, '****8660')


class TestParseAll(unittest.TestCase):
    """Тесты для parse_all."""

    def test_single_page(self):
        """Одна страница с заголовком и транзакциями."""
        pages = [[
            'Владелец счёта',
            'Иванов Иван Петрович',
            'Остаток на 01.12.2022 22 584,52',
            'Остаток на 29.05.2023 8 387,17',
            'Дата операции Время Категория Сумма Остаток',
            'и код авторизации',
            'операции2',
            '13.01.2023 08:33 Прочие операции +35 910,00 58 494,52',
            '13.01.2023 258766 Заработная плата. Операция по карте ****8340',
        ]]
        header, txns = parse_all(pages)
        self.assertIsNotNone(header)
        self.assertEqual(header.owner_name, 'Иванов Иван Петрович')
        self.assertEqual(header.opening_balance, Decimal('22584.52'))
        self.assertEqual(header.closing_balance, Decimal('8387.17'))
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].amount_rub, Decimal('35910.00'))

    def test_multiple_pages(self):
        """Несколько страниц — транзакции собираются вместе."""
        pages = [
            # Страница 1: заголовок + 1 транзакция
            [
                'Владелец счёта',
                'Тест',
                'Остаток на 01.12.2022 100,00',
                'Остаток на 29.05.2023 300,00',
                'Дата операции Время Категория Сумма Остаток',
                'и код авторизации',
                'операции2',
                '13.01.2023 08:33 Прочие операции +50,00 150,00',
                '13.01.2023 258766 Первая операция',
            ],
            # Страница 2: 1 транзакция
            [
                'Дата операции Время Категория Сумма Остаток',
                'и код авторизации',
                'операции2',
                '14.01.2023 10:00 Прочие операции +150,00 300,00',
                '14.01.2023 111111 Вторая операция',
            ],
        ]
        header, txns = parse_all(pages)
        self.assertIsNotNone(header)
        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[0].amount_rub, Decimal('50.00'))
        self.assertEqual(txns[1].amount_rub, Decimal('150.00'))

    def test_empty_pages(self):
        """Пустой список страниц."""
        header, txns = parse_all([])
        self.assertIsNone(header)
        self.assertEqual(len(txns), 0)

    def test_page_with_no_transactions(self):
        """Страница без транзакций (только заголовок)."""
        pages = [[
            'Владелец счёта',
            'Тест',
            'Остаток на 01.12.2022 100,00',
            'Остаток на 29.05.2023 100,00',
            'Дата операции Время Категория Сумма Остаток',
            'и код авторизации',
            'операции2',
            'Продолжение на следующей странице',
        ]]
        header, txns = parse_all(pages)
        self.assertIsNotNone(header)
        self.assertEqual(len(txns), 0)


if __name__ == '__main__':
    unittest.main()
