#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @time   : 18-6-14 上午10:03
# @author : Feng_Hui
# @email  : capricorn1203@126.com
from .deal_excel import CsvToDict
csv_to_dict = CsvToDict('original_data2.csv')
my_data = csv_to_dict.read_file()
my_dict = my_data.to_dict(orient='records')
