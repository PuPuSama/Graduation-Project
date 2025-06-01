import time
import tts
import requests
import json
import re
from config import config
from play import play
from loguru import logger
# 导入聊天服务模块
import chat

flag = 0
city = "北京"  # 默认城市

# 天气API配置
WEATHER_API_KEY = "8cc15e673ddf4380a6e28af8a13bec05"  # API密钥
WEATHER_API_URL = "https://nt4qbhaetu.re.qweatherapi.com/v7/weather/now"  # 天气信息API URL
CITY_LOOKUP_URL = "https://nt4qbhaetu.re.qweatherapi.com/geo/v2/city/lookup"  # 城市查询API URL

def timedetect(text):
    global flag, city
    
    # 清理文本，去除标点符号
    clean_text = text.replace('。', '').replace('，', '').replace('？', '').replace('!', '').replace('！', '')
    
    # 时间查询关键词列表
    time_keywords = [
        '时间', '几点了', '现在几点了', '当前时间', '现在的时间', 
        '现在时间', '现在几点', '几点钟了', '几点钟', '时间是',
        '报时', '现在是什么时间', '告诉我时间', '告诉我几点了'
    ]
    
    # 日期查询关键词列表
    date_keywords = [
        '日期', '今天是几号', '今天的日期', '今天几号', '今天日期',
        '几月几号', '今天是什么日期', '几号了', '日期是', '今天是',
        '日历', '告诉我日期', '告诉我今天日期', '今天几月几号'
    ]
    
    # 天气查询关键词列表
    weather_keywords = [
        '天气', '天气怎么样', '天气如何', '查询天气', '今天天气', 
        '天气情况', '天气预报', '今日天气', '现在天气', '今天的天气',
        '外面天气', '今天气温', '天气好吗'
    ]
    
    # 出行建议关键词列表
    travel_advice_keywords = [
        '出行建议', '穿什么', '怎么穿', '出门注意', '今天适合出门吗',
        '今天穿什么', '出行提示', '需要带伞吗', '需要外套吗', '出门准备',
        '今天出门', '出门穿什么', '穿衣建议', '出门要带伞吗', '怎么出行'
    ]
    
    # 检查时间查询意图
    for keyword in time_keywords:
        if keyword in clean_text:
            logger.info('detected keyword time')
            flag = 1
            return True
    
    # 检查日期查询意图
    for keyword in date_keywords:
        if keyword in clean_text:
            logger.info('detected keyword date')
            flag = 2
            return True
    
    # 检查天气查询意图
    for keyword in weather_keywords:
        if keyword in clean_text:
            logger.info('detected keyword weather')
            flag = 3
            # 尝试提取城市名
            extract_city(clean_text)
            return True
            
    # 检查出行建议意图
    for keyword in travel_advice_keywords:
        if keyword in clean_text:
            logger.info('detected keyword travel advice')
            flag = 4
            # 尝试提取城市名
            extract_city(clean_text)
            return True
            
    return False

def extract_city(text):
    """从文本中提取城市名称"""
    global city
    
    # 城市名提取模式
    city_pattern = r'(.+?)的天气'
    match = re.search(city_pattern, text)
    if match:
        extracted_city = match.group(1)
        if len(extracted_city) < 10 and len(extracted_city) > 1:
            city = extracted_city
            logger.info(f'detected city: {city}')
            return
    
    # 备用方式：寻找以"的"结尾的词
    for word in text.split():
        if word.endswith("的") and len(word) > 1:
            potential_city = word[:-1]  # 去掉"的"字
            if len(potential_city) < 10:
                city = potential_city
                logger.info(f'detected city: {city}')
                return

