import os
import sys
import execjs

def js_from_file(file_name: str):
    """
    读取js文件
    :return:
    """
    with open(file_name, 'r', encoding='UTF-8') as file:
        result = file.read()
    return result

def encryptAES(passd: str, salt: str) -> str:
    js_path = os.path.dirname(os.path.abspath(sys.argv[0])) + "/encrypt.js"
    return execjs.compile(js_from_file(js_path)).call("encryptAES", passd, salt)
