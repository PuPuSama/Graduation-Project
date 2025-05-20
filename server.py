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
import threading
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import arcade
import logging
from flask import request, Flask, jsonify, render_template
from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stdout, colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}", level="INFO")
logger.add('Log/PI-Assistant.log', colorize=False, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {file}:{line} - <level>{message}</level>", level="DEBUG")

# 导入项目模块
from config import config
from const_config import music_enable, schedule_enable, udp_enable, hass_demo_enable
import chat
import if_time_and_weather
import tts
from play import play
import Scene

# 根据配置导入可选模块
optional_modules = {}
if music_enable:
    import if_music
    optional_modules['music'] = if_music
if schedule_enable:
    import schedule
    optional_modules['schedule'] = schedule
if udp_enable:
    import udpserver
    optional_modules['udp'] = udpserver
if hass_demo_enable:
    import hass_light_demo
    optional_modules['hass'] = hass_light_demo

# 关闭Flask日志
logging.getLogger('werkzeug').setLevel(logging.ERROR)

class ServerManager:
    """PI-Assistant服务器管理类"""
    
    def __init__(self):
        """初始化服务器管理器"""
        # 系统状态
        self.running = False
        self.threads = {}
        self.executor = ThreadPoolExecutor(max_workers=10)
        
        # 通知相关
        self.notify_player = None
        self.notify_sound = None
        self.last_time = None
        
        # 快速命令
        self.quick_commands = ["wake", "终止程序", "下一首。"]
        
        # 答案缓存
        self.last_answer = None
        
        # 创建Flask应用
        self.app = Flask('PI-Assistant')
        self._setup_routes()
    
    def _setup_routes(self):
        """设置Flask路由"""
        
        # 主页
        @self.app.route('/')
        def index():
            editable_config = {k: config.params[k] for k in config.allow_params if k in config.params}
            return render_template('index.html', config=editable_config)
        
        # 更新配置
        @self.app.route('/update_config', methods=['POST'])
        def update_config():
            try:
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
            except Exception as e:
                logger.error(f"更新配置时出错: {e}")
                return jsonify(success=False, error=str(e)), 500
        
        # 获取答案
        @self.app.route('/get_answer', methods=['GET'])
        def get_answer():
            try:
                current_answer = config.params.get('answer', '')
                # 检查答案是否有变化
                if current_answer != self.last_answer:
                    self.last_answer = current_answer
                    return jsonify(answer=current_answer)
                else:
                    return jsonify(answer=None)
            except Exception as e:
                logger.error(f"获取答案时出错: {e}")
                return jsonify(answer=None, error=str(e)), 500
        
        # 快速命令管理
        @self.app.route('/get_quick_commands', methods=['GET'])
        def get_quick_commands():
            return jsonify(self.quick_commands)
        
        @self.app.route('/add_quick_command', methods=['POST'])
        def add_quick_command():
            try:
                command = request.json.get('command')
                if command and command not in self.quick_commands:
                    self.quick_commands.append(command)
                    return jsonify(success=True)
                return jsonify(success=False)
            except Exception as e:
                logger.error(f"添加快速命令时出错: {e}")
                return jsonify(success=False, error=str(e)), 500
        
        @self.app.route('/remove_quick_command', methods=['POST'])
        def remove_quick_command():
            try:
                index = request.json.get('index')
                if 0 <= index < len(self.quick_commands):
                    del self.quick_commands[index]
                    return jsonify(success=True)
                return jsonify(success=False)
            except Exception as e:
                logger.error(f"删除快速命令时出错: {e}")
                return jsonify(success=False, error=str(e)), 500
        
        # Cookie处理
        @self.app.route('/cookie')
        def handle_cookie():
            try:
                submit = request.args.get('cookie')
                logger.info(f"收到cookie：{submit}")
                with open('cookie.txt', 'w') as f:
                    f.write(submit)
                return 'ok'
            except Exception as e:
                logger.error(f"处理cookie时出错: {e}")
                return str(e), 500
        
        # 语音通知
        @self.app.route('/words')
        def handle_words():
            try:
                words = request.args.get('words')
                if not config.get('Noticenotify'):
                    return 'ok'
                    
                try:
                    tts.ssml_wav(words, 'Sound/notify.wav')
                except Exception as e:
                    logger.error(f"转换语音时出错: {e}")
                    play('Sound/ttserror.wav')
                    return 'ok'
                    
                # 播放通知
                if not config.get("chat_enable") and not config.get("notify_enable"):
                    config.set(notify_enable=True)
                    time.sleep(0.5)
                    play('Sound/ding.wav')
                    self.notify_sound = arcade.Sound('Sound/notify.wav')
                    self.notify_player = self.notify_sound.play()
                
                return 'ok'
            except Exception as e:
                logger.error(f"处理语音通知时出错: {e}")
                return str(e), 500
        
        # UDP通信
        @self.app.route('/get')
        def handle_udp_get():
            try:
                if udp_enable:
                    optional_modules['udp'].udp_hi()
                return 'receive'
            except Exception as e:
                logger.error(f"处理UDP请求时出错: {e}")
                return str(e), 500
        
        # 设备连接反馈
        @self.app.route('/back')
        def handle_device_back():
            try:
                play('Sound/ding.wav')
                play('Sound/devconnect.wav')
                return 'ok'
            except Exception as e:
                logger.error(f"处理设备连接反馈时出错: {e}")
                return str(e), 500
        
        # 命令处理
        @self.app.route('/command')
        def handle_command():
            try:
                words = request.args.get('words')
                config.set(command=words)
                return 'ok'
            except Exception as e:
                logger.error(f"处理命令时出错: {e}")
                return str(e), 500
                
        # 健康检查
        @self.app.route('/health')
        def health_check():
            return jsonify({
                'status': 'healthy',
                'threads': {name: thread.is_alive() for name, thread in self.threads.items()},
                'config': {
                    'chat_enable': config.get('chat_enable'),
                    'notify_enable': config.get('notify_enable')
                }
            })
    
    def _monitor_notifications(self):
        """监控通知播放状态"""
        times = 0
        
        while self.running:
            try:
                # 检查通知播放状态
                if (self.notify_player and self.notify_sound and 
                    self.notify_sound.is_playing(self.notify_player)):
                    
                    # 通知已播放完成
                    if self.notify_sound.is_complete(self.notify_player): 
                        config.set(notify_enable=False)
                        try:
                            self.notify_sound.stop(self.notify_player)
                            logger.info('通知播放停止：自动完成')
                        except Exception as e:
                            logger.warning(f'无法停止通知播放: {e}')
                        times = 0
                    else:
                        # 计算通知播放时间
                        times += 1
                        # 如果播放超过16秒（8 * 2秒），强制停止
                        if times >= 8:
                            config.set(notify_enable=False)
                            try:
                                self.notify_sound.stop(self.notify_player)
                                logger.warning('通知播放停止：超时')
                            except Exception as e:
                                logger.warning(f'无法停止超时通知: {e}')
                            times = 0
                
                # 整点报时功能
                self._handle_hourly_notification()
                
                # 休眠以减少CPU使用
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"通知监控线程错误: {e}")
                time.sleep(5)  # 错误后增加恢复时间
    
    def _handle_hourly_notification(self):
        """处理整点报时功能"""
        try:
            current_hour = time.localtime()[3]
            current_minute = time.localtime()[4]
            
            # 在整点且启用了时间通知时
            if current_minute == 0 and config.get("timenotify") is True:
                # 避免重复通知
                if self.last_time != current_hour:
                    logger.info('整点报时')
                    # 格式化小时（12小时制）
                    hour_12 = current_hour if current_hour < 13 else current_hour - 12
                    words = f'整点报时,已经{hour_12}点啦'
                    
                    try:
                        # 生成语音文件
                        tts.ssml_wav(words, 'Sound/notify.wav')
                        
                        # 如果没有其他活动，播放通知
                        if not config.get("chat_enable") and not config.get("notify_enable"):
                            config.set(notify_enable=True)
                            play('Sound/ding.wav')
                            self.notify_sound = arcade.Sound('Sound/notify.wav')
                            self.notify_player = self.notify_sound.play()
                            
                    except Exception as e:
                        logger.warning(f"生成整点报时语音失败: {e}")
                        # 播放备用提示音
                        if not config.get("chat_enable") and not config.get("notify_enable"):
                            play('Sound/ding.wav')
                            play('Sound/notifytime.wav')
                            
                    # 更新最后通知的小时
                    self.last_time = current_hour
        except Exception as e:
            logger.error(f"处理整点报时时出错: {e}")
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def handle_shutdown(sig, frame):
            logger.info('正在关闭服务...')
            self.shutdown()
            
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
    
    def start_services(self):
        """启动所有服务线程"""
        self.running = True
        
        # 设置信号处理器
        self._setup_signal_handlers()
        
        # 启动聊天服务
        self.threads['chat'] = Thread(target=chat.startchat)
        self.threads['chat'].daemon = True
        self.threads['chat'].start()
        logger.info('聊天服务启动成功')
        
        # 启动通知监控
        self.threads['monitor'] = Thread(target=self._monitor_notifications)
        self.threads['monitor'].daemon = True
        self.threads['monitor'].start()
        
        # 启动天气时间服务
        self.threads['weather_time'] = Thread(target=if_time_and_weather.admin)
        self.threads['weather_time'].daemon = True
        self.threads['weather_time'].start()
        logger.info('天气时间服务启动成功')
        
        # 根据配置启动可选服务
        if music_enable:
            self.threads['music'] = Thread(target=if_music.watch)
            self.threads['music'].daemon = True
            self.threads['music'].start()
            logger.info('音乐服务启动成功')
        
        if udp_enable:
            self.threads['udp'] = Thread(target=udpserver.udp_server)
            self.threads['udp'].daemon = True
            self.threads['udp'].start()
            logger.info('UDP服务启动成功')
        
        if schedule_enable:
            self.threads['schedule'] = Thread(target=schedule.timer)
            self.threads['schedule'].daemon = True
            self.threads['schedule'].start()
            logger.info('日程服务启动成功')
        
        if hass_demo_enable:
            self.threads['hass'] = Thread(target=hass_light_demo.handle)
            self.threads['hass'].daemon = True
            self.threads['hass'].start()
            logger.info('Home Assistant演示服务启动成功')
        
        logger.info('所有服务启动完成，PI-Assistant 正在运行')
    
    def run(self, host='0.0.0.0', port=5000):
        """运行Flask服务器"""
        try:
            # 启动所有服务线程
            self.start_services()
            
            # 运行Flask应用
            self.app.run(host=host, port=port)
        except Exception as e:
            logger.error(f"运行服务器时出错: {e}")
            self.shutdown()
    
    def shutdown(self):
        """关闭服务器并释放资源"""
        logger.info("正在关闭服务器...")
        self.running = False
        
        # 停止通知播放
        if self.notify_player and self.notify_sound:
            try:
                self.notify_sound.stop(self.notify_player)
            except:
                pass
        
        # 关闭线程池
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
        
        # 等待关键线程结束
        for name, thread in list(self.threads.items()):
            if thread.is_alive():
                logger.info(f"等待{name}线程结束...")
                # 设置较短的超时时间
                thread.join(timeout=0.5)
        
        logger.info("服务器已关闭")
        os._exit(0)

# 主程序入口
if __name__ == '__main__':
    server = ServerManager()
    server.run()

