class Decode:
    """解码器管理器，负责管理所有注册的解码器并提供统一的调用接口"""
    
    NO_RESULT_NO_DECODER = {"result": False, "error": "未找到合适解码器"}
    # 静态字典，用于存储注册的解码器类
    _registered_decoders = {}
    
    @classmethod
    def register_decoder(cls, decoder_class):
        """注册解码器类到静态字典
        
        Args:
            decoder_class: 要注册的解码器类
        """
        vendor = decoder_class.vendor
        if vendor:
            cls._registered_decoders[vendor] = decoder_class
    
    @classmethod
    def fromID(cls, id_str: str) -> dict:
        """根据ID字符串自动选择对应的解码器并调用fromID方法
        
        Args:
            id_str: 要解码的ID字符串
            
        Returns:
            包含解码信息的字典，如果没有找到合适的解码器则返回错误信息
        """
        for vendor, decoder_class in cls._registered_decoders.items():
            if decoder_class.isThisVendorID(id_str):
                return decoder_class.fromID(id_str)
        return cls.NO_RESULT_NO_DECODER
    
    @classmethod
    def fromPN(cls, pn: str) -> dict:
        """根据产品编号自动选择对应的解码器并调用fromPN方法
        
        Args:
            pn: 要解码的产品编号
            
        Returns:
            包含解码信息的字典，如果没有找到合适的解码器则返回错误信息
        """
        for vendor, decoder_class in cls._registered_decoders.items():
            if decoder_class.isThisVendorPN(pn):
                return decoder_class.fromPN(pn)
        return cls.NO_RESULT_NO_DECODER
    
    @classmethod
    def get_all_vendors(cls) -> list:
        """获取所有已注册的厂商列表
        
        Returns:
            已注册厂商名称的列表
        """
        return list(cls._registered_decoders.keys())