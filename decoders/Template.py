import abc
from .Decode import Decode

class TemplateDecoder(abc.ABC):
    """解码器模板抽象基类，定义了解码器必须实现的接口"""
    
    vendor: str = ""  # 厂商名称，子类需要覆盖此属性
    
    def __init_subclass__(cls, **kwargs):
        """子类初始化时自动注册到Decode类"""
        super().__init_subclass__(**kwargs)
        if cls.vendor:
            Decode.register_decoder(cls)
    
    @abc.abstractmethod
    @classmethod
    def fromID(cls, id_str: str) -> dict:
        """根据ID字符串解码信息
        
        Args:
            id_str: 要解码的ID字符串
            
        Returns:
            包含解码信息的字典
        """
        pass
    
    @abc.abstractmethod
    @classmethod
    def fromPN(cls, pn: str) -> dict:
        """根据产品编号解码信息
        
        Args:
            pn: 要解码的产品编号
            
        Returns:
            包含解码信息的字典
        """
        pass
    
    @abc.abstractmethod
    @classmethod
    def isThisVendorPN(cls, pn: str) -> bool:
        """检查产品编号是否属于当前厂商
        
        Args:
            pn: 要检查的产品编号
            
        Returns:
            如果属于当前厂商返回True，否则返回False
        """
        pass

    @abc.abstractmethod
    @classmethod
    def isThisVendorID(cls, id_str: str) -> bool:
        """检查ID字符串是否属于当前厂商
        
        Args:
            id_str: 要检查的ID字符串
            
        Returns:
            如果属于当前厂商返回True，否则返回False
        """
        pass