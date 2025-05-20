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
import subprocess
import requests
import json
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import arcade
import logging
from flask import request, Flask, jsonify, render_template, Response
from loguru import logger
from pathlib import Path
import queue

# 配置日志
logger.remove()
logger.add(sys.stdout, colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}", level="INFO")
logger.add('Log/PI-Assistant.log', colorize=False, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {file}:{line} - <level>{message}</level>", level="DEBUG")

# 导入项目模块
from config import config
from const_config import music_enable, schedule_enable, udp_enable, hass_demo_enable, qqid, qqmusicpath, qqmusicport
import chat
import if_time_and_weather
import tts
from play import play
import Scene
from sensor_simulator import SensorSimulator

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
        self.quick_commands = ["wake", "终止程序", "下一首。"]
        
        # 答案缓存
        self.last_answer = None
        
        # 音乐API相关
        self.qqmusic_api_path = None
        self.qqmusic_api_process = None
        self.qqmusic_api_port = getattr(sys.modules.get('const_config'), 'qqmusicport', 3300)
        
        # 创建Flask应用
        self.app = Flask('PI-Assistant')
        self.sensor_simulator = SensorSimulator()
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
                logger.info(f"收到配置更新请求: {data}")
                
                updated_keys = []
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
                    updated_keys.append(key)
                
                logger.info(f"已更新配置项: {updated_keys}")
                return jsonify(success=True, updated_keys=updated_keys)
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
                
                # 设置命令到配置
                config.set(command=words)
                
                # 清空现有队列
                while not stream_response_queue.empty():
                    stream_response_queue.get()
                    
                # 创建监听线程监听deepseek_stream_with_tts的response_queue
                def monitor_deepseek_stream():
                    try:
                        # 导入必要模块
                        from deepseek_stream_with_tts import deepseek_chat, response_queue, RESPONSE_END_MARKER
                        
                        # 创建一个本地队列用于转发
                        forwarder_queue = queue.Queue()
                        original_get = response_queue.get
                        
                        # 替换原始队列的get方法，实现窃听但不干扰原始流程
                        def spying_get(*args, **kwargs):
                            item = original_get(*args, **kwargs)
                            if item != RESPONSE_END_MARKER:  # 不转发结束标记
                                forwarder_queue.put(item)
                            else:
                                forwarder_queue.put("[END]")  # 使用自己的结束标记
                            return item
                        
                        # 监听开始前先备份原始方法
                        response_queue.get = spying_get
                        
                        # 启动转发线程
                        def forward_responses():
                            while True:
                                try:
                                    item = forwarder_queue.get(timeout=30)  # 30秒超时
                                    stream_response_queue.put(item)
                                    if item == "[END]":
                                        break
                                except queue.Empty:
                                    break
                        
                        forwarder_thread = threading.Thread(target=forward_responses, daemon=True)
                        forwarder_thread.start()
                        
                        # 等待一段时间后恢复原始方法
                        time.sleep(60)  # 等待足够长的时间
                        response_queue.get = original_get
                        
                    except Exception as e:
                        logger.error(f"监听深度学习模型响应时出错: {e}")
                        # 确保恢复原始方法
                        try:
                            if 'original_get' in locals() and 'response_queue' in locals():
                                response_queue.get = original_get
                        except:
                            pass
                
                # 启动监听线程
                threading.Thread(target=monitor_deepseek_stream, daemon=True).start()
                
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
        
        # 传感器数据
        @self.app.route('/api/sensor_data')
        def get_sensor_data():
            try:
                sensor_data = self.sensor_simulator.get_all_sensor_data()
                return jsonify(sensor_data)
            except Exception as e:
                logger.error(f"获取传感器数据时出错: {e}")
                return jsonify({"error": str(e)}), 500
        
        # 流式回答
        @self.app.route('/api/stream_response')
        def stream_response():
            try:
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
            except Exception as e:
                logger.error(f"流式回答时出错: {e}")
                return jsonify({"error": str(e)}), 500
        
        # 获取配置
        @self.app.route('/api/get_config')
        def get_config():
            try:
                # 获取允许编辑的配置项
                editable_config = {k: config.params[k] for k in config.allow_params if k in config.params}
                return jsonify(success=True, config=editable_config)
            except Exception as e:
                logger.error(f"获取配置时出错: {e}")
                return jsonify(success=False, error=str(e)), 500
    
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
    
    def _find_qqmusic_api_path(self):
        """自动查找QQMusicApi目录路径"""
        # 首先检查配置文件中的路径
        if qqmusicpath and os.path.exists(qqmusicpath):
            logger.info(f"使用配置文件中的QQMusicApi路径: {qqmusicpath}")
            return qqmusicpath
            
        # 查找可能的路径
        possible_paths = [
            # 当前目录下
            os.path.join(os.getcwd(), 'QQMusicApi'),
            # 当前目录上级
            os.path.join(os.path.dirname(os.getcwd()), 'QQMusicApi'),
            # 相对路径
            './QQMusicApi',
            '../QQMusicApi'
        ]
        
        # 检查每个可能的路径
        for path in possible_paths:
            if os.path.exists(path) and os.path.isdir(path):
                # 验证是否是QQMusicApi目录 (检查package.json是否存在且包含qq-music-api)
                package_json = os.path.join(path, 'package.json')
                if os.path.exists(package_json):
                    try:
                        with open(package_json, 'r') as f:
                            content = f.read()
                            if 'qq-music-api' in content:
                                logger.info(f"自动找到QQMusicApi路径: {path}")
                                return path
                    except Exception as e:
                        logger.warning(f"读取package.json时出错: {e}")
                        continue
        
        logger.error("未找到有效的QQMusicApi目录!")
        return None
    
    def _update_qqmusic_config(self):
        """更新QQMusicApi配置文件，设置正确的QQ号和端口"""
        if not self.qqmusic_api_path:
            logger.error("QQMusicApi路径未设置，无法更新配置")
            return False
            
        config_file = os.path.join(self.qqmusic_api_path, 'bin', 'config.js')
        if not os.path.exists(config_file):
            logger.error(f"找不到QQMusicApi配置文件: {config_file}")
            return False
            
        try:
            # 读取现有配置
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 检查是否需要更新QQ号
            if qqid and len(qqid) > 0:
                # 替换QQ号
                import re
                pattern_qq = r'qq:\s*[\'"](\d+)[\'"]'
                if re.search(pattern_qq, content):
                    content = re.sub(pattern_qq, f"qq: '{qqid}'", content)
                else:
                    logger.warning("未找到配置文件中的QQ配置项，无法更新QQ号")
                
                # 替换端口号
                pattern_port = r'port:\s*(\d+)'
                if re.search(pattern_port, content):
                    content = re.sub(pattern_port, f"port: {self.qqmusic_api_port}", content)
                else:
                    logger.warning("未找到配置文件中的端口配置项，无法更新端口")
                
                # 写回配置文件
                with open(config_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
                logger.info(f"已更新QQMusicApi配置: QQ={qqid}, 端口={self.qqmusic_api_port}")
                return True
            else:
                logger.warning("未设置QQ号，跳过QQMusicApi配置更新")
                return False
                
        except Exception as e:
            logger.error(f"更新QQMusicApi配置时出错: {e}")
            return False
    
    def _start_qqmusic_api(self):
        """启动QQ音乐API服务"""
        if not music_enable:
            logger.info("音乐功能未启用，跳过启动QQ音乐API")
            return False
            
        # 查找QQMusicApi路径
        self.qqmusic_api_path = self._find_qqmusic_api_path()
        if not self.qqmusic_api_path:
            logger.error("无法找到QQMusicApi路径，无法启动QQ音乐API")
            return False
        
        # 检查是否已经启动
        try:
            response = requests.get(f'http://127.0.0.1:{self.qqmusic_api_port}/user/getCookie', timeout=3)
            if response.status_code == 200:
                logger.info("QQ音乐API服务已经在运行")
                return True
        except:
            logger.info("QQ音乐API服务未运行，正在启动...")
        
        # 更新配置文件
        self._update_qqmusic_config()
        
        # 构建启动命令
        cwd = os.getcwd()  # 保存当前工作目录
        try:
            # 切换到QQMusicApi目录
            os.chdir(self.qqmusic_api_path)
            
            # 使用subprocess启动npm
            # Windows系统使用不同的命令
            if os.name == 'nt':
                cmd = ['npm', 'start']
                # 不显示窗口
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.qqmusic_api_process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    startupinfo=startupinfo
                )
            else:
                cmd = ['npm', 'start']
                self.qqmusic_api_process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
            # 切回原来的工作目录
            os.chdir(cwd)
            
            # 等待服务启动
            retry_count = 0
            max_retries = 15  # 增加重试次数
            while retry_count < max_retries:
                try:
                    response = requests.get(f'http://127.0.0.1:{self.qqmusic_api_port}/user/getCookie', timeout=3)
                    if response.status_code == 200:
                        logger.info("QQ音乐API服务启动成功!")
                        return True
                except:
                    pass
                    
                time.sleep(1)
                retry_count += 1
                if retry_count % 5 == 0:
                    logger.info(f"等待QQ音乐API服务启动... ({retry_count}/{max_retries})")
                
            logger.error(f"QQ音乐API服务启动失败，尝试了 {max_retries} 次")
            return False
            
        except Exception as e:
            os.chdir(cwd)  # 确保切回原工作目录
            logger.error(f"启动QQ音乐API时出错: {e}")
            return False
    
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
            # 先启动QQ音乐API
            api_started = self._start_qqmusic_api()
            if api_started:
                logger.info('QQ音乐API服务启动成功')
            else:
                logger.warning('QQ音乐API服务启动失败，音乐功能可能无法正常使用')
                
            # 启动音乐服务线程
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
        
        # 关闭QQ音乐API进程
        if self.qqmusic_api_process:
            logger.info("正在关闭QQ音乐API服务...")
            try:
                if os.name == 'nt':  # Windows
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.qqmusic_api_process.pid)])
                else:  # Linux/Mac
                    os.killpg(os.getpgid(self.qqmusic_api_process.pid), signal.SIGTERM)
                self.qqmusic_api_process = None
                logger.info("QQ音乐API服务已关闭")
            except Exception as e:
                logger.error(f"关闭QQ音乐API服务时出错: {e}")
        
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

