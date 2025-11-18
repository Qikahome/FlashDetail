import requests
import re
import shlex
from nonebot.exception import FinishedException
from .FDConfig import config_instance as plugin_config
from . import FDQueryMethods
from .FDJsonDatabase import db_instance
import urllib3
# 插件版本信息
PLUGIN_VERSION = "4.3.0"
    
# 抑制因忽略SSL验证产生的警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    from nonebot import *
    from nonebot.adapters import Event, Message
    from nonebot.rule import startswith
    from nonebot.params import CommandArg
    from nonebot.adapters.onebot.v11 import Event as V11Event
    from nonebot.adapters.onebot.v11 import Bot as V11Bot

    async def is_enabled_for(event: Event) -> bool:
        return plugin_config.is_valid_user(event.get_session_id().split("_"))


    def is_admin(user_id: str) -> bool:
        return user_id in plugin_config.admin_users


    def is_owner(user_id: str) -> bool:
        """判断是否为所有者（仅owner可管理管理员）"""
        return user_id == plugin_config.owner



    # 基础帮助文本（所有用户可见）
    BASE_HELP_TEXT = """
FlashDetail插件使用说明

基础查询命令：
    ID <id> - 根据闪存ID查询详细信息
    查 <料号> - 查询闪存详情，支持部分料号搜索，自动尝试搜索和Micron料号解析
    搜 <关键词> - 搜索相关料号
    查DRAM <料号/ID> - 查询DRAM内存信息
    撤回 - 回复消息并发送此命令可撤回被回复消息（非管理员只能撤回自己的消息）
    /micron <料号> - 解析镁光BGA CODE料号获取完整料号
    /phison <参数> - 解析群联料号

    其他命令：
        /status - 显示插件运行状态
        /version - 显示插件版本信息
        /help - 显示此帮助信息

    提示：
    - 所有查询命令均可添加 --refresh 参数强制刷新缓存
    - 所有查询命令均可添加 --debug 参数显示调试信息
    - 所有查询命令均可添加 --url 参数指定查询api地址
    - 所有非"无结果"的查询结果会自动缓存，提高后续查询速度"""
    
    # 管理员帮助文本（仅管理员和所有者可见）
    ADMIN_HELP_TEXT = """

管理员命令：
    /whitelist add/list/remove - 管理白名单用户/群组
    /blacklist add/list/remove - 管理黑名单用户/群组
    /api - 显示api相关信息（具体用法使用/api help）

    白名单/黑名单命令格式：
        /whitelist add user/group <id> - 添加用户/群组到白名单
        /whitelist remove user/group <id> - 从白名单移除用户/群组
        /whitelist list [user/group] - 显示白名单（可选指定类型）
        /whitelist remove - 清空所有白名单
        /whitelist remove user/group - 清空指定类型白名单

    （黑名单命令格式与白名单相同）

    快捷封禁/解封命令：
        /ban <user_id> - 将用户加入黑名单（不能封禁管理员）
        /pardon <user_id> - 将用户从黑名单移除"""
    
    # 所有者帮助文本（仅所有者可见）
    OWNER_HELP_TEXT = """

所有者命令：
    /admin add/list/remove - 管理管理员列表
    /op <user_id> - 设置指定用户为管理员
    /deop <user_id> - 移除用户的管理员权限
    /reload - 重载插件
    /config - 管理插件配置（仅所有者可用）

    管理员命令格式：
        /admin add <user_id> - 添加管理员
        /admin remove <user_id> - 移除管理员（不能移除所有者）
        /admin list - 列出所有管理员及所有者

    配置命令格式：
        /config list - 显示当前配置状态
        /config <选项名> <值> - 设置配置项（如true/false或数字）
"""

    
    
    # 命令定义
    whitelist_cmd = on_command("whitelist", priority=1, rule=is_enabled_for, block=False)
    blacklist_cmd = on_command("blacklist", priority=1, rule=is_enabled_for, block=False)
    admin_cmd = on_command("admin", priority=1, rule=is_enabled_for, block=False)  # 管理员管理命令 
    listened_commands = startswith(("ID", "DRAM", "查", "搜","/micron","/phison"), ignorecase=True)
    MessageHandler = on_message(priority=10, rule=is_enabled_for & listened_commands, block=False)
    help_cmd = on_command("help", priority=1, rule=is_enabled_for, block=False)
    api_cmd = on_command("api", priority=1, rule=is_enabled_for, block=False)
    reload_cmd = on_command("reload", priority=1, rule=is_enabled_for, block=False)
    status_cmd = on_command("status", priority=1, rule=is_enabled_for, block=False)
    version_cmd = on_command("version", priority=1, rule=is_enabled_for, block=False)
    op_cmd = on_command("op", priority=1, rule=is_enabled_for, block=False)  # 管理员管理命令
    deop_cmd = on_command("deop", priority=1, rule=is_enabled_for, block=False)
    ban_cmd = on_command("ban", priority=1, rule=is_enabled_for, block=False)
    pardon_cmd = on_command("pardon", priority=1, rule=is_enabled_for, block=False)
    refresh_cmd = on_command("refresh", priority=1, rule=is_enabled_for, block=False)
    config_cmd = on_command("config", priority=1, rule=is_enabled_for, block=False)
    database_cmd = on_command("database", priority=1, rule=is_enabled_for, block=False)
    喵 = on_message(priority=10, rule=is_enabled_for, block=False)
    repeater = on_message(priority=10, rule=is_enabled_for, block=False)
    撤回_cmd = on_message(priority=10, rule=is_enabled_for, block=False)
    whoami_cmd = on_command("whoami", priority=1, block=False)

    # 查看当前用户ID
    @whoami_cmd.handle()
    async def whoami(event: Event):
        user_id = event.get_user_id()
        await whoami_cmd.send(f"您的用户ID是：{user_id}")

    def is_key_word(message_text:str) -> bool:
        return message_text.strip() and any([i in message_text.lower() for i in ["撤回","/","查","id"]])
    # 撤回
    @撤回_cmd.handle()
    async def 撤回(event: V11Event, bot: V11Bot):
        
        # 获取消息内容
        message_text = event.get_message().extract_plain_text().strip()
        
        # 检查是否包含"撤回"关键词
        if "撤回" not in message_text:
            return
        
        # 检查是否是回复消息
        if event.reply:
            print(event.reply)
            # 获取被回复的消息ID
            reply_message_id = event.reply.message_id
            # 检查是否是管理员或者撤回目标是用户自己的消息
            if (not is_admin(event.get_user_id())) and (event.get_user_id() != event.reply.sender):
                return
            try:
                # 尝试撤回消息
                await bot.delete_msg(message_id=reply_message_id)
            except Exception as e:
                # 撤回失败（可能没有权限）
                await 撤回_cmd.send(f"撤回失败，可能没有权限：{str(e)}")
    

    last_message:dict[str,list[str,int]] = {}  # 格式：{session_id: [last_message, times]}

    # 复读机
    @repeater.handle()
    async def repeater_handler(event: Event):
        if(is_key_word(event.get_message().extract_plain_text())):
            return
        session_id = event.get_session_id().split("_")
        if(session_id[0]!="group"):
            return
        session_id=session_id[1]
        if(event.get_message().extract_plain_text() == last_message.get(session_id,["",0])[0]):
            last_message[session_id][1] += 1
        else:
            last_message[session_id] = [event.get_message().extract_plain_text(), 1]
        if(plugin_config.configs["repeater"] and last_message[session_id][1]==plugin_config.configs["repeater"]):
            (await repeater.finish(last_message[session_id][0])) if last_message[session_id][0] else repeater.finish()


    # 喵喵喵
    @喵.handle()
    async def 喵_handler(event: Event):
        if(plugin_config.configs["cat"] and "喵" in event.get_message().extract_plain_text()):
            await 喵.finish("喵")
    

    def parse_config_value(value: str) -> Any:
        if value.lower() in ["true", "yes"]:
            return True
        elif value.lower() in ["false", "no"]:
            return False
        elif value.isdigit():
            return int(value)
        else:
            return value

    # 配置管理命令
    @config_cmd.handle()
    async def config_handler(event: Event, arg: Message = CommandArg()):
        user_id = event.get_user_id()
        if not is_owner(user_id):
            await config_cmd.finish("")
            return
        args = arg.extract_plain_text().strip().split()
        if not args:
            args=["list"]

        # 显示当前配置
        if args[0] == "list":
            result="当前配置状态：\n"
            for key, value in plugin_config.configs.items():
                result += f"{key}: {value}\n"
            await config_cmd.finish(result)
        
        # 设置其他配置项
        elif args[0] in plugin_config.configs.keys():
            value = parse_config_value(args[1].lower())
            if type(value) == type(plugin_config.configs[args[0]]):
                plugin_config.configs[args[0]] = value
                plugin_config.save_all()
                await config_cmd.finish(f"已设置{args[0]}为{value}")
            
            else:
                await config_cmd.finish(f"值错误，请使用{type(plugin_config.configs[args[0]]).__name__}类型")
    
        
        else:
            await config_cmd.finish("未知的配置项，请使用：auto_accept_friend 或 auto_join_group")

    # 重载配置
    @reload_cmd.handle()
    async def reload_config_handler(event: Event):
        # 先检查是否为所有者
        if not is_owner(event.get_user_id()):
            await reload_cmd.finish("权限不足，只有所有者可以重载配置")
        else:
            try:
                reload_cmd.send("正在尝试重载，可能需要一些时间\n重载完成后不会自动提醒，请手动检查状态")
                with open(__file__, "a") as f:
                    f.write("# reload\n")
            except Exception as e:
                await reload_cmd.finish(f"配置重载失败: {str(e)}")
    
    # 状态查询命令
    @status_cmd.handle()
    async def status_handler(event: Event):
        # 获取配置状态信息
        status_info = []
        status_info.append("FlashDetail 插件状态信息")
        status_info.append(f"版本: {PLUGIN_VERSION}")
        # 移除不再使用的api_url引用
        status_info.append(f"所有者: {plugin_config.owner}")
        status_info.append(f"管理员数量: {len(plugin_config.admin_users)}")
        status_info.append(f"白名单用户数: {len(plugin_config.whitelist_user)}")
        status_info.append(f"白名单群组数: {len(plugin_config.whitelist_group)}")
        status_info.append(f"黑名单用户数: {len(plugin_config.blacklist_user)}")
        status_info.append(f"黑名单群组数: {len(plugin_config.blacklist_group)}")
        
        await status_cmd.finish("\n".join(status_info))
    
    # 版本查询命令
    @version_cmd.handle()
    async def version_handler(event: Event):
        version_info = [
            f"FlashDetail 插件 v{PLUGIN_VERSION}",
            "功能: Flash和DRAM料号查询工具",
            "支持命令: 查/搜/ID/查DRAM/help/api/admin/whitelist/blacklist/status/version/reload/micron",
            "作者: Qikahome/3281",
            "仅供学习和测试使用"
        ]
        await version_cmd.finish("\n".join(version_info))
    # 帮助命令
    @help_cmd.handle()
    async def help_command_handler(event: Event):
        # 根据用户权限显示不同级别的帮助文本
        user_id = event.get_user_id()
        help_text = BASE_HELP_TEXT
        
        # 管理员和所有者可以看到管理员相关命令
        if is_admin(user_id) or is_owner(user_id):
            help_text += ADMIN_HELP_TEXT
        
        # 只有所有者可以看到所有者相关命令
        if is_owner(user_id):
            help_text += OWNER_HELP_TEXT
        
        await help_cmd.finish(help_text)


    # 消息命令
    @MessageHandler.handle()
    async def message_handler(foo: Event):
        # 不再需要单独检查用户有效性，因为is_enabled_for规则已经做了检查
        result = get_message_result(foo.get_plaintext())
        if result and result[-1] == '\n':
            result = result[:-1]
        if result: 
            await MessageHandler.finish(result)
        else:
            await MessageHandler.finish()


    # API命令
    @api_cmd.handle()
    async def api_command_handler(event: Event, arg: Message = CommandArg()):
        # 不再需要单独检查用户有效性，因为is_enabled_for规则已经做了检查
        user_id = event.get_user_id()
        arg_text = arg.extract_plain_text().strip()
        parts = arg_text.split() if arg_text else []
        if not parts:parts=["fd","list"]
        if parts[0] == "help":
            API_HELP_TEXT="""\
命令格式：
/api list - 列出API地址
/api status - 检查API状态
/api add <url> - 添加API地址
/api del <url> - 删除API地址
/api del --all - 删除所有API地址
/api insert <index> <url> - 在指定位置插入API地址"""
            await api_cmd.finish(API_HELP_TEXT)
        if parts[0] != "fe" and parts[0] != "fd":
            parts.insert(0,"fd")
        if parts[0] == "fd":
            if parts[1] == "list":
                await api_cmd.finish(f"当前的api地址：{"".join(["\n   "+text for text in plugin_config.flash_detect_api_urls])}")
            elif parts[1]=="status":
                await api_cmd.finish(f"当前的api状态：{"".join(["\n"+url+":"+("正常" if FDQuery(url) else "异常") for url in plugin_config.flash_detect_api_urls])}")
            elif parts[1]=="add":
                if len(parts) != 3:
                    await api_cmd.finish("指令格式错误，正确用法：/api add <url>")
                url = parts[2]
                if url[:4] not in ("http", "https"):
                    url = "http://" + url
                if url[-1] == '/':
                    url = url[:-1]
                plugin_config.flash_detect_api_urls.append(url)
                plugin_config.save_all()
                await api_cmd.finish(f"已在flash_detector api地址添加：{url}")
            elif parts[1]=="del":
                if len(parts) == 2:
                    await api_cmd.finish("若要移除所有的url地址，请使用/api del --all")
                if len(parts) != 3:
                    await api_cmd.finish("指令格式错误，正确用法：/api del <url>")
                url = parts[2]
                if url == "--all":
                    plugin_config.flash_detect_api_urls.clear()
                    plugin_config.save_all()
                    await api_cmd.finish("已移除所有flash_detector api地址") 
                if url in plugin_config.flash_detect_api_urls:
                    plugin_config.flash_detect_api_urls.remove(url)
                    plugin_config.save_all()
                    await api_cmd.finish(f"已从flash_detector api地址删除：{url}")
                else:
                    await api_cmd.finish(f"flash_detector api地址列表中不存在：{url}")
            elif parts[1] == "insert":
                if len(parts) != 4:
                    await api_cmd.finish("指令格式错误，正确用法：/api insert <index> <url>")
                index = int(parts[2])
                url = parts[3]
                if url[:4] not in ("http", "https"):
                    url = "http://" + url
                if url[-1] == '/':
                    url = url[:-1]
                plugin_config.flash_detect_api_urls.insert(index, url)
                plugin_config.save_all()
                await api_cmd.finish(f"已在flash_detector api地址列表的第{index}个位置插入：{url}")
        elif parts[1] == "fe":
            if parts[2] == "list":
                await api_cmd.finish(f"当前的api地址：{"".join(["\n   "+text for text in plugin_config.flash_extra_api_urls])}")
            elif parts[2]=="status":
                await api_cmd.finish(f"当前的api状态：{"".join(["\n"+url+":"+("正常" if FDQuery(url) else "异常") for url in plugin_config.flash_extra_api_urls])}")
            elif parts[2]=="add":
                if len(parts) != 3:
                    await api_cmd.finish("指令格式错误，正确用法：/api fe add <url>")
                url = parts[2]
                if url[:4] not in ("http", "https"):
                    url = "http://" + url
                if url[-1] == '/':
                    url = url[:-1]
                plugin_config.flash_extra_api_urls.append(url)
                plugin_config.save_all()
                await api_cmd.finish(f"已在flash_extra api地址添加：{url}")
            elif parts[2]=="del":
                if len(parts) == 2:
                    await api_cmd.finish("若要移除所有的url地址，请使用/api fe del --all")
                if len(parts) != 3:
                    await api_cmd.finish("指令格式错误，正确用法：/api fe del <url>")
                url = parts[2]
                if url == "--all":
                    plugin_config.flash_extra_api_urls.clear()
                    plugin_config.save_all()
                    await api_cmd.finish("已移除所有flash_extra api地址") 
                if url in plugin_config.flash_extra_api_urls:
                    plugin_config.flash_extra_api_urls.remove(url)
                    plugin_config.save_all()
                    await api_cmd.finish(f"已从flash_extra api地址删除：{url}")
                else:
                    await api_cmd.finish(f"flash_extra api地址列表中不存在：{url}")
            elif parts[2] == "insert":
                if len(parts) != 4:
                    await api_cmd.finish("指令格式错误，正确用法：/api fe insert <index> <url>")
                index = int(parts[2])
                url = parts[3]
                if url[:4] not in ("http", "https"):
                    url = "http://" + url
                if url[-1] == '/':
                    url = url[:-1]
                plugin_config.flash_extra_api_urls.insert(index, url)
                plugin_config.save_all()
                await api_cmd.finish(f"已在flash_extra api地址列表的第{index}个位置插入：{url}")


    # 白名单命令
    @whitelist_cmd.handle()
    async def whitelist_handler(event: Event, arg: Message = CommandArg()):
        user_id = event.get_user_id()
        if not is_admin(user_id):
            return
        args = arg.extract_plain_text().strip().split()
        result = handle_list_command("whitelist", args)
        if result:
            await whitelist_cmd.finish(result)


    # 黑名单命令
    @blacklist_cmd.handle()
    async def blacklist_handler(event: Event, arg: Message = CommandArg()):
        user_id = event.get_user_id()
        if not is_admin(user_id):
            return
        args = arg.extract_plain_text().strip().split()
        result = handle_list_command("blacklist", args)
        if result:
            await blacklist_cmd.finish(result)


    # 管理员管理命令（仅所有者可用）
    @admin_cmd.handle()
    async def admin_handler(event: Event, arg: Message = CommandArg()):
        user_id = event.get_user_id()
        if not is_owner(user_id):  # 仅所有者可操作
            return
        args = arg.extract_plain_text().strip().split()
        result = handle_admin_command(args)
        if result:
            await admin_cmd.finish(result)
    
    # 将用户设为管理员（仅所有者可用）
    @op_cmd.handle()
    async def op_handler(event: Event, arg: Message = CommandArg()):
        user_id = event.get_user_id()
        if not is_owner(user_id):
            return
        target_id = arg.extract_plain_text().strip()
        if not target_id:
            await op_cmd.finish("请指定要设置为管理员的用户ID")
            return
        if target_id in plugin_config.admin_users:
            await op_cmd.finish(f"用户 {target_id} 已是管理员")
            return
        plugin_config.admin_users.append(target_id)
        plugin_config.save_all()
        await op_cmd.finish(f"已将用户 {target_id} 设置为管理员")
    
    # 移除用户的管理员权限（仅所有者可用）
    @deop_cmd.handle()
    async def deop_handler(event: Event, arg: Message = CommandArg()):
        user_id = event.get_user_id()
        if not is_owner(user_id):
            return
        target_id = arg.extract_plain_text().strip()
        if not target_id:
            await deop_cmd.finish("请指定要移除管理员权限的用户ID")
            return
        if target_id not in plugin_config.admin_users:
            await deop_cmd.finish(f"用户 {target_id} 不是管理员")
            return
        plugin_config.admin_users.remove(target_id)
        plugin_config.save_all()
        await deop_cmd.finish(f"已移除用户 {target_id} 的管理员权限")
    
    # 将用户加入黑名单（仅所有者可用）
    @ban_cmd.handle()
    async def ban_handler(event: Event, arg: Message = CommandArg()):
        user_id = event.get_user_id()
        if not is_admin(user_id):
            return
        target_id = arg.extract_plain_text().strip()
        if not target_id:
            await ban_cmd.finish("请指定要封禁的用户ID")
            return
        if target_id in plugin_config.blacklist_user:
            await ban_cmd.finish(f"用户 {target_id} 已在黑名单中")
            return
        # 禁止将管理员加入黑名单
        if target_id in plugin_config.admin_users:
            await ban_cmd.finish(f"不能将管理员 {target_id} 加入黑名单，请先移除其管理员权限")
            return
        plugin_config.blacklist_user.append(target_id)
        plugin_config.save_all()
        await ban_cmd.finish(f"已将用户 {target_id} 加入黑名单")
    
    # 将用户从黑名单移除（仅所有者可用）
    @pardon_cmd.handle()
    async def pardon_handler(event: Event, arg: Message = CommandArg()):
        user_id = event.get_user_id()
        if not is_admin(user_id):
            return
        target_id = arg.extract_plain_text().strip()
        if not target_id:
            await pardon_cmd.finish("请指定要解封的用户ID")
            return
        if target_id not in plugin_config.blacklist_user:
            await pardon_cmd.finish(f"用户 {target_id} 不在黑名单中")
            return
        plugin_config.blacklist_user.remove(target_id)
        plugin_config.save_all()
        await pardon_cmd.finish(f"已将用户 {target_id} 从黑名单移除")

    # 数据库管理命令（仅管理员可用）
    @database_cmd.handle()
    async def database_handler(event: Event, arg: Message = CommandArg()):
        user_id = event.get_user_id()
        if not is_admin(user_id):
            await database_cmd.finish("该命令仅管理员可用")
            return
        
        args_text = arg.extract_plain_text().strip()
        if not args_text:
            await database_cmd.finish("请输入命令参数：/database add/replace/remove <path> <key> <value>")
            return
        
        args = shlex.split(args_text)
        if len(args) < 2:
            await database_cmd.finish("参数不足，请输入完整命令格式")
            return
        
        action = args[0].lower()
        if action not in ["add", "replace", "remove"]:
            await database_cmd.finish("无效操作，仅支持 add/replace/remove")
            return
        
        path = args[1]
        path_parts = path.split(".")
        
        # 处理特殊情况：remove命令且有3个参数 → 合并后两个为table.pk
        if action == "remove" and len(args) == 3 and len(path_parts) == 1:
            table = args[1]
            pk = args[2]
        else:
            table = path_parts[0]
            pk = ".".join(path_parts[1:]) if len(path_parts) > 1 else None
        
        if action in ["add", "replace"]:
            if not pk:
                await database_cmd.finish("路径格式错误，add/replace 必须为 <表名.主键>")
                return
            
            if len(args) < 4:
                await database_cmd.finish(f"{action}命令格式：/database {action} <path> <key> <value>")
                return
            
            key = args[2]
            value = " ".join(args[3:])
            
            try:
                # 获取现有记录
                existing_record = db_instance.get(table, pk)
                new_record = existing_record.copy() if existing_record else {}
                
                if action == "add":
                    if key in new_record:
                        await database_cmd.finish(f"操作失败：{table}.{pk} 已存在 {key} 字段")
                        return
                    new_record[key] = value
                
                if action == "replace":
                    new_record[key] = value
                
                # 保存更新后的记录
                success = db_instance.set(table, pk, new_record)
                if success:
                    await database_cmd.finish(f"已成功{action} {table}.{pk} 的 {key} 字段")
                else:
                    await database_cmd.finish(f"操作失败：路径不存在")
            except FinishedException:
                raise  # 重新抛出，让nonebot处理
            except Exception as e:
                await database_cmd.finish(f"操作失败：{str(e)}")
        
        elif action == "remove":
            try:
                # 1. 删除整个表 (格式: /database remove <table_name>)
                if not pk and len(args) == 2:
                    success = db_instance.delete_table(table)
                    if success:
                        await database_cmd.finish(f"已成功删除表 {table}")
                    else:
                        await database_cmd.finish(f"操作失败：表 {table} 不存在")
                    return
                
                # 2. 没有 pk 但有其他参数 → 格式错误
                if not pk:
                    await database_cmd.finish("参数格式错误，删除表应为 /database remove <表名>")
                    return
                
                # 3. 删除整个记录 (格式: /database remove <table.pk> 或 /database remove <table.pk> *)
                if len(args) == 2 or (len(args) >= 3 and args[2] == "*"):
                    success = db_instance.delete(table, pk)
                    if success:
                        await database_cmd.finish(f"已成功删除记录 {table}.{pk}")
                    else:
                        await database_cmd.finish(f"操作失败：记录 {table}.{pk} 不存在")
                    return
                
                # 4. 删除特定字段 (格式: /database remove <table.pk> <field>)
                if len(args) < 3:
                    await database_cmd.finish("remove命令格式：/database remove <path> <key>")
                    return
                
                key = args[2]
                
                # 获取现有记录
                existing_record = db_instance.get(table, pk)
                if not existing_record:
                    await database_cmd.finish(f"操作失败：{table}.{pk} 不存在")
                    return
                
                if key not in existing_record:
                    await database_cmd.finish(f"操作失败：{table}.{pk} 不存在 {key} 字段")
                    return
                
                # 删除字段
                del existing_record[key]
                
                if existing_record:
                    # 保存更新后的记录
                    success = db_instance.set(table, pk, existing_record)
                    if success:
                        await database_cmd.finish(f"已成功删除 {table}.{pk} 的 {key} 字段")
                    else:
                        await database_cmd.finish(f"操作失败：保存失败")
                else:
                    # 删除空记录
                    success = db_instance.delete(table, pk)
                    if success:
                        await database_cmd.finish(f"已成功删除 {table}.{pk} 的 {key} 字段，因记录为空已删除整个记录")
                    else:
                        await database_cmd.finish(f"操作失败：删除字段失败")
            except FinishedException:
                raise  # 重新抛出，让nonebot处理
            except Exception as e:
                await database_cmd.finish(f"操作失败：{str(e)}")

    def handle_list_command(list_type: str, args: list) -> str:
        """处理黑白名单命令"""
        # 如果没有参数，默认执行list操作
        if not args:
            args = ["list"]

        list_mapping = {
            ("whitelist", "user"): "whitelist_user",
            ("whitelist", "group"): "whitelist_group",
            ("blacklist", "user"): "blacklist_user",
            ("blacklist", "group"): "blacklist_group"
        }
        all_types = ["user", "group"]
        operation = args[0].lower()

        if operation == "add":
            if len(args) != 3:
                return f"添加指令格式错误：/{list_type} add <user/group> <id>"
            target_type, target_id = args[1].lower(), args[2].strip()
            if target_type not in all_types:
                return "类型错误，只能是user或group"
            list_field = list_mapping[(list_type, target_type)]
            target_list = getattr(plugin_config, list_field)
            if target_id in target_list:
                return f"{list_type}中已存在{target_type} {target_id}"
            # 禁止将管理员加入黑名单
            if list_type == "blacklist" and target_type == "user" and target_id in plugin_config.admin_users:
                return f"不能将管理员 {target_id} 加入黑名单，请先移除其管理员权限"
            target_list.append(target_id)
            plugin_config.save_all()
            return f"已将{target_type} {target_id}添加到{list_type}"

        elif operation == "remove":
            if len(args) == 1:
                for target_type in all_types:
                    setattr(plugin_config, list_mapping[(list_type, target_type)], [])
                plugin_config.save_all()
                return f"已清空{list_type}的所有用户和群组"
            if len(args) == 2:
                target_type = args[1].lower()
                if target_type not in all_types:
                    return "类型错误，只能是user或group"
                list_field = list_mapping[(list_type, target_type)]
                if not getattr(plugin_config, list_field):
                    return f"{list_type}的{target_type}列表已为空"
                setattr(plugin_config, list_field, [])
                plugin_config.save_all()
                return f"已清空{list_type}的{target_type}列表"
            if len(args) == 3:
                target_type, target_id = args[1].lower(), args[2].strip()
                if target_type not in all_types:
                    return "类型错误，只能是user或group"
                list_field = list_mapping[(list_type, target_type)]
                target_list = getattr(plugin_config, list_field)
                if target_id not in target_list:
                    return f"{list_type}的{target_type}列表中不存在{target_id}"
                target_list.remove(target_id)
                plugin_config.save_all()
                return f"已从{list_type}的{target_type}列表移除{target_id}"
            return f"移除指令格式错误，最多3个参数：/{list_type} remove [user/group] [id]"

        elif operation == "list":
            if len(args) == 1:
                result = [f"{list_type}列表："]
                for target_type in all_types:
                    list_field = list_mapping[(list_type, target_type)]
                    target_list = getattr(plugin_config, list_field)
                    result.append(f"\n{target_type}列表：")
                    result.extend([f"- {id_}" for id_ in target_list]) if target_list else result.append("(空)")
                return "\n".join(result)
            if len(args) == 2:
                target_type = args[1].lower()
                if target_type not in all_types:
                    return "类型错误，只能是user或group"
                list_field = list_mapping[(list_type, target_type)]
                target_list = getattr(plugin_config, list_field)
                result = [f"{list_type}的{target_type}列表："]
                result.extend([f"- {id_}" for id_ in target_list]) if target_list else result.append("(空)")
                return "\n".join(result)
            return f"列表指令格式错误，最多2个参数：/{list_type} list [user/group]"

        else:
            return f"未知操作：{operation}，支持add/remove/list"


    def handle_admin_command(args: list) -> str:
        """处理管理员管理命令（仅所有者可用）"""
        if not args:
            return "管理员命令格式错误，示例：\n" \
                "/admin add <id> → 添加管理员\n" \
                "/admin remove <id> → 移除管理员\n" \
                "/admin list → 列出所有管理员"

        operation = args[0].lower()

        # 添加管理员
        if operation == "add":
            if len(args) != 2:
                return "添加管理员格式错误：/admin add <id>"
            admin_id = args[1].strip()
            if admin_id in plugin_config.admin_users:
                return f"ID {admin_id} 已是管理员"
            # 防止移除所有者的管理员权限（如果所有者在admin_users中）
            if admin_id == plugin_config.owner and admin_id not in plugin_config.admin_users:
                plugin_config.admin_users.append(admin_id)
                plugin_config.save_all()
                return f"已添加所有者 {admin_id} 为管理员"
            plugin_config.admin_users.append(admin_id)
            plugin_config.save_all()
            return f"已添加 {admin_id} 为管理员"

        # 移除管理员
        elif operation == "remove":
            if len(args) != 2:
                return "移除管理员格式错误：/admin remove <id>"
            admin_id = args[1].strip()
            # 禁止移除所有者
            if admin_id == plugin_config.owner:
                return "禁止移除所有者的管理员权限"
            if admin_id not in plugin_config.admin_users:
                return f"ID {admin_id} 不是管理员"
            plugin_config.admin_users.remove(admin_id)
            plugin_config.save_all()
            return f"已移除 {admin_id} 的管理员权限"

        # 列出管理员
        elif operation == "list":
            if len(args) != 1:
                return "列出管理员格式错误：/admin list"
            result = ["管理员列表："]
            if plugin_config.admin_users:
                for idx, admin_id in enumerate(plugin_config.admin_users, 1):
                    # 标记所有者
                    mark = "（所有者）" if admin_id == plugin_config.owner else ""
                    result.append(f"{idx}. {admin_id}{mark}")
            else:
                result.append("(空)")
            return "\n".join(result)

        else:
            return f"未知操作：{operation}，支持add/remove/list"

    

