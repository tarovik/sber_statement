#!/usr/bin/env python3
"""
Парсер выписки СберБанка из PDF в CSV.

Использование:
    python parse.py <input.pdf> [output.csv]

Если output.csv не указан, имя формируется из входного файла.
"""

import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import pdfplumber


# ═══════════════════════════════════════════════════════════════
# Модели данных
# ═══════════════════════════════════════════════════════════════

@dataclass
class Transaction:
    """Одна операция из выписки."""

    date_operation: str           # Дата операции (МСК), формат ГГГГ-ММ-ДД
    operation_time: str           # Время операции, формат ЧЧ:ММ
    date_processing: str          # Дата обработки, формат ГГГГ-ММ-ДД
    auth_code: str                # Код авторизации (6 цифр)
    category: str                 # Категория операции
    description: str              # Описание операции
    amount_rub: Decimal           # Сумма в рублях (положительная = зачисление, отрицательная = списание)
    balance: Decimal              # Остаток после операции
    card_account: str             # Номер карты/счёта (****8660) или пусто
    currency_code: str            # Код валюты операции (RSD и т.п.) или пусто
    amount_currency: Optional[Decimal] = None  # Сумма в валюте операции

    def __str__(self) -> str:
        sign = "+" if self.amount_rub >= 0 else ""
        return (
            f"{self.date_operation} | {self.category} | "
            f"{sign}{self.amount_rub} руб. | остаток {self.balance}"
        )


@dataclass
class StatementHeader:
    """Заголовок выписки — итоговая информация."""

    owner_name: str               # Владелец счёта
    account_number: str           # Номер счёта
    currency: str                 # Валюта счёта
    period_start: str             # Начало периода (ГГГГ-ММ-ДД)
    period_end: str               # Конец периода (ГГГГ-ММ-ДД)
    opening_balance: Decimal      # Остаток на начало периода
    closing_balance: Decimal      # Остаток на конец периода
    total_deposits: Decimal       # Всего пополнений
    total_withdrawals: Decimal    # Всего списаний


# ═══════════════════════════════════════════════════════════════
# Чтение PDF
# ═══════════════════════════════════════════════════════════════

def extract_pdf_text(pdf_path: str) -> list[str]:
    """
    Извлекает текст из PDF-файла и возвращает список строк для каждой страницы.

    Args:
        pdf_path: Путь к PDF-файлу.

    Returns:
        Список строк, где каждый элемент — текст одной страницы.
    """
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
    return pages_text


def split_into_lines(pages_text: list[str]) -> list[list[str]]:
    """
    Разделяет текст каждой страницы на строки.

    Args:
        pages_text: Список текстов страниц.

    Returns:
        Список списков строк (по страницам).
    """
    return [page.split('\n') for page in pages_text]


# ═══════════════════════════════════════════════════════════════
# Парсинг транзакций
# ═══════════════════════════════════════════════════════════════

# Регулярные выражения
RE_DATE = r'\d{2}\.\d{2}\.\d{4}'     # ДД.ММ.ГГГГ
RE_TIME = r'\d{2}:\d{2}'             # ЧЧ:ММ
RE_AMOUNT = r'[+-]?\d{1,3}(?:\s?\d{3})*(?:,\d{2})?'  # Русский формат числа
RE_CARD = r'\*{4}\d{4}'              # Маскированный номер карты/счёта

# Шаблон строки операции (строка 1): дата время категория сумма остаток
RE_OP_LINE1 = re.compile(
    rf'^({RE_DATE})\s+({RE_TIME})\s+(.+?)\s+({RE_AMOUNT})\s+({RE_AMOUNT})$'
)

# Шаблон строки обработки (строка 2): дата код_авторизации описание
RE_OP_LINE2 = re.compile(
    rf'^({RE_DATE})\s+(\d{{6}})\s+(.+)$'
)


