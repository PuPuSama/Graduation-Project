# coding=utf-8
import hashlib
import time
import xml.etree.ElementTree as ET
from flask import Flask, request, make_response
from loguru import logger

app = Flask(__name__)

# 微信公众号配置信息 - 从微信公众平台获取
TOKEN = "your_token"  # 这是您在微信公众平台设置的Token

@app.route('/wechat', methods=['GET', 'POST'])
def wechat_handler():
    """处理微信服务器的请求"""
    # 1. 处理微信服务器的验证请求
    if request.method == 'GET':
        # 微信服务器验证时会发送签名(signature)、时间戳(timestamp)、随机数(nonce)和确认字符串(echostr)
        signature = request.args.get('signature', '')
        timestamp = request.args.get('timestamp', '')
        nonce = request.args.get('nonce', '')
        echostr = request.args.get('echostr', '')
        
        # 验证签名
        if check_signature(signature, timestamp, nonce):
            logger.info("微信验证成功")
            return echostr
        else:
            logger.warning("微信验证失败")
            return "Verification failed", 403
    
    # 2. 处理用户发送的消息
    if request.method == 'POST':
        # 获取XML数据
        xml_data = request.data
        logger.debug(f"收到微信消息: {xml_data}")
        
        # 解析XML
        xml_dict = parse_xml(xml_data)
        logger.info(f"解析后的消息: {xml_dict}")
        
        # 提取消息信息
        msg_type = xml_dict.get('MsgType')
        from_user = xml_dict.get('FromUserName')
        to_user = xml_dict.get('ToUserName')
        
        # 记录所有接收到的消息（测试用）
        logger.info(f"收到消息类型: {msg_type}, 发送者: {from_user}")
        
        # 处理文本消息
        if msg_type == 'text':
            content = xml_dict.get('Content', '')
            logger.info(f"收到文本消息: {content}")
            
            # 简单回复，告知用户消息已收到
            reply_content = f"已收到您的消息: {content}"
            return create_reply(to_user, from_user, reply_content)
        
        # 对于其他类型的消息，简单回复
        return create_reply(to_user, from_user, f"收到了您的{msg_type}类型消息")

def check_signature(signature, timestamp, nonce):
    """验证微信签名"""
    # 排序
    temp_list = [TOKEN, timestamp, nonce]
    temp_list.sort()
    # 拼接字符串
    temp_str = ''.join(temp_list)
    # SHA1加密
    hash_obj = hashlib.sha1(temp_str.encode('utf-8'))
    # 获取加密结果
    calc_signature = hash_obj.hexdigest()
    # 比对签名
    return calc_signature == signature

def parse_xml(xml_data):
    """解析微信XML消息为字典"""
    try:
        # 解析XML
        root = ET.fromstring(xml_data)
        xml_dict = {}
        # 遍历所有子节点
        for child in root:
            xml_dict[child.tag] = child.text
        return xml_dict
    except Exception as e:
        logger.error(f"解析XML出错: {e}")
        return {}

def create_reply(to_user, from_user, content):
    """创建回复消息"""
    # 当前时间戳
    timestamp = int(time.time())
    # 构建回复XML
    reply_xml = f"""
    <xml>
        <ToUserName><![CDATA[{to_user}]]></ToUserName>
        <FromUserName><![CDATA[{from_user}]]></FromUserName>
        <CreateTime>{timestamp}</CreateTime>
        <MsgType><![CDATA[text]]></MsgType>
        <Content><![CDATA[{content}]]></Content>
    </xml>
    """
    # 创建响应
    response = make_response(reply_xml)
    response.content_type = 'application/xml'
    return response

if __name__ == '__main__':
    # 启动服务器
    logger.info("启动微信公众号消息处理服务器...")
    # 监听所有网络接口的8080端口
    app.run(host='0.0.0.0', port=8080, debug=True)