except Exception as e:
    print(f"not running in onebot: {e}")


def classification(arg: dict[str, int]) -> str:
    result=""
    if(arg.get('ch') and arg['ch']!="未知"):
        result += f"{translations['channel']}{arg['ch']}\n"
    if(arg.get('ce') and arg['ce']!="未知"):
        result += f"{translations['ce']}{arg['ce']}\n"
    if(arg.get('die') and arg['die']!="未知"):
        result += f"{translations['die']}{arg['die']}\n"
    return result

def flashId(arg: list[str]) -> str:
    return "" if not arg else f"{translations['availableID']}{', '.join(arg)}\n"


translations = {
    "id": "", "vendor": "厂商：", "die": "Die数量：", "plane": "平面数：","totalPlane": "总平面数/Ce：",
    "pageSize": "页面大小：", "blockSize": "块大小：", "processNode": "制程：",
    "cellLevel": "单元类型：", "partNumber": "料号：", "type": "类型：", "density": "容量：",
    "channel": "通道数：","ce": "片选：","die": "Die数量：","availablePn": "可能的料号：",
    "deviceWidth": "位宽：","voltage": "电压：", "generation": "代数：", "package": "封装：", 
    "availableID": "可能的ID：","depth": "深度：","grade": "等级：","speed": "速度：",
    "vendor_code": "厂商代码：","version": "版本：","width": "位宽："
}

