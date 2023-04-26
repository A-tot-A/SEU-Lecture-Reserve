import requests
import re
import json
import ddddocr
import base64
import time, datetime
import argparse

from encrypt import encryptAES
from rich.console import Console
from rich.table import Table
from apscheduler.schedulers.blocking import BlockingScheduler

login_url           = "https://newids.seu.edu.cn/authserver/login"
activity_list_url   = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/queryActivityList.do"
verify_code_url     = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/vcode.do"
appoiment_url       = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/yySave.do"

headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36"}

"""
使用用户名和密码登录网站获取Cookie
:return: Session
"""
def login(username: str, passwd: str) -> requests.Session:
    session = requests.Session()
    session.headers = headers
    try:
        response = session.get(login_url, timeout=3)
        pattern = re.compile("<input type=\"hidden\" (name|id)=\"(.*?)\" value=\"(.*?)\"/?>")
        match = re.findall(pattern, response.text)
        form = {"username" : username}
        for attr, key, val in match:
            form[key] = val
            if attr == "id":
                form["password"] = encryptAES(passwd, val)
        response = session.post(login_url, data=form, timeout=3)
    except requests.exceptions.Timeout:
        # print("登陆超时！")
        return None
    except:
        print("登陆失败，请重试！")
        return None
    
    return session

"""
获取所有的讲座信息列表
:return: dict
"""
def getQueryList(session: requests.Session) -> list:
    response = session.get(activity_list_url)

    form = {"pageIndex": 1,
        "pageSize": 10,
        "sortField": '',
        "sortOrder": ''
        }
    
    try:
        response = session.post(activity_list_url, data=form, timeout=3)
    except:
        print("获取讲座信息失败！")
        return None

    obj = json.loads(response.text)
    datas:list = obj["datas"]
    while obj["pageIndex"] * obj["pageSize"] < obj["total"]:
        form["pageIndex"] = obj["pageIndex"] + 1
        response = session.post(activity_list_url, data=form, timeout=3)
        obj = json.loads(response.text)
        datas += obj["datas"]
    return datas

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
获取字典列表中的某一个属性
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
def reserveRequest(session: requests.Session, WID: str) -> bool:
    response = session.get(verify_code_url)
    b64code = json.loads(response.text)['result'].split(',')[1]

    # image = Image.open(BytesIO(base64.b64decode(b64code))).convert("RGB")
    # image.save("tmp.jpeg")

    ocr = ddddocr.DdddOcr(beta=True, show_ad=False)
    res = ocr.classification(base64.b64decode(b64code))
    form = {'paramJson': json.dumps({'HD_WID':WID,'vcode':res})}
    response = session.post(appoiment_url, data=form)
    return json.loads(response.text)['code'] == 200

"""
讲座预约工作函数
:return: bool
"""
def reserveJob(WID:str, username: str, password: str) -> bool:
    session = None
    while session is None:
        session = login(username, password)
    while not reserveRequest(session, WID):
        time.sleep(0.1)
    session.close()
    print(f"{datetime.datetime.now()} 预约成功!")
        
"""
定时任务
:return:
"""
def schedule(WID: str, date: datetime.datetime, username: str, password: str):
    sche = BlockingScheduler()
    job = sche.add_job(reserveJob, trigger="date", args=[WID, username, password], next_run_time=date)
    sche.print_jobs()
    sche.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", "-i", type=str, default=None)
    parser.add_argument("--list", "-l", action="store_true")
    parser.add_argument("--username", "-u", type=str, required=True)
    parser.add_argument("--password", "-p", type=str, required=True)
    args = parser.parse_args()

    session = None
    while session is None:
        session = login(args.username, args.password)
    query_list = getQueryList(session)
    session.close()

    if args.list:
        printQueryListTable(query_list)
    
    if args.id:
        if date_str := getReserveBeginTime(query_list, args.id):
            begin_date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            if begin_date <= datetime.datetime.now():
                reserveJob(args.id)
            else:
                schedule(args.id, begin_date - datetime.timedelta(seconds=5), args.username, args.password)
        else:
            print("未找到的id！")
