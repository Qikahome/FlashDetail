import re
from .Template import TemplateDecoder
from .Utils import get_die_cellLevel
class IMDecoder(TemplateDecoder):
    vendor = "IM"
    DENSITY_MAPPING = {
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
    @classmethod
    def calculate_die_size(cls, density: str, die_count: str) -> str:
        try:
            if not density or not die_count or density == "未知" or die_count == "未知":
                return "未知"
            
            match = re.match(r'(\d+)(GB|MB|TB)', density)
            if not match:
                return "未知"
            
            size_value = int(match.group(1))
            size_unit = match.group(2)
            die_number = int(die_count)
            
            if die_number > 0:
                die_size_value = size_value / die_number
                return f"{die_size_value:.0f}{size_unit}" if die_size_value.is_integer() else f"{die_size_value}{size_unit}"
            else:
                return "未知"
        except (ValueError, ZeroDivisionError, AttributeError):
            return "未知"
    @classmethod
    def fromID(cls, id_str: str) -> dict:
        # IM解码逻辑
        data = {}
        data["id"] = id_str
        data["vendor"] = {"2C":"镁光","89":"英特尔","B5":"SpecTek"}[clean_id[:2]]
        data["density"] = DENSITY_MAPPING_IM.get(clean_id[2:4], "未知")
        data["die"], data["cellLevel"] = get_die_cellLevel(clean_id)

        _2d_pn = clean_id[6:8]
        if _2d_pn == "32":  # 3D
            data["processNode"] = {
                "AA": {"MLC":"3D1 32L(L06)","TLC":"3D1 32L(B0K)","QLC":"3D2 64L(N18)"}.get(data["cellLevel"]),
                "A1": "3D1 32L(B05)" if clean_id[2:4] == "84" else "3D2 64L(B16)",
                "A6": {"TLC":"3D2 64L(B17)","QLC":"3D4 144L(N38A)"}.get(data["cellLevel"]),
                "A2": "3D3 96L(B27A)",
                "E6": "3D3 96L(B27C)" if clean_id[-1] == "4" else "3D3 96L(B27B)",
                "C2": "3D4 144L(N38B)",
                "C6": "3D3 96L(N28A)" if clean_id[4] == "1" else "3D4 144L(N38A)",
                "E5": "3D4 144L(B36R)",
                "EA": {
                    "10": "3D4 144L(B37R)",
                    "30": {"TLC":"3D5 176L(B47R)","QLC":"3D5 176L(N48R)"}.get(data["cellLevel"]),
                    "34": "3D5 176L(B47T)"
                }.get(clean_id[10::]),
                "E8": {"TLC":"3D6 232L(B58R)","QLC":"3D6 232L(N58R)"}.get(data["cellLevel"])
            }.get(clean_id[8:10], "未知")
            
            if data["processNode"] is None:
                data["processNode"] = "未知"
            
            data["plane"] = "2" if (data["processNode"] == "3D2 64L(B16)" or data["processNode"] == "3D1 32L(B05)") else "4"
            data["pageSize"] = "16"
        else:  # 2D
            data["processNode"] = {"46":"32nm","CB":"25nm","3C":"20nm","54":"16nm"}.get(_2d_pn, "未知")
            data["plane"] = "2"
            
            die_size = cls.calculate_die_size(data["density"], data["die"])
            
            # 补充工艺节点详细信息
            if data["processNode"] != "未知":
                cell_level_char = {"SLC":"M","MLC":"L","TLC":"B",}.get(data["cellLevel"], "x")
                pn_char = {"46":"6","CB":"7","3C":"8","54":"9"}.get(_2d_pn, "x")
                die_size_char = {"16GB":"5","8GB":"4","4GB":"3","2GB":"2"}.get(die_size, "x")
                data["processNode"] += f"({cell_level_char}{pn_char}{die_size_char})"
            
            # 设置pageSize
            if data["processNode"] in ("20nm(L84)", "25nm(L74)"):
                data["pageSize"] = "8"
            elif not data["processNode"].startswith("32nm"):
                data["pageSize"] = "16"

        return {"result": True, "data": data}

    @classmethod
    def isMicronPn(cls, pn: str) -> bool:
        return pn[5].isdigit() or pn[8] in ("A","B","C","E","G")
    
    @classmethod
    def fromPN(cls, pn: str) -> dict:
        if pn.startswith("29P"):
            return {"result": True, "data": {"vendor": "英特尔", "type": "XPoint"}}
        if pn.startswith("29F") and cls.isMicronPn(pn):
            return cls.fromMicronNandPn("mt"+pn)

    @classmethod
    def fromMicronNandPn(cls, pn: str) -> dict:
        data = {}
        data["pn"] = pn
        data["vendor"] = "镁光"
        data["type"] = "NAND"
        data["density"] = ""
        for i in range(5, len(pn)):
            data["density"] += pn[i]
            if not pn[i].isdigit():
                data["density"] += "b"
                pn = pn[i+1:]
                break
        data["deviceWidth"] = pn[0:2]
        data["cellLevel"] = {"A":"SLC","C":"MLC","E":"TLC","G":"QLC"}.get(pn[2], "未知")
        ce,ch,rb,die = {"A":(0,1,0,1),"B":(1,1,1,1),"C":(3,2,"未知",3),"D":(1,1,1,2),
            "E":(2,2,2,2),"F":(2,1,2,2),"G":(3,3,3,3),"H":(1,1,"未知",4),"J":(2,1,2,4),
            "K":(2,2,2,4),"L":(4,4,4,4),"M":(4,2,4,4),"N":(6,3,"未知",6),"P":(8,2,"未知",8),
            "Q":(4,4,4,8),"R":(2,2,2,8),"S":(4,4,"未知",16),"T":(8,2,4,16),"U":(4,2,4,8),
            "V":(8,4,4,16),"W":(4,2,"未知",16),"X":(4,2,"未知",4),"Y":(7,4,"未知",11),
            }.get(pn[2], ("未知","未知","未知","未知"))
        data["classification"] = {"ce":ce,"ch":ch,"rb":rb,"die":die}
        data["voltage"] = {"A":"Vcc:3.3V,VccQ:3.3V","U":"Vcc:3.3V,VccQ:3.3V or 1.8V","H":"Vcc:3.3V,VccQ:1.8V or 1.2V"}.get(pn[3], "未知")
        data["generation"] = ["A","B","C","D","E","F","G","H","J","K","L","M","N","P","Q","R","S","T","U","V","W","X","Y","Z"].index(pn[4])+1
        data["\u63a5\u53e3"] = {"async":"未知","sync":"未知"} #pn[5]
        data["package"] = {"W":"TSOP48","J":"BGA132","H":("BGA63" if pn[7]=="4" else "BGA100"),"C":("LGA48" if pn[7]=="7" else "LGA52")}
    @classmethod
    def isThisVendorPN(cls, pn: str) -> bool:
        upper_pn = pn.upper()
        # 检查是否以29、MT或PF开头，或者以任意数字+G/B/T开头
        return upper_pn.startswith("29") or upper_pn.startswith("MT") or upper_pn.startswith("PF") or re.match(r'^\d[GBT]', upper_pn) is not None
    
    @classmethod
    def isThisVendorID(cls, id_str: str) -> bool:
        return clean_id.startswith(("2C","89","B5"));