data_parsers = {"classification": classification, "flashId": flashId}


def result_to_text(arg: dict, debug: bool=False, **kwargs) -> str:  
    if not arg.get("result", False):
        return f"未能查询到结果：{arg.get('error', '未知错误' if not debug else str(arg))}"
    result = ""
    data=arg.get("data", {})
    if isinstance(data,dict):
        for key,value in data.items():
            if(value == "未知" or not value):continue
            if(key == "density"):
                width=data.get('width', "8")
                result += f"{translations[key]}{FDQueryMethods.format_density(value,int(width[1:] if width.startswith('x') else width))}\n"
                continue
            func=data_parsers.get(key, None)
            if func:
                result += func(value)
            else:
                trans=translations.get(key, None)
                if trans!=None:
                    result += f"{trans}{value}\n"
        if(result.count("\n")<2):
            result=""
    elif isinstance(data, list) and data:
        result += f"{translations['availablePn']}{', '.join(data)}\n"
    return result

def all_numbers_alpha(string: str) -> bool:
    # 使用正则表达式判断字符是否在0-9A-Za-z_/:-范围内
    return string and all(re.match(r'^[0-9A-Za-z_/:\-]$', c) for c in string)

def ID(arg: str, **kwargs) -> str:
    # 转换为小写进行处理，确保不区分大小写
    arg = arg.lower()
    raw_result=FDQueryMethods.get_detail_from_ID(arg=arg, **kwargs)   
    result = result_to_text(raw_result, **kwargs)
    if result and "accept" in raw_result:
        raw_result["accept"]()
    if not result and len(arg)>3:
        if all_numbers_alpha(arg):
            result = "无结果"
    return result

