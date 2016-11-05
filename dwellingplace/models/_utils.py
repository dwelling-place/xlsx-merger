# pylint: disable=no-member

import json
import logging
from datetime import datetime

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
                parts = xlrd.xldate_as_tuple(metric_dict['Date'], xl.datemode)
                metric_dict['Date'] = datetime(*parts)
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
    structure.save()


def save_json(data, path):
    with open(path, 'w') as outfile:
        json.dump(data, outfile, indent=4)

    return path


def save_xlsx(data, path):
    log.debug("Creating %s", path)
    workbook = xlsxwriter.Workbook(path)
    structure = Structure.load()
    for sheet_name, column_names in structure.items():
        worksheet = workbook.add_worksheet(sheet_name)

        # Add header row
        header = column_names
        log.debug("Header: %s", header)

        # Add data rows
        index = 1
        for datum in data:
            row = [datum.get(key, None) for key in header]
            if len(list(filter(None, row))) <= 4:
                log.debug("Skipping Row since it is mostly Nones: %s", row)
            else:
                worksheet.write_row(index, 0, row)
                index += 1

        # Convert the data to a table (for Microsoft BI)
        worksheet.add_table("A1:ZZ9999")  # pylint: disable=no-value-for-parameter
        worksheet.write_row(0, 0, header)

    workbook.close()

    return path
