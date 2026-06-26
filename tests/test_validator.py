"""
Unit-тесты для validate_balance.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import unittest
from decimal import Decimal

from parse import StatementHeader, Transaction, validate_balance


class TestValidateBalance(unittest.TestCase):
    """Тесты для validate_balance."""

    # --- Helpers ---

    def _make_header(self, opening: str, closing: str) -> StatementHeader:
        return StatementHeader(
            owner_name='Тест',
            account_number='40817 810 7 3812 1234567',
            currency='RUB',
            period_start='2023-01-01',
            period_end='2023-05-29',
            opening_balance=Decimal(opening),
            closing_balance=Decimal(closing),
            total_deposits=Decimal('0'),
            total_withdrawals=Decimal('0'),
        )

    def _make_txn(self, amount: str) -> Transaction:
        return Transaction(
            date_operation='2023-01-13',
            operation_time='08:33',
            date_processing='2023-01-13',
            auth_code='258766',
            category='Тест',
            description='Тестовая операция',
            amount_rub=Decimal(amount),
            balance=Decimal('0'),
            card_account='',
            currency_code='',
            amount_currency=None,
        )

    # --- header is None ---

    def test_header_none(self):
        """header=None → balance_ok=False, все нули."""
        ok, expected, calculated, discrepancy = validate_balance(None, [])
        self.assertFalse(ok)
        self.assertEqual(expected, Decimal('0'))
        self.assertEqual(calculated, Decimal('0'))
        self.assertEqual(discrepancy, Decimal('0'))

    def test_header_none_with_transactions(self):
        """header=None с транзакциями → balance_ok=False."""
        txns = [self._make_txn('100.00')]
        ok, _, _, _ = validate_balance(None, txns)
        self.assertFalse(ok)

    # --- Успешная проверка баланса ---

    def test_balance_ok_simple(self):
        """Простейший случай: начальное + зачисление = конечное."""
        header = self._make_header('100.00', '200.00')
        txns = [self._make_txn('100.00')]
        ok, expected, calculated, discrepancy = validate_balance(header, txns)
        self.assertTrue(ok)
        self.assertEqual(expected, Decimal('200.00'))
        self.assertEqual(calculated, Decimal('200.00'))
        self.assertEqual(discrepancy, Decimal('0'))

    def test_balance_ok_debit(self):
        """Начальное - списание = конечное."""
        header = self._make_header('200.00', '100.00')
        txns = [self._make_txn('-100.00')]
        ok, expected, calculated, discrepancy = validate_balance(header, txns)
        self.assertTrue(ok)
        self.assertEqual(calculated, Decimal('100.00'))

    def test_balance_ok_multiple(self):
        """Несколько операций: зачисления и списания."""
        header = self._make_header('1000.00', '1500.00')
        txns = [
            self._make_txn('500.00'),    # +500
            self._make_txn('-200.00'),   # -200
            self._make_txn('300.00'),    # +300
            self._make_txn('-100.00'),   # -100
        ]
        # 1000 + 500 + 300 - 200 - 100 = 1500
        ok, expected, calculated, discrepancy = validate_balance(header, txns)
        self.assertTrue(ok)
        self.assertEqual(calculated, Decimal('1500.00'))

    def test_balance_ok_empty_transactions(self):
        """Нет операций: начальное = конечное."""
        header = self._make_header('500.00', '500.00')
        ok, _, calculated, _ = validate_balance(header, [])
        self.assertTrue(ok)
        self.assertEqual(calculated, Decimal('500.00'))

    def test_balance_ok_all_credits(self):
        """Только зачисления."""
        header = self._make_header('0.00', '600.00')
        txns = [
            self._make_txn('100.00'),
            self._make_txn('200.00'),
            self._make_txn('300.00'),
        ]
        ok, _, calculated, _ = validate_balance(header, txns)
        self.assertTrue(ok)
        self.assertEqual(calculated, Decimal('600.00'))

    def test_balance_ok_all_debits(self):
        """Только списания."""
        header = self._make_header('1000.00', '400.00')
        txns = [
            self._make_txn('-300.00'),
            self._make_txn('-200.00'),
            self._make_txn('-100.00'),
        ]
        ok, _, calculated, _ = validate_balance(header, txns)
        self.assertTrue(ok)
        self.assertEqual(calculated, Decimal('400.00'))

    # --- Ошибка баланса ---

    def test_balance_fail(self):
        """Баланс не сходится."""
        header = self._make_header('100.00', '300.00')
        txns = [self._make_txn('100.00')]  # 100 + 100 = 200, а не 300
        ok, expected, calculated, discrepancy = validate_balance(header, txns)
        self.assertFalse(ok)
        self.assertEqual(expected, Decimal('300.00'))
        self.assertEqual(calculated, Decimal('200.00'))
        self.assertEqual(discrepancy, Decimal('100.00'))

    def test_balance_fail_calculated_larger(self):
        """Расчётное больше ожидаемого."""
        header = self._make_header('100.00', '100.00')
        txns = [self._make_txn('50.00')]  # 100 + 50 = 150 ≠ 100
        ok, expected, calculated, discrepancy = validate_balance(header, txns)
        self.assertFalse(ok)
        self.assertEqual(calculated, Decimal('150.00'))
        self.assertEqual(discrepancy, Decimal('50.00'))

    def test_balance_fail_calculated_smaller(self):
        """Расчётное меньше ожидаемого."""
        header = self._make_header('100.00', '200.00')
        txns = [self._make_txn('50.00')]  # 100 + 50 = 150 ≠ 200
        ok, expected, calculated, discrepancy = validate_balance(header, txns)
        self.assertFalse(ok)
        self.assertEqual(calculated, Decimal('150.00'))
        self.assertEqual(discrepancy, Decimal('50.00'))

    # --- Граничные случаи ---

    def test_zero_amounts(self):
        """Все суммы нулевые."""
        header = self._make_header('0.00', '0.00')
        txns = [
            self._make_txn('0.00'),
            self._make_txn('-0.00'),
        ]
        ok, _, calculated, _ = validate_balance(header, txns)
        self.assertTrue(ok)
        self.assertEqual(calculated, Decimal('0.00'))

    def test_single_txn_only(self):
        """Одна транзакция."""
        header = self._make_header('22584.52', '58494.52')
        txns = [self._make_txn('35910.00')]
        ok, _, calculated, _ = validate_balance(header, txns)
        self.assertTrue(ok)
        self.assertEqual(calculated, Decimal('58494.52'))

    def test_large_numbers(self):
        """Большие числа, реалистичные данные."""
        header = self._make_header('22584.52', '8387.17')
        txns = [
            self._make_txn('35910.00'),
            self._make_txn('7517.00'),
            self._make_txn('-1500.00'),
            self._make_txn('-99.00'),
            self._make_txn('-7000.00'),
        ]
        # 22584.52 + 35910.00 + 7517.00 - 1500.00 - 99.00 - 7000.00
        # = 22584.52 + 43427.00 - 8599.00 = 57412.52 ≠ 8387.17
        ok, _, calculated, discrepancy = validate_balance(header, txns)
        self.assertFalse(ok)

    def test_precision_exact(self):
        """Точное совпадение с копейками."""
        header = self._make_header('22584.52', '31243.22')
        txns = [
            self._make_txn('10000.00'),
            self._make_txn('-1341.30'),
        ]
        # 22584.52 + 10000.00 - 1341.30 = 31243.22
        ok, _, calculated, discrepancy = validate_balance(header, txns)
        self.assertTrue(ok)
        self.assertEqual(calculated, Decimal('31243.22'))
        self.assertEqual(discrepancy, Decimal('0'))

    def test_precision_fail_by_penny(self):
        """Расхождение на 1 копейку — ошибка (допуск = 0)."""
        header = self._make_header('100.00', '200.01')
        txns = [self._make_txn('100.00')]  # 100 + 100 = 200.00 ≠ 200.01
        ok, _, _, discrepancy = validate_balance(header, txns)
        self.assertFalse(ok)
        self.assertEqual(discrepancy, Decimal('0.01'))

    def test_negative_opening(self):
        """Отрицательное начальное сальдо."""
        header = self._make_header('-100.00', '50.00')
        txns = [self._make_txn('150.00')]
        # -100 + 150 = 50
        ok, _, calculated, _ = validate_balance(header, txns)
        self.assertTrue(ok)
        self.assertEqual(calculated, Decimal('50.00'))

    def test_negative_closing(self):
        """Отрицательное конечное сальдо."""
        header = self._make_header('100.00', '-50.00')
        txns = [self._make_txn('-150.00')]
        # 100 - 150 = -50
        ok, _, calculated, _ = validate_balance(header, txns)
        self.assertTrue(ok)
        self.assertEqual(calculated, Decimal('-50.00'))


if __name__ == '__main__':
    unittest.main()