def _parse_russian_number(text: str, is_debit: bool = False) -> Decimal:
    """
    Преобразует русский формат числа в Decimal.
    Примеры: "22 584,52" -> -22584.52 (списание, отрицательное),
             "+31 320,00" -> 31320.00 (зачисление, положительное),
             "31 243,22" -> -31243.22 (без знака = списание).

    Args:
        text: Строка с числом в русском формате.
        is_debit: Если True и нет явного знака, число будет отрицательным.

    Returns:
        Decimal значение.
    """
    text = text.strip()
    sign = 1
    if text.startswith('+'):
        sign = 1
        text = text[1:]
    elif text.startswith('-'):
        sign = -1
        text = text[1:]
    else:
        # Без знака = списание (отрицательное)
        sign = -1 if is_debit else 1

    # Убираем пробелы (разделители тысяч) и неразрывные пробелы
    text = text.replace('\u00a0', '').replace(' ', '')
    # Заменяем запятую на точку
    text = text.replace(',', '.')

    try:
        return Decimal(text) * sign
    except InvalidOperation:
        return Decimal('0')


def _extract_card_number(text: str) -> str:
    """
    Извлекает маскированный номер карты/счёта из текста.

    Args:
        text: Текст описания операции.

    Returns:
        Номер карты/счёта или пустая строка.
    """
    match = re.search(RE_CARD, text)
    if match:
        return match.group(0)
    return ''


def _convert_date(date_str: str) -> str:
    """
    Преобразует дату из формата ДД.ММ.ГГГГ в ГГГГ-ММ-ДД.

    Args:
        date_str: Дата в формате ДД.ММ.ГГГГ.

    Returns:
        Дата в формате ГГГГ-ММ-ДД.
    """
    parts = date_str.split('.')
    return f'{parts[2]}-{parts[1]}-{parts[0]}'


def parse_header(lines: list[str]) -> Optional[StatementHeader]:
    """
    Парсит заголовок выписки из первой страницы.

    Args:
        lines: Строки первой страницы.

    Returns:
        Объект StatementHeader или None.
    """
    header = StatementHeader(
        owner_name='',
        account_number='',
        currency='',
        period_start='',
        period_end='',
        opening_balance=Decimal('0'),
        closing_balance=Decimal('0'),
        total_deposits=Decimal('0'),
        total_withdrawals=Decimal('0'),
    )

    full_text = '\n'.join(lines)

    # Владелец счёта — строка после "Владелец счёта"
    for i, line in enumerate(lines):
        if 'Владелец счёта' in line and i + 1 < len(lines):
            header.owner_name = lines[i + 1].strip()
            break

    # Период
    m = re.search(r'За период\s+(\d{2}\.\d{2}\.\d{4})\s*[—–-]\s*(\d{2}\.\d{2}\.\d{4})', full_text)
    if m:
        header.period_start = _convert_date(m.group(1))
        header.period_end = _convert_date(m.group(2))

    # Остаток на начало и конец + пополнение/списание
    # Формат: "Остаток на ДД.ММ.ГГГГ СУММА"
    # Находим все вхождения — первое = начало, последнее = конец периода
    all_balances = list(re.finditer(
        r'Остаток на (\d{2}\.\d{2}\.\d{4})\s+(\d[\d\s]*,\d{2})', full_text
    ))
    if all_balances:
        header.opening_balance = _parse_russian_number(all_balances[0].group(2))
        header.closing_balance = _parse_russian_number(all_balances[-1].group(2))

    # Пополнение / Списание
    # В pdfplumber "Пополнение" может быть на одной строке с номером счёта
    m_dep = re.search(r'Пополнение\s+(\d[\d\s]*,\d{2})', full_text)
    if m_dep:
        header.total_deposits = _parse_russian_number(m_dep.group(1))

    # Номер счёта
    m_acc = re.search(r'(\d{5}\s?\d{3}\s?\d\s?\d{4}\s?\d{7})', full_text)
    if m_acc:
        header.account_number = m_acc.group(1).strip()

    # Валюта
    m_cur = re.search(r'Российский рубль', full_text)
    if m_cur:
        header.currency = 'RUB'

    # Пополнение и списание — ищем рядом с номером счёта
    # Формат в pdfplumber: "Номер счёта 40817 810 7 3812 XXXXXXX Пополнение 2 281 162,83"
    for line in lines:
        if 'Пополнение' in line:
            m = re.search(r'Пополнение\s+(\d[\d\s]*,\d{2})', line)
            if m:
                header.total_deposits = _parse_russian_number(m.group(1))
        if 'Списание' in line:
            m = re.search(r'Списание\s+(\d[\d\s]*,\d{2})', line)
            if m:
                header.total_withdrawals = _parse_russian_number(m.group(1))

    return header


