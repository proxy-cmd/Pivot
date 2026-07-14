import re


BLOCKED_SQL = re.compile(r'\b(insert|update|delete|drop|alter|create|grant|revoke|attach|detach|pragma|vacuum|replace|truncate)\b', re.I)


def validate_readonly_sql(query: str) -> str:
    query = query.strip().rstrip(';')
    if not query.lower().startswith(('select ', 'with ')):
        raise ValueError('Only SELECT and WITH queries are permitted.')
    if ';' in query or BLOCKED_SQL.search(query):
        raise ValueError('Unsafe SQL operation rejected.')
    return query
