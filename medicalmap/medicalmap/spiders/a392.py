# -*- coding: utf-8 -*-
import re
from scrapy.http import Request
from urllib.parse import urljoin
from w3lib.html import remove_tags
from scrapy_redis.spiders import RedisSpider
from scrapy.loader.processors import MapCompose
from medicalmap.items import CommonLoader2, HospitalInfoItem, HospitalDepItem, DoctorInfoItem, HospitalAliasItem
from medicalmap.utils.common import now_day, custom_remove_tags, get_county2, match_special2, get_city, \
    MUNICIPALITY2, match_special, clean_info2


class A392Spider(RedisSpider):
    name = '392'
    allowed_domains = ['39.net']
    start_urls = [
        'http://yyk.39.net/beijing/hospitals/',
        # 'http://yyk.39.net/shanghai/hospitals/',
        # 'http://yyk.39.net/tianjin/hospitals/',
        # 'http://yyk.39.net/chongqing/hospitals/'
    ]
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'Host': 'yyk.39.net',
        'Referer': 'http://www.39.net/',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (compatible;Baiduspider-render/2.0; +http://www.baidu.com/search/spider.html'
    }
    custom_settings = {
        # 延迟设置
        # 'DOWNLOAD_DELAY': 5,
        # 自动限速设置
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 1,
        'AUTOTHROTTLE_MAX_DELAY': 3,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 128.0,
        'AUTOTHROTTLE_DEBUG': False,
        # 并发请求数的控制,默认为16
        'CONCURRENT_REQUESTS': 16,
        # scrapy_redis settings
        # reference from: https://github.com/rmax/scrapy-redis
        'SCHEDULER': "scrapy_redis.scheduler.Scheduler",
        'DUPEFILTER_CLASS': "scrapy_redis.dupefilter.RFPDupeFilter",
        'SCHEDULER_PERSIST': True,
        'SCHEDULER_QUEUE_CLASS': "scrapy_redis.queue.PriorityQueue",
        'SCHEDULER_SERIALIZER': "scrapy_redis.picklecompat",
        # redis settings
        'REDIS_ITEMS_KEY': '%(spider)s:items',
        'REDIS_HOST': 'localhost',
        'REDIS_PORT': 6379,
        'REDIS_START_URLS_KEY': '%(name)s:start_urls'
    }
    host = 'http://yyk.39.net/'
    hospital_url = 'http://yyk.39.net/hospital/'
    hospital_postfix = '_detail.html'
    dept_postfix = '_labs.html'
    next_doctor_url = 'http://yyk.39.net/hospital/{}.html?pageNo={}'
    data_source_from = '39健康网'
    dc_cnt_from_dept = 0
    dc_cnt_from_dept_detail = 0

    def start_requests(self):
        for each_area_url in self.start_urls:
            yield Request(each_area_url, headers=self.headers, callback=self.parse)

    def parse(self, response):
        self.logger.info('>>>>>>正在抓取所有医院信息>>>>>>')
        all_hospitals = response.xpath('//div[@class="serach-left-list"]/ul/li')
        hospital_pro = response.xpath('//div[@id="yyk_header_location"]/strong/text()').extract_first('')
        for each_hospital in all_hospitals[0:1]:
            each_hospital_link = each_hospital.xpath('a/@href').extract_first('')
            each_hospital_name = each_hospital.xpath('div[1]/div[1]/a/text()').extract_first('')
            if each_hospital_link:
                hospital_id = re.search(r'.*/(.*?).html$', each_hospital_link)
                hospital_link = urljoin(self.host, each_hospital_link)
                if hospital_id:
                    hospital_id = hospital_id.group(1)

                    # 获取医院详细信息
                    hospital_detail_url = '{0}{1}'.format(hospital_id, self.hospital_postfix)
                    hospital_intro_link = urljoin(self.hospital_url, hospital_detail_url)
                    self.headers['Referer'] = hospital_link
                    yield Request(hospital_intro_link,
                                  headers=self.headers,
                                  callback=self.parse_hospital_info,
                                  meta={
                                      'hospital_pro': hospital_pro,
                                      'hospital_name': custom_remove_tags(each_hospital_name)
                                  },
                                  dont_filter=True)

                    # 获取科室信息
                    dept_detail_url = '{0}{1}'.format(hospital_id, self.dept_postfix)
                    dept_link = urljoin(self.hospital_url, dept_detail_url)
                    yield Request(urljoin(self.host, dept_link),
                                  headers=self.headers,
                                  callback=self.parse_hospital_dep,
                                  dont_filter=True,
                                  meta={
                                      'hospital_name': each_hospital_name
                                  })

            # 获取医生信息,入口:医院列表页面[推荐专家],存在的问题:部分医生没有科室
            # doctors_link = each_hospital.xpath('div[@class="as"]/a[contains(text(),'
            #                                    '"推荐专家")]/@href').extract_first('')
            # if doctors_link:
            #     self.headers['Referer'] = response.url
            #     yield Request(urljoin(self.host, doctors_link),
            #                   headers=self.headers,
            #                   callback=self.parse_doctor_info,
            #                   dont_filter=True,
            #                   meta={'hospital_name': each_hospital_name})

        # 翻页
        has_next = response.xpath('//div[@class="next"]/a[contains(text(),"下一页")]/@href').extract_first('')
        if has_next:
            next_page_link = urljoin(self.host, has_next)
            self.headers['Referer'] = response.url
            yield Request(next_page_link, headers=self.headers, callback=self.parse)

    def parse_hospital_info(self, response):
        hospital_name = response.meta.get('hospital_name')
        self.logger.info('>>>>>>正在抓取:[{}]医院详细信息>>>>>>'.format(hospital_name))
        try:
            # 获取医院等级与类别
            l_a_c = response.xpath('//div[@class="l"]/h2/span/i/text()').extract()
            l_a_c = custom_remove_tags(remove_tags('|'.join(l_a_c)))
            h_l = h_c = m_t = None
            if l_a_c:

                # 等级
                level = re.search(r'(.*等|.*级|.*甲)', l_a_c)
                if level:
                    h_l = level.group(1).split('|')[-1]

                # 类别
                category = re.search(r'(.*?医院)', l_a_c.replace('医保定点医院', ''))
                if category:
                    h_c = category.group(1).split('|')[-1]

                # 医保类型
                medical_type = re.search(r'(.*定点)', l_a_c)
                if medical_type:
                    m_t = medical_type.group(1).split('|')[-1]
            else:
                h_l = h_c = None

            # 获取省市信息
            hospital_pro = response.meta.get('hospital_pro')
            hospital_city = hospital_county = None
            h_a = response.xpath('//dt[contains(text(),"地址")]/ancestor::dl[1]/dd').extract()
            hospital_address = custom_remove_tags(remove_tags(''.join(h_a).replace('查看地图', '')))
            if hospital_pro and hospital_address:
                if hospital_pro in MUNICIPALITY2:
                    hospital_city = hospital_pro
                    hospital_pro = ''
                    hos_c = hospital_city.replace('市', '')
                    useless_info = '{}{}|{}'.format(hos_c, '市', hos_c)
                    single_address = match_special2(hospital_address.split(';')[0])
                    hospital_county = get_county2(useless_info, single_address)
                else:
                    hos_p = hospital_pro
                    hospital_pro = '{0}{1}'.format(hospital_pro, '省')
                    single_address = match_special2(hospital_address.split(';')[0])
                    hospital_city = get_city(hospital_pro, single_address)
                    if hospital_city:
                        hos_c = hospital_city.replace('市', '')
                        useless_info = '{}|{}|{}|{}'.format(hospital_pro, hos_p, hospital_city, hos_c)
                        hospital_county = get_county2(useless_info, single_address)

            # 公立/私立
            h_t = custom_remove_tags(response.xpath('//li/b[contains(text(),"国营")]/text()').extract_first(''))
            hospital_type = '公立' if h_t == '国营' else ''

            # 医院信息item
            loader = CommonLoader2(item=HospitalInfoItem(), response=response)
            loader.add_xpath('hospital_name', '//div[@class="l"]/h2/text()', MapCompose(custom_remove_tags))
            loader.add_value('hospital_level', h_l, MapCompose(custom_remove_tags))
            loader.add_value('hospital_type', hospital_type)
            loader.add_value('hospital_category', h_c, MapCompose(custom_remove_tags))
            loader.add_value('hospital_addr', hospital_address, MapCompose(custom_remove_tags))
            loader.add_value('hospital_pro', hospital_pro, MapCompose(custom_remove_tags))
            loader.add_value('hospital_city', hospital_city, MapCompose(custom_remove_tags))
            loader.add_value('hospital_county', hospital_county, MapCompose(custom_remove_tags))
            loader.add_xpath('hospital_phone',
                             '//dt[contains(text(),"电话")]/ancestor::dl[1]/dd',
                             MapCompose(remove_tags, custom_remove_tags))
            loader.add_xpath('hospital_intro',
                             '//dt/strong[contains(text(),"简介")]/ancestor::dl[1]/dd',
                             MapCompose(remove_tags, custom_remove_tags))
            loader.add_value('medicare_type', m_t, MapCompose(custom_remove_tags))
            # loader.add_value('registered_channel', self.data_source_from)
            loader.add_value('dataSource_from', self.data_source_from)
            loader.add_value('hospital_url', response.url)
            loader.add_value('update_time', now_day())
            hospital_item = loader.load_item()
            yield hospital_item

            # 获取医院别名
            hospital_alias = response.xpath('//div[@class="l"]/p/text()').extract_first('')
            if hospital_alias:
                h_s = custom_remove_tags(hospital_alias)
                if h_s:
                    all_hospital_alias = h_s.split('，')
                    for each_alias in all_hospital_alias:
                        if each_alias != hospital_name:
                            alias_loader = CommonLoader2(item=HospitalAliasItem(), response=response)
                            alias_loader.add_xpath('hospital_name',
                                                   '//div[@class="l"]/h2/text()',
                                                   MapCompose(custom_remove_tags))
                            alias_loader.add_value('hospital_alias_name',
                                                   each_alias,
                                                   MapCompose(custom_remove_tags, match_special))
                            alias_loader.add_value('dataSource_from', self.data_source_from)
                            alias_loader.add_value('update_time', now_day())
                            alias_item = alias_loader.load_item()
                            yield alias_item
        except Exception as e:
            self.logger.error('在抓取医院详细信息过程中出错了,原因是：{}'.format(repr(e)))

    def parse_hospital_dep(self, response):
        hospital_name = response.meta.get('hospital_name')
        self.logger.info('>>>>>>正在抓取:[{}]科室信息>>>>>>'.format(hospital_name))
        try:
            all_dept_links = response.xpath('//div[@class="lab-list"]/div')
            for each_dept_link in all_dept_links:
                dept_type = each_dept_link.xpath('div/a/text()').extract_first('')
                dept_info = each_dept_link.xpath('ul/li')
                for each_dept_info in dept_info:
                    dept_name = each_dept_info.xpath('a/text()').extract_first('')
                    dept_doctor_cnt = each_dept_info.xpath('span/b[1]/text()').extract_first('')
                    dept_detail_link = each_dept_info.xpath('a/@href').extract_first('')
                    dept_loader = CommonLoader2(item=HospitalDepItem(), response=response)
                    dept_loader.add_value('dept_name', dept_name, MapCompose(custom_remove_tags))
                    dept_loader.add_value('dept_type', dept_type, MapCompose(custom_remove_tags))
                    dept_loader.add_xpath('hospital_name',
                                          '//div[@class="l"]/h2/text()',
                                          MapCompose(custom_remove_tags))
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
                                          'dept_doctor_cnt': dept_doctor_cnt,
                                          'hospital_name': hospital_name
                                      },
                                      dont_filter=True)
        except Exception as e:
            self.logger.error('在抓取医院科室信息过程中出错了,原因是：{}'.format(repr(e)))

    def parse_hospital_dep_detail(self, response):
        hospital_name = response.meta.get('hospital_name')
        self.logger.info('>>>>>>正在抓取:[{}]科室详细信息>>>>>>'.format(hospital_name))
        try:
            # 获取科室详细信息
            dept_loader = response.meta.get('dept_loader')
            dept_name = response.meta.get('dept_name')
            dept_info = ''.join(response.xpath('//div[@class="sum-text"]').extract())
            dept_loader.add_value('dept_info', dept_info, MapCompose(remove_tags, custom_remove_tags, clean_info2))
            dept_loader.add_value('crawled_url', response.url)
            dept_item = dept_loader.load_item()
            yield dept_item

            # # 获取医生信息
            # dept_doctor_cnt = response.meta.get('dept_doctor_cnt')
            # if dept_doctor_cnt:
            #     self.logger.info('>>>>>>正在抓取:[{}]医生信息>>>>>>'.format(hospital_name))
            #     self.dc_cnt_from_dept += int(dept_doctor_cnt)
            #     # self.logger.info('[{}]-[{}]有[{}]个医生'.format(hospital_name, dept_name, dept_doctor_cnt))
            #     # 其他医生
            #     all_doctors_in_dept = response.xpath('//li[contains(@class,"labdoctor")]')
            #     all_doctors_in_dept2 = response.xpath('//li[contains(@class,"labdoctor")]/strong/a/@href|'
            #                                           '//ul[@class="exp-ys"]/li/a/@href').extract()
            #     dept_doctor_cnt2 = str(len(set(all_doctors_in_dept2)))
            #     self.dc_cnt_from_dept_detail += int(dept_doctor_cnt2)
            #     # self.crawler.signals.connect(self.output_statistics, signals.spider_closed)
            #     # self.logger.info('[{}]-[{}]有[{}]个医生'.format(hospital_name, dept_name, dept_doctor_cnt2))
            #     for each_doctor in all_doctors_in_dept:
            #         doctor_name = each_doctor.xpath('strong/a/text()').extract_first('')
            #         doctor_level = each_doctor.xpath('cite/text()').extract_first('')
            #         doctor_link = each_doctor.xpath('strong/a/@href').extract_first('')
            #         if doctor_name and doctor_link:
            #             self.headers['Referer'] = response.url
            #             yield Request(urljoin(self.host, doctor_link),
            #                           headers=self.headers,
            #                           callback=self.parse_doctor_info_detail,
            #                           dont_filter=True,
            #                           meta={
            #                               'hospital_name': hospital_name,
            #                               'dept_name': dept_name,
            #                               'doctor_name': doctor_name,
            #                               'doctor_level': doctor_level
            #                           })
            # # 推荐专家
            # expert_recommend = response.xpath('//ul[@class="exp-ys"]/li')
            # for each_expert in expert_recommend:
            #     each_doctor_link = each_expert.xpath('a/@href').extract_first('')
            #     if each_doctor_link:
            #         recommend_expert = response.xpath('//li[contains(@class,"labdoctor")]/strong/a[contains'
            #                                           '(@href,"{}")]/@href'.format(each_doctor_link)).extract_first('')
            #         if not recommend_expert:
            #             each_doctor_name = each_expert.xpath('div/strong/a/text()').extract_first('')
            #             each_doctor_level = each_expert.xpath('div/cite/text()').extract_first('')
            #             if each_doctor_name and each_doctor_name:
            #                 self.headers['Referer'] = response.url
            #                 yield Request(urljoin(self.host, each_doctor_link),
            #                               headers=self.headers,
            #                               callback=self.parse_doctor_info_detail,
            #                               dont_filter=True,
            #                               meta={
            #                                   'hospital_name': hospital_name,
            #                                   'dept_name': dept_name,
            #                                   'doctor_name': each_doctor_name,
            #                                   'doctor_level': each_doctor_level.strip().split(' ')[0]
            #                               })
        except Exception as e:
            self.logger.error('在抓取医院科室详细信息过程中出错了,原因是：{}'.format(repr(e)))

    def parse_doctor_info(self, response):
        hospital_name = response.meta.get('hospital_name')
        self.logger.info('>>>>>>正在抓取[{}]医生信息>>>>>>'.format(hospital_name))
        try:
            all_doctors_link = response.xpath('//dt[contains(@id,"doctor")]/a/@href').extract()
            for each_doctor_link in all_doctors_link:
                doctor_link = urljoin(self.host, each_doctor_link)
                self.headers['Referer'] = response.url
                yield Request(doctor_link,
                              headers=self.headers,
                              callback=self.parse_doctor_info_detail,
                              dont_filter=True,
                              meta={'hospital_name': hospital_name})
            # 医生翻页
            hospital_doctors_id = re.search(r'/hospital/(.*?).html', response.url)
            next_page_num = response.xpath('//div[@class="pages"]/span[1]/following::a[1]['
                                           'not(contains(text(),"39健康网就医助手"))]/text()').extract_first('')
            if hospital_doctors_id and next_page_num:
                hospital_doctors_id = hospital_doctors_id.group(1)
                next_page_link = self.next_doctor_url.format(hospital_doctors_id, next_page_num)
                self.headers['Referer'] = response.url
                yield Request(next_page_link,
                              headers=self.headers,
                              callback=self.parse_doctor_info,
                              dont_filter=True,
                              meta={'hospital_name': hospital_name})
        except Exception as e:
            self.logger.error('在抓取医生信息的过程中出错了,原因是：{}'.format(repr(e)))

    def parse_doctor_info_detail(self, response):
        hospital_name = response.meta.get('hospital_name')
        self.logger.info('>>>>>>正在抓取[{}]医生详细信息>>>>>>'.format(hospital_name))
        try:
            doctor_name = response.meta.get('doctor_name')
            dept_name = response.meta.get('dept_name')
            doctor_level = response.meta.get('doctor_level')
            doc_gt1 = remove_tags(''.join(response.xpath('//div[@class="intro_more"]').extract()))
            doc_gt2 = response.xpath('//dd[contains(text(),"擅长领域")]/text()').extract_first('')
            doctor_good_at = doc_gt1.replace('[关闭]', '') if doc_gt1 else doc_gt2
            loader = CommonLoader2(item=DoctorInfoItem(), response=response)
            loader.add_value('doctor_name', doctor_name, MapCompose(custom_remove_tags))
            loader.add_value('dept_name', dept_name, MapCompose(custom_remove_tags))
            loader.add_value('hospital_name', hospital_name, MapCompose(custom_remove_tags))
            loader.add_value('doctor_level', doctor_level, MapCompose(custom_remove_tags))
            loader.add_xpath('doctor_intro',
                             '//div[@class="hos-guide-box1"]',
                             MapCompose(remove_tags, custom_remove_tags))
            loader.add_value('doctor_goodAt',
                             doctor_good_at,
                             MapCompose(custom_remove_tags, match_special, clean_info2))
            loader.add_value('dataSource_from', self.data_source_from)
            loader.add_value('crawled_url', response.url)
            loader.add_value('update_time', now_day())
            doctor_item = loader.load_item()
            yield doctor_item
        except Exception as e:
            self.logger.error('在抓取医生详细信息的过程中出错了,原因是：{}'.format(repr(e)))

    def output_statistics(self):
        """输出统计信息"""
        self.crawler.stats.set_value('dc_cnt_from_dept/count', self.dc_cnt_from_dept)
        self.crawler.stats.set_value('dc_cnt_from_dept_detail/count', self.dc_cnt_from_dept_detail)
