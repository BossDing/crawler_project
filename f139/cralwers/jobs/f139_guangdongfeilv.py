# -*- coding: utf-8 -*-
# @author = 'Feng_hui'
# @time = '2018/2/28 9:55'
# @email = 'fengh@asto-inc.com'
from .f139_price import F139Price
from ..config import f139_config, f139_logger


class F139GdFl(F139Price):
    job_name = '富宝报价抓取——广东地区废铝价格'
    data_url = "http://data.f139.com/list.do?pid=&vid=17&qw=3:27"
    title = '{}{}'.format(f139_config.prefix_of_title, "广东地区废铝价格")

    def run(self):
        f139_logger.logger.info('正在抓取: {}'.format(self.job_name))
        if not self.is_login():
            self.login()
        selector = self.get_selector(self.data_url)
        name = selector.xpath('//div[@id="#"]/div/table/tr/td[position()=1]/a')
        area = selector.xpath('//div[@id="#"]/div/table/tr/td[position()=2]')
        rate = selector.xpath('//div[@id="#"]/div/table/tr/td[position()=3]')
        price = selector.xpath('//div[@id="#"]/div/table/tr/td[position()=5]')
        up_or_down = selector.xpath('//div[@id="#"]/div/table/tr/td[position()=6]')
        # 第一列：地区
        first_column = [each_row.xpath('text()')[0].strip().replace('地区/来源', '省份').replace('山东临沂', '山东')
                        for each_row in area]
        # # 第二列：含量
        second_column = [each_row.xpath('text()')[0].strip() for each_row in rate]
        # 第三列：品名
        third_column = ['品名']
        third_column.extend([each_row.xpath('text()')[0].strip() for each_row in name])
        # 第四列：价格
        fourth_column = [each_row.xpath('text()')[0].strip().replace('价格', '不含税价（元/吨）')
                         for each_row in price]
        # 第四列：涨跌
        fifth_column = []
        for each_row in up_or_down:
            text_flat = each_row.xpath('text()')
            # print(text_flat)
            if text_flat and text_flat != ['\r\n\t\t\t\t\t\t\t', '\r\n\t\t\t\t\t']:
                fifth_column.append(text_flat[0].strip())
            else:
                # print(each_row.xpath('string(.)'))
                text_rise = each_row.xpath('font[@class="up"]/text()')
                # print(text_rise)
                if text_rise:
                    fifth_column.append('&uarr;' + text_rise[0].strip())
                else:
                    text_fall = each_row.xpath('font[@class="down"]/text()')
                    # print(text_fall)
                    if text_fall:
                        # print(text_fall)
                        fifth_column.append('&darr;' + text_fall[0].strip())
                    else:
                        fifth_column.append('')
        # 整合表格
        first_column = first_column[0:8] + first_column[9:15] + first_column[16:21]
        second_column = second_column[0:8] + second_column[9:15] + second_column[16:21]
        third_column = third_column[0:8] + third_column[9:15] + third_column[16:21]
        fourth_column = fourth_column[0:8] + fourth_column[9:15] + fourth_column[16:21]
        fifth_column = fifth_column[0:8] + fifth_column[9:15] + fifth_column[16:21]
        table = zip(first_column, second_column, third_column, fourth_column, fifth_column)
        single_tr = []

        # 构造表格
        for each_row in table:
            # print(each_row, type(each_row))
            single_tr.append('<tr>' + ''.join(['<td>' + str(each) + '</td>' for each in each_row]) + '</tr>')
        table_content = '<table>' + ''.join(single_tr) + '</table>'
        print(table_content)
        return table_content


# if __name__ == "__main__":
#     start_time = time.time()
#     f139_price = F139GdFl()
#     f139_price.run()
#     # import os
#     # print(os.pardir)
#     print('总共用时：', time.time() - start_time)
