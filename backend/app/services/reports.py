"""Generate and persist dataset report exports."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from ..dataset_io import save_text
from ..store import add_report

SUPPORTED_FORMATS = {'md', 'csv', 'pdf'}


def create(dataset: dict[str, Any], title: str, format_name: str) -> dict[str, str]:
    normalized_format = validate_format(format_name)
    report_title = title or 'Pivot report'
    filename = safe_filename(report_title)

    content, suffix = render_report(dataset, report_title, normalized_format)
    path = save_text(dataset, content, filename, f'.{suffix}')
    report_id = add_report(dataset['id'], report_title, normalized_format, path)

    return {
        'id': report_id,
        'title': report_title,
        'format': normalized_format,
        'download_url': f'/api/datasets/{dataset["id"]}/reports/{report_id}/download',
    }


def validate_format(format_name: str) -> str:
    normalized_format = format_name.lower()
    if normalized_format not in SUPPORTED_FORMATS:
        raise ValueError('Reports currently support Markdown, CSV, and PDF.')
    return normalized_format


def safe_filename(title: str) -> str:
    normalized = re.sub(r'[^a-zA-Z0-9_-]+', '-', title).strip('-').lower()
    return normalized or 'pivot-report'


def render_report(dataset: dict[str, Any], title: str, format_name: str) -> tuple[str, str]:
    if format_name == 'csv':
        return csv_report(dataset), 'csv'

    markdown = markdown_report(dataset, title)
    if format_name == 'pdf':
        return pdf_report(markdown), 'pdf'

    return markdown, 'md'


def markdown_report(dataset: dict[str, Any], title: str) -> str:
    profile = dataset.get('profile') or {}
    issues = profile.get('issues', [])
    issue_lines = '\n'.join(
        f"- {issue['type']}: {issue['count']} affected rows — {issue['impact']}"
        for issue in issues
    )
    return (
        f'# {title}\n\n'
        f'Dataset: **{dataset["name"]}**\n\n'
        '## Profile\n\n'
        f'- Rows: {profile.get("rows", 0)}\n'
        f'- Columns: {profile.get("columns", 0)}\n'
        f'- Quality score: {profile.get("quality_score", 0)}/100\n\n'
        '## Detected issues\n\n'
        f'{issue_lines}'
    )


def csv_report(dataset: dict[str, Any]) -> str:
    profile = dataset.get('profile') or {}
    rows = [
        {'field': 'dataset', 'value': dataset['name']},
        {'field': 'rows', 'value': profile.get('rows', 0)},
        {'field': 'columns', 'value': profile.get('columns', 0)},
        {'field': 'quality_score', 'value': profile.get('quality_score', 0)},
    ]
    return pd.DataFrame(rows).to_csv(index=False)


def pdf_report(markdown: str) -> str:
    content_stream = pdf_content_stream(markdown)
    objects = pdf_objects(content_stream)
    return assemble_pdf(objects)


def pdf_content_stream(markdown: str) -> str:
    lines = markdown.replace('**', '').splitlines()[:42]
    text_operations = ' '.join(f'({escape_pdf_text(line[:115])}) Tj 0 -16 Td' for line in lines)
    return f'BT /F1 11 Tf 48 760 Td {text_operations} ET'


def escape_pdf_text(value: str) -> str:
    encoded = str(value).encode('latin-1', 'replace').decode('latin-1')
    return encoded.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def pdf_objects(content_stream: str) -> list[str]:
    line_break = '\n'
    content_length = len(content_stream.encode('latin-1', 'replace'))
    return [
        '<< /Type /Catalog /Pages 2 0 R >>',
        '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        f'<< /Length {content_length} >>{line_break}stream{line_break}{content_stream}{line_break}endstream',
    ]


def assemble_pdf(objects: list[str]) -> str:
    line_break = '\n'
    pdf = '%PDF-1.4' + line_break
    offsets = [0]
    for index, object_value in enumerate(objects, 1):
        offsets.append(len(pdf.encode('latin-1')))
        pdf += f'{index} 0 obj{line_break}{object_value}{line_break}endobj{line_break}'

    cross_reference_offset = len(pdf.encode('latin-1'))
    cross_reference = ''.join(f'{offset:010d} 00000 n {line_break}' for offset in offsets[1:])
    return (
        f'{pdf}xref{line_break}0 {len(objects) + 1}{line_break}'
        f'0000000000 65535 f {line_break}{cross_reference}'
        f'trailer << /Size {len(objects) + 1} /Root 1 0 R >>{line_break}'
        f'startxref{line_break}{cross_reference_offset}{line_break}%%EOF'
    )
