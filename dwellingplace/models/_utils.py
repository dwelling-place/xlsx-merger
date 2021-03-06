# pylint: disable=no-member

import json
import logging
from datetime import datetime
from typing import List
from collections import defaultdict

import xlrd
import xlsxwriter

from .metric import Metric
from .structure import Structure


log = logging.getLogger(__name__)


def parse_xlsx_into_dicts(xl):
    """
    :param xl: an xlrd object
    :return:
    """
    for sheet_name in xl.sheet_names():
        sheet = xl.sheet_by_name(sheet_name)
        column_names = sheet.row_values(0)
        # mongodb doesn't like '.' in field names
        column_names = [c.replace('.', '') for c in column_names]
        for row in range(1, sheet.nrows):
            metric_dict = {}
            for col in range(0, sheet.ncols):
                col_name = column_names[col]
                if col_name:  # ignore blanks
                    metric_dict[col_name] = sheet.cell(row, col).value
            # special conversions
            try:
                year, month, *_ = xlrd.xldate_as_tuple(metric_dict['Date'], xl.datemode)
                metric_dict['Date'] = datetime(year, month, 1, 0, 0, 0)
            except TypeError as err:
                errmsg = "Invalid date in sheet {!r} row {}. Go back, fix the cell in your spreadsheet, and upload it again.".format(sheet_name, row)
                err.message = errmsg
                raise err
            # done with this row
            yield metric_dict


def merge_metrics_from_dicts(metric_dicts):
    for new_data in metric_dicts:
        metric = Metric.find(PropertyID=new_data['PropertyID'], Date=new_data['Date'])
        for k, v in new_data.items():
            if v not in (None, ''):
                metric[k] = v
        metric.save()


def update_structure(xl, structure):
    """
    :param xl: an xlrd object
    """
    for sheet_name in xl.sheet_names():
        sheet = xl.sheet_by_name(sheet_name)
        column_names = sheet.row_values(0)
        # mongodb doesn't like '.' in field names
        column_names = [c.replace('.', '') for c in column_names]
        structure[sheet_name] = column_names
    return structure


def save_json(data, path):
    with open(path, 'w') as outfile:
        json.dump(data, outfile, indent=4)

    return path


def save_xlsx(data: list, sheets: List[str], path: str, *, prefill: bool):
    log.debug("Creating %s", path)
    workbook = xlsxwriter.Workbook(path)
    structure = Structure.load()

    for sheet_name, column_names in structure.items():
        if sheet_name not in sheets:
            continue

        worksheet = workbook.add_worksheet(sheet_name)
        prefill_cache = defaultdict(list)

        # Add header row
        header = column_names
        log.debug("Add header: %s", header)
        worksheet.write_row(0, 0, header)

        # Add data rows
        row = 1
        for datum in data:

            if skip_row(datum, header):
                continue

            update_cache(datum, prefill_cache)

            for col, key in enumerate(header):
                value, options = get_value(datum, key)
                fmt = workbook.add_format(options) if options else None
                worksheet.write(row, col, value, fmt)

            row += 1

        # Prefill rows
        if prefill and prefill_cache:
            most_recent_date = max(prefill_cache.keys())
            next_date = increment_month(most_recent_date)
            log.info("Prefilling data for %s", next_date)
            for key in prefill_cache[most_recent_date]:
                worksheet.write(row, 0, key)
                # TODO: don't specify formatting here, use `get_value`
                fmt = workbook.add_format({'num_format': "mmm yyyy"})
                worksheet.write(row, 1, next_date, fmt)
                row += 1

        # Convert the data to a table (for Microsoft BI)
        worksheet.add_table(0, 0, row - 1, len(header) - 1, {
            'autofilter': False,
            'style': '',
            'banded_rows': False,
            'columns': [{'header': col_name} for col_name in column_names],
        })

        # Set column widths
        for col, name in enumerate(header):
            worksheet.set_column(col, col, max(len(name) * 0.95, 10))
        worksheet.set_column(0, 0, 12)  # PropertyID
        worksheet.set_column(1, 1, 11)  # Date

    workbook.close()

    return path


def get_header(data):
    """Collect column names from every data set."""
    header = set()

    for datum in data:
        header.update(datum.keys())

    return list(header)


def skip_row(datum, header):
    """Determine if a row has not been filled in for this sheet."""
    values = [datum.get(key) for key in header]
    return sum(1 for value in values if value) <= 4


def update_cache(datum, cache):
    key, _ = get_value(datum, 'PropertyID')
    date, _ = get_value(datum, 'Date')
    if key and date:
        cache[date].append(key)


def get_value(datum, key):
    """Optimize the value and format for XLSX storage."""
    value = datum.get(key, None)
    options = None

    if isinstance(value, datetime):
        value = value.replace(tzinfo=None)
        options = {'num_format': "mmm yyyy"}

    if isinstance(value, float) and -1 < value < 1.0 and value != 0:
        options = {'num_format': "0.00%"}

    return value, options


def increment_month(date):
    year = date.year
    month = date.month + 1

    if month > 12:
        month = 1
        year += 1

    return date.replace(year=year, month=month)
