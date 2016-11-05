# pylint: disable=no-member

import json
import logging
from datetime import datetime

import openpyxl
import xlrd

log = logging.getLogger(__name__)

from .metric import Metric

def save_json(data, path):
    with open(path, 'w') as outfile:
        json.dump(data, outfile, indent=4)

    return path


def save_xlsx(data, path):
    log.debug("Creating %s", path)
    workbook = openpyxl.Workbook()
    worksheet = workbook.active

    # Add header row
    header = _get_header(data)
    log.debug("Header: %s", header)
    worksheet.append(header)

    # Enable filtering on every column
    worksheet.auto_filter.ref = "A1:ZZ9999"
    for index in range(len(header)):
        worksheet.auto_filter.add_filter_column(index, [])

    # Add data rows
    for datum in data:
        row = [datum.get(key, '') for key in header]
        log.debug("Row: %s", row)
        worksheet.append(row)

    workbook.save(path)

    return path


def _get_header(data):
    """Collect column names from every data set."""
    header = set()

    for datum in data:
        header.update(datum.keys())

    return list(header)

def parse_xlsx_into_dicts(xl):
    '''
    :param xl: an xlrd object
    :return:
    '''
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
            year, month, day, hour, minute, second = xlrd.xldate_as_tuple(metric_dict['Date'], xl.datemode)
            metric_dict['Date'] = datetime(year, month, day, hour, minute, second)
            # done with this row
            yield metric_dict

def merge_metrics_from_dicts(metric_dicts):
    for metric_dict in metric_dicts:
        m = Metric.find(PropertyID=metric_dict['PropertyID'], Date=metric_dict['Date'])
        m.update(**metric_dict)
        m.save()
