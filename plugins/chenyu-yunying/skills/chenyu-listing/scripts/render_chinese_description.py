"""Render a validated Chinese HTML description as readable Excel rich text."""

from copy import copy
from html.parser import HTMLParser
from math import ceil
from re import sub
from unicodedata import east_asian_width


class _DescriptionParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.runs = []
        self.stack = []

    def _append(self, value, bold=False):
        if not value:
            return
        if self.runs and self.runs[-1][1] == bold:
            self.runs[-1] = (self.runs[-1][0] + value, bold)
        else:
            self.runs.append((value, bold))

    def handle_starttag(self, tag, attrs):
        if tag not in {'p', 'b', 'br'} or attrs:
            raise ValueError(f'Unsupported description HTML tag: {tag}')
        if tag == 'br':
            self._append('\n')
        else:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag != 'br' or attrs:
            raise ValueError(f'Unsupported description HTML tag: {tag}')
        self._append('\n')

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            raise ValueError(f'Unbalanced description HTML tag: {tag}')
        self.stack.pop()
        if tag == 'p':
            self._append('\n\n')

    def handle_data(self, data):
        value = sub(r'\s+', ' ', data)
        if self.runs and self.runs[-1][0].endswith('\n'):
            value = value.lstrip()
        self._append(value, 'b' in self.stack)


def description_runs(source_html):
    """Return (text, bold) runs while retaining paragraph and line breaks."""
    parser = _DescriptionParser()
    parser.feed(str(source_html))
    parser.close()
    if parser.stack:
        raise ValueError('Unclosed description HTML tag')
    while parser.runs:
        value, bold = parser.runs[-1]
        trimmed = value.rstrip('\n')
        if trimmed:
            parser.runs[-1] = (trimmed, bold)
            break
        parser.runs.pop()
    return parser.runs


def _display_width(line):
    return sum(2 if east_asian_width(character) in {'F', 'W'} else 1
               for character in line)


def write_chinese_description(cell, source_html, min_column_width=45):
    """Write formatted translation to an openpyxl cell and make it readable."""
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont

    runs = description_runs(source_html)
    cell.value = CellRichText(
        [TextBlock(InlineFont(b=True), value) if bold else value
         for value, bold in runs]
    )
    alignment = copy(cell.alignment)
    alignment.wrap_text = True
    alignment.vertical = 'top'
    cell.alignment = alignment
    column = cell.parent.column_dimensions[cell.column_letter]
    column.width = max(column.width or 0, min_column_width)
    plain_text = ''.join(value for value, _ in runs)
    width = max(1, column.width)
    visual_lines = sum(max(1, ceil(_display_width(line) / width))
                       for line in plain_text.split('\n'))
    row = cell.parent.row_dimensions[cell.row]
    row.height = max(row.height or 0, min(409, 12 + 15 * visual_lines))
    return cell
