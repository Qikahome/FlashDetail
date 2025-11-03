import json
import requests
import os
from bs4 import BeautifulSoup
import urllib3

from .FDConfig import config_instance as config
from .FDJsonDatabase import save_to_database, get_from_database

# 抑制因忽略SSL验证产生的警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
       

# 容量单位转换函数
def format_density(arg,width:int=8) -> str:
    """
    将容量值从 Tb/Gb/Mb/纯数字转换为 TB/GB/MB（按1024进位）
    输出规则：无小数则显示整数，有小数保留两位；末尾带换行符
    """
    try:
        arg=str(arg)
        value = arg.strip().split(",")[0]
        bytes_val = 0.0  # 统一转换为 MB 作为中间单位

        # 提取数值并转换为 MB（1字节=8比特）
        if value.endswith("Tb"):
            num = float(value[:-2])
            bytes_val = num * 1024 * 1024 / 8  # Tb → MB
        elif value.endswith("Gb"):
            num = float(value[:-2])
            bytes_val = num * 1024 / 8  # Gb → MB
        elif value.endswith("Mb"):
            num = float(value[:-2])
            bytes_val = num / 8  # Mb → MB
        elif value.endswith("G"): #对于dram需要特殊处理
            num = float(value[:-1])
            bytes_val = num * 1024 * width / 8
        elif value.endswith("M"):
            num = float(value[:-1])
            bytes_val = num * width / 8 
        else:
            num = float(value)  # 纯数字默认视为 Mb
            bytes_val = num / 8  # 转换为 MB

        # 按1024进位选择单位，并处理小数
        if bytes_val >= 1024 * 1024:
            # 转换为 TB
            tb = bytes_val / (1024 * 1024)
            if tb.is_integer():
                return f"{int(tb)} TB"
            return f"{tb:.2f} TB"
        elif bytes_val >= 1024:
            # 转换为 GB
            gb = bytes_val / 1024
            if gb.is_integer():
                return f"{int(gb)} GB"
            return f"{gb:.2f} GB"
        else:
            # 保留为 MB
            if bytes_val.is_integer():
                return f"{int(bytes_val)} MB"       
            return f"{bytes_val:.2f} MB"
    except (ValueError, TypeError) as e:
        print(f"容量单位转换错误: {str(e)}")
        # 格式无效时直接返回原始值（带前缀和换行）
        return f"{arg}"

