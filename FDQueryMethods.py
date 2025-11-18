import json
import requests
import os
from bs4 import BeautifulSoup
import urllib3

from .FDConfig import config_instance as config
from .FDJsonDatabase import save_to_database, get_from_database, db_instance

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
        elif value.endswith("GB") and width!=8: #对于dram需要特殊处理
            num = float(value[:-2])
            bytes_val = num * 1024 * width / 8
        elif value.endswith("MB") and width!=8:
            num = float(value[:-2])
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

def get_from_micron(pn:str,debug: bool=False) -> requests.Response:
    """从Micron API获取数据"""
    response = get_html_with_requests(f"{"https://www.micron.com/content/micron/us/en/sales-support/design-tools/fbga-parts-decoder/_jcr_content.products.json/getpartbyfbgacode/-/-/-/en_US/-/-/"}{pn}",debug)
    if response:
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

def get_detail(arg: str, refresh: bool = False,debug: bool=False,save: bool=None,local: bool=None,url:str|None=None,**kwargs) -> dict:
    """获取闪存料号详细信息
    
    Args:
        arg: 闪存料号
        refresh: 是否强制刷新数据（不使用缓存）
        debug: 是否开启调试模式
        save: 是否保存到数据库
        local: 是否强制使用本地模式（不联网查询）
        url: 自定义API URL      
        
    Returns:
        查询结果字典，包含accept方法用于保存数据到数据库
    """
    result={}
    if not arg.strip():
        result = {"result": False, "error": "料号不能为空"}
        # 添加accept方法（对于失败结果，不执行任何操作）
        result["accept"] = lambda: None

    
    try:
        # 尝试从缓存获取数据（如果不是强制刷新）
        if not result and not refresh:
            # 使用arg.lower()确保不区分大小写查询
            cached_data = get_from_database('flash_detail', arg.lower(),debug)
            if cached_data:
                # 为缓存数据添加accept方法（不执行任何操作，因为已经在数据库中）
                cached_data["accept"] = lambda: None
                return cached_data
                
        if is_hex(arg) and arg.startswith(("89","45","2C","EC","AD","98","9B")):
            return get_detail_from_ID(arg=arg,refresh=refresh,debug=debug,save=save,url=url,**kwargs)
        # 尝试本地算法解码（WIP）
        if not result and local is not False: pass
        # 尝试联网解码
        if not result and local is not True:
            html = get_from_flash_detector(f"decode?lang=chs&pn={arg}",debug,url)
            if not html:
                result = {"result": False, "error": "API请求失败"}
                result["accept"] = lambda: None
                return result
                
            soup = BeautifulSoup(html.text, 'lxml')
            p_tags = soup.find('p')
            if p_tags:
                result = json.loads(p_tags.get_text())
        
        if not result.get("result",False):
            result = {"result": False, "error": "未找到有效数据"}

        if result:
            # 添加accept方法，仅在调用时保存数据到数据库
            if result.get("result",False) and save is None:
                def accept_func():
                    save_to_database('flash_detail', arg.lower(), result,debug)
                    # 移除accept方法，避免重复调用
                    if "accept" in result:
                        del result["accept"]
                result["accept"] = accept_func
            else:
                if save is True:
                    save_to_database('flash_detail', arg.lower(), result,debug)
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


def search(arg: str, debug: bool=False, count: int=10, url:str|None=None, local: bool=None, **kwargs) -> dict:
    """搜索闪存料号
    
    Args:
        arg: 搜索关键词
        debug: 是否开启调试模式
        count: 返回结果数量（默认10条）
        url: 自定义API URL
        local: 是否使用本地数据库搜索
              - None: 先搜索本地，数量不足再请求API
              - True: 只搜索本地
              - False: 只请求API
        
    Returns:
        搜索结果字典
    """
    if not arg.strip():
        return {"result": False, "error": "搜索关键词不能为空"}
    
    local_results = []
    api_results = []
    combined_results = []
    
    # 根据local参数决定搜索策略
    if local is not False:
        # 搜索本地数据库
        if debug:
            print(f"尝试本地数据库搜索: {arg}")
        local_search_result = search_local_database(arg, count, debug)
        if local_search_result.get("result", False):
            local_results = local_search_result["data"]
            combined_results.extend(local_results)
    
    if local is not True and len(combined_results) < count:
        # 如果local是默认值None且本地结果不足count条，则请求API
        remaining = count - len(combined_results)
        if debug:
            print(f"本地结果不足({len(combined_results)}条)，尝试API搜索获取剩余({remaining}条)结果")
        try:
            html = get_from_flash_detector(f"searchPn?limit={remaining}&lang=chs&pn={arg}", debug, url)
            if html:
                soup = BeautifulSoup(html.text, 'lxml')
                p_tags = soup.find('p')
                if p_tags:
                    api_result = json.loads(p_tags.get_text())
                    if api_result.get("result", False):
                        api_results = api_result["data"]
                        combined_results.extend(api_results)
        except (json.JSONDecodeError, Exception) as e:
            if debug:
                print(f"API搜索失败: {str(e)}")
    
    # 处理最终结果
    return {
        "result": True,
        "data": combined_results
    }


def search_local_database(query: str, count: int = 10, debug: bool = False) -> dict:
    """从本地数据库中搜索相关料号信息
    
    Args:
        query: 搜索关键词
        count: 返回结果数量
        debug: 是否开启调试模式
        
    Returns:
        搜索结果字典，格式与API返回一致
    """
    if not query.strip():
        return {"result": False, "error": "搜索关键词不能为空"}
    
    try:
        results = []
        query_lower = query.lower()
        
        # 获取表中的所有键
        keys = db_instance.list_keys('flash_detail')
        for key in keys:
            # 只搜索包含关键词的键
            if query_lower in key:
                # 构造与API返回一致的格式
                results.append(f"{db_instance.get('flash_detail', key).get("data",{}).get('vendor', '未知')} {key.upper()}")
                    
            if len(results) >= count:
                break
        
        if debug:
            print(f"本地数据库搜索结果: {results}")
        
        if results:
            return {
                "result": True,
                "data": results
            }
        else:
            return {"result": False, "error": "未找到匹配结果"}
    
    except Exception as e:
        print(f"本地数据库搜索失败: {str(e)}")
        return {"result": False, "error": str(e)}

def calculate_die_size(density: str, die_count: str) -> str:
    """根据总密度和芯片数计算单芯片(die)大小
    
    Args:
        density: 闪存总密度（如"512MB"、"1GB"等）
        die_count: 芯片数量（如"2"、"4"等）
        
    Returns:
        单芯片大小（如"256MB"、"2GB"等），如果计算失败返回"未知"
    """
    try:
        # 检查输入参数有效性
        if not density or not die_count or density == "未知" or die_count == "未知":
            return "未知"
        
        # 提取数字部分和单位
        import re
        match = re.match(r'(\d+)(GB|MB|TB)', density)
        if not match:
            return "未知"
        
        size_value = int(match.group(1))
        size_unit = match.group(2)
        die_number = int(die_count)
        
        # 计算单芯片大小
        if die_number > 0:
            die_size_value = size_value / die_number
            return f"{die_size_value:.0f}{size_unit}" if die_size_value.is_integer() else f"{die_size_value}{size_unit}"
        else:
            return "未知"
            
    except (ValueError, ZeroDivisionError, AttributeError) as e:
        # 记录错误信息
        logging.error(f"计算单芯片大小时出错: {str(e)}")
        return "未知"

def total_density(density: str, die_count: str) -> str:
    """根据单die大小和die数量计算总大小
    
    Args:
        density: 单die大小（如"512MB"、"1GB"等）
        die_count: 芯片数量（如"2"、"4"等）
        
    Returns:
        总闪存大小（如"1GB"、"2TB"等），如果计算失败返回原始单die容量
    """
    try:
        original_density = density
        density = str(density).strip()
        die_count = int(die_count.strip())
        bytes_val = 0.0  # 统一转换为 MB 作为中间单位

        # 提取单die数值并转换为 MB
        if density.endswith("Tb"):
            num = float(density[:-2])
            bytes_val = num * 1024 * 1024 / 8  # Tb → MB
        elif density.endswith("Gb"):
            num = float(density[:-2])
            bytes_val = num * 1024 / 8  # Gb → MB
        elif density.endswith("Mb"):
            num = float(density[:-2])
            bytes_val = num / 8  # Mb → MB
        elif density.endswith("GB"):
            num = float(density[:-2])
            bytes_val = num * 1024  # GB → MB
        elif density.endswith("MB"):
            num = float(density[:-2])
            bytes_val = num  # MB → MB
        elif density.endswith("G"):
            num = float(density[:-1])
            bytes_val = num * 1024  # G → MB
        elif density.endswith("M"):
            num = float(density[:-1])
            bytes_val = num  # M → MB
        else:
            num = float(density)  # 纯数字默认视为 Mb
            bytes_val = num / 8  # 转换为 MB

        # 计算总容量
        total_bytes = bytes_val * die_count

        # 转换为合适的单位
        if total_bytes >= 1024 * 1024:
            return f"{total_bytes / (1024 * 1024):.2f}TB" if (total_bytes / (1024 * 1024)) != int(total_bytes / (1024 * 1024)) else f"{int(total_bytes / (1024 * 1024))}TB"
        elif total_bytes >= 1024:
            return f"{total_bytes / 1024:.2f}GB" if (total_bytes / 1024) != int(total_bytes / 1024) else f"{int(total_bytes / 1024)}GB"
        else:
            return f"{total_bytes:.2f}MB" if total_bytes != int(total_bytes) else f"{int(total_bytes)}MB"
    except Exception:
        return str(original_density)


def get_detail_from_ID(arg: str, refresh: bool = False,debug: bool=False,save: bool=None,local: bool=None,url:str|None=None,**kwargs) -> dict:
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
        if local is not False:
            data={}
            data["id"]=id_str
            def get_die_cellLevel(id_str: str) -> tuple:
                die_cellLevel=int(id_str[5],16)
                return ["1","2","4","8"][die_cellLevel%4],["SLC","MLC","TLC","QLC"][die_cellLevel//4]
            DENSITY_MAPPING_TOGGLE = { # Toggle阵营的容量规则
                "D3": "1GB",   
                "D5": "2GB",   
                "D7": "4GB",   
                "DE": "8GB",      
                "3A": "16GB",  "5A": "16GB",    
                "3C": "32GB",  "5C": "32GB",  
                "3E": "64GB", 
                "48": "128GB", "5E": "128GB", "7E": "128GB", "89": "128GB", 
                "58": "160GB",
                "73": "170.625GB",
                "49": "256GB", 
                "40": "512GB", 
                "41": "1TB",
            }
            DENSITY_MAPPING_IM = { #IM的容量规则
                "DC": "512MB",    
                "48": "2GB",
                "68": "4GB",
                "88": "8GB",   "64": "8GB",
                "84": "16GB",  
                "A4": "32GB", 
                "B4": "48GB",
                "C3": "64GB", "C4": "64GB",
                "CB": "96GB",
                "D3": "128GB","D4": "128GB", 
                "E4": "256GB",
            }
            #Toggle阵营
            if id_str.startswith(("98","45")): 
                result["result"] = True
                data["vendor"]={"98":"东芝/恺侠","45":"闪迪/西数"}[id_str[:2]]
                data["density"] = DENSITY_MAPPING_TOGGLE.get(id_str[2:4], "未知")
                data["die"],data["cellLevel"]=get_die_cellLevel(id_str)
                data["pageSize"] = ["32","64","128","16"][int(id_str[7],16)%4]
                totalPlane={"6":"2","A":"4","E":"8","2":"16"}[id_str[9]]
                data["plane"] = str(int(totalPlane)//int(data["die"]))
                while(int(data["plane"]) >= 16): data["plane"]=str(int(data["plane"])//16)
                pn1=int(id_str[10],16)%8
                pn2=int(id_str[11],16)%8
                p_n=str(pn1)+str(pn2)
                data["processNode"]={"71":"BiCS2","72":"BiCS3","63":"BiCS4(.5)","64":"BiCS5","65":"BiCS6","66":"BiCS8",
                    "51":"15nm(1z)","50":"A19nm(1y)","57":"19nm(1x)","56":"24nm"
                }.get(p_n,"未知")
            elif id_str.startswith("AD"):
                result["result"] = True
                data["vendor"]="海力士"
                data["density"] = DENSITY_MAPPING_TOGGLE.get(id_str[2:4], "未知")
                data["die"],data["cellLevel"]=get_die_cellLevel(id_str)
                data["density"]=total_density(data["density"],data["die"])
                data["pageSize"] = ["2","4","8","16"][int(id_str[7],16)%4]
                data["plane"] = ["1","2","4","8"][int(id_str[4],16)%4]
                # data["plane"] = str(int(data["totalPlane"])//int(data["die"]))
                data["processNode"] = {"42":"32nm","4A":"16nm","50":"14nm",
                "60":"3DV1","70":"3DV2","80":"3DV3","90":"3DV4","A0":"3DV5",
                "B0":"3DV6","C0":"3DV7","D0":"3DV8"}.get(id_str[10:12],"未知")
            # onfi阵营 
            elif id_str.startswith(("2C","89")):
                result["result"] = True
                data["vendor"]={"2C":"镁光","89":"英特尔"}[id_str[:2]]
                data["density"] = DENSITY_MAPPING_IM.get(id_str[2:4], "未知")
                data["die"],data["cellLevel"]=get_die_cellLevel(id_str)
                # data["pageSize"] = ["2","4","8","16"][int(id_str[7],16)%4] #还不知道 # 我翻遍了料号都看不出来 #只能查表了
                _2d_pn=id_str[6:8]
                if(_2d_pn=="32"):# 3D
                    data["processNode"]={"AA":{"MLC":"3D1 32L(L06)","TLC":"3D1 32L(B0K)","QLC":"3D2 64L(N18)"}.get(data["cellLevel"],"3D1 32L"),
                    "A1":"3D1 32L(B05)" if id_str[2:4]=="84" else "3D2 64L(B16)",
                    "A6":{"TLC":"3D2 64L(B17)","QLC":"3D4 144L(N38A)"}.get(data["cellLevel"],"3D2 64L(B17)"),
                    "A2":"3D3 96L(B27A)",
                    "E6":"3D3 96L(B27B)",
                    "C2":"3D4 144L(N38B)",
                    "C6":"3D3 96L(N28A)",
                    "E5":"3D4 144L(B36R)",
                    "EA":{"10":"3D4 144L(B37R)","30":{"TLC":"3D5 176L(B47R)","QLC":"3D5 176L(N48R)"}.get(data["cellLevel"],"3D5 176L"),
                    "34":"3D5 176L(B47T)"}.get(id_str[10::],"3D5 176L"),
                    "E8":{"TLC":"3D6 232L(B58R)","QLC":"3D6 232L(N58R)"}.get(data["cellLevel"],"3D6 232L")}.get(id_str[8:10],"未知")
                    data["plane"]="2" if (data["processNode"]=="3D2 64L(B16)" or data["processNode"]=="3D1 32L(B05)") else "4"
                    data["pageSize"] = "16"
                else:
                    data["processNode"] = {"46":"32nm","CB":"25nm","3C":"20nm","54":"16nm"}.get(_2d_pn,"未知")
                    data["plane"] = "2"
                    die_size = calculate_die_size(data["density"],data["die"])
                    data["processNode"] += f"({({"SLC":"M","MLC":"L","TLC":"B"}.get(data["cellLevel"],"x"))}{({"46":"6","CB":"7","3C":"8","54":"9"}.get(_2d_pn,"x"))}{({"16GB":"5","8GB":"4","4GB":"3","2GB":"2"}.get(die_size,"x"))})"
                    if data["processNode"] in ("20nm(L84)","25nm(L74)"): data["pageSize"] = "8"
                    elif not data["processNode"].startswith("32nm"): data["pageSize"] = "16"

            result["data"] = data
        # 联网解码
        if local is not True and not result.get("result",False):
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

        if save is None and result.get("result",False):
            # def accept_func():
            #     save_to_database('flash_id_detail', id_str.lower(), result,debug)
            #     # 移除accept方法，避免重复调用
            #     if "accept" in result:
            #         del result["accept"]
            # result["accept"] = accept_func
            result["accept"] = lambda: None
        else:
            if save is True:
                save_to_database('flash_id_detail', id_str.lower(), result,debug)
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
def parse_micron_pn(arg: str, refresh: bool = False, debug: bool=False,save: bool=None,local: bool=False,**kwargs) -> dict:
    """解析Micron PN
    
    Args:
        arg: 镁光料号
        refresh: 是否强制刷新数据（不使用缓存）
        debug: 是否开启调试模式
        save: 是否保存到数据库（None表示根据结果自动判断）
        local: 是否仅使用本地缓存（不联网）
        url: 自定义API URL
        
    Returns:
        查询结果字典，包含accept方法用于保存数据到数据库
    """
    result={}
    if not arg.strip():
        result = {"result": False, "error": "料号不能为空"}
        result["accept"] = lambda: None
    try:
        pn = arg.strip().upper()
        
        # 尝试从缓存获取数据（如果不是强制刷新）
        if not refresh:
            # 使用pn.lower()确保不区分大小写查询
            cached_data = get_from_database('micron_pn_decode', pn.lower(),debug)
            if debug:
                print(cached_data)
            if cached_data:
                return cached_data
        # 本地解码（不可能的，Not WIP）
        if local is not False: pass
        # 访问micron-online接口获取完整part-number
        if local is not True and not result:
            micron_response = get_from_micron(pn, debug) 
            # 尝试解析JSON响应
            response_data = json.loads(micron_response.text)
            if debug:
                print(response_data)
            # 确保返回的数据结构包含必要字段
            result["data"]=response_data.get("details",[{}])[0]
            result["result"]=bool(result["data"])
        # 添加accept方法，仅在调用时保存数据到数据库
        if result.get("result", True) and save:  # 如果没有result字段，默认为True
            def accept_func():
                save_to_database('micron_pn_decode', pn.lower(), result,debug)
                # 移除accept方法，避免重复调用
                if "accept" in result:
                    del result["accept"]
            result["accept"] = accept_func
        else:
            if save is True:
                save_to_database('micron_pn_decode', pn.lower(), result,debug)
            result["accept"] = lambda: None
        if debug:
            print(result)
        return result
    except json.JSONDecodeError:
        result = {"result": False, "error": "返回数据格式错误"}
        result["accept"] = lambda: None
        return result
    except Exception as e:
        result = {"result": False, "error": str(e)}
        result["accept"] = lambda: None
        return result

# DRAM料号查询函数
def get_dram_detail(arg: str, refresh: bool = False, debug: bool=False,save: bool=None,local: bool=None,url:str|None=None,**kwargs) -> dict:
    """查询DRAM详情（适配DRAM专属API）
    
    Args:
        arg: DRAM料号
        refresh: 是否强制刷新数据（不使用缓存）
        debug: 是否开启调试模式
        save: 是否保存到数据库（None表示根据结果自动判断）
        local: 是否仅使用本地缓存（不联网）
        url: 自定义API URL
        
    Returns:
        查询结果字典，包含accept方法用于保存数据到数据库
    """
    if not arg.strip():
        result = {"result": False, "error": "DRAM料号不能为空"}
        result["accept"] = lambda: None
        return result
    
    result={}
    try:   
        pn = arg.strip()
        # 处理5位DRAM料号特殊逻辑
        if len(pn) == 5:
            micron_json = parse_micron_pn(pn, refresh)
            # 获取完整的part-number并使用它调用DRAM接口
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
        # 本地算法解码（这是有可能的，所以WIP）
        if not result and local is not False:pass
        
        # 在线dram解码
        if not result and local is not True:
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
        if save is None and result.get("result"):
            def accept_func():
                save_to_database('dram_detail', full_pn.lower(), result,debug)
                # 移除accept方法，避免重复调用
                if "accept" in result:
                    del result["accept"]
            result["accept"] = accept_func
        else:
            if save is True:
                save_to_database('dram_detail', full_pn.lower(), result,debug)
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


def parse_phison_pn(arg: str, debug: bool=False,save: bool=None,**kwargs) -> dict:
    """查询Phison详情（仅本地解码）
    
    Args:
        arg: Phison料号
        debug: 是否开启调试模式

        
    Returns:
        查询结果字典
    """
    try:
        pn=arg.strip()
        if not pn:
            result = {"result": False, "error": "Phison料号不能为空"}
            result["accept"] = lambda: None
            return result
        if len(pn) != 10:
            result = {"result": False, "error": "Phison料号长度必须为10位"} 
            result["accept"] = lambda: None
            return result
        data={}
        data["vendor"]="群联-"+{"T":"东芝","S":"恺侠","I":"镁光","K":"镁光","H":"海力士",
                                "D":"闪迪","C":"长江存储","N":"英特尔"}.get(pn[0],"未知")
        data["package"]={"A":"BGA132","P":"BGA152","C":"BGA272","O":"SAT-LGA60",
                        "K":"SAT-LGA60","R":"SAT-LGA60","F":"TSOP48","T":"TSOP48",
                        "G":"TSOP48","2":"BGA154"}.get(pn[1],"未知")
        data["classification"]={}
        data["classification"]["ce"],data["die"]={"1":(1,1),"2":(2,2),"5":(2,2),"6":(2,4),
                    "7":(4,4),"8":(4,8),"A":(4,16),"B":(8,8),
                    "C":(8,16),"K":(6,6)}.get(pn[2],(0,"未知"))
        data["die"]=str(data["die"])
        data["density"]={"7":"16GB","8":"32GB","9":"64GB","A":"128GB",
                        "B":"256GB","E":"192GB","H":"512GB","I":"1024GB",
                        "J":"2048GB"}.get(pn[3],"未知")
        def get_process_node(pn: str) -> str:
            """根据Phison料号获取制程"""
            if pn[0]=="T" or pn[0]=="S" or pn[0]=="D": #闪迪/恺侠
                return {"H":"24nm MLC2p(D2H)","P":"1ynm MLC4p(DFK)","R":"1znm TLC(THL)",
                        "S":"1znm MLC2P(DDL)","U":"1znm MLC4p(DFL)",#2D
                        "V":"BiCS2","I":"BiCS3","W":"BiCS4","X":"BiCS4.5",
                        "Y":"BiCS5","1":"BiCS6"}.get(pn[8],"未知")
            elif pn[0]=="H":#海力士
                return {"P":"16nm","X":"3DV7"}.get(pn[8],"未知(海力士料号缺乏，希望大家多多提供)")
            elif pn[0]=="I" or pn[0]=="K" or pn[0]=="N":#IM
                return {"N":"20nm MLC(L85)","P":"16nm MLC(L95)",#2D
                        "O":"L06/B16/N18","V":"B27A","I":"B27B","X":"B37R",
                        "Y":"B47R"}.get(pn[8],"未知")
            elif pn[0]=="C":
                return {"O":"JGS"}.get(pn[8],"未知(长江存储料号缺乏，希望大家多多提供)")
            else:
                return "未知"
        
        data["processNode"]=get_process_node(pn)
        return {"result": True, "data": data, "accept": lambda: None}
    except Exception as e:
        result = {"result": False, "error": f"错误：{str(e)}"}
        result["accept"] = lambda: None
        return result