def parse_transactions_page(lines: list[str]) -> list[Transaction]:
    """
    Парсит транзакции с одной страницы.

    Args:
        lines: Строки страницы.

    Returns:
        Список Transaction.
    """
    transactions = []

    # Находим начало таблицы операций — после маркерной строки
    # Ищем строку, содержащую "и код авторизации" или "В валюте счёта"
    start_idx = 0
    for i, line in enumerate(lines):
        if 'и код авторизации' in line or 'В валюте счёта' in line:
            start_idx = i + 1
            break

    # Пропускаем строку с "операции2" (подзаголовок)
    if start_idx < len(lines) and 'операции2' in lines[start_idx]:
        start_idx += 1

    # Обрабатываем строки, начиная с таблицы
    i = start_idx
    while i < len(lines):
        line = lines[i].strip()

        # Пропускаем служебные строки
        if (not line or
            'Продолжение' in line or
            'Страница' in line or
            'Выписка по платёжному' in line or
            'Для проверки' in line or
            'Дата формирования' in line or
            line.startswith('*') or
            'Действителен' in line or
            'Скачать' in line or
            'Проверить' in line or
            line.startswith('с ') or
            line.startswith('40') or  # хэш подписи
            'ПАО Сбербанк' in line or
            'Денежные средства' in line or
            'В выписке' in line or
            'Срок обработки' in line or
            'По курсу банка' in line or
            'Согласно статье' in line or
            '1' == line or
            '2' == line or
            'Дата списания' in line or
            'Дата закрытия' in line or
            'Дата открытия' in line or
            'Заказано в СберБанк' in line or
            'ул. Вавилова' in line or
            '900 www.sberbank' in line or
            re.match(r'^\d{2}\.\d{2}\.\d{4}$', line)):  # одинокая дата
            i += 1
            continue

        # Попробуем распарсить как строку операции (строка 1)
        m1 = RE_OP_LINE1.match(line)
        if m1:
            date_op = _convert_date(m1.group(1))
            time_str = m1.group(2)
            category = m1.group(3).strip()
            amount_str = m1.group(4)
            balance_str = m1.group(5)

            # Без знака + перед суммой = списание (отрицательное)
            is_debit = not amount_str.startswith('+')
            amount_rub = _parse_russian_number(amount_str, is_debit=is_debit)
            balance = _parse_russian_number(balance_str, is_debit=False)

            # Строка 2 (дата обработки + код + описание)
            i += 1
            if i >= len(lines):
                break

            line2 = lines[i].strip()

            # Пропускаем служебные строки между транзакциями
            while (i < len(lines) and
                   (not line2 or
                    'Продолжение' in line2 or
                    line2.startswith('*') or
                    re.match(r'^\d{2}\.\d{2}\.\d{4}$', line2))):
                i += 1
                if i < len(lines):
                    line2 = lines[i].strip()
                else:
                    break

            if i >= len(lines):
                break

            # Парсим строку 2
            m2 = RE_OP_LINE2.match(line2)
            if m2:
                date_proc = _convert_date(m2.group(1))
                auth_code_str = m2.group(2)
                description = m2.group(3).strip()

                # Извлекаем иностранную валюту и сумму из конца описания
                # Разбиваем на токены по пробелам для точного выделения
                currency_code = ''
                amount_currency = None
                tokens = description.strip().split()
                if len(tokens) >= 2:
                    last_token = tokens[-1]
                    # Проверяем: последний токен — код валюты (3 буквы)
                    if re.match(r'^[A-Z]{3}$', last_token):
                        potential_currency = last_token
                        # Ищем сумму: это может быть 2 токена ("2" + "331,00") или 1 токен ("187,00")
                        amount_found = None
                        amount_tokens = 0

                        # Сначала пробуем 2 токена ("2 331,00", "5 000" или "-2 331,00") — важнее, т.к. 1 токен может
                        # частично совпасть с "331,00" (3 цифры до запятой) или "000" (3 цифры)
                        if len(tokens) >= 3:
                            two_tokens = tokens[-3] + ' ' + tokens[-2]
                            if re.match(r'^[+-]?\d{1,3}\s\d{3}(?:,\d{2})?$', two_tokens):
                                amount_found = two_tokens
                                amount_tokens = 2

                        # Если не сработало, пробуем 1 токен ("187,00", "1500" или "-500,00")
                        if amount_found is None and len(tokens) >= 2:
                            single_token = tokens[-2]
                            if re.match(r'^[+-]?\d{1,3}(?:\s?\d{3})*(?:,\d{2})?$', single_token):
                                amount_found = single_token
                                amount_tokens = 1

                        if amount_found is not None:
                            amount_currency = _parse_russian_number(amount_found, is_debit=False)
                            currency_code = potential_currency
                            # Убираем сумму и валюту из описания
                            desc_tokens = tokens[:-(amount_tokens + 1)]
                            description = ' '.join(desc_tokens)

                auth_code = auth_code_str
                card = _extract_card_number(description)

                # Проверяем, не продолжается ли описание на следующей строке
                i += 1
                if i < len(lines):
                    next_line = lines[i].strip()
                    # Если следующая строка НЕ начинается с даты — это продолжение описания
                    if (next_line and
                        not re.match(rf'^{RE_DATE}\s', next_line) and
                        'Продолжение' not in next_line and
                        not next_line.startswith('*')):
                        # Продолжение описания
                        description += ' ' + next_line
                        # Проверяем, может быть тут номер карты
                        if not card:
                            card = _extract_card_number(next_line)
                        if not card:
                            card = _extract_card_number(description)
                        i += 1

                transaction = Transaction(
                    date_operation=date_op,
                    operation_time=time_str,
                    date_processing=date_proc,
                    auth_code=auth_code,
                    category=category,
                    description=description,
                    amount_rub=amount_rub,
                    balance=balance,
                    card_account=card,
                    currency_code=currency_code,
                    amount_currency=amount_currency,
                )
                transactions.append(transaction)
            else:
                # Строка 2 не распарсилась — возможно это однострочная запись или ошибка
                i += 1
                continue
        else:
            i += 1
            continue

    return transactions


