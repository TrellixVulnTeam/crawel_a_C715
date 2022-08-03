import json
import logging
import subprocess
from socket import *
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

from common.utility import Utility
# from common.mapping import Mapping

from selenium.webdriver import ActionChains
from selenium.common.exceptions import NoSuchElementException
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

logging.basicConfig(filename="train_log", format='%(asctime)s - %(name)s - %(levelname)s -%(module)s:  %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S ',
                    level=logging.INFO)
logger = logging.getLogger()
KZT = logging.StreamHandler()
KZT.setLevel(logging.DEBUG)
logger.addHandler(KZT)


class SuperBrowser(object):
    # 基础配置
    config = Utility()
    # 获取业务类型
    business_type = config.get('business_type')
    logger.info("business_type: %s" % business_type)

    # 指定使用英语
    __LANGUAGE = config.get('language')

    # ----------------------------------------->> Socket通信地址端口
    host = config.get('socket_host')
    port = int(config.get('socket_port'))
    logger.info('socket > host: %s, port: %s' % (host, port))
    # ----------------------------------------->> 请求紫鸟超级浏览器API方法
    __GET_BROWSER_LIST = "getBrowserList"  # 获取店铺列表
    __START_BROWSER = "startBrowser"  # 启动店铺(主程序)
    __STOP_BROWSER = "stopBrowser"  # 关闭店铺窗口
    __GET_BROWSER_ENV_INFO = "getBrowserEnvInfo"  # 启动店铺(webdriver)
    __HEARTBEAT = "heartbeat"  # 非必要接口，只是用于保活Socket连接
    __EXIT = "exit"  # 正常退出超级浏览器主进程，会自动关闭已启动店铺并保持店铺cookie等信息。

    def __init__(self):
        logger.info("初始化Socket连接...")
        logger.info("启动紫鸟浏览器......")

        self.buf_size = int(self.config.get('socket_buf_size'))
        self.IS_HEADLESS = self.config.get('browser_is_headless')  # 浏览器是否启用无头模式 false 否、true 是

        # 获取紫鸟·超级浏览器安装路径
        path_super_browser = self.config.get('path_super_browser')
        cmd = "{} --run_type=web_driver --socket_port={}".format(path_super_browser, self.port)
        subprocess.Popen(cmd)

        try:
            # ------------------------------创建套接字通道
            self.address = (self.host, self.port)
            self.tcpCliSock = socket(AF_INET, SOCK_STREAM)  # 创建套接字
            self.tcpCliSock.connect(self.address)  # 主动初始化TCP服务器连接
        except ConnectionRefusedError as e:
            logger.error(e)
            subprocess.Popen('taskkill /f /im superbrowser.exe')
        except Exception as e:
            logger.error(e)

    def browser_api(self, action, args=None):
        """
        紫鸟·超级浏览器API
        :param action: 方法
        :param args: 可选参数
        :return:
        """
        REQUEST_ID = "0123456789"  # 全局唯一标识
        user_info = json.dumps({  # 用户信息
            "company": self.config.get('browser_company_name'),
            "username": self.config.get('browser_username'),
            "password": self.config.get('browser_password')
        })

        # cdm默认为获取店铺列表
        common = {"userInfo": user_info, "action": self.__GET_BROWSER_LIST, "requestId": REQUEST_ID}
        if action == self.__START_BROWSER or action == self.__GET_BROWSER_ENV_INFO or action == self.__STOP_BROWSER:
            common['browserOauth'] = args['browserOauth']
            common['isHeadless'] = args['isHeadless']
        if action == self.__START_BROWSER:
            common['launcherPage'] = "https://sellercentral.amazon.co.uk"
            common['runMode'] = "1"
        common['action'] = action
        return common

    def socket_communication(self, params):
        """
        Socket通信
        :param params: 参数对象
        :return:
        """
        try:
            args = (str(params) + '\r\n').encode('utf-8')
            # 将 string 中的数据发送到连接的套接字
            self.tcpCliSock.send(args)
            # 接收的最大数据量
            res = self.tcpCliSock.recv(self.buf_size)
            return json.loads(res)
        except ConnectionResetError as e:
            logger.warning("ConnectionResetError: %s" % e)
            logger.info("socket 连接已关闭")
        except Exception as e:
            logger.error("socket_communication error: %s" % e)
        pass

    # 举个栗子🌰
    def browser_list(self):
        """
        获取店铺列表
        这里采用Redis管理店铺，为了后期分布式部署准备。
        :return:
        {
            "statusCode": "状态码",
            "err": "异常信息",
            "action": "getBrowserList",
            "requestId": "全局唯一标识",
            "browserList": [{
                "browserOauth": "店铺ID",
                "browserName": "店铺名称",
                "browserIp": "店铺IP",
                "siteId": "店铺所属站点",
                "isExpired": false //ip是否过期
            }]
        }
        """
        logger.info("")
        logger.info("获取店铺列表.")
        shop_list_params = self.browser_api(self.__GET_BROWSER_LIST)
        shop_info = self.socket_communication(shop_list_params)
        if shop_info['statusCode'] == 0:
            print(shop_info)
            browser_size = len(shop_info['browserList'])
            logger.info("目前店铺总数: %s, 正在记录店铺信息...,请稍等." % browser_size)
            for index, browser in enumerate(shop_info['browserList']):
                index += 1
                print(browser['browserName'] + "====" + browser['browserOauth'])
            return shop_info['browserList']
        else:
            if "err" not in shop_info:
                shop_info["err"] = ""
            logger.warning("statusCode:%s, err: %s" % (shop_info['statusCode'], shop_info['err']))
            return 0

    def start_browser(self, browserOauth="azRUaVhpWlR4cDk0alZPVnovUEl2Zz09"):
        """
        启动店铺
        :param shop_id: 店铺ID
        :return:
        """
        # 启动店铺(两种方式) startBrowser / getBrowserEnvInfo
        start_params = self.browser_api(self.__START_BROWSER,
                                        {"browserOauth": browserOauth, "isHeadless": self.IS_HEADLESS,
                                         "launcherPage": "https://sellercentral.amazon.co.uk"})
        shop_obj = self.socket_communication(start_params)
        logger.info("启动店铺信息: %s" % shop_obj)
        return shop_obj

    def getBrowserEnvInfo(self, browserOauth="azRUaVhpWlR4cDk0alZPVnovUEl2Zz09"):
        """
        启动店铺
        :param shop_id: 店铺ID
        :return:
        """
        # 启动店铺(两种方式) startBrowser / getBrowserEnvInfo
        start_params = self.browser_api(self.__GET_BROWSER_ENV_INFO,
                                        {"browserOauth": browserOauth, "isHeadless": self.IS_HEADLESS,
                                         "launcherPage": "https://sellercentral.amazon.co.uk"})
        shop_obj = self.socket_communication(start_params)
        logger.info("启动店铺信息: %s" % shop_obj)
        return shop_obj

    def greg(self,browserOauth=None):
        data = self.start_browser(browserOauth=browserOauth)
        # data = self.getBrowserEnvInfo()
        logger.info(data)
        options = Options()
        debuggerAddress = "127.0.0.1:{}".format(data['debuggingPort'])
        logger.info(debuggerAddress)
        options.add_experimental_option("debuggerAddress", debuggerAddress)
        options.add_argument("--disable-plugins=false")
        options.add_argument("--disable-java=false")
        options.add_argument("--disable-javascript=false")
        options.add_argument("--disable-plugins=false")
        options.add_argument("--no-sandbox=true")
        options.add_argument("--lang=zh-CN")

        # executable_path = data['browserPath']
        executable_path = r"C:/Users/Administrator/Desktop/worker/紫鸟浏览器内核/chromedriver87.exe"
        s=Service(executable_path=self.config.get("executable_path"))
        driver = webdriver.Chrome( options=options,service=s)
        driver.get("https://sellercentral.amazon.com")
        try:
            driver.find_element(by=By.XPATH,
                                value='//*[@class="text align-end color-white font-size-default ember font-normal"]//a').click()
            time.sleep(1)
        except:
            pass
        try:
            driver.find_element(by=By.ID, value="signInSubmit").click()
        except:
            try:
                driver.find_element(by=By.XPATH, value='//div[@class="a-column a-span12"][0]').click()
                time.sleep(1)
                driver.find_element(by=By.ID, value="signInSubmit").click()
            except:
                pass
        time.sleep(1)
        # text = driver.find_element(by=By.XPATH,
                                #    value='//div[@class="css-93gqc1"][4]//span[@class="css-kws921 e1i7w3tc50"]').text
        driver.find_element(by=By.XPATH ,value="/html/body/div[1]/div[2]/div[1]/div/div/div[1]/kat-box/div/div[3]/div/div[2]/div/div[3]/div/div[3]/button/div/div").click()
        driver.find_element(by=By.XPATH ,value='//*[@id="picker-container"]/div/div[3]/div/button').click()
        driver.find_element(by=By.XPATH ,value='//*[@id="KpiCardList"]/div/div[1]/div/div[4]/casino-knowhere-layer/div/button/div/div/div[2]').click()
        text=driver.find_element(by=By.XPATH,value='//*[@id="KpiCardList"]/div/div[1]/div/div[4]/casino-knowhere-layer/div/div/div/div[3]/div/div[2]').text
        print("店铺总余额:" + text)
        driver.find_element(by=By.XPATH, value='//div[@class="css-93gqc1"][4]//*[@data-testid="KpiCardButton"]').click()
        spanlist = driver.find_elements(by=By.XPATH, value='//div[@class="css-1entqxh e1i7w3tc67"]//span[@class="css-in3yi3 e1i7w3tc45"]')
        alist = driver.find_elements(by=By.XPATH, value='//div[@class="css-1entqxh e1i7w3tc67"]//a[@data-testid="Link"]')
        for index, value in enumerate(spanlist):
            print(value.text + alist[index].text)




 
if __name__ == "__main__":
    # add_argument参数明细教程 http://t.zoukankan.com/lixianshengfitting-p-12530313.html
    superBrowser = SuperBrowser()
    browserList=superBrowser.browser_list()
    # superBrowser.start_browser()
    # superBrowser.startBrowserNew()
    if browserList :
        for browserOauth in browserList :
            try:
                superBrowser.greg(browserOauth=browserOauth["browserOauth"])
            except Exception as err:
                logger.warning(err)
    # superBrowser.driver_browser()