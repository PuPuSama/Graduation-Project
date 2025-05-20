
"""
Azure语音识别模块
用于将语音文件转换为文本，使用Microsoft Azure的语音识别服务
"""

import json
import time
import requests
from loguru import logger
from const_config import azure_key

# Azure语音识别服务配置
AZURE_STT_URL = 'https://eastasia.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1'
DEFAULT_LANGUAGE = 'zh-CN'
DEFAULT_AUDIO_FILE = 'Sound/question.wav'
REQUEST_TIMEOUT = 12  # 请求超时时间(秒)
MAX_RETRIES = 2       # 最大重试次数

def recognize(audio_file=DEFAULT_AUDIO_FILE, language=DEFAULT_LANGUAGE):
    """
    将语音文件发送到Azure进行语音识别
    
    参数:
        audio_file: 要识别的音频文件路径
        language: 识别语言，默认为中文
    
    返回:
        识别的文本字符串，如果识别失败则返回空字符串
    """
    # 构建请求URL和头信息
    url = f"{AZURE_STT_URL}?language={language}"
    headers = {
        'Accept': 'application/json;text/xml',
        'Content-Type': "audio/wav; codecs=audio/pcm; samplerate=16000",
        'Ocp-Apim-Subscription-Key': azure_key
    }
    
    # 创建会话并发送请求
    session = requests.session()
    
    try:
        # 读取音频文件
        with open(audio_file, 'rb') as f:
            # 重试机制
            for attempt in range(MAX_RETRIES):
                try:
                    logger.debug(f"发送语音识别请求(尝试 {attempt+1}/{MAX_RETRIES})")
                    response = session.post(
                        url, 
                        headers=headers, 
                        data=f, 
                        timeout=REQUEST_TIMEOUT
                    )
                    response.raise_for_status()  # 检查HTTP错误
                    break
                except requests.exceptions.RequestException as e:
                    logger.warning(f"请求失败: {e}")
                    if attempt < MAX_RETRIES - 1:  # 不是最后一次尝试
                        wait_time = 3 * (attempt + 1)  # 逐步增加等待时间
                        logger.info(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                    else:
                        logger.error("所有重试尝试均失败")
                        return ""
    except FileNotFoundError:
        logger.error(f"找不到音频文件: {audio_file}")
        return ""
    except Exception as e:
        logger.error(f"读取音频文件时出错: {e}")
        return ""
    
    # 处理响应
    try:
        # 解析JSON响应
        result_json = response.json()
        logger.debug(f"识别响应: {result_json}")
        
        # 提取识别文本
        recognized_text = result_json.get('DisplayText', '')
        return recognized_text
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"解析响应失败: {e}")
        logger.debug(f"原始响应: {response.text}")
        return ""
    except Exception as e:
        logger.error(f"处理响应时出错: {e}")
        return ""

if __name__ == "__main__":
    # 测试代码
    result = recognize()
    print(f"识别结果: '{result}'")