def parse_all(pages_lines: list[list[str]]) -> tuple[Optional[StatementHeader], list[Transaction]]:
    """
    Парсит весь документ: заголовок с первой страницы и транзакции со всех страниц.

    Args:
        pages_lines: Список списков строк по страницам.

    Returns:
        Кортеж (header, transactions).
    """
    header = None
    all_transactions = []

    # Первая страница содержит заголовок и часть транзакций
    if pages_lines:
        header = parse_header(pages_lines[0])
        page1_txns = parse_transactions_page(pages_lines[0])
        all_transactions.extend(page1_txns)

    # Остальные страницы
    for page_lines in pages_lines[1:]:
        txns = parse_transactions_page(page_lines)
        all_transactions.extend(txns)

    return header, all_transactions


# ═══════════════════════════════════════════════════════════════
# Запись CSV и лога
# ═══════════════════════════════════════════════════════════════

CSV_DELIMITER = ';'
CSV_HEADER = [
    'date_operation',
    'operation_time',
    'date_processing',
    'auth_code',
    'category',
    'description',
    'amount_rub',
    'balance',
    'card_account',
    'currency_code',
    'amount_currency',
]


def _format_decimal(value: Decimal, use_comma: bool = False) -> str:
    """
    Форматирует Decimal в строку.

    Args:
        value: Decimal значение.
        use_comma: Если True, использует запятую как десятичный разделитель.

    Returns:
        Строковое представление числа.
    """
    s = str(value)
    if '.' not in s:
        s += '.00'
    if use_comma:
        s = s.replace('.', ',')
    return s


