"""Минимальный генератор XLSX без внешних зависимостей (zip + OOXML)."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, Sequence
from xml.sax.saxutils import escape

TITLE = 1
SUBTITLE = 2
HEADER = 3
BODY = 4
BODY_CENTER = 5
WEEKEND = 6
HOLIDAY = 7
TOTAL = 8
SIGNATURE = 9
BOLD = 10
WEEKEND_CENTER = 11
HOLIDAY_CENTER = 12
BOLD_WEEKEND = 13
BOLD_HOLIDAY = 14
MATRIX_DUTY = 15
WEEKEND_HEAD = 16
HOLIDAY_HEAD = 17
BW_HEADER = 18
BW_BODY = 19
BW_CENTER = 20
BW_WEEKEND = 21
BW_HOLIDAY = 22
BW_BOLD = 23
BW_SIGNATURE = 24
BW_HOLIDAY_BOLD = 25
BW_WEEKEND_BOLD = 26

Cell = tuple[Any, int]

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="5">
<font><sz val="11"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="15"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="10.5"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>
<font><i/><sz val="9"/><color rgb="FF64748B"/><name val="Calibri"/><family val="2"/></font>
</fonts>
<fills count="9">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF0F766E"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFEF3C7"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF1F5F9"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE7E7E7"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="lightUp"><fgColor rgb="FF000000"/><bgColor rgb="FFFFFFFF"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFD9D9D9"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="3">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFCBD5E1"/></left><right style="thin"><color rgb="FFCBD5E1"/></right><top style="thin"><color rgb="FFCBD5E1"/></top><bottom style="thin"><color rgb="FFCBD5E1"/></bottom><diagonal/></border>
<border><left style="thin"><color rgb="FF000000"/></left><right style="thin"><color rgb="FF000000"/></right><top style="thin"><color rgb="FF000000"/></top><bottom style="thin"><color rgb="FF000000"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="27">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="3" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="1" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>
<xf numFmtId="0" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="1" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="1" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="3" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="1" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="1" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="1" fillId="8" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="2" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="2" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="6" borderId="2" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="7" borderId="2" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="1" fillId="0" borderId="2" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>
<xf numFmtId="0" fontId="1" fillId="7" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="1" fillId="6" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


@dataclass
class Sheet:
    name: str
    rows: Sequence[Sequence[Cell]]
    widths: Sequence[float]
    merges: Sequence[str] = ()
    row_heights: dict[int, float] = field(default_factory=dict)
    freeze_rows: int = 0
    freeze_cols: int = 0
    print_title_rows: tuple[int, int] | None = None
    print_title_column: bool = False
    orientation: str = "landscape"
    fit_to_width: int | None = 1
    scale: int | None = None
    footer: tuple[str, str, str] = ("", "", "")


def _column(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def column_name(index: int) -> str:
    """Имя колонки по индексу с нуля: 0 → A, 27 → AB."""
    return _column(index)


def _sheet_name(name: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", " ", name).strip()[:31]
    return cleaned or "Лист"


def _cell_xml(reference: str, value: Any, style: int) -> str:
    if value is None or value == "":
        return f'<c r="{reference}" s="{style}"/>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{reference}" s="{style}"><v>{value}</v></c>'
    text = escape(str(value))
    return (
        f'<c r="{reference}" s="{style}" t="inlineStr">'
        f'<is><t xml:space="preserve">{text}</t></is></c>'
    )


def _sheet_xml(sheet: Sheet) -> str:
    heights = sheet.row_heights
    max_cols = max((len(row) for row in sheet.rows), default=1)

    sheet_rows = []
    for row_index, row in enumerate(sheet.rows, start=1):
        height = heights.get(row_index)
        attrs = f' r="{row_index}"'
        if height:
            attrs += f' ht="{height}" customHeight="1"'
        cells = "".join(
            _cell_xml(f"{_column(col_index)}{row_index}", value, style)
            for col_index, (value, style) in enumerate(row)
        )
        sheet_rows.append(f"<row{attrs}>{cells}</row>")

    cols = "".join(
        f'<col min="{index + 1}" max="{index + 1}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(sheet.widths)
    )
    merge_xml = ""
    if sheet.merges:
        merge_xml = (
            f'<mergeCells count="{len(sheet.merges)}">'
            + "".join(f'<mergeCell ref="{ref}"/>' for ref in sheet.merges)
            + "</mergeCells>"
        )
    pane_xml = ""
    if sheet.freeze_rows or sheet.freeze_cols:
        top_left = f"{_column(sheet.freeze_cols)}{sheet.freeze_rows + 1}"
        if sheet.freeze_cols and sheet.freeze_rows:
            pane = "bottomRight"
        elif sheet.freeze_cols:
            pane = "topRight"
        else:
            pane = "bottomLeft"
        pane_xml = (
            f'<pane xSplit="{sheet.freeze_cols}" ySplit="{sheet.freeze_rows}" '
            f'topLeftCell="{top_left}" activePane="{pane}" state="frozen"/>'
            f'<selection pane="{pane}" activeCell="{top_left}" sqref="{top_left}"/>'
        )
    footer_xml = ""
    left, center, right = sheet.footer
    if left or center or right:
        footer_xml = (
            "<headerFooter><oddFooter>"
            f"&amp;L{escape(left)}&amp;C{escape(center)}&amp;R{escape(right)}"
            "</oddFooter></headerFooter>"
        )
    sheet_pr = (
        '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>'
        if sheet.fit_to_width is not None else ""
    )
    if sheet.fit_to_width is not None:
        page_setup = (
            f'<pageSetup paperSize="9" orientation="{sheet.orientation}" '
            'fitToWidth="1" fitToHeight="0"/>'
        )
    else:
        page_setup = (
            f'<pageSetup paperSize="9" orientation="{sheet.orientation}" '
            f'scale="{sheet.scale or 100}"/>'
        )

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
{sheet_pr}
<dimension ref="A1:{_column(max_cols - 1)}{len(sheet.rows)}"/>
<sheetViews><sheetView workbookViewId="0">{pane_xml}</sheetView></sheetViews>
<sheetFormatPr defaultRowHeight="16"/>
<cols>{cols}</cols>
<sheetData>{"".join(sheet_rows)}</sheetData>
{merge_xml}
<printOptions horizontalCentered="1"/>
<pageMargins left="0.35" right="0.25" top="0.55" bottom="0.55" header="0.2" footer="0.25"/>
{page_setup}
{footer_xml}
</worksheet>"""


