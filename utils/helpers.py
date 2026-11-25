"""
Common presentation helpers, currency formatters, and number-to-words converters.
"""
from decimal import Decimal
from typing import Union


def format_currency(amount: Union[Decimal, float, int, str], symbol: str = "₹") -> str:
    """Format numeric value in Indian Rupee format e.g. ₹1,23,456.00."""
    try:
        val = Decimal(str(amount))
        # Indian number grouping
        is_negative = val < 0
        val = abs(val)
        parts = f"{val:.2f}".split(".")
        integer_part = parts[0]
        decimal_part = parts[1]

        if len(integer_part) > 3:
            last_three = integer_part[-3:]
            remaining = integer_part[:-3]
            # Group remaining in twos
            groups = []
            while remaining:
                groups.append(remaining[-2:])
                remaining = remaining[:-2]
            groups.reverse()
            formatted_int = ",".join(groups) + "," + last_three
        else:
            formatted_int = integer_part

        formatted = f"{symbol}{'-' if is_negative else ''}{formatted_int}.{decimal_part}"
        return formatted
    except Exception:
        return f"{symbol}{amount}"


def number_to_words_inr(amount: Union[Decimal, float, int]) -> str:
    """Convert amount to Indian Rupee words (e.g. 'One Thousand Two Hundred Rupees Only')."""
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def convert_two_digits(n):
        if n < 20:
            return ones[n]
        else:
            t = tens[n // 10]
            o = ones[n % 10]
            return f"{t} {o}".strip()

    def convert_three_digits(n):
        h = n // 100
        rem = n % 100
        res = []
        if h > 0:
            res.append(f"{ones[h]} Hundred")
        if rem > 0:
            if res:
                res.append("and")
            res.append(convert_two_digits(rem))
        return " ".join(res).strip()

    val = Decimal(str(amount))
    int_part = int(val)
    paise = int(round((val - int_part) * 100))

    if int_part == 0:
        words = "Zero Rupees"
    else:
        parts = []
        crore = int_part // 10000000
        int_part %= 10000000
        lakh = int_part // 100000
        int_part %= 100000
        thousand = int_part // 1000
        int_part %= 1000
        hundreds = int_part

        if crore > 0:
            parts.append(f"{convert_two_digits(crore)} Crore")
        if lakh > 0:
            parts.append(f"{convert_two_digits(lakh)} Lakh")
        if thousand > 0:
            parts.append(f"{convert_two_digits(thousand)} Thousand")
        if hundreds > 0:
            parts.append(convert_three_digits(hundreds))

        words = " ".join(parts).strip() + " Rupees"

    if paise > 0:
        words += f" and {convert_two_digits(paise)} Paise"

    return words + " Only"
