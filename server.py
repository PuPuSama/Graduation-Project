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
import json
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import arcade
import logging
from flask import request, Flask, jsonify, render_template, Response
from loguru import logger
import queue
import functools

# 配置日志
logger.remove()
logger.add(sys.stdout, colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}", level="INFO")
logger.add('Log/PI-Assistant.log', colorize=False, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {file}:{line} - <level>{message}</level>", level="DEBUG")

# 导入项目模块
from config import config
import chat
import if_time_and_weather
import tts
from play import play
from sensor_simulator import SensorSimulator

# 关闭Flask日志
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# 添加全局响应队列（只在显示时使用，不影响原有的TTS流程）
stream_response_queue = queue.Queue()

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
        self.quick_commands = ["wake", "终止程序"]
        
        # 答案缓存
        self.last_answer = None
        
        # 创建Flask应用
        self.app = Flask('PI-Assistant')
        self.sensor_simulator = SensorSimulator()
        self._setup_routes()
    
    def route_error_handler(self, route_func):
        """添加统一错误处理的路由装饰器
        
        为API路由函数添加try-except包装，捕获所有异常并返回格式化的错误响应，
        避免在每个路由函数中重复编写错误处理代码。
        
        Args:
            route_func: 要装饰的路由函数
            
        Returns:
            包含错误处理的包装函数
        """
        @functools.wraps(route_func)
        def wrapper(*args, **kwargs):
            try:
                # 调用原始路由函数
                return route_func(*args, **kwargs)
            except Exception as e:
                # 记录错误日志
                logger.error(f"{route_func.__name__}路由处理出错: {e}")
                # 返回统一的错误响应
                return jsonify(
                    success=False, 
                    error=str(e),
                    route=route_func.__name__
                ), 500
        return wrapper
    
    def _setup_basic_routes(self):
        """设置基本路由"""
        # 主页
        @self.app.route('/')
        def index():
            editable_config = {k: config.params[k] for k in config.allow_params if k in config.params}
            return render_template('index.html', config=editable_config)
        
        # 健康检查
        @self.app.route('/health')
        @self.route_error_handler
        def health_check():
            return jsonify({
                'status': 'healthy',
                'threads': {name: thread.is_alive() for name, thread in self.threads.items()},
                'config': {
                    'chat_enable': config.get('chat_enable'),
                    'notify_enable': config.get('notify_enable')
                }
            })
    
    def _convert_config_value(self, value):
        """将字符串值转换为适当的数据类型
        
        Args:
            value: 要转换的值
            
        Returns:
            转换后的值（布尔值、整数、浮点数或原始字符串）
        """
        # 非字符串值直接返回
        if not isinstance(value, str):
            return value
        
        # 转换布尔值
        if value.lower() == 'true':
            return True
        if value.lower() == 'false':
            return False
        
        # 转换整数
        if value.isdigit():
            return int(value)
        
        # 尝试转换浮点数
        try:
            return float(value)
        except ValueError:
            pass
        
        # 保持原始字符串
        return value
    
    def _setup_config_routes(self):
        """设置配置相关路由"""
        # 更新配置
        @self.app.route('/update_config', methods=['POST'])
        @self.route_error_handler
        def update_config():
            data = request.json
            logger.info(f"收到配置更新请求: {data}")
            
            # 更新配置并记录已更新的键
            updated_keys = []
            for key, value in data.items():
                # 转换值类型
                converted_value = self._convert_config_value(value)
                # 更新配置
                config.set(**{key: converted_value})
                updated_keys.append(key)
            
            logger.info(f"已更新配置项: {updated_keys}")
            return jsonify(success=True, updated_keys=updated_keys)
        
        # 获取配置
        @self.app.route('/api/get_config')
        @self.route_error_handler
        def get_config():
            # 只返回允许编辑的配置项
            editable_config = {k: config.params[k] for k in config.allow_params if k in config.params}
            return jsonify(success=True, config=editable_config)
    
    def _setup_answer_routes(self):
        """设置答案相关路由"""
        # 获取答案
        @self.app.route('/get_answer', methods=['GET'])
        @self.route_error_handler
        def get_answer():
            current_answer = config.params.get('answer', '')
            # 检查答案是否有变化
            if current_answer != self.last_answer:
                self.last_answer = current_answer
                return jsonify(answer=current_answer)
            else:
                return jsonify(answer=None)
    
    def _setup_command_routes(self):
        """设置命令相关路由"""
        # 快速命令管理
        @self.app.route('/get_quick_commands', methods=['GET'])
        @self.route_error_handler
        def get_quick_commands():
            return jsonify(self.quick_commands)
        
        @self.app.route('/add_quick_command', methods=['POST'])
        @self.route_error_handler
        def add_quick_command():
            command = request.json.get('command')
            if command and command not in self.quick_commands:
                self.quick_commands.append(command)
                return jsonify(success=True)
            return jsonify(success=False)
        
        @self.app.route('/remove_quick_command', methods=['POST'])
        @self.route_error_handler
        def remove_quick_command():
            index = request.json.get('index')
            if 0 <= index < len(self.quick_commands):
                del self.quick_commands[index]
                return jsonify(success=True)
            return jsonify(success=False)
        
        # 命令处理
        @self.app.route('/command')
        @self.route_error_handler
        def handle_command():
            words = request.args.get('words')
            
            # 设置命令到配置
            config.set(command=words)
            
            # 清空现有队列
            while not stream_response_queue.empty():
                stream_response_queue.get()
                
            # 创建监听线程监听deepseek_stream_with_tts的response_queue
            self._start_response_monitor()
            
            return 'ok'
    
    def _start_response_monitor(self):
        """监听语音模型的响应并转发到Web界面
        
        将深度学习模型产生的响应文本转发到前端，实现实时显示效果
        """
        def monitor_responses():
            try:
                # 导入必要模块
                from deepseek_stream_with_tts import response_queue, RESPONSE_END_MARKER
                
                logger.info("开始监听语音模型响应")
                
                # 监听并转发响应
                while True:
                    try:
                        # 从模型响应队列获取内容
                        item = response_queue.get(timeout=20)
                        
                        # 处理结束标记
                        if item == RESPONSE_END_MARKER:
                            # 发送自定义结束标记到前端
                            stream_response_queue.put("[END]")
                            logger.info("语音模型响应结束")
                            break
                        
                        # 转发响应内容到前端显示队列
                        stream_response_queue.put(item)
                        
                    except queue.Empty:
                        logger.warning("等待响应超时")
                        break
                        
            except Exception as e:
                logger.error(f"监听响应时出错: {e}")
        
        # 启动监听线程
        threading.Thread(target=monitor_responses, daemon=True).start()
    
    def _setup_notification_routes(self):
        """设置通知相关路由"""
        # Cookie处理
        @self.app.route('/cookie')
        @self.route_error_handler
        def handle_cookie():
            submit = request.args.get('cookie')
            logger.info(f"收到cookie：{submit}")
            with open('cookie.txt', 'w') as f:
                f.write(submit)
            return 'ok'
        
        # 语音通知
        @self.app.route('/words')
        @self.route_error_handler
        def handle_words():
            words = request.args.get('words')
            if not config.get('Noticenotify'):
                return 'ok'
                
            try:
                tts.ssml_wav(words, 'Sound/notify.wav')
                # 使用统一的通知播放方法
                self._play_notification('Sound/notify.wav')
            except Exception as e:
                logger.error(f"转换语音时出错: {e}")
                play('Sound/ttserror.wav')
            
            return 'ok'
        
        # 设备连接反馈
        @self.app.route('/back')
        @self.route_error_handler
        def handle_device_back():
            play('Sound/ding.wav')
            play('Sound/devconnect.wav')
            return 'ok'
    
    def _setup_stream_routes(self):
        """设置流式响应路由"""
        @self.app.route('/api/stream_response')
        @self.route_error_handler
        def stream_response():
            def generate():
                # 发送SSE头部
                yield "data: {\"status\":\"connected\"}\n\n"
                
                while True:
                    try:
                        # 尝试从队列获取新内容，超时1秒
                        chunk = stream_response_queue.get(timeout=1)
                        
                        # 如果收到结束标记
                        if chunk == "[END]":
                            # 发送结束标记
                            yield f"data: {json.dumps({'status': 'completed'})}\n\n"
                            # 清空队列
                            while not stream_response_queue.empty():
                                stream_response_queue.get()
                            break
                        
                        # 发送内容块
                        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                        
                    except queue.Empty:
                        # 发送保持连接的消息
                        yield f"data: {json.dumps({'status': 'waiting'})}\n\n"
                
            return Response(generate(), mimetype="text/event-stream")
    
    def _setup_sensor_routes(self):
        """设置传感器相关路由"""
        @self.app.route('/api/sensor_data')
        @self.route_error_handler
        def get_sensor_data():
            sensor_data = self.sensor_simulator.get_all_sensor_data()
            return jsonify(sensor_data)
    
    def _setup_routes(self):
        """设置所有Flask路由"""
        # 按功能划分路由
        self._setup_basic_routes()        # 基本路由
        self._setup_config_routes()       # 配置相关
        self._setup_answer_routes()       # 答案相关
        self._setup_command_routes()      # 命令相关
        self._setup_notification_routes() # 通知相关
        self._setup_stream_routes()       # 流式响应
        self._setup_sensor_routes()       # 传感器相关
    
    def _play_notification(self, sound_file, with_ding=True):
        """统一处理通知播放
        
        Args:
            sound_file: 要播放的声音文件
            with_ding: 是否先播放提示音
        """
        try:
            # 只有在没有其他活动时才播放通知
            if not config.get("chat_enable") and not config.get("notify_enable"):
                config.set(notify_enable=True)
                
                if with_ding:
                    play('Sound/ding.wav')
                    
                self.notify_sound = arcade.Sound(sound_file)
                self.notify_player = self.notify_sound.play()
                return True
            return False
        except Exception as e:
            logger.error(f"播放通知出错: {e}")
            return False
    
    def _check_notification_playback(self, times):
        """检查通知播放状态并处理完成或超时
        
        Args:
            times: 当前计数器值
            
        Returns:
            int: 更新后的计数器值
        """
        # 如果没有播放器或声音，或者未在播放中，则直接返回
        if not (self.notify_player and self.notify_sound and 
                self.notify_sound.is_playing(self.notify_player)):
            return 0
            
        # 检查是否播放完成
        if self.notify_sound.is_complete(self.notify_player):
            config.set(notify_enable=False)
            try:
                self.notify_sound.stop(self.notify_player)
                logger.info('通知播放停止：自动完成')
            except Exception as e:
                logger.warning(f'无法停止通知播放: {e}')
            return 0
        else:
            # 计算通知播放时间，如果超过16秒（8 * 2秒），强制停止
            times += 1
            if times >= 8:
                config.set(notify_enable=False)
                try:
                    self.notify_sound.stop(self.notify_player)
                    logger.warning('通知播放停止：超时')
                except Exception as e:
                    logger.warning(f'无法停止超时通知: {e}')
                return 0
            return times
    
    def _check_hourly_notification(self):
        """检查是否需要整点报时
        
        在整点时间（分钟为0）且启用了时间通知时，
        播放整点报时语音提醒。
        """
        try:
            current_hour = time.localtime()[3]
            current_minute = time.localtime()[4]
            
            # 判断是否整点且启用了时间通知
            if current_minute == 0 and config.get("timenotify") is True:
                # 避免重复通知
                if self.last_time != current_hour:
                    self._play_hourly_notification(current_hour)
        except Exception as e:
            logger.error(f"检查整点报时时出错: {e}")

    def _play_hourly_notification(self, hour):
        """播放整点报时语音
        
        Args:
            hour: 当前小时
        """
        logger.info('整点报时')
        # 格式化小时（12小时制）
        hour_12 = hour if hour < 13 else hour - 12
        words = f'整点报时,已经{hour_12}点啦'
        
        try:
            # 生成并播放语音
            tts.ssml_wav(words, 'Sound/notify.wav')
            if self._play_notification('Sound/notify.wav'):
                # 更新最后通知的小时
                self.last_time = hour
        except Exception as e:
            logger.warning(f"生成整点报时语音失败: {e}")
            # 播放备用提示音
            if not config.get("chat_enable") and not config.get("notify_enable"):
                play('Sound/ding.wav')
                play('Sound/notifytime.wav')
                # 更新最后通知的小时
                self.last_time = hour
    
    def _monitor_notifications(self):
        """监控通知播放状态和整点报时
        
        这个方法在后台线程中运行，负责：
        1. 监控通知播放状态，处理完成和超时
        2. 检查整点时间并触发报时功能
        """
        times = 0  # 计时器计数，用于检测通知播放超时
        
        while self.running:
            try:
                # 1. 检查通知播放状态
                times = self._check_notification_playback(times)
                
                # 2. 检查整点报时
                self._check_hourly_notification()
                
                # 休眠以减少CPU使用
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"通知监控错误: {e}")
                times = 0  # 重置计数器
                time.sleep(5)  # 错误后恢复时间
    
    def _start_service(self, service_name, target_func, daemon=True):
        """启动单个服务线程
        
        Args:
            service_name: 服务名称，用于日志和线程跟踪
            target_func: 服务函数
            daemon: 是否设置为守护线程
            
        Returns:
            Thread: 启动的线程对象
        """
        logger.info(f'正在启动{service_name}服务...')
        thread = Thread(target=target_func, name=service_name)
        thread.daemon = daemon
        thread.start()
        self.threads[service_name] = thread
        logger.info(f'{service_name}服务启动成功')
        return thread
    
    def _wait_for_threads(self, threads_to_wait=None, timeout=0.5):
        """等待指定线程结束
        
        Args:
            threads_to_wait: 需要等待的线程列表，默认为所有线程
            timeout: 每个线程等待的超时时间
        """
        if threads_to_wait is None:
            threads_to_wait = list(self.threads.items())
            
        for name, thread in threads_to_wait:
            if thread.is_alive():
                logger.info(f"等待{name}线程结束...")
                thread.join(timeout=timeout)
                if thread.is_alive():
                    logger.warning(f"{name}线程未能在超时时间内结束")
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def handle_shutdown(sig, frame):
            logger.info('正在关闭服务...')
            self.shutdown()
            
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
    
    def start_services(self):
        """启动所有必要的服务线程
        
        包括：
        1. 聊天服务 - 处理语音交互
        2. 通知监控 - 管理通知和整点报时
        3. 天气时间服务 - 提供天气和时间信息
        """
        # 设置状态为运行中
        self.running = True
        
        # 注册信号处理器（Ctrl+C和终止信号）
        self._setup_signal_handlers()
        
        # 按顺序启动服务
        services = [
            ('chat', chat.startchat),
            ('monitor', self._monitor_notifications),
            ('weather_time', if_time_and_weather.admin)
        ]
        
        # 启动所有服务
        for name, func in services:
            self._start_service(name, func)
        
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
        """优雅地关闭服务器并释放所有资源
        
        按以下顺序执行关闭操作：
        1. 停止所有后台任务
        2. 停止通知播放
        3. 关闭线程池
        4. 等待线程结束
        5. 退出程序
        """
        logger.info("正在关闭服务器...")
        
        # 1. 设置运行状态为False，通知所有循环停止
        self.running = False
        
        # 2. 停止通知播放
        self._stop_notification()
        
        # 3. 关闭线程池
        self._shutdown_thread_pool()
        
        # 4. 等待所有线程结束
        self._wait_for_threads()
        
        logger.info("服务器已关闭")
        
        # 5. 确保程序完全退出
        os._exit(0)

    def _stop_notification(self):
        """停止当前播放的通知"""
        if self.notify_player and self.notify_sound:
            try:
                self.notify_sound.stop(self.notify_player)
                logger.info("已停止通知播放")
            except Exception as e:
                logger.warning(f"停止通知播放时出错: {e}")

    def _shutdown_thread_pool(self):
        """关闭线程池"""
        if hasattr(self, 'executor'):
            logger.info("正在关闭线程池...")
            self.executor.shutdown(wait=False)

# 主程序入口
if __name__ == '__main__':
    server = ServerManager()
    server.run()