def _print_titles(sheet: Sheet) -> str | None:
    refs = []
    if sheet.print_title_column:
        refs.append(f"'{escape(_sheet_name(sheet.name))}'!$A:$A")
    if sheet.print_title_rows:
        first, last = sheet.print_title_rows
        refs.append(f"'{escape(_sheet_name(sheet.name))}'!${first}:${last}")
    return ",".join(refs) if refs else None


def build_workbook(sheets: Sequence[Sheet]) -> bytes:
    if not sheets:
        raise ValueError("Нужен хотя бы один лист")
    names = [_sheet_name(item.name) for item in sheets]
    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    workbook_sheets = []
    workbook_rels = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    defined_names = []
    for index, sheet in enumerate(sheets):
        number = index + 1
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{number}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        workbook_sheets.append(
            f'<sheet name="{escape(names[index])}" sheetId="{number}" r:id="rId{number}"/>'
        )
        workbook_rels.append(
            f'<Relationship Id="rId{number}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{number}.xml"/>'
        )
        titles = _print_titles(sheet)
        if titles:
            defined_names.append(
                f'<definedName name="_xlnm.Print_Titles" localSheetId="{index}">'
                f"{titles}</definedName>"
            )
    content_types.append("</Types>")
    workbook_rels.append(
        '<Relationship Id="rId%d" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>' % (len(sheets) + 1)
    )
    workbook_rels.append("</Relationships>")

    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
        '<bookViews><workbookView activeTab="0"/></bookViews>\n'
        f'<sheets>{"".join(workbook_sheets)}</sheets>\n'
        + (
            f'<definedNames>{"".join(defined_names)}</definedNames>\n'
            if defined_names else ""
        )
        + "</workbook>"
    )
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "".join(content_types))
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", "".join(workbook_rels))
        archive.writestr("xl/styles.xml", _STYLES)
        for index, sheet in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(sheet))
    return buffer.getvalue()