# HTTP请求工具函数
def get_html_with_requests(url: str,debug: bool=False) -> requests.Response:
    """使用requests库获取HTML内容，忽略HTTPS证书验证错误"""
    if debug:
        print(f"请求URL: {url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # 添加verify=False参数以忽略SSL证书验证错误
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.raise_for_status()  # 检查请求是否成功
        return response
    except Exception as e:
        print(f"HTTP请求失败: {str(e)}")
        return None

def get_from_flash_detector(postfix:str,debug: bool=False,url:str|None=None) -> requests.Response:
    """从闪存检测器API获取数据"""
    if url:
        response = get_html_with_requests(f"{url}/{postfix}",debug)
        if response:
            return response
    if not url:
        for u in config.flash_detect_api_urls:
            response = get_html_with_requests(f"{u}/{postfix}",debug)
            if response and response.status_code == 200:
                return response
    return None

def get_from_flash_extra(postfix:str,debug: bool=False,url:str|None=None) -> requests.Response:
    """从闪存额外信息API获取数据"""
    if url:
        response = get_html_with_requests(f"{url}/{postfix}",debug)
        if response:
            return response
    if not url:
        for u in config.flash_extra_api_urls:
            response = get_html_with_requests(f"{u}/{postfix}",debug)
            if response and response.status_code == 200:
                return response
    return None

# 十六进制验证函数
def is_hex(s: str) -> bool:
    """检查字符串是否全为十六进制字符"""
    try:
        int(s, 16)
        return True
    except ValueError:
        return False

def get_detail(arg: str, refresh: bool = False,debug: bool=False,save: bool=True,url:str|None=None) -> dict:
    """获取闪存料号详细信息
    
    Args:
        arg: 闪存料号
        firstTime: 是否首次查询
        refresh: 是否强制刷新数据（不使用缓存）
        debug: 是否开启调试模式
        save: 是否保存到数据库
        url: 自定义API URL      
        
    Returns:
        查询结果字典，包含accept方法用于保存数据到数据库
    """
    if not arg.strip():
        result = {"result": False, "error": "料号不能为空"}
        # 添加accept方法（对于失败结果，不执行任何操作）
        result["accept"] = lambda: None
        return result
    
    try:
        # 尝试从缓存获取数据（如果不是强制刷新）
        if not refresh:
            # 使用arg.lower()确保不区分大小写查询
            cached_data = get_from_database('flash_detail', arg.lower(),debug)
            if cached_data:
                # 为缓存数据添加accept方法（不执行任何操作，因为已经在数据库中）
                cached_data["accept"] = lambda: None
                return cached_data
                
        if is_hex(arg) and arg.startswith(("89","45","2C","EC","AD","98","9B")):
            return get_detail_from_ID(arg=arg,refresh=refresh,debug=debug,save=save,url=url)
            
        html = get_from_flash_detector(f"decode?lang=chs&pn={arg}",debug,url)
        if not html:
            result = {"result": False, "error": "API请求失败"}
            result["accept"] = lambda: None
            return result
            
        soup = BeautifulSoup(html.text, 'lxml')
        p_tags = soup.find('p')
        if p_tags:
            result = json.loads(p_tags.get_text())
            # 添加accept方法，仅在调用时保存数据到数据库
            if result.get("result") and save:
                def accept_func():
                    save_to_database('flash_detail', arg.lower(), result,debug)
                    # 移除accept方法，避免重复调用
                    if "accept" in result:
                        del result["accept"]
                result["accept"] = accept_func
            else:
                result["accept"] = lambda: None
            return result
            
        result = {"result": False, "error": "未找到有效数据"}
        result["accept"] = lambda: None
        return result
    except json.JSONDecodeError:
        result = {"result": False, "error": "API返回格式错误（非JSON）"}
        result["accept"] = lambda: None
        return result
    except Exception as e:
        result = {"result": False, "error": str(e)}
        result["accept"] = lambda: None
        return result


def search(arg: str,debug: bool=False,count: int=10,url:str|None=None) -> dict:
    """搜索闪存料号
    
    Args:
        arg: 搜索关键词
        debug: 是否开启调试模式
        count: 返回结果数量（默认10条）
        url: 自定义API URL
        
    Returns:
        搜索结果字典
    """
    if not arg.strip():
        return {"result": False, "error": "搜索关键词不能为空"}
    
    try:
        html = get_from_flash_detector(f"searchPn?limit={count}&lang=chs&pn={arg}",debug,url)
        if not html:
            return {"result": False, "error": "API请求失败"}
            
        soup = BeautifulSoup(html.text, 'lxml')
        p_tags = soup.find('p')
        if p_tags:
            result = json.loads(p_tags.get_text())
            return result
            
        return {"result": False, "error": "未找到有效数据"}
    except json.JSONDecodeError:
        return {"result": False, "error": "API返回格式错误（非JSON）"}
    except Exception as e:
        return {"result": False, "error": str(e)}


def get_detail_from_ID(arg: str, refresh: bool = False,debug: bool=False,save: bool=False,local: bool=True,url:str|None=None) -> dict:
    """通过闪存ID获取详细信息
    
    Args:
        arg: 闪存ID
        refresh: 是否强制刷新数据（不使用缓存）
        debug: 是否开启调试模式
        save: 是否保存到数据库
        local: 是否使用本地算法解码
        url: 自定义API URL
        
    Returns:
        查询结果字典，包含accept方法用于保存数据到数据库
    """
    if not arg.strip():
        result = {"result": False, "error": "ID不能为空"}
        result["accept"] = lambda: None
        return result
    
    try:
        # 提取有效字符（字母/数字）
        id_str= ""
        for c in arg:
            if c.upper() in ["0","1","2","3","4","5","6","7","8","9","A","B","C","D","E","F"]:
                id_str += c.upper()
            if len(id_str) >= 12:
                break  # 超过12位则截断
        # 不足12位则补0
        if len(id_str) < 12:
            id_str += '0' * (12 - len(id_str))  
        
        # 尝试从缓存获取数据（如果不是强制刷新）
        if not refresh:
            # 使用id_str.lower()确保不区分大小写查询
            cached_data = get_from_database('flash_id_detail', id_str.lower(),debug)
            if cached_data:
                cached_data["accept"] = lambda: None
                return cached_data
        result={}
        # 本地算法解码
        if local:
            data={}
            data["id"]=id_str
            def get_die_cellLevel(id_str: str) -> tuple:
                die_cellLevel=int(id_str[5],16)
                return ["1","2","4","8"][die_cellLevel%4],["SLC","MLC","TLC","QLC"][die_cellLevel//4]
            DENSITY_MAPPING1 = {
                "D3": "1GB", "D5": "2GB", "D7": "4GB", "DE": "8GB",
                "3A": "16GB", "5A": "16GB",  # 16GB有两种编码
                "3C": "32GB", "5C": "32GB",  # 32GB有两种编码
                "3E": "64GB", 
                "48": "128GB", "5E": "128GB", "7E": "128GB",  # 128GB有三种编码
                "49": "256GB", "89": "256GB",  # 256GB有两种编码
                "40": "512GB", "41": "1TB", "58": "160GB"
            }
            if id_str.startswith(("98","45")):
                result["result"] = True
                data["vendor"]={"98":"东芝/恺侠","45":"闪迪/西数"}[id_str[:2]]
                data["density"] = DENSITY_MAPPING1.get(id_str[2:4], "未知")
                data["die"],data["cellLevel"]=get_die_cellLevel(id_str)
                data["pageSize"] = ["2","4","8","16"][int(id_str[7],16)%4]
                data["totalPlane"]={"6":"2","A":"4","E":"8","2":"16"}[id_str[9]]
                pn1=int(id_str[10],16)%8
                pn2=int(id_str[11],16)%8
                p_n=str(pn1)+str(pn2)
                data["processNode"]={"71":"BiCS2","72":"BiCS3","63":"BiCS4(.5)","64":"BiCS5","65":"BiCS6",
                    "51":"15nm(1z)","50":"A19nm(1y)","57":"19nm(1x)","56":"24nm"
                }[p_n]
            if id_str.startswith("AD"):
                result["result"] = True
                data["vendor"]="海力士"
                data["density"] = DENSITY_MAPPING1.get(id_str[2:4], "未知")
                data["die"],data["cellLevel"]=get_die_cellLevel(id_str)
                data["pageSize"] = ["2","4","8","16"][int(id_str[7],16)%4]
                data["totalPlane"] = ["1","2","4","8"][int(id_str[4],16)%4]
                data["processNode"]={"42":"32nm","4A":"16nm","50":"14nm","60":"3DV1","70":"3DV2","80":"3DV3","90":"3DV4","A0":"3DV5","B0":"3DV6","C0":"3DV7","D0":"3DV8"}.get(id_str[10:12],"未知")

            result["data"] = data
        if not result.get("result",False):
            html = get_from_flash_detector(f"decodeId?lang=chs&id={id_str}",debug,url)
            if not html:
                result = {"result": False, "error": "API请求失败"}
                result["accept"] = lambda: None
                return result
                
            soup = BeautifulSoup(html.text, 'lxml')
            p_tags = soup.find('p')
            if p_tags:
                result = json.loads(p_tags.get_text())
            # 添加accept方法，仅在调用时保存数据到数据库
        if result.get("result",False) :
            if save:
                def accept_func():
                    save_to_database('flash_id_detail', id_str.lower(), result,debug)
                    # 移除accept方法，避免重复调用
                    if "accept" in result:
                        del result["accept"]
                result["accept"] = accept_func
            else:
                result["accept"] = lambda: None
            return result
            
        result = {"result": False, "error": "未找到有效数据"}
        result["accept"] = lambda: None
        return result
    except json.JSONDecodeError:
        result = {"result": False, "error": "API返回格式错误（非JSON）"}
        result["accept"] = lambda: None
        return result
    except Exception as e:
        result = {"result": False, "error": str(e)}
        result["accept"] = lambda: None
        return result


# Micron料号解析函数
def parse_micron_pn(arg: str, refresh: bool = False, debug: bool=False,save: bool=True,url:str|None=None) -> dict:
    """解析Micron PN
    
    Args:
        arg: 镁光料号
        refresh: 是否强制刷新数据（不使用缓存）
        debug: 是否开启调试模式
        save: 是否保存到数据库
        url: 自定义API URL
        
    Returns:
        查询结果字典，包含accept方法用于保存数据到数据库
    """
    if not arg.strip():
        result = {"result": False, "error": "料号不能为空"}
        result["accept"] = lambda: None
        return result
    
    pn = arg.strip().upper()
    
    # 尝试从缓存获取数据（如果不是强制刷新）
    if not refresh:
        # 使用pn.lower()确保不区分大小写查询
        cached_data = get_from_database('micron_pn_decode', pn.lower(),debug)
        if debug:
            print(cached_data)
        if cached_data:
            return cached_data
    
    # 访问micron-online接口获取完整part-number
    micron_response = get_from_flash_extra(f"micron-online?param={pn}", debug,url) 
    if not micron_response:
        result = {"result": False, "error": "解码镁光料号失败"}
        result["accept"] = lambda: None
        return result
    
    try:
        # 尝试解析JSON响应
        response_data = json.loads(micron_response.text)
        # 确保返回的数据结构包含必要字段
        response_data["data"]=response_data["detail"]
        response_data["detail"]=None
        # 添加accept方法，仅在调用时保存数据到数据库
        if response_data.get("result", True) and save:  # 如果没有result字段，默认为True
            def accept_func():
                save_to_database('micron_pn_decode', pn.lower(), response_data,debug)
                # 移除accept方法，避免重复调用
                if "accept" in response_data:
                    del response_data["accept"]
            response_data["accept"] = accept_func
        else:
            response_data["accept"] = lambda: None
        if debug:
            print(response_data)
        return response_data
    except json.JSONDecodeError:
        result = {"result": False, "error": "返回数据格式错误"}
        result["accept"] = lambda: None
        return result
    except Exception as e:
        result = {"result": False, "error": str(e)}
        result["accept"] = lambda: None
        return result

# DRAM料号查询函数
def get_dram_detail(arg: str, refresh: bool = False, debug: bool=False,save: bool=True,url:str|None=None) -> dict:
    """查询DRAM详情（适配DRAM专属API）
    
    Args:
        arg: DRAM料号
        refresh: 是否强制刷新数据（不使用缓存）
        debug: 是否开启调试模式
        save: 是否保存到数据库
        url: 自定义API URL
        
    Returns:
        查询结果字典，包含accept方法用于保存数据到数据库
    """
    if not arg.strip():
        result = {"result": False, "error": "DRAM料号不能为空"}
        result["accept"] = lambda: None
        return result
    
    pn = arg.strip()
    
    # 处理5位DRAM料号特殊逻辑
    if len(pn) == 5:
        micron_json = parse_micron_pn(pn, refresh)
        if not micron_json.get("result"):
            result = {"result": False, "error": f"未能获取完整DRAM料号：{micron_json.get('error', '未知错误')}"}
            result["accept"] = lambda: None
            return result
        
        # 获取完整的part-number并使用它调用DRAM接口
        # 兼容不同的数据结构：part-number可能在data字典或直接在根级别
        if "data" in micron_json and "part-number" in micron_json["data"]:
            full_pn = micron_json["data"]["part-number"]
        else:
            result = {"result": False, "error": "获取完整DRAM料号失败：找不到part-number字段"}
            result["accept"] = lambda: None
            return result
        micron_json["accept"]()
    else:
        full_pn = pn
    
    # 如果不强制刷新，先尝试从数据库读取
    if not refresh:
        # 使用full_pn.lower()确保不区分大小写查询
        cached_data = get_from_database('dram_detail', full_pn.lower(),debug)
        if cached_data:
            cached_data["accept"] = lambda: None
            return cached_data
    
    try:
        # 使用原始料号或从micron-online获取的完整料号调用DRAM接口
        response = get_from_flash_extra(f"DRAM?param={full_pn}", debug,url)
        if not response:
            result = {"result": False, "error": "DRAM API请求失败"}
            result["accept"] = lambda: None
            return result

        # 解析API返回的JSON
        resp_json = json.loads(response.text)
        if not resp_json.get("result"):
            result = {"result": False, "error": "未查询到DRAM信息"}
            result["accept"] = lambda: None
            return result

        # 自动将detail中所有键名转换为小写并放入data对象
        detail = resp_json.get("detail", {})
        # 先创建小写键名的字典
        data = {key.lower(): value for key, value in detail.items()}
        # 然后添加vendor字段
        data["vendor"] = resp_json.get("Vendor", "未知")
            
        result = {
            "result": True,
            "data": data
        }
        
        # 添加accept方法，仅在调用时保存数据到数据库
        if save:
            def accept_func():
                save_to_database('dram_detail', full_pn.lower(), result,debug)
                # 移除accept方法，避免重复调用
                if "accept" in result:
                    del result["accept"]
            result["accept"] = accept_func
        else:
            result["accept"] = lambda: None
        
        return result
    except json.JSONDecodeError:
        result = {"result": False, "error": "DRAM API返回格式错误"}
        result["accept"] = lambda: None
        return result
    except Exception as e:
        result = {"result": False, "error": f"错误：{str(e)}"}
        result["accept"] = lambda: None
        return result