def 查(arg: str, retry: bool=True, **kwargs) -> str:
    # 转换为小写进行处理，确保不区分大小写
    arg = arg.lower()
    raw_result=FDQueryMethods.get_detail(arg=arg, **kwargs)
    result = result_to_text(raw_result, **kwargs)
    if result and "accept" in raw_result:
        raw_result["accept"]()
    if not result and retry:
        search_result = FDQueryMethods.search(arg=arg, **kwargs)
        if search_result.get("result", False) and search_result.get("data", []):
            result = f"可能的料号：{search_result["data"][0].split()[-1]}\n{查(search_result["data"][0].split()[-1], False,**kwargs)}"
    if not result and len(arg.strip())==5:
        micron_kwargs=kwargs.copy()
        micron_kwargs["url"]=None
        micron_result=FDQueryMethods.parse_micron_pn(arg.strip(), **micron_kwargs)        
        if micron_result.get("result", False) and micron_result.get("data", {}).get("part-number", ""):
            if "accept" in micron_result:
                micron_result["accept"]()
            result = f"镁光料号：{micron_result.get('data', {}).get('part-number', '')}\n{查(micron_result.get('data', {}).get('part-number', ''), False,**kwargs)}"
        else: result = f"未知料号：{micron_result.get('error', '未知错误')}"
    if not result:
        if all_numbers_alpha(arg):
            result = "无结果"
    return result