def write_csv(filepath: str, transactions: list[Transaction], decimal_comma: bool = False) -> None:
    """
    Записывает транзакции в CSV-файл.

    Args:
        filepath: Путь к выходному CSV-файлу.
        transactions: Список транзакций.
        decimal_comma: Если True, использовать запятую как десятичный разделитель.
    """
    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=CSV_DELIMITER, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(CSV_HEADER)

        for t in transactions:
            writer.writerow([
                t.date_operation,
                t.operation_time,
                t.date_processing,
                t.auth_code,
                t.category,
                t.description,
                _format_decimal(t.amount_rub, decimal_comma),
                _format_decimal(t.balance, decimal_comma),
                t.card_account,
                t.currency_code,
                _format_decimal(t.amount_currency, decimal_comma) if t.amount_currency is not None else '',
            ])

    print(f'CSV сохранён: {filepath}')


def write_log(
    filepath: str,
    header: Optional[StatementHeader],
    transactions: list[Transaction],
    balance_ok: bool,
    expected_balance: Decimal,
    calculated_balance: Decimal,
    discrepancy: Decimal,
) -> None:
    """
    Записывает лог-файл с результатами обработки и проверки баланса.

    Args:
        filepath: Путь к лог-файлу.
        header: Заголовок выписки.
        transactions: Список транзакций.
        balance_ok: Сошёлся ли баланс.
        expected_balance: Ожидаемое конечное сальдо.
        calculated_balance: Фактическое расчётное сальдо.
        discrepancy: Расхождение.
    """
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    total_credits = sum(t.amount_rub for t in transactions if t.amount_rub > 0)
    total_debits = abs(sum(t.amount_rub for t in transactions if t.amount_rub < 0))

    lines = []
    lines.append('=== ОТЧЁТ ОБРАБОТКИ ВЫПИСКИ ===')
    lines.append(f'Дата обработки: {now}')
    lines.append('')
    lines.append('--- Заголовок выписки ---')
    if header:
        lines.append(f'Владелец счёта: {header.owner_name}')
        lines.append(f'Номер счёта: {header.account_number}')
        lines.append(f'Валюта: {header.currency}')
        lines.append(f'Период: {header.period_start} — {header.period_end}')
        lines.append('')
        lines.append('--- Финансовые итоги из PDF ---')
        lines.append(f'Остаток на начало периода: {header.opening_balance}')
        lines.append(f'Пополнения (зачислено):    {header.total_deposits}')
        lines.append(f'Списания:                  {header.total_withdrawals}')
        lines.append(f'Остаток на конец периода:  {header.closing_balance}')
    lines.append('')
    lines.append('--- Результат парсинга ---')
    lines.append(f'Всего операций найдено:    {len(transactions)}')
    lines.append(f'Сумма зачислений (парсинг):  {total_credits}')
    lines.append(f'Сумма списаний (парсинг):    {total_debits}')
    lines.append(f'Расчётное конечное сальдо:   {calculated_balance}')
    lines.append(f'Ожидаемое конечное сальдо:   {expected_balance}')
    lines.append(f'Расхождение:                 {discrepancy}')
    lines.append('')

    if balance_ok:
        lines.append('--- ПРОВЕРКА БАЛАНСА: УСПЕШНО ✅ ---')
        if header:
            lines.append(
                f'{header.opening_balance} + {total_credits} - {total_debits} = {calculated_balance}'
            )
    else:
        lines.append('--- ПРОВЕРКА БАЛАНСА: ОШИБКА ❌ ---')
        lines.append(f'Ожидаемое конечное сальдо:    {expected_balance}')
        lines.append(f'Фактическое (расчётное):      {calculated_balance}')
        lines.append(f'Расхождение:                  {discrepancy}')
        lines.append('')
        lines.append('!!! ВНИМАНИЕ: Баланс НЕ СОШЁЛСЯ !!!')

    with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))

    print(f'Лог сохранён: {filepath}')


def output_csv_path(input_pdf: str, output_csv: Optional[str] = None) -> str:
    """
    Определяет путь к выходному CSV-файлу.

    Args:
        input_pdf: Путь к входному PDF.
        output_csv: Опциональный путь к CSV.

    Returns:
        Путь к CSV-файлу.
    """
    if output_csv:
        return output_csv
    base = os.path.splitext(input_pdf)[0]
    return base + '.csv'


def output_log_path(csv_path: str) -> str:
    """Определяет путь к лог-файлу."""
    base = os.path.splitext(csv_path)[0]
    return base + '.log'


