import re


BLOCKED_SQL = re.compile(r'\b(insert|update|delete|drop|alter|create|grant|revoke|attach|detach|pragma|vacuum|replace|truncate)\b', re.I)
MAX_SQL_LENGTH = 20_000


def validate_readonly_sql(query: str) -> str:
    if not isinstance(query, str) or len(query) > MAX_SQL_LENGTH:
        raise ValueError('Query is missing or too long.')
    query = query.strip().rstrip(';')
    if not query.lower().startswith(('select ', 'with ')):
        raise ValueError('Only SELECT and WITH queries are permitted.')
    if ';' in query or '--' in query or '/*' in query or '*/' in query or BLOCKED_SQL.search(query):
        raise ValueError('Unsafe SQL operation rejected.')
    return query
