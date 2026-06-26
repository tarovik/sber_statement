"""
Unit-тесты для csv_writer.py: _format_decimal, write_csv, output paths.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import csv
import shutil
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal

from parse import _format_decimal, write_csv, write_log, output_csv_path, output_log_path, StatementHeader, Transaction


def _read_csv(filepath):
    """Читает CSV с разделителем ; и возвращает список строк."""
    with open(filepath, 'r', encoding='utf-8', newline='') as f:
        reader = csv.reader(f, delimiter=';')
        return list(reader)


class TestFormatDecimal(unittest.TestCase):
    """Тесты для _format_decimal."""

    # --- Режим с точкой (default) ---

    def test_positive_dot(self):
        """Положительное число с точкой."""
        self.assertEqual(_format_decimal(Decimal('35910.00')), '35910.00')

    def test_negative_dot(self):
        """Отрицательное число с точкой."""
        self.assertEqual(_format_decimal(Decimal('-7000.00')), '-7000.00')

    def test_integer_dot(self):
        """Целое число (без дробной части) — добавляет .00."""
        self.assertEqual(_format_decimal(Decimal('5')), '5.00')
        self.assertEqual(_format_decimal(Decimal('0')), '0.00')

    def test_small_number_dot(self):
        """Маленькое число."""
        self.assertEqual(_format_decimal(Decimal('0.01')), '0.01')
        self.assertEqual(_format_decimal(Decimal('-0.50')), '-0.50')

    def test_large_number_dot(self):
        """Большое число."""
        self.assertEqual(_format_decimal(Decimal('1000000.50')), '1000000.50')
        self.assertEqual(_format_decimal(Decimal('2281162.83')), '2281162.83')

    def test_rsd_amount_dot(self):
        """Сумма в валюте (RSD)."""
        self.assertEqual(_format_decimal(Decimal('2331.00')), '2331.00')
        self.assertEqual(_format_decimal(Decimal('187.00')), '187.00')

    def test_negative_integer_dot(self):
        """Отрицательное целое."""
        self.assertEqual(_format_decimal(Decimal('-99')), '-99.00')

    def test_jpy_whole_amount_dot(self):
        """JPY целое число (без копеек) — 5000 → 5000.00."""
        self.assertEqual(_format_decimal(Decimal('5000')), '5000.00')
        self.assertEqual(_format_decimal(Decimal('1500')), '1500.00')
        self.assertEqual(_format_decimal(Decimal('12000')), '12000.00')

    # --- Режим с запятой (decimal_comma=True) ---

    def test_positive_comma(self):
        """Положительное число с запятой."""
        self.assertEqual(_format_decimal(Decimal('35910.00'), use_comma=True), '35910,00')

    def test_negative_comma(self):
        """Отрицательное число с запятой."""
        self.assertEqual(_format_decimal(Decimal('-7000.00'), use_comma=True), '-7000,00')

    def test_integer_comma(self):
        """Целое число с запятой."""
        self.assertEqual(_format_decimal(Decimal('5'), use_comma=True), '5,00')
        self.assertEqual(_format_decimal(Decimal('0'), use_comma=True), '0,00')

    def test_small_number_comma(self):
        """Маленькое число с запятой."""
        self.assertEqual(_format_decimal(Decimal('0.01'), use_comma=True), '0,01')
        self.assertEqual(_format_decimal(Decimal('-0.50'), use_comma=True), '-0,50')

    def test_large_number_comma(self):
        """Большое число с запятой."""
        self.assertEqual(_format_decimal(Decimal('1000000.50'), use_comma=True), '1000000,50')
        self.assertEqual(_format_decimal(Decimal('2281162.83'), use_comma=True), '2281162,83')

    def test_rsd_amount_comma(self):
        """Сумма в валюте с запятой."""
        self.assertEqual(_format_decimal(Decimal('2331.00'), use_comma=True), '2331,00')
        self.assertEqual(_format_decimal(Decimal('187.00'), use_comma=True), '187,00')

    def test_negative_integer_comma(self):
        """Отрицательное целое с запятой."""
        self.assertEqual(_format_decimal(Decimal('-99'), use_comma=True), '-99,00')

    def test_jpy_whole_amount_comma(self):
        """JPY целое число с запятой — 5000 → 5000,00."""
        self.assertEqual(_format_decimal(Decimal('5000'), use_comma=True), '5000,00')
        self.assertEqual(_format_decimal(Decimal('1500'), use_comma=True), '1500,00')


class TestWriteCsv(unittest.TestCase):
    """Тесты для write_csv."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_txns(self):
        """Создаёт несколько тестовых транзакций."""
        return [
            Transaction(
                date_operation='2023-01-13',
                operation_time='08:33',
                date_processing='2023-01-13',
                auth_code='258766',
                category='Прочие операции',
                description='Заработная плата. Операция по карте ****8340',
                amount_rub=Decimal('35910.00'),
                balance=Decimal('58494.52'),
                card_account='****8340',
                currency_code='',
                amount_currency=None,
            ),
            Transaction(
                date_operation='2023-01-10',
                operation_time='14:22',
                date_processing='2023-01-10',
                auth_code='112233',
                category='Покупка',
                description='YANDEX.GO MOSKVA RUS',
                amount_rub=Decimal('-1500.00'),
                balance=Decimal('22584.52'),
                card_account='****8340',
                currency_code='RSD',
                amount_currency=Decimal('2331.00'),
            ),
            Transaction(
                date_operation='2023-01-05',
                operation_time='09:15',
                date_processing='2023-01-05',
                auth_code='445566',
                category='Перевод с карты',
                description='Перевод для Т. Иванов Иван',
                amount_rub=Decimal('-500.50'),
                balance=Decimal('24084.52'),
                card_account='',
                currency_code='',
                amount_currency=None,
            ),
        ]

    def test_write_csv_dot(self):
        """CSV с точкой как десятичным разделителем."""
        path = os.path.join(self.tmpdir, 'test_dot.csv')
        txns = self._make_txns()
        write_csv(path, txns, decimal_comma=False)

        rows = _read_csv(path)
        self.assertEqual(len(rows), 4)  # header + 3 transactions
        self.assertEqual(rows[0], [
            'date_operation', 'operation_time', 'date_processing', 'auth_code',
            'category', 'description', 'amount_rub', 'balance', 'card_account',
            'currency_code', 'amount_currency',
        ])

        # Первая транзакция (зачисление, положительная)
        self.assertEqual(rows[1][1], '08:33')  # operation_time
        self.assertEqual(rows[1][4], 'Прочие операции')  # category
        self.assertEqual(rows[1][5], 'Заработная плата. Операция по карте ****8340')  # description
        self.assertEqual(rows[1][6], '35910.00')  # amount_rub
        self.assertEqual(rows[1][7], '58494.52')  # balance
        self.assertEqual(rows[1][8], '****8340')  # card_account

        # Вторая транзакция (списание, RSD)
        self.assertEqual(rows[2][1], '14:22')
        self.assertEqual(rows[2][6], '-1500.00')
        self.assertEqual(rows[2][7], '22584.52')
        self.assertEqual(rows[2][8], '****8340')
        self.assertEqual(rows[2][9], 'RSD')
        self.assertEqual(rows[2][10], '2331.00')

        # Третья транзакция (без карты, без валюты)
        self.assertEqual(rows[3][1], '09:15')
        self.assertEqual(rows[3][6], '-500.50')
        self.assertEqual(rows[3][7], '24084.52')
        self.assertEqual(rows[3][8], '')
        self.assertEqual(rows[3][9], '')
        self.assertEqual(rows[3][10], '')

    def test_write_csv_comma(self):
        """CSV с запятой как десятичным разделителем."""
        path = os.path.join(self.tmpdir, 'test_comma.csv')
        txns = self._make_txns()
        write_csv(path, txns, decimal_comma=True)

        rows = _read_csv(path)
        self.assertEqual(len(rows), 4)

        # Первая транзакция
        self.assertEqual(rows[1][1], '08:33')  # operation_time не меняется от comma
        self.assertEqual(rows[1][6], '35910,00')
        self.assertEqual(rows[1][7], '58494,52')

        # Вторая транзакция (RSD)
        self.assertEqual(rows[2][6], '-1500,00')
        self.assertEqual(rows[2][10], '2331,00')

        # Третья транзакция
        self.assertEqual(rows[3][6], '-500,50')

    def test_write_csv_empty(self):
        """Пустой список транзакций — только заголовок."""
        path = os.path.join(self.tmpdir, 'test_empty.csv')
        write_csv(path, [], decimal_comma=False)

        rows = _read_csv(path)
        self.assertEqual(len(rows), 1)  # только header

    def test_write_csv_encoding(self):
        """CSV в UTF-8 — русский текст сохраняется корректно."""
        path = os.path.join(self.tmpdir, 'test_encoding.csv')
        txns = [Transaction(
            date_operation='2023-01-13',
            operation_time='08:33',
            date_processing='2023-01-13',
            auth_code='258766',
            category='Прочие операции',
            description='Заработная плата. Операция по карте ****8340',
            amount_rub=Decimal('35910.00'),
            balance=Decimal('58494.52'),
            card_account='****8340',
            currency_code='',
            amount_currency=None,
        )]
        write_csv(path, txns)

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Заработная плата', content)
        self.assertIn('Прочие операции', content)

    def test_write_csv_delimiter(self):
        """Разделитель — точка с запятой."""
        path = os.path.join(self.tmpdir, 'test_delim.csv')
        txns = self._make_txns()
        write_csv(path, txns)

        with open(path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
        self.assertEqual(first_line.count(';'), 10)  # 11 колонок = 10 разделителей


class TestOutputPaths(unittest.TestCase):
    """Тесты для output_csv_path и output_log_path."""

    def test_output_csv_path_default(self):
        """Без второго аргумента — имя из входного PDF."""
        result = output_csv_path('/path/to/statement.pdf')
        self.assertEqual(result, '/path/to/statement.csv')

    def test_output_csv_path_custom(self):
        """С указанным выходным путём."""
        result = output_csv_path('input.pdf', 'output.csv')
        self.assertEqual(result, 'output.csv')

    def test_output_csv_path_windows(self):
        """Путь с обратными слешами (Windows)."""
        result = output_csv_path('C:\\Users\\test\\statement.pdf')
        self.assertEqual(result, 'C:\\Users\\test\\statement.csv')

    def test_output_csv_path_no_extension(self):
        """PDF без расширения."""
        result = output_csv_path('statement')
        self.assertEqual(result, 'statement.csv')

    def test_output_log_path(self):
        """Лог от CSV."""
        result = output_log_path('/path/to/output.csv')
        self.assertEqual(result, '/path/to/output.log')

    def test_output_log_path_windows(self):
        """Лог от CSV с Windows-путём."""
        result = output_log_path('C:\\Users\\test\\output.csv')
        self.assertEqual(result, 'C:\\Users\\test\\output.log')


class TestWriteCsvEdgeCases(unittest.TestCase):
    """Тесты для граничных случаев write_csv."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_csv_integer_amounts(self):
        """Суммы без дробной части (целые Decimal)."""
        path = os.path.join(self.tmpdir, 'test_int.csv')
        txns = [
            Transaction(
                date_operation='2023-01-01', operation_time='10:00',
                date_processing='2023-01-01',
                auth_code='000000', category='Тест',
                description='Тестовая операция',
                amount_rub=Decimal('100'),  # целое число
                balance=Decimal('200'),     # целое число
                card_account='', currency_code='', amount_currency=None,
            ),
        ]
        write_csv(path, txns, decimal_comma=False)

        rows = self._read_csv(path)
        # Должны получить 100.00 и 200.00
        self.assertEqual(rows[1][6], '100.00')
        self.assertEqual(rows[1][7], '200.00')

    def test_write_csv_comma_integer_amounts(self):
        """Целые суммы с запятой."""
        path = os.path.join(self.tmpdir, 'test_int_comma.csv')
        txns = [
            Transaction(
                date_operation='2023-01-01', operation_time='10:00',
                date_processing='2023-01-01',
                auth_code='000000', category='Тест',
                description='Тест',
                amount_rub=Decimal('100'),
                balance=Decimal('200'),
                card_account='', currency_code='', amount_currency=None,
            ),
        ]
        write_csv(path, txns, decimal_comma=True)

        rows = self._read_csv(path)
        self.assertEqual(rows[1][6], '100,00')
        self.assertEqual(rows[1][7], '200,00')

    def test_write_csv_negative_amount_currency(self):
        """Отрицательная amount_currency (-500.00) в CSV."""
        path = os.path.join(self.tmpdir, 'test_neg_cur.csv')
        txns = [
            Transaction(
                date_operation='2023-01-01', operation_time='10:00',
                date_processing='2023-01-01',
                auth_code='000000', category='Возврат',
                description='AMAZON.DE',
                amount_rub=Decimal('3000.00'),
                balance=Decimal('15000.00'),
                card_account='****8340', currency_code='EUR',
                amount_currency=Decimal('-500.00'),
            ),
        ]
        write_csv(path, txns, decimal_comma=False)

        rows = self._read_csv(path)
        self.assertEqual(rows[1][6], '3000.00')  # amount_rub
        self.assertEqual(rows[1][9], 'EUR')      # currency_code
        self.assertEqual(rows[1][10], '-500.00')  # amount_currency

    def test_write_csv_negative_amount_currency_comma(self):
        """Отрицательная amount_currency с запятой (-500,00)."""
        path = os.path.join(self.tmpdir, 'test_neg_cur_comma.csv')
        txns = [
            Transaction(
                date_operation='2023-01-01', operation_time='10:00',
                date_processing='2023-01-01',
                auth_code='000000', category='Возврат',
                description='STEAM GAMES.COM',
                amount_rub=Decimal('99.95'),
                balance=Decimal('10099.95'),
                card_account='', currency_code='EUR',
                amount_currency=Decimal('-99.95'),
            ),
        ]
        write_csv(path, txns, decimal_comma=True)

        rows = self._read_csv(path)
        self.assertEqual(rows[1][10], '-99,95')

    def test_write_csv_jpy_amount_currency(self):
        """JPY amount_currency=5000 → 5000.00 в CSV."""
        path = os.path.join(self.tmpdir, 'test_jpy.csv')
        txns = [
            Transaction(
                date_operation='2023-01-01', operation_time='10:00',
                date_processing='2023-01-01',
                auth_code='000000', category='Покупка',
                description='AMAZON.CO.JP',
                amount_rub=Decimal('-3000.00'),
                balance=Decimal('10000.00'),
                card_account='****8340', currency_code='JPY',
                amount_currency=Decimal('5000'),  # целое число без копеек
            ),
        ]
        write_csv(path, txns, decimal_comma=False)

        rows = self._read_csv(path)
        self.assertEqual(rows[1][6], '-3000.00')  # amount_rub
        self.assertEqual(rows[1][9], 'JPY')       # currency_code
        self.assertEqual(rows[1][10], '5000.00')  # amount_currency

    def test_write_csv_jpy_amount_currency_comma(self):
        """JPY amount_currency=5000 с запятой → 5000,00 в CSV."""
        path = os.path.join(self.tmpdir, 'test_jpy_comma.csv')
        txns = [
            Transaction(
                date_operation='2023-01-01', operation_time='10:00',
                date_processing='2023-01-01',
                auth_code='000000', category='Покупка',
                description='UNIQLO.JP',
                amount_rub=Decimal('-1500.00'),
                balance=Decimal('8500.00'),
                card_account='', currency_code='JPY',
                amount_currency=Decimal('1500'),
            ),
        ]
        write_csv(path, txns, decimal_comma=True)

        rows = self._read_csv(path)
        self.assertEqual(rows[1][6], '-1500,00')
        self.assertEqual(rows[1][9], 'JPY')
        self.assertEqual(rows[1][10], '1500,00')

    def test_write_csv_special_chars(self):
        """Описания с кавычками и точками с запятой экранируются корректно."""
        path = os.path.join(self.tmpdir, 'test_special.csv')
        txns = [
            Transaction(
                date_operation='2023-01-01', operation_time='10:00',
                date_processing='2023-01-01',
                auth_code='000000', category='Тест;категория',
                description='Описание с; точкой запятой и "кавычками"',
                amount_rub=Decimal('-100.50'),
                balance=Decimal('500.00'),
                card_account='****8660', currency_code='', amount_currency=None,
            ),
        ]
        write_csv(path, txns, decimal_comma=False)

        rows = self._read_csv(path)
        # Кавычки и спецсимволы должны быть корректно прочитаны csv.reader
        self.assertEqual(rows[1][4], 'Тест;категория')
        self.assertEqual(rows[1][5], 'Описание с; точкой запятой и "кавычками"')
        self.assertEqual(rows[1][6], '-100.50')

    def _read_csv(self, filepath):
        return _read_csv(filepath)


class TestWriteLog(unittest.TestCase):
    """Тесты для write_log."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_header(self):
        return StatementHeader(
            owner_name='Иванов Иван Петрович',
            account_number='40817 810 7 3812 1234567',
            currency='RUB',
            period_start='2022-12-01',
            period_end='2023-05-29',
            opening_balance=Decimal('22584.52'),
            closing_balance=Decimal('8387.17'),
            total_deposits=Decimal('2281162.83'),
            total_withdrawals=Decimal('2272504.13'),
        )

    def _make_txns(self):
        return [
            Transaction(
                date_operation='2023-01-13', operation_time='08:33',
                date_processing='2023-01-13',
                auth_code='258766', category='Прочие операции',
                description='Заработная плата.',
                amount_rub=Decimal('35910.00'), balance=Decimal('58494.52'),
                card_account='****8340', currency_code='', amount_currency=None,
            ),
            Transaction(
                date_operation='2023-01-10', operation_time='14:22',
                date_processing='2023-01-10',
                auth_code='112233', category='Покупка',
                description='YANDEX.GO MOSKVA RUS',
                amount_rub=Decimal('-1500.00'), balance=Decimal('22584.52'),
                card_account='****8340', currency_code='RSD',
                amount_currency=Decimal('2331.00'),
            ),
        ]

    def test_write_log_created(self):
        """Лог-файл создаётся и содержит ключевые секции."""
        path = os.path.join(self.tmpdir, 'test.log')
        header = self._make_header()
        txns = self._make_txns()
        write_log(path, header, txns, balance_ok=True,
                   expected_balance=Decimal('8387.17'),
                   calculated_balance=Decimal('8387.17'),
                   discrepancy=Decimal('0.00'))

        self.assertTrue(os.path.exists(path))
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('ОТЧЁТ ОБРАБОТКИ ВЫПИСКИ', content)
        self.assertIn('Заголовок выписки', content)
        self.assertIn('Иванов Иван Петрович', content)
        self.assertIn('Финансовые итоги из PDF', content)
        self.assertIn('Результат парсинга', content)
        self.assertIn('ПРОВЕРКА БАЛАНСА: УСПЕШНО', content)
        self.assertIn('✅', content)

    def test_write_log_balance_fail(self):
        """Лог при ошибке баланса содержит предупреждение."""
        path = os.path.join(self.tmpdir, 'test_fail.log')
        header = self._make_header()
        txns = self._make_txns()
        write_log(path, header, txns, balance_ok=False,
                   expected_balance=Decimal('8387.17'),
                   calculated_balance=Decimal('31243.22'),
                   discrepancy=Decimal('22856.05'))

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('ПРОВЕРКА БАЛАНСА: ОШИБКА', content)
        self.assertIn('❌', content)
        self.assertIn('!!! ВНИМАНИЕ: Баланс НЕ СОШЁЛСЯ !!!', content)
        self.assertIn('31243.22', content)

    def test_write_log_no_header(self):
        """Лог без заголовка (header=None) — без ошибок."""
        path = os.path.join(self.tmpdir, 'test_no_header.log')
        write_log(path, None, [], balance_ok=True,
                   expected_balance=Decimal('0'),
                   calculated_balance=Decimal('0'),
                   discrepancy=Decimal('0'))

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('ОТЧЁТ ОБРАБОТКИ ВЫПИСКИ', content)
        self.assertNotIn('Владелец счёта:', content)

    def test_write_log_empty_transactions(self):
        """Лог с пустым списком транзакций."""
        path = os.path.join(self.tmpdir, 'test_empty_txns.log')
        header = self._make_header()
        write_log(path, header, [], balance_ok=True,
                   expected_balance=Decimal('22584.52'),
                   calculated_balance=Decimal('22584.52'),
                   discrepancy=Decimal('0'))

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('Всего операций найдено:    0', content)


if __name__ == '__main__':
    unittest.main()