def 搜(arg: str,**kwargs) -> str:
    # 转换为小写进行处理，确保不区分大小写
    arg = arg.lower()
    raw_result = FDQueryMethods.search(arg,**kwargs)
    result = result_to_text(raw_result, **kwargs)
    if not result:
        if all_numbers_alpha(arg):
            result = "无结果"
    return result



def 查DRAM(arg: str, **kwargs) -> str:
    # 转换为小写进行处理，确保不区分大小写
    arg = arg.lower()
    raw_result=FDQueryMethods.get_dram_detail(arg=arg, **kwargs)
    result = result_to_text(raw_result, **kwargs)
    if result and "accept" in raw_result:
        raw_result["accept"]()
    if not result:
        result = "无结果"
    return result



def micron_handler(arg: str, debug: bool=False, **kwargs):
    # 转换为小写进行处理，确保不区分大小写
    arg = arg.lower()
    
    # 调用parse_micron_pn函数解析料号
    result = FDQueryMethods.parse_micron_pn(arg, **kwargs)
    
    # 如果查询成功，调用accept()方法保存到数据库
    if result.get("result", False) and "accept" in result:
        result["accept"]()
    
    # 检查并返回part-number
    if "data" in result :
        return f"完整料号: {result['data']['part-number']}"
    else:
        error_msg = result.get("error", "解析失败，未找到料号信息" if not debug else str(result))
        return error_msg


