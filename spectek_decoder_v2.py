import requests
from bs4 import BeautifulSoup
import urllib3
import ssl

# 抑制不安全请求的警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class TLSAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super(TLSAdapter, self).init_poolmanager(*args, **kwargs)

def decode_spectek_mark(mark_code):
    """
    解码Spectek的Mark Code，返回产品信息。

    :param mark_code: Spectek的Mark Code字符串，例如 "PE812"
    :return: 包含Mark Code、Part Number和Product Family的列表，例如[['Mark Code', 'Part Number', 'Product Family'], ['PE812', 'SGG64M16V68AG8GNF', 'DDR3']]
    """
    url = "https://www.spectek.com/menus/mark_code.aspx"
    session = requests.Session()
    session.mount('https://', TLSAdapter())
    
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.spectek.com/menus/mark_code.aspx"
    })
    
    try:
        # 1. 发送 GET 请求以获取初始页面和隐藏的状态字段
        response = session.get(url, verify=False, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 提取 ASP.NET 必需的隐藏字段
        viewstate = soup.find('input', {'id': '__VIEWSTATE'})['value']
        viewstate_gen = soup.find('input', {'id': '__VIEWSTATEGENERATOR'})['value']
        event_validation_el = soup.find('input', {'id': '__EVENTVALIDATION'})
        event_validation = event_validation_el['value'] if event_validation_el else ""
        
        # 2. 构建 POST 数据
        payload = {
            '__VIEWSTATE': viewstate,
            '__VIEWSTATEGENERATOR': viewstate_gen,
            '__EVENTVALIDATION': event_validation,
            'ctl00$MainCPH$MarkCodeTextBox': mark_code,
            'ctl00$MainCPH$MarkCodeButton.x': '10',
            'ctl00$MainCPH$MarkCodeButton.y': '10'
        }
        
        # 3. 发送 POST 请求
        response = session.post(url, data=payload, verify=False, timeout=15)
        
        # 4. 解析返回的 HTML 以提取结果
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'id': 'MainCPH_MarkCodeGridView'})
        
        if not table:
            return "未找到解码结果，请检查代码是否正确。"
        
        results = []
        rows = table.find_all('tr')
        for row in rows:
            cols = row.find_all(['td', 'th'])
            cols = [ele.text.strip() for ele in cols]
            if cols:
                results.append(cols)
                
        return results
    except Exception as e:
        return f"请求失败: {str(e)}"

if __name__ == "__main__":
    test_code = "PE812"
    print(f"正在解码: {test_code}...")
    result = decode_spectek_mark(test_code) #format:[['Mark Code', 'Part Number', 'Product Family'], ['PE812', 'SGG64M16V68AG8GNF', 'DDR3']]
    print(result.__repr__())
