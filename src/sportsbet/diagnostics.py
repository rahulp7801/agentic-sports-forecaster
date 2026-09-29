"""Bounded worker diagnostics without exception messages, SQL, or credentials."""
import re


def error_fields(error: Exception) -> dict:
    result = {'error_type': type(error).__name__}
    seen = set()
    current = error
    for _ in range(4):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        code = getattr(current, 'sqlstate', None)
        if isinstance(code, str) and re.fullmatch(r'[0-9A-Z]{5}', code):
            result['sqlstate'] = code
            break
        current = getattr(current, 'orig', None) or getattr(current, '__cause__', None)
    return result