# ═══════════════════════════════════════════════════════════════
# Валидация баланса
# ═══════════════════════════════════════════════════════════════

def validate_balance(
    header: Optional[StatementHeader],
    transactions: list[Transaction],
) -> tuple[bool, Decimal, Decimal, Decimal]:
    """
    Проверяет, сходится ли баланс:
    opening_balance + sum(credits) - sum(debits) = closing_balance

    Args:
        header: Заголовок выписки с начальным и конечным сальдо.
        transactions: Список транзакций.

    Returns:
        Кортеж (balance_ok, expected_balance, calculated_balance, discrepancy).
    """
    if not header:
        return False, Decimal('0'), Decimal('0'), Decimal('0')

    opening = header.opening_balance
    expected_closing = header.closing_balance

    total_credits = sum(t.amount_rub for t in transactions if t.amount_rub > 0)
    total_debits = abs(sum(t.amount_rub for t in transactions if t.amount_rub < 0))

    calculated_closing = opening + total_credits - total_debits
    discrepancy = abs(calculated_closing - expected_closing)

    balance_ok = discrepancy == Decimal('0')

    return balance_ok, expected_closing, calculated_closing, discrepancy


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='Парсинг выписки СберБанка из PDF в CSV',
        epilog='Если выходной файл не указан, имя формируется из входного.',
    )
    parser.add_argument('input_pdf', help='Путь к входному PDF-файлу выписки')
    parser.add_argument('output_csv', nargs='?', default=None,
                        help='Путь к выходному CSV-файлу (опционально)')
    parser.add_argument('--decimal-comma', action='store_true',
                        help='Использовать запятую вместо точки как десятичный разделитель')

    args = parser.parse_args()

    # 1. Извлечение текста
    print(f'Чтение PDF: {args.input_pdf}')
    try:
        pages_text = extract_pdf_text(args.input_pdf)
    except FileNotFoundError:
        print(f'ОШИБКА: Файл не найден: {args.input_pdf}')
        sys.exit(1)
    except Exception as e:
        print(f'ОШИБКА при чтении PDF: {e}')
        sys.exit(1)

    if not pages_text:
        print('ОШИБКА: Не удалось извлечь текст из PDF')
        sys.exit(1)

    print(f'Загружено страниц: {len(pages_text)}')

    # 2. Парсинг
    pages_lines = split_into_lines(pages_text)
    header, transactions = parse_all(pages_lines)

    if header:
        print(f'Владелец счёта: {header.owner_name}')
        print(f'Период: {header.period_start} — {header.period_end}')
        print(f'Начальное сальдо: {header.opening_balance}')
        print(f'Конечное сальдо: {header.closing_balance}')
        print(f'Пополнения: {header.total_deposits}')
        print(f'Списания: {header.total_withdrawals}')

    print(f'Найдено транзакций: {len(transactions)}')

    if not transactions:
        print('Нет транзакций для сохранения.')
        return

    # 3. Валидация баланса
    balance_ok, expected_balance, calculated_balance, discrepancy = validate_balance(
        header, transactions
    )

    if balance_ok:
        print('✅ ПРОВЕРКА БАЛАНСА: УСПЕШНО')
    else:
        print(f'❌ ПРОВЕРКА БАЛАНСА: ОШИБКА')
        print(f'   Ожидалось: {expected_balance}')
        print(f'   Рассчитано: {calculated_balance}')
        print(f'   Расхождение: {discrepancy}')

    # 4. Сохранение CSV
    csv_path = output_csv_path(args.input_pdf, args.output_csv)
    write_csv(csv_path, transactions, decimal_comma=args.decimal_comma)

    # 5. Сохранение лога
    log_path = output_log_path(csv_path)
    write_log(
        log_path,
        header,
        transactions,
        balance_ok,
        expected_balance,
        calculated_balance,
        discrepancy,
    )

    if not balance_ok:
        print()
        print('!!! ВНИМАНИЕ: Баланс НЕ СОШЁЛСЯ !!!')
        print(f'Проверьте лог-файл: {log_path}')
        sys.exit(1)


if __name__ == '__main__':
    main()
