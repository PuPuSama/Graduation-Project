#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PI-Assistant 服务器模块
负责Web接口、线程管理和系统协调
"""

import sys
import os
import signal
import time
from loguru import logger
# 优化日志配置，减少I/O操作
logger.remove()
logger.add(sys.stdout, colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}", level="INFO")
# 增加日志轮转大小，减少文件I/O，提高日志级别到WARNING减少信息日志
logger.add('Log/PI-Assistant.log', rotation="10 MB", compression="zip", colorize=False, 
           format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {file}:{line} - <level>{message}</level>", 
           level="WARNING")  # 将INFO改为WARNING减少日志量

from flask import request, Flask, jsonify, render_template
import arcade
from threading import Thread, Lock
import chat
from config import config
from const_config import gpio_wake_enable
import if_time_and_weather
import tts
from play import play
# 导入MQTT管理模块，替代直接导入MQTTSensorClient
import mqtt_manager
# 导入火灾预警系统
import fire_alarm

# 禁用Flask的调试日志
import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# 全局变量
notifyplayer = None
notifysound = None

# 语音文件缓存配置
SOUND_DIR = "Sound"  # 语音文件目录
# 整点报时语音缓存
HOUR_VOICE_CACHE = {}  # 用于缓存不同小时的报时语音


def ensure_sound_dir():
    """确保语音文件目录存在"""
    if not os.path.exists(SOUND_DIR):
        os.makedirs(SOUND_DIR)
        logger.debug(f"创建语音文件目录: {SOUND_DIR}")

def get_hour_voice_file(hour):
    """获取指定小时的整点报时语音文件，如果不存在则生成"""
    # 标准化小时，使用12小时制
    display_hour = hour if hour < 13 else hour - 12
    
    # 构建文件名
    file_name = f"hour_{hour}.wav"
    file_path = os.path.join(SOUND_DIR, file_name)
    
    # 如果文件不存在，则生成
    if not os.path.exists(file_path):
        logger.info(f"整点报时语音文件 {file_path} 不存在，正在生成...")
        words = f'整点报时,已经{display_hour}点啦'
        try:
            tts.ssml_wav(words, file_path)
            logger.info(f"整点报时语音文件 {file_path} 已生成")
        except Exception as e:
            logger.error(f"生成整点报时语音文件失败: {e}")
            return None
    
    return file_path

app = Flask('PI-Assistant')

@app.route('/')
def index():
    """主页 - 使用新的统一界面"""
    editable_config = {k: config.params[k] for k in config.allow_params if k in config.params}
    return render_template('index.html', config=editable_config)

@app.route('/update_config', methods=['POST'])
def update_config():
    """更新配置参数"""
    data = request.json
    for key, value in data.items():
        # 转换为合适的数据类型
        if isinstance(value, str):
            if value.lower() == 'true':
                value = True
            elif value.lower() == 'false':
                value = False
            elif value.isdigit():
                value = int(value)
            else:
                try:
                    value = float(value)
                except ValueError:
                    pass
        config.set(**{key: value})
    return jsonify(success=True)

last_answer = None

@app.route('/get_answer', methods=['GET'])
def get_answer():
    """获取最新的助手回复"""
    global last_answer
    current_answer = config.params.get('answer', '')
    # 检查答案是否有变化
    if current_answer != last_answer:
        last_answer = current_answer
        return jsonify(answer=current_answer)
    else:
        return jsonify(answer=None)

quick_commands = ["wake", "终止程序"]

@app.route('/get_quick_commands', methods=['GET'])
def get_quick_commands():
    """获取快捷命令列表"""
    return jsonify(quick_commands)

@app.route('/add_quick_command', methods=['POST'])
def add_quick_command():
    """添加新的快捷命令"""
    command = request.json.get('command')
    if command and command not in quick_commands:
        quick_commands.append(command)
        return jsonify(success=True)
    return jsonify(success=False)

@app.route('/remove_quick_command', methods=['POST'])
def remove_quick_command():
    """删除快捷命令"""
    index = request.json.get('index')
    if 0 <= index < len(quick_commands):
        del quick_commands[index]
        return jsonify(success=True)
    return jsonify(success=False)

@app.route('/command')
def what():
    """接收命令"""
    words = request.args.get('words')
    config.set(command=words)
    return 'ok'

@app.route('/api/sensor_data')
def get_sensor_data():
    """获取传感器数据API - 简化版，直接读取传感器数据"""
    current_time = time.time()
    
    # 获取传感器数据
    sensor_data = mqtt_manager.get_sensor_data()
    
    return jsonify(sensor_data)

@app.route('/api/device_status')
def get_device_status():
    """获取设备状态API"""
    device_status = mqtt_manager.get_device_status()
    
    return jsonify(device_status)

@app.route('/api/control_device', methods=['POST'])
def control_device():
    """控制设备API"""
    data = request.json
    if not data:
        return jsonify({"error": "无效的请求数据"}), 400
        
    device = data.get('device')
    state = data.get('state')
    
    if device is None or state is None:
        return jsonify({"error": "缺少必要参数"}), 400
    
    if device not in ['led', 'buzzer']:
        return jsonify({"error": "不支持的设备类型"}), 400
    
    if device == 'led':
        mqtt_manager.control_led(state)
        logger.debug(f"控制LED: {state}")
    elif device == 'buzzer':
        mqtt_manager.control_buzzer(state)
        logger.debug(f"控制蜂鸣器: {state}")
    
    return jsonify({"success": True, "device": device, "state": state})

@app.route('/api/fire_alarm_status')
def get_fire_alarm_status():
    """获取火灾预警系统状态"""
    system = fire_alarm.get_fire_alarm_system()
    
    status = {
        "running": system.running,
        "connected": system.connected,
        "flame_detected": system.flame_detected,
        "smoke_detected": system.smoke_detected,
        "last_alarm_time": system.last_alarm_time
    }
    
    return jsonify(status)

def signal_handler(sig, frame):
    """处理程序退出信号"""
    logger.info('正在关闭系统...')
    # 停止MQTT客户端
    mqtt_manager.stop_mqtt_client()
    
    # 停止火灾预警系统
    fire_alarm_system = fire_alarm.get_fire_alarm_system()
    if fire_alarm_system:
        fire_alarm_system.stop()
    
    logger.info('系统已安全关闭')
    os._exit(0)

def admin():
    """管理定时任务和通知"""
    global notifyplayer, notifysound
    last_time = None
    times = 0
    
    # 确保语音文件目录存在
    ensure_sound_dir()
    
    # 记录上次整点报时日志的日期
    last_timenotify_log_day = None
    
    while True:
        if notifyplayer and notifysound and notifysound.is_playing(notifyplayer):
            if notifysound.is_complete(notifyplayer): 
                config.set(notify_enable=False)
                try:
                    notifysound.stop(notifyplayer)
                except:
                    pass
                times = 0
            else:
                times = times + 1
                if times >= 8:
                    config.set(notify_enable=False)
                    try:
                        notifysound.stop(notifyplayer)
                    except:
                        pass
                    times = 0

        if time.localtime()[4] == 0 and config.get("timenotify") is True:
            current_hour = time.localtime()[3]
            current_day = time.localtime()[2]  # 当前日期
            
            if last_time != current_hour:
                # 只在每天第一次整点报时时记录日志，减少重复日志
                if last_timenotify_log_day != current_day:
                    logger.info(f'整点报时 ({current_hour}:00)')
                    last_timenotify_log_day = current_day
                else:
                    logger.debug(f'整点报时 ({current_hour}:00)')
                
                try:
                    # 获取或生成整点报时语音文件
                    hour_voice_file = get_hour_voice_file(current_hour)
                    
                    if hour_voice_file and os.path.exists(hour_voice_file):
                        if config.get("chat_enable") is False and config.get("notify_enable") is False:
                            config.set(notify_enable=True)
                            play('Sound/ding.wav')
                            notifysound = arcade.Sound(hour_voice_file)
                            notifyplayer = notifysound.play()
                    else:
                        # 如果语音文件不存在，使用旧方法
                        words = f'整点报时,已经{current_hour if current_hour<13 else current_hour-12}点啦'
                        tts.ssml_wav(words, 'Sound/notify.wav')
                        if config.get("chat_enable") is False and config.get("notify_enable") is False:
                            config.set(notify_enable=True)
                            play('Sound/ding.wav')
                            notifysound = arcade.Sound('Sound/notify.wav')
                            notifyplayer = notifysound.play()
                except Exception as e:
                    logger.warning(f"整点报时出错: {e}")
                    if config.get("chat_enable") is False and config.get("notify_enable") is False:
                        play('Sound/ding.wav')
                        play('Sound/notifytime.wav')
                
                last_time = current_hour

        # 增加睡眠时间，减少CPU使用率
        time.sleep(5)  # 从2秒增加到5秒

if __name__ == '__main__':
  
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动聊天服务
    t = Thread(target=chat.startchat)
    t.daemon = True  # 设置为守护线程
    t.start()
    logger.info('聊天服务已启动')
    
    # 启动管理线程
    t2 = Thread(target=admin)
    t2.daemon = True  # 设置为守护线程
    t2.start()
     
    # 启动时间和天气服务
    t5 = Thread(target=if_time_and_weather.admin)
    t5.daemon = True  # 设置为守护线程
    t5.start()
    
    # 启动MQTT传感器客户端
    mqtt_manager.get_mqtt_client()
    
    # 启动火灾预警系统
    fire_alarm_system = fire_alarm.start_fire_alarm_system()
    logger.info('火灾预警系统已启动')
    
    # 初始化LED控制器
    try:
        import led_control
        led = led_control.get_led_controller()
        logger.info('LED控制器已初始化')
    except Exception as e:
        logger.error(f"初始化LED控制器失败: {e}")
    
    logger.info('系统启动完成，PI-Assistant正在运行')
    
    # 启动Flask服务器
    app.run(host='0.0.0.0', threaded=True)  # 使用线程模式提高并发性能