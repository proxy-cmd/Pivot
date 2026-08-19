import re


BLOCKED_SQL = re.compile(r'\b(insert|update|delete|drop|alter|create|grant|revoke|attach|detach|pragma|vacuum|replace|truncate)\b', re.I)
MAX_SQL_LENGTH = 20_000


def validate_readonly_sql(query: str) -> str:
    if not isinstance(query, str):
        raise ValueError('Query is missing or too long.')

    if len(query) > MAX_SQL_LENGTH:
        raise ValueError('Query is missing or too long.')

    normalized_query = query.strip().rstrip(';')
    if not normalized_query.lower().startswith(('select ', 'with ')):
        raise ValueError('Only SELECT and WITH queries are permitted.')

    if contains_sql_comment(normalized_query):
        raise ValueError('Unsafe SQL operation rejected.')

    if BLOCKED_SQL.search(normalized_query):
        raise ValueError('Unsafe SQL operation rejected.')

    return normalized_query


def contains_sql_comment(query: str) -> bool:
    return ';' in query or '--' in query or '/*' in query or '*/' in query
