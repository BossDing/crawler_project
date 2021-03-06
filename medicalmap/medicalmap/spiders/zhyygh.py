# -*- coding: utf-8 -*-
import re
import scrapy
from urllib.parse import urljoin
from w3lib.html import remove_tags
from scrapy.http import Request
from scrapy.loader.processors import MapCompose
from medicalmap.utils.common import now_day, custom_remove_tags, get_county2, match_special, clean_info2
from medicalmap.items import CommonLoader2, HospitalInfoItem, HospitalDepItem, DoctorInfoItem, DoctorRegInfoItem


class ZhyyghSpider(scrapy.Spider):
    name = 'zhyygh'
    allowed_domains = ['zhyygh.cn']
    start_urls = ['https://www.zhyygh.cn/web/hospital_list.jsp']

    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'Host': 'www.zhyygh.cn',
        'Referer': 'https://www.zhyygh.cn/web/index.jsp',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/65.0.3325.181 Safari/537.36'
    }
    custom_settings = {
        # 延迟设置
        # 'DOWNLOAD_DELAY': 1,
        # 自动限速设置
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 1,
        'AUTOTHROTTLE_MAX_DELAY': 3,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 32.0,
        'AUTOTHROTTLE_DEBUG': False,
        # 并发请求数的控制,默认为16
        'CONCURRENT_REQUESTS': 16
    }
    host = 'https://www.zhyygh.cn/web/'
    entry_url = 'https://www.zhyygh.cn/web/hospital_list.jsp'
    dept_url = 'https://www.zhyygh.cn/web/include/hospital/dept_listNew.jsp?hospital_id={}&t={}'
    doctor_url = 'https://www.zhyygh.cn/web/include/hospital/doctor_listNew.jsp?hospital_id={}&t={}'
    temp_dept_type = ''
    temp_dept_name = ''
    data_source_from = '珠海预约挂号平台'

    def start_requests(self):
        yield Request(self.entry_url, headers=self.headers, callback=self.parse)

    def parse(self, response):
        self.logger.info('>>>>>>正在抓取所有医院信息>>>>>>')
        try:
            all_hospital = response.xpath('//h6/a[contains(@href,"hospital.jsp")]')
            for each_hospital in all_hospital:
                each_hospital_link = each_hospital.xpath('@href').extract_first('')
                each_hospital_name = each_hospital.xpath('text()').extract_first('')
                if each_hospital_link:
                    each_hospital_link = urljoin(self.host, each_hospital_link)
                    self.headers['Referer'] = response.url
                    yield Request(each_hospital_link,
                                  headers=self.headers,
                                  callback=self.parse_hospital_info,
                                  dont_filter=True)

                    # 获取科室信息
                    hospital_id = re.search(r'hospital_id=(\d+)', each_hospital_link)
                    if hospital_id:
                        hospital_id = hospital_id.group(1)
                        # 科室信息
                        dept_link = self.dept_url.format(hospital_id, timestamp())
                        self.headers['Referer'] = response.url
                        yield Request(dept_link,
                                      headers=self.headers,
                                      callback=self.parse_hospital_dep,
                                      meta={
                                          'hospital_name': each_hospital_name
                                      })
                        # 医生信息
                        doctor_link = self.doctor_url.format(hospital_id, timestamp())
                        self.headers['Referer'] = response.url
                        yield Request(doctor_link,
                                      headers=self.headers,
                                      callback=self.parse_doctor_info,
                                      meta={
                                          'hospital_name': each_hospital_name
                                      })
        except Exception as e:
            self.logger.error('在抓取所有医院信息过程中出错了,原因是：{}'.format(repr(e)))

    def parse_hospital_info(self, response):
        self.logger.info('>>>>>>正在抓取医院详细信息>>>>>>')
        try:
            hospital_address = response.xpath('//b[contains(text(),"医院地址")]/'
                                              'ancestor::td[1]/text()').extract_first('')
            hospital_county = get_county2('中国|广东省|广东|珠海市|珠海', hospital_address)
            loader = CommonLoader2(item=HospitalInfoItem(), response=response)
            loader.add_xpath('hospital_name',
                             '//b[contains(text(),"医院全称")]/ancestor::td[1]/text()',
                             MapCompose(custom_remove_tags))
            loader.add_xpath('hospital_level',
                             '//b[contains(text(),"医院级别")]/ancestor::td[1]/text()',
                             MapCompose(custom_remove_tags))
            loader.add_value('hospital_addr', hospital_address, MapCompose(custom_remove_tags))
            loader.add_value('hospital_pro', '广东省')
            loader.add_value('hospital_city', '珠海市')
            loader.add_value('hospital_county', hospital_county, MapCompose(custom_remove_tags))
            loader.add_xpath('hospital_phone',
                             '//b[contains(text(),"联系电话")]/ancestor::td[1]/text()',
                             MapCompose(custom_remove_tags))
            loader.add_xpath('hospital_intro',
                             '//b[contains(text(),"简介")]/ancestor::td[1]',
                             MapCompose(remove_tags, custom_remove_tags, match_special))
            loader.add_value('registered_channel', self.data_source_from)
            loader.add_value('dataSource_from', self.data_source_from)
            loader.add_value('crawled_url', response.url)
            loader.add_value('update_time', now_day())
            hospital_item = loader.load_item()
            yield hospital_item
        except Exception as e:
            self.logger.error('在抓取医院详细信息过程中出错了,原因是：{}'.format(repr(e)))

    def parse_hospital_dep(self, response):
        hospital_name = response.meta.get('hospital_name')
        self.logger.info('>>>>>>正在抓取:[{}]科室信息>>>>>>'.format(hospital_name))
        try:
            all_dept = response.xpath('//table[@id="deptlist"]/tr')
            for each_dept in all_dept:
                dept_type = each_dept.xpath('td[1][@rowspan]/text()').extract_first('')
                if dept_type:
                    self.temp_dept_type = dept_type
                all_dept_td = each_dept.xpath('td[not(@rowspan)]')
                for each_dept_td in all_dept_td:
                    dept_name = each_dept_td.xpath('a/text()').extract_first('')
                    dept_detail_link = each_dept_td.xpath('a/@href').extract_first('')
                    if dept_name and dept_detail_link:
                        dept_loader = CommonLoader2(item=HospitalDepItem(), response=response)
                        dept_loader.add_value('dept_name', dept_name, MapCompose(custom_remove_tags))
                        dept_loader.add_value('hospital_name', hospital_name, MapCompose(custom_remove_tags))
                        dept_loader.add_value('dept_type', self.temp_dept_type, MapCompose(custom_remove_tags))
                        dept_loader.add_value('dataSource_from', self.data_source_from)
                        dept_loader.add_value('update_time', now_day())

                        # 获取科室详细信息
                        if dept_name and dept_detail_link:
                            self.headers['Referer'] = response.url
                            yield Request(urljoin(self.host, dept_detail_link),
                                          headers=self.headers,
                                          callback=self.parse_hospital_dep_detail,
                                          meta={
                                              'dept_name': dept_name,
                                              'dept_loader': dept_loader,
                                              'hospital_name': hospital_name
                                          },
                                          dont_filter=True)
        except Exception as e:
            self.logger.error('在抓取医院科室信息过程中出错了,原因是：{}'.format(repr(e)))

    def parse_hospital_dep_detail(self, response):
        hospital_name = response.meta.get('hospital_name')
        dept_name = response.meta.get('dept_name')
        self.logger.info('>>>>>>正在抓取:[{}]科室详细信息>>>>>>'.format(hospital_name))
        try:
            # 获取科室详细信息
            dept_loader = response.meta.get('dept_loader')
            dept_info = ''.join(response.xpath('//p[contains(text(),"科室简介")]/ancestor::tr[1]').extract())
            dept_loader.add_value('dept_info',
                                  dept_info,
                                  MapCompose(remove_tags, custom_remove_tags, clean_info2, match_special))
            dept_loader.add_value('crawled_url', response.url)
            dept_item = dept_loader.load_item()
            yield dept_item

            # 获取医生信息,医生数据偏少
            # self.logger.info('>>>>>>正在抓取:[{}]医生信息>>>>>>'.format(hospital_name))
            # all_doctors_in_dept = response.xpath('//li[contains(@onclick,"doctor.jsp")]/@onclick').extract()
            # self.logger.info('[{}]有{}个医生'.format(hospital_name, len(all_doctors_in_dept)))
            # for each_doctor_link in all_doctors_in_dept:
            #     self.headers['Referer'] = response.url
            #     each_doctor_link = re.search(r'\'(.*?)\'', each_doctor_link)
            #     if each_doctor_link:
            #         yield Request(urljoin(self.host, each_doctor_link.group(1)),
            #                       headers=self.headers,
            #                       callback=self.parse_doctor_info_detail,
            #                       meta={
            #                           'dept_name': dept_name,
            #                           'hospital_name': hospital_name
            #                       })
        except Exception as e:
            self.logger.error('在抓取医院科室详细信息过程中出错了,原因是：{}'.format(repr(e)))

    def parse_doctor_info(self, response):
        hospital_name = response.meta.get('hospital_name')
        self.logger.info('>>>>>>正在抓取:[{}]医生信息>>>>>>'.format(hospital_name))
        try:
            all_dept = response.xpath('//table[@id="deptlist"]/tr')
            for each_dept in all_dept:
                dept_name = each_dept.xpath('td[1][@rowspan]/text()').extract_first('')
                if dept_name:
                    self.temp_dept_name = dept_name
                all_doctor_links = each_dept.xpath('td[not(@rowspan)]/a/@href').extract()
                for each_doctor_link in all_doctor_links:
                    self.headers['Referer'] = response.url
                    yield Request(urljoin(self.host, each_doctor_link),
                                  headers=self.headers,
                                  callback=self.parse_doctor_info_detail,
                                  meta={
                                      'dept_name': self.temp_dept_name,
                                      'hospital_name': hospital_name
                                  },
                                  dont_filter=True)
        except Exception as e:
            self.logger.error('在抓取医生信息过程中出错了,原因是：{}'.format(repr(e)))

    def parse_doctor_info_detail(self, response):
        hospital_name = response.meta.get('hospital_name')
        dept_name = response.meta.get('dept_name')
        self.logger.info('>>>>>>正在抓取[{}]医生详细信息>>>>>>'.format(hospital_name))
        try:
            # 获取医生信息
            loader = CommonLoader2(item=DoctorInfoItem(), response=response)
            loader.add_xpath('doctor_name',
                             '//td/b[contains(text(),"姓名")]/ancestor::td[1]',
                             MapCompose(remove_tags, custom_remove_tags, match_special))
            loader.add_value('dept_name', dept_name, MapCompose(custom_remove_tags))
            loader.add_xpath('hospital_name',
                             '//div[@class="page_position"]/a[last()-1]/text()',
                             MapCompose(custom_remove_tags))
            loader.add_xpath('sex',
                             '//td/b[contains(text(),"性别")]/ancestor::td[1]',
                             MapCompose(remove_tags, custom_remove_tags, match_special, clean_info2))
            loader.add_xpath('doctor_level',
                             '//td/b[contains(text(),"职称")]/ancestor::td[1]',
                             MapCompose(remove_tags, custom_remove_tags, match_special, clean_info2))
            loader.add_xpath('doctor_intro',
                             '//td/b[contains(text(),"医生简介")]/ancestor::td[1]',
                             MapCompose(remove_tags, custom_remove_tags, clean_info2))
            loader.add_value('dataSource_from', self.data_source_from)
            loader.add_value('crawled_url', response.url)
            loader.add_value('update_time', now_day())
            doctor_item = loader.load_item()
            yield doctor_item

            # 获取医生排班信息
            self.logger.info('>>>>>>正在抓取[{}]医生排班信息>>>>>>'.format(hospital_name))
            has_doctor_scheduling = response.xpath('//td/div[@class="doctor-work"]')
            if has_doctor_scheduling:
                doctor_scheduling_tr = response.xpath('//table[@class="workTable"]/tbody/tr')
                all_scheduling_date = response.xpath('//table[@class="workTable"]/thead/tr/td[position()>1]').extract()
                scheduling_date_list = custom_remove_tags(remove_tags(','.join(all_scheduling_date))).split(',')
                for each_td in doctor_scheduling_tr:
                    scheduling_time = each_td.xpath('td[1]/text()').extract_first('')
                    scheduling_info = each_td.xpath('td[position()>1]')
                    for index, each_s_i in enumerate(scheduling_info):
                        has_scheduling = each_s_i.xpath('div')
                        if has_scheduling:
                            each_scheduling_date = scheduling_date_list[index][0:3]
                            reg_info = '{0}{1}'.format(each_scheduling_date, scheduling_time)
                            reg_loader = CommonLoader2(item=DoctorRegInfoItem(), response=response)
                            reg_loader.add_xpath('doctor_name',
                                                 '//td/b[contains(text(),"姓名")]/ancestor::td[1]',
                                                 MapCompose(remove_tags, custom_remove_tags, match_special))
                            reg_loader.add_value('dept_name', dept_name, MapCompose(custom_remove_tags))
                            reg_loader.add_xpath('hospital_name',
                                                 '//div[@class="page_position"]/a[last()-1]/text()',
                                                 MapCompose(custom_remove_tags))
                            reg_loader.add_value('reg_info', reg_info)
                            reg_loader.add_value('dataSource_from', self.data_source_from)
                            reg_loader.add_value('crawled_url', response.url)
                            reg_loader.add_value('update_time', now_day())
                            reg_item = reg_loader.load_item()
                            yield reg_item
        except Exception as e:
            self.logger.error('在抓取医生详细信息的过程中出错了,原因是：{}'.format(repr(e)))
