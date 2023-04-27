import os, sys, re, json, argparse, logging
import time, datetime
import requests
import ddddocr
import base64

from rich.console import Console
from rich.table import Table
from apscheduler.schedulers.blocking import BlockingScheduler
from PIL import Image
from io import BytesIO

from encrypt import encryptAES

logging.basicConfig(format='%(asctime)s %(filename)s %(funcName)s %(lineno)s [%(levelname)s]:%(message)s',filename=f"./logs/{datetime.datetime.now()}.log", encoding="utf-8", level=logging.INFO)

login_url           = "https://newids.seu.edu.cn/authserver/login"
activity_list_url   = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/queryActivityList.do"
verify_code_url     = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/vcode.do"
appoiment_url       = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/yySave.do"

headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36"}

"""
持续尝试直到无异常发生
:return: func(args...)
"""
def doUntilSuccess(func, *args, counter = 100):
    ret = None
    while counter != 0:
        try:
            ret = func(*args)
        except Exception as ex:
            logging.warning(ex)
            time.sleep(0.1)
        else:
            break
    return ret

"""
使用用户名和密码登录网站获取Cookie
:return: Session
"""
def login(username: str, passwd: str) -> requests.Session:
    def _login(username: str, passwd: str) -> requests.Session:
        session = requests.Session()
        session.headers = headers
        response = session.get(login_url, timeout=3)
        pattern = re.compile("<input type=\"hidden\" (name|id)=\"(.*?)\" value=\"(.*?)\"/?>")
        match = re.findall(pattern, response.text)
        form = {"username" : username}
        for attr, key, val in match:
            form[key] = val
            if attr == "id":
                form["password"] = encryptAES(passwd, val)
        response = session.post(login_url, data=form, timeout=3)

        return session

    return doUntilSuccess(_login, username, passwd)

"""
获取所有的讲座信息列表
:return: dict
"""
def getQueryList(session: requests.Session) -> list:
    def _getQueryList(session: requests.Session) -> list:
        response = session.get(activity_list_url, timeout=3)

        form = {"pageIndex": 1,
            "pageSize": 10,
            "sortField": '',
            "sortOrder": ''
            }
        
        response = session.post(activity_list_url, data=form, timeout=3)

        obj = json.loads(response.text)
        datas:list = obj["datas"]
        while obj["pageIndex"] * obj["pageSize"] < obj["total"]:
            form["pageIndex"] = obj["pageIndex"] + 1
            response = session.post(activity_list_url, data=form, timeout=3)
            obj = json.loads(response.text)
            datas += obj["datas"]
        return datas

    return doUntilSuccess(_getQueryList, session)

"""
获取对应ID的讲座的预约开始时间
:return: dict
"""
def getReserveBeginTime(query_list: dict, WID: str) -> str :
    for item in query_list:
        if item["WID"] == WID:
            return item["YYKSSJ"]
    return None

"""
格式化输出讲座列表
:return: dict
"""
def printQueryListTable(query_list: list) -> list:
    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("讲座ID", style="dim", width=32)
    table.add_column("讲座名称")
    table.add_column("预约开始时间")

    id_list = [item["WID"] for item in query_list]
    name_list = [item["JZMC"] for item in query_list]
    time_list = [item["YYKSSJ"] for item in query_list]
    for (id, name, timestamp) in zip(id_list, name_list, time_list):
        if "线上" in name:
            table.add_row(id, f"[red]{name}[/red]", timestamp)
        else:
            table.add_row(id, name, timestamp)

    console.print(table)

"""
使用给定的ID发起预约请求
:return: bool
"""
def reserveRequest(session: requests.Session, WID: str):
    def _reserveRequest(session: requests.Session, WID: str):
        response = session.get(verify_code_url, timeout=3)
        b64code = json.loads(response.text)['result'].split(',')[1]

        # image = Image.open(BytesIO(base64.b64decode(b64code))).convert("RGB")
        # image.save("tmp.jpeg")

        ocr = ddddocr.DdddOcr(beta=True, show_ad=False)
        res = ocr.classification(base64.b64decode(b64code))
        form = {'paramJson': json.dumps({'HD_WID':WID,'vcode':res})}
        response = session.post(appoiment_url, data=form, timeout=3)

        response_obj = json.loads(response.text)
        logging.info(response_obj)
        print(response_obj)

        if response_obj['code'] == 200:
            return
    
        if "验证码错误" in response_obj['msg']:
            raise Exception(f"验证码错误 {res}")
        if "尚未开放" in response_obj['msg']:
            raise Exception(f"尚未开放预约")

    return doUntilSuccess(_reserveRequest, session, WID)

"""
讲座预约工作函数
:return: bool
"""
def reserveJob(WID:str, username: str, password: str, date:datetime.datetime = None, scheduler:BlockingScheduler = None) -> bool:
    session = login(username, password)

    while date and datetime.datetime.now() < date:
        time.sleep(0.005)
    
    reserveRequest(session, WID)
    session.close()

    if scheduler:
        scheduler.shutdown(wait=False)
        
"""
定时任务
:return:
"""
def schedule(WID: str, date: datetime.datetime, username: str, password: str):
    sche = BlockingScheduler()
    job = sche.add_job(reserveJob, trigger="date", args=[WID, username, password, date, sche], next_run_time=date - datetime.timedelta(seconds=10))
    sche.print_jobs()
    sche.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", "-i", type=str, default=None)
    parser.add_argument("--list", "-l", action="store_true", default=True)
    parser.add_argument("--username", "-u", type=str, required=True)
    parser.add_argument("--password", "-p", type=str, required=True)
    args = parser.parse_args()

    session = login(args.username, args.password)
    query_list = getQueryList(session)
    session.close()

    if args.list:
        printQueryListTable(query_list)
    
    if args.id:
        if date_str := getReserveBeginTime(query_list, args.id):
            begin_date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            if begin_date <= datetime.datetime.now():
                reserveJob(args.id, args.username, args.password)
            else:
                schedule(args.id, begin_date, args.username, args.password)
        else:
            print("未找到的id！")