def phison_handler(arg: str, debug: bool=False, **kwargs):
    # 转换为大写进行处理，确保不区分大小写
    arg = arg.upper()
    
    # 调用parse_phison_pn函数解析料号
    raw_result = FDQueryMethods.parse_phison_pn(arg, **kwargs)
    
    result=result_to_text(raw_result, **kwargs)
    if not result :
        result = raw_result.get("error", "无结果" if not debug else str(raw_result))
    return result


def get_message_result(message: str) -> str:
    try:
        
        # 如果有参数且长度超过72，则返回错误信息
        if len(message) > 72:
            return "查询参数过长，请输入不超过72个字符"
        args = message.split("--")
        args = [arg.strip() for arg in args]
        message=args[0]
        refresh_flag=True if "refresh" in args else None
        debug_flag=True if "debug" in args else None
        save_flag=True if "save" in args else False if "nosave" in args else None
        local_flag=True if "local" in args else False if "online" in args else None
        if(debug_flag):
            print(args)
        count="".join([(arg.split("=")[-1].strip() if arg.startswith("count") else "") for arg in args])
        count=10 if not count else int(count)

        url="".join([(arg.split("=")[-1].strip() if arg.startswith("url") else "") for arg in args])
        if url:
            url=url.strip().strip("/")
        else:
            url=None

        result = ""
        # 处理DRAM查询指令（支持大小写不敏感）
        # 创建基础参数字典
        kwargs = {}
        if refresh_flag is not None:
            kwargs["refresh"] = refresh_flag
        if debug_flag is not None:
            kwargs["debug"] = debug_flag
        if save_flag is not None:
            kwargs["save"] = save_flag
        if local_flag is not None:
            kwargs["local"] = local_flag
        if url is not None:
            kwargs["url"] = url

        if message.lower().startswith("/micron"):
            result = micron_handler(message[7:].strip(), **kwargs)
        elif message.lower().startswith("/phison"):
            result = phison_handler(message[7:].strip(), **kwargs)
        elif message.lower().startswith("dram"):
            result = 查DRAM(message[5:].strip(), **kwargs)
        elif message.lower().startswith("查dram"):
            result = 查DRAM(message[6:].strip(), **kwargs)
        elif message.lower().startswith(("id")):
            result = ID(message[2:].strip(), **kwargs)
        elif message.startswith(("查")):
            result = 查(message[1:].strip(), **kwargs) 
        elif message.startswith(("搜")):
            result = 搜(message[1:].strip(),**kwargs)
        else:
            result = "未知命令(请使用/help获取帮助)"
        output = False if "nooutput" in args else True
        return result if output else ""
    except Exception as e:
        return f"处理错误：{str(e)}"

def instance():
    print("命令行模式：支持 查/搜/ID/查DRAM 指令，也可使用 /help 查看帮助（exit退出）")
    while True:
        try:
            message = input("> ")
            if message.lower() == "exit":
                break
            print(get_message_result(message))
        except Exception as e:
            print(f"错误：{e}")


if __name__ == "__main__":
    if 'plugin_config' not in globals():
        from .FDConfig import Config

        # 不传递路径参数，让Config内部处理正确的配置文件路径
        plugin_config = Config.from_file()
    instance()

# reload
# reload