def get_city_id(city_name):
    """
    通过API查询城市ID
    
    参数:
        city_name (str): 城市名称
    
    返回:
        str: 城市ID，如果查询失败则返回北京的ID
    """
    try:
        # 构建查询参数
        params = {
            'key': WEATHER_API_KEY,
            'location': city_name
        }
        
        # 发送请求
        response = requests.get(CITY_LOOKUP_URL, params=params)
        
        # 检查响应状态
        if response.status_code == 200:
            data = response.json()
            
            # 检查API响应是否成功
            if 'code' in data and data['code'] == '200' and 'location' in data and len(data['location']) > 0:
                # 获取第一个匹配结果的ID
                city_id = data['location'][0]['id']
                logger.info(f"成功获取城市ID: {city_id} (城市: {city_name})")
                return city_id
            else:
                logger.warning(f"未找到城市 '{city_name}' 的ID，使用默认ID")
                return "101010100"  # 默认使用北京ID
        else:
            logger.error(f"查询城市ID失败: HTTP {response.status_code}")
            return "101010100"  # 默认使用北京ID
            
    except Exception as e:
        logger.error(f"查询城市ID时出错: {e}")
        return "101010100"  # 默认使用北京ID

def get_weather(city_name):
    """获取指定城市的天气信息"""
    try:
        # 首先获取城市ID
        city_id = get_city_id(city_name)
        
        # API参数
        params = {
            'key': WEATHER_API_KEY,
            'location': city_id
        }
        
        # 发送请求
        response = requests.get(WEATHER_API_URL, params=params)
        
        # 检查响应状态码
        if response.status_code == 200:
            data = response.json()
            
            # 检查API响应是否成功
            if 'code' in data and data['code'] == '200' and 'now' in data:
                now_data = data['now']
                
                weather_info = {
                    'city': city_name,  # 使用请求的城市名，而不是API返回的名称
                    'temperature': now_data.get('temp', 'N/A'),
                    'feels_like': now_data.get('feelsLike', 'N/A'),
                    'condition': now_data.get('text', 'N/A'),
                    'humidity': now_data.get('humidity', 'N/A'),
                    'wind_dir': now_data.get('windDir', 'N/A'),
                    'wind_scale': now_data.get('windScale', 'N/A'),
                    'precip': now_data.get('precip', '0')
                }
                
                return weather_info
            else:
                logger.error(f"天气API返回错误: {data.get('code', 'N/A')}")
                return None
        else:
            logger.error(f"天气API请求失败: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"获取天气信息时出错: {e}")
        return None

def notifytime():
    tts.ssml_save(f"当前时间:{time.strftime('%H:%M', time.localtime())}",'Sound/timenotify.raw')
    config.set(notify_enable=True)
    play('Sound/ding.wav')
    play('Sound/timenotify.raw')
    config.set(notify_enable=False)
    
    # 修改: 直接调用chat的hwcallback函数
    chat.hwcallback()
    logger.info("时间通知结束，已触发对话激活")

def notifydate():
    tts.ssml_save(f"今天的日期:{time.strftime('%m月%d号', time.localtime())}",'Sound/timenotify.raw')
    config.set(notify_enable=True)
    play('Sound/ding.wav')
    play('Sound/timenotify.raw')
    config.set(notify_enable=False)
    
    # 修改: 直接调用chat的hwcallback函数
    chat.hwcallback()
    logger.info("日期通知结束，已触发对话激活")

def notifyweather():
    """通知当前天气情况"""
    global city
    
    weather_info = get_weather(city)
    if weather_info:
        # 构建天气播报文本
        weather_text = f"{weather_info['city']}当前天气{weather_info['condition']}，"
        weather_text += f"温度{weather_info['temperature']}度，"
        weather_text += f"体感温度{weather_info['feels_like']}度，"
        weather_text += f"湿度{weather_info['humidity']}%，"
        weather_text += f"{weather_info['wind_dir']}{weather_info['wind_scale']}级"
        
        # 如果有降水，添加降水信息
        if float(weather_info['precip']) > 0:
            weather_text += f"，降水量{weather_info['precip']}毫米"
        
        # 更新answer变量，使前端能看到天气信息
        config.set(answer=weather_text)
        
        # 保存并播放语音
        tts.ssml_save(weather_text, 'Sound/weathernotify.raw')
        config.set(notify_enable=True)
        play('Sound/ding.wav')
        play('Sound/weathernotify.raw')
        config.set(notify_enable=False)
        
        # 天气播报完成后触发对话激活
        try:
            chat.hwcallback()
        except Exception as e:
            logger.error(f"调用hwcallback出错: {e}")
            # 即使出错也不中断流程
        
        logger.info("天气通知结束，已触发对话激活")
    else:
        error_text = f"抱歉，无法获取{city}的天气信息"
        
        # 更新answer变量，使前端显示错误信息
        config.set(answer=error_text)
        
        # 保存并播放错误语音
        tts.ssml_save(error_text, 'Sound/weathernotify.raw')
        config.set(notify_enable=True)
        play('Sound/ding.wav')
        play('Sound/weathernotify.raw')
        config.set(notify_enable=False)
        
        # 错误提示后触发对话激活
        try:
            chat.hwcallback()
        except Exception as e:
            logger.error(f"调用hwcallback出错: {e}")
            # 即使出错也不中断流程
        
        logger.info("天气通知结束，已触发对话激活")

def notifytraveladvice():
    """提供出行建议"""
    global city
    
    # 获取天气信息
    weather_info = get_weather(city)
    if weather_info:
        # 构建提示文本
        prompt = f"基于以下气象数据，以口语化的方式给出今日出门建议：\n"
        prompt += f"城市：{weather_info['city']}\n"
        prompt += f"户外状况：{weather_info['condition']}\n"
        prompt += f"气温：{weather_info['temperature']}°C\n"
        prompt += f"体感温度：{weather_info['feels_like']}°C\n"
        prompt += f"空气湿度：{weather_info['humidity']}%\n"
        prompt += f"风向：{weather_info['wind_dir']}\n"
        prompt += f"风力等级：{weather_info['wind_scale']}级\n"
        
        if float(weather_info['precip']) > 0:
            prompt += f"降水量：{weather_info['precip']}毫米\n"
            
        prompt += "请给出穿着、交通方式、是否携带雨具等方面的建议。作为语音助手回答，语气自然，不要分点，控制在100字以内。"
        
        # 更新answer变量，告知用户正在生成建议
        processing_text = f"正在为您生成{weather_info['city']}的出行建议..."
        config.set(answer=processing_text)
        
        # 播放处理提示音
        tts.ssml_save(processing_text, 'Sound/generating.raw')
        config.set(notify_enable=True)
        play('Sound/ding.wav')
        play('Sound/generating.raw')
        config.set(notify_enable=False)
        
        # 设置命令，让大模型生成出行建议
        config.set(command=prompt)
        
        logger.info(f"已发送出行建议请求，城市: {city}")
    else:
        error_text = f"抱歉，无法获取{city}的天气信息，无法提供出行建议"
        
        # 更新answer变量，使前端显示错误信息
        config.set(answer=error_text)
        
        # 保存并播放错误语音
        tts.ssml_save(error_text, 'Sound/weathernotify.raw')
        config.set(notify_enable=True)
        play('Sound/ding.wav')
        play('Sound/weathernotify.raw')
        config.set(notify_enable=False)
        
        # 错误提示后触发对话激活
        try:
            chat.hwcallback()
        except Exception as e:
            logger.error(f"调用hwcallback出错: {e}")
            # 即使出错也不中断流程
        
        logger.info("出行建议请求失败，已触发对话激活")

def admin():
    global flag
    while(1):
        if flag == 1:
            notifytime()
            flag = 0
        if flag == 2:
            notifydate()
            flag = 0
        if flag == 3:
            notifyweather()
            flag = 0
        if flag == 4:
            notifytraveladvice()
            flag = 0
        time.sleep(1)

