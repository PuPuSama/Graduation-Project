#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LED语音控制模块
用于处理与LED相关的语音命令，包括模糊控制
"""

import re
import sys
import os
import mqtt_manager
from loguru import logger
from config import config
from tts import ssml_save
from play import play

# 配置日志
logger.add("Log/led_voice_control.log", rotation="10 MB", compression="zip", level="INFO")

# LED控制关键词
LED_ON_KEYWORDS = [
    '开灯', '打开灯', '开启灯', '打开电灯', '开启电灯', '把灯打开', '把灯开了',
    '灯开', '开个灯', '把灯开起来', '打开一下灯', '开一下灯', '灯亮', '亮灯'
]

LED_OFF_KEYWORDS = [
    '关灯', '关闭灯', '熄灯', '关掉灯', '把灯关了', '把灯关掉', '关闭电灯',
    '灯关', '关一下灯', '把灯关上', '关掉电灯', '熄掉灯', '灯灭'
]

LED_BRIGHTNESS_UP_KEYWORDS = [
    '灯亮一点', '灯亮点', '亮一点', '亮度高一点', '亮度大一点', '灯光亮一点',
    '灯光亮点', '灯光亮些', '提高亮度', '增加亮度', '灯太暗', '灯光太暗',
    '亮度太低', '灯不够亮', '灯光不够亮', '灯暗了', '灯变暗了', '太暗了',
    '看不清', '看不清楚', '亮度不够', '光线不足', '光线太暗', '不够亮'
]

LED_BRIGHTNESS_DOWN_KEYWORDS = [
    '灯暗一点', '灯暗点', '暗一点', '亮度低一点', '亮度小一点', '灯光暗一点',
    '灯光暗点', '灯光暗些', '降低亮度', '减小亮度', '灯太亮', '灯光太亮',
    '亮度太高', '灯太刺眼', '灯光太刺眼', '灯亮了', '灯变亮了', '太亮了',
    '刺眼', '亮度太高', '光线太强', '光线刺眼', '亮得刺眼', '太刺眼'
]

LED_BLINK_KEYWORDS = [
    '灯闪', '闪灯', '灯闪烁', '闪烁', '灯闪一下', '灯闪烁一下', '让灯闪烁',
    '灯光闪烁', '闪一闪', '闪一下灯', '灯光闪一下', '灯闪亮', '灯光闪亮'
]

def process_led_command(text):
    """
    处理LED相关的语音命令
    
    参数:
        text: 语音识别的文本
    
    返回:
        处理结果消息
    """
    if not text:
        return None
    
    # 转换为小写并去除标点符号，便于匹配
    clean_text = text.lower().replace('。', '').replace('，', '').replace('？', '').replace('!', '').replace('！', '')
    
    # 检查是否包含LED控制关键词
    if any(keyword in clean_text for keyword in LED_ON_KEYWORDS):
        return handle_led_on(clean_text)
    
    elif any(keyword in clean_text for keyword in LED_OFF_KEYWORDS):
        return handle_led_off()
    
    elif any(keyword in clean_text for keyword in LED_BRIGHTNESS_UP_KEYWORDS):
        return handle_led_brightness_up(clean_text)
    
    elif any(keyword in clean_text for keyword in LED_BRIGHTNESS_DOWN_KEYWORDS):
        return handle_led_brightness_down(clean_text)
    
    elif any(keyword in clean_text for keyword in LED_BLINK_KEYWORDS):
        return handle_led_blink(clean_text)
    
    # 没有匹配到LED控制关键词
    return None

def handle_led_on(text):
    """处理开灯命令"""
    # 尝试从文本中提取亮度信息
    brightness = None
    
    # 匹配百分比亮度，支持多种格式如"开灯，亮度50%"、"亮度设置为60%"等
    percent_match = re.search(r'亮度.*?(\d+)(\s*%)?', text)
    if percent_match:
        brightness = int(percent_match.group(1))
        brightness = max(1, min(100, brightness))  # 确保亮度在1-100范围内
    
    # 匹配描述性亮度，如"开灯，亮度高一点"
    elif '亮度高' in text or '亮度大' in text or '亮一点' in text:
        brightness = 80
    elif '亮度中' in text or '中等亮度' in text:
        brightness = 50
    elif '亮度低' in text or '亮度小' in text or '暗一点' in text:
        brightness = 30
    
    # 执行开灯操作
    if brightness is not None:
        mqtt_manager.adjust_led_brightness(brightness=brightness)
        response = f"好的，已开灯，亮度设置为{brightness}%"
    else:
        mqtt_manager.control_led(True)
        response = "好的，已开灯"
    
    # 播放语音反馈
    speak_response(response)
    return response

def handle_led_off():
    """处理关灯命令"""
    mqtt_manager.control_led(False)
    response = "好的，已关灯"
    
    # 播放语音反馈
    speak_response(response)
    return response

def handle_led_brightness_up(text):
    """处理增加亮度命令"""
    # 获取当前LED状态
    led_controller = mqtt_manager.get_led_controller()
    
    # 如果LED当前是关闭状态，则开启它
    if not led_controller.is_on:
        mqtt_manager.control_led(True)
    
    # 尝试从文本中提取亮度增加的幅度
    step = 20  # 默认增加20%
    
    # 匹配具体数值，如"亮度增加30%"
    percent_match = re.search(r'亮度增加\s*(\d+)(\s*%)?', text)
    if percent_match:
        step = int(percent_match.group(1))
        step = max(5, min(50, step))  # 确保步长在5-50范围内
    
    # 根据描述调整步长
    elif '亮很多' in text or '亮许多' in text or '亮非常多' in text:
        step = 40
    elif '亮一点点' in text or '亮一丁点' in text or '亮一点儿' in text:
        step = 10
    
    # 执行增加亮度操作
    mqtt_manager.adjust_led_brightness(change=step)
    
    # 获取调整后的亮度
    current_brightness = led_controller.brightness
    response = f"好的，已增加亮度，当前亮度{current_brightness}%"
    
    # 播放语音反馈
    speak_response(response)
    return response

def handle_led_brightness_down(text):
    """处理降低亮度命令"""
    # 获取当前LED状态
    led_controller = mqtt_manager.get_led_controller()
    
    # 如果LED当前是关闭状态，则不执行操作
    if not led_controller.is_on:
        response = "灯已经关闭，无法降低亮度"
        speak_response(response)
        return response
    
    # 尝试从文本中提取亮度降低的幅度
    step = 20  # 默认降低20%
    
    # 匹配具体数值，如"亮度降低30%"
    percent_match = re.search(r'亮度降低\s*(\d+)(\s*%)?', text)
    if percent_match:
        step = int(percent_match.group(1))
        step = max(5, min(50, step))  # 确保步长在5-50范围内
    
    # 根据描述调整步长
    elif '暗很多' in text or '暗许多' in text or '暗非常多' in text:
        step = 40
    elif '暗一点点' in text or '暗一丁点' in text or '暗一点儿' in text:
        step = 10
    
    # 执行降低亮度操作
    mqtt_manager.adjust_led_brightness(change=-step)
    
    # 获取调整后的亮度
    current_brightness = led_controller.brightness
    response = f"好的，已降低亮度，当前亮度{current_brightness}%"
    
    # 播放语音反馈
    speak_response(response)
    return response

def handle_led_blink(text):
    """处理灯闪烁命令"""
    # 尝试从文本中提取闪烁次数
    times = 3  # 默认闪烁3次
    
    # 匹配具体数值，如"灯闪烁5次"
    times_match = re.search(r'闪烁\s*(\d+)\s*次', text)
    if times_match:
        times = int(times_match.group(1))
        times = max(1, min(10, times))  # 确保次数在1-10范围内
    
    # 执行闪烁操作
    mqtt_manager.blink_led(times, 0.3)
    response = f"好的，灯已闪烁{times}次"
    
    # 播放语音反馈
    speak_response(response)
    return response

def speak_response(text):
    """播放语音反馈"""
    # 检测是否在测试模式下运行
    is_test_mode = 'pytest' in sys.modules or os.environ.get('TESTING', '0') == '1' or os.environ.get('SKIP_AUDIO', '0') == '1'
    
    if is_test_mode:
        logger.info(f"测试模式：跳过语音播放，响应文本: {text}")
        return
    
    try:
        # 确保Sound目录存在
        os.makedirs('Sound', exist_ok=True)
        
        # 保存语音文件
        response_file = 'Sound/led_response.raw'
        ssml_save(text, response_file)
        
        # 更新前端显示
        try:
            config.set(answer=text)
        except Exception as e:
            logger.warning(f"更新前端显示时出错: {e}")
        
        # 播放语音
        try:
            config.set(notify_enable=True)
            if os.path.exists('Sound/ding.wav'):
                play('Sound/ding.wav')
            if os.path.exists(response_file):
                play(response_file)
            config.set(notify_enable=False)
        except Exception as e:
            logger.warning(f"播放语音文件时出错: {e}")
    except Exception as e:
        logger.error(f"播放语音反馈时出错: {e}")
        # 失败时不会中断程序流程

# 注册LED语音命令处理器
def register_led_voice_handler():
    """注册LED语音命令处理器"""
    try:
        # 这里可以添加将处理器注册到语音命令系统的代码
        logger.info("LED语音命令处理器已注册")
    except Exception as e:
        logger.error(f"注册LED语音命令处理器失败: {e}")

# 初始化
if __name__ == "__main__":
    # 测试LED语音命令处理
    test_commands = [
        "开灯",
        "把灯开亮一点",
        "灯太暗了，亮度增加30%",
        "灯光太亮了，暗一点",
        "关灯",
        "让灯闪烁5次"
    ]
    
    for cmd in test_commands:
        print(f"测试命令: '{cmd}'")
        result = process_led_command(cmd)
        print(f"处理结果: {result}\n") 