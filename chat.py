#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
聊天服务模块 - 处理语音交互、对话流程和响应生成
"""

import os
import sys
import time
import threading
import arcade
from enum import Enum
from loguru import logger
from config import config
from play import play
from tts import ssml_wav

# 导入配置常量
from const_config import (
    snowboy_enable, porcupine_enable, gpio_wake_enable, 
    use_online_recognize, use_deepseek, chat_or_standard
)

# 导入核心功能模块
import speechpoint
import prompt_and_deal
import if_exit
import if_time_and_weather

# 根据配置导入语音识别模块
if use_online_recognize:
    import azure_reco

# 根据配置导入热词检测模块
if snowboy_enable:
    from const_config import snowboypath
    sys.path.append(snowboypath)
    from snowboy import hotwordBymic as hotword_module
elif porcupine_enable:
    from const_config import porcupinepath
    sys.path.append(porcupinepath)
    from Porcupine import porcupine as hotword_module

# 根据配置导入GPIO模块
if gpio_wake_enable:
    import RPi.GPIO as GPIO

# 根据配置导入对话模型
if use_deepseek:
    if chat_or_standard:
        import deepseek_stream_with_tts as dialog_module
    else:
        import deepseek as dialog_module


# 聊天服务状态枚举
class ChatState(Enum):
    IDLE = 0           # 无活动
    WAKE_ACTIVATED = 1 # 休眠激活
    RUN_ACTIVATED = 2  # 运行时激活
    ERROR = 3          # 错误状态
    SHUTDOWN = -1      # 关闭服务


class ChatService:
    """聊天服务类，封装对话流程和状态管理"""
    
    def __init__(self):
        """初始化聊天服务状态"""
        # 音频播放相关
        self.chat_sound = None
        self.chat_player = None
        self.sound_play_counter = 0
        
        # 对话控制标志
        self.next_enabled = True
        self.next_dialog = False
        self.running = False
        self.active_state = ChatState.IDLE
        self.allow_running = True
        self.service_active = True
        
        # 文本输入相关
        self.text_input_enabled = False
        self.input_text = ''
        self.manual_input_enabled = False
        
        # 热词检测线程
        self.hotword_thread = None
        
        # 上次整点报时的小时
        self.last_time = None
    
    #-------------------------------------------------------------------------
    # 核心服务管理
    #-------------------------------------------------------------------------
    
    def monitor_service(self):
        """监控聊天服务状态的主循环"""
        while self.service_active:
            # 处理特殊状态
            if self._handle_special_states():
                continue
                
            # 检查音频播放状态
            self._check_audio_playback()
            
            # 处理下一轮对话
            self._check_for_next_dialog()
            
            # 处理状态转换
            if self.active_state == ChatState.RUN_ACTIVATED:
                self.allow_running = False
                self.active_state = ChatState.WAKE_ACTIVATED
            
            # 循环间隔
            time.sleep(0.5)
    
    def _handle_special_states(self):
        """处理特殊状态，返回是否已处理"""
        # 处理错误状态
        if self.active_state == ChatState.ERROR:
            logger.error('聊天服务错误，程序即将退出')
            play('Sound/exit.wav')
            os._exit(0)
            return True
            
        # 处理服务关闭
        if self.active_state == ChatState.SHUTDOWN:
            self.service_active = False
            return True
            
        return False
    
    def start_command_processor(self):
        """启动命令处理线程"""
        def command_processor():
            while self.service_active:
                command = config.get("command")
                if command:
                    if self.process_command(command):
                        config.set(command='')
                time.sleep(0.5)
        
        processor_thread = threading.Thread(target=command_processor)
        processor_thread.daemon = True
        processor_thread.start()
        return processor_thread
    
    #-------------------------------------------------------------------------
    # 音频播放管理
    #-------------------------------------------------------------------------
    
    def _check_audio_playback(self):
        """检查并管理音频播放状态"""
        is_playing = (self.chat_sound and self.chat_player and 
                      self.chat_sound.is_playing(self.chat_player))
        is_complete = (self.chat_sound and self.chat_player and 
                       self.chat_sound.is_complete(self.chat_player))
        
        # 没有声音播放且不在对话过程中时释放语音资源
        if not is_playing and not self.running:
            config.set(chat_enable=False)
        
        # 处理长时间播放的声音
        if is_playing:
            if is_complete:
                self._stop_sound_playback("通过监控函数停止声音播放")
            else:
                self.sound_play_counter += 1
                # 如果播放时间过长（约85秒），强制停止
                if self.sound_play_counter >= 170:
                    self._stop_sound_playback("超时停止声音播放")
    
    def _stop_sound_playback(self, reason=""):
        """停止声音播放"""
        if self.chat_sound and self.chat_player:
            try:
                self.chat_sound.stop(self.chat_player)
                self.sound_play_counter = 0
                if reason:
                    logger.info(reason)
            except Exception:
                logger.warning('停止声音播放失败')
    
    def _stop_current_sound(self):
        """停止当前正在播放的声音"""
        if (self.chat_player and self.chat_sound and 
            self.chat_sound.is_playing(self.chat_player)):
            try:
                logger.info('停止当前声音播放')
                self.chat_sound.stop(self.chat_player)
                self.sound_play_counter = 0
            except Exception:
                logger.warning('停止声音播放失败')
    
    #-------------------------------------------------------------------------
    # 对话流程管理
    #-------------------------------------------------------------------------
    
    def _check_for_next_dialog(self):
        """检查是否需要开始下一轮对话"""
        # 检查是否有声音播放
        is_playing = (self.chat_sound and self.chat_player and 
                      self.chat_sound.is_playing(self.chat_player))
        is_complete = (self.chat_sound and self.chat_player and 
                       self.chat_sound.is_complete(self.chat_player))
        
        # 检查TTS任务是否完成
        tts_complete = False
        if use_deepseek and chat_or_standard:
            tts_complete = (hasattr(dialog_module, 'tts_manager') and 
                           dialog_module.tts_manager.tts_task and 
                           dialog_module.tts_manager.tts_task.get())
        
        # 判断是否应该开始新对话
        should_start_dialog = (
            not self.running and 
            not config.get("notify_enable") and 
            (self.active_state == ChatState.WAKE_ACTIVATED or 
             (self.next_dialog and is_complete) or 
             (self.next_dialog and tts_complete))
        )
        
        if should_start_dialog:
            # 流式模式下添加延时
            if use_deepseek and chat_or_standard:
                time.sleep(2)
            
            # 启动对话线程
            self._start_new_dialog()
    
    def _start_new_dialog(self):
        """启动新的对话线程"""
        dialog_thread = threading.Thread(target=self.process_dialog)
        dialog_thread.daemon = True
        config.set(chat_enable=True)
        dialog_thread.start()
        logger.info('开始新对话')
    
    def process_dialog(self):
        """处理完整的对话流程"""
        # 设置对话状态
        self.running = True
        self.next_dialog = True if self.next_enabled else False
        
        # 停止当前正在播放的声音
        self._stop_current_sound()
        
        # 重置激活状态
        self.active_state = ChatState.IDLE
        
        # 重置TTS执行状态（如果适用）
        if use_deepseek and chat_or_standard and hasattr(dialog_module, 'tts_manager'):
            dialog_module.tts_manager.tts_executed = False
        
        # 对话流程的主要步骤
        if not self._handle_voice_input():
            self._end_dialog()
            return
        
        # 重置输入标志
        self.manual_input_enabled = False
        self.text_input_enabled = False
        
        if not self._handle_special_commands():
            self._end_dialog()
            return
        
        if not self._generate_response():
            self._end_dialog()
            return
        
        # 处理TTS和音频播放
        self._handle_audio_response()
        
        # 结束对话
        self._end_dialog()
    
    def _end_dialog(self):
        """结束对话，重置状态"""
        logger.info('对话结束')
        self.allow_running = True
        self.running = False
    
    #-------------------------------------------------------------------------
    # 语音输入处理
    #-------------------------------------------------------------------------
    
    def _handle_voice_input(self):
        """处理语音输入，返回是否成功"""
        # 如果不允许运行，直接返回失败
        if not self.allow_running:
            return False
        
        # 如果已经有文本输入或手动输入，跳过录音
        if self.text_input_enabled or self.manual_input_enabled:
            return True
        
        # 录制语音
        if not self._record_voice():
            return False
        
        # 语音识别
        if not self._recognize_speech():
            return False
        
        return True
    
    def _record_voice(self):
        """录制语音，返回是否成功"""
        try:
            # 录音提示音
            play('Sound/ding.wav')
            logger.info('准备开始录音')
            
            # 录制语音
            speechpoint.record_file()
            
            # 录音结束提示音
            play('Sound/dong.wav')
            return True
            
        except Exception as e:
            logger.warning(f"录音出错: {e}")
            play('Sound/ding.wav')
            play('Sound/quit.wav')
            self._reset_dialog_state(False)
            return False
    
    def _recognize_speech(self):
        """进行语音识别，返回是否成功"""
        if not self.allow_running or self.text_input_enabled:
            return True
            
        try:
            self.input_text = azure_reco.recognize()
            logger.info(f"识别结果: {self.input_text}")
            return True
        except Exception as e:
            logger.warning(f"语音识别失败: {e}")
            play('Sound/recoerror.wav')
            self._reset_dialog_state(False)
            return False
    
    #-------------------------------------------------------------------------
    # 命令处理
    #-------------------------------------------------------------------------
    
    def _handle_special_commands(self):
        """处理特殊命令，返回是否继续对话"""
        if not self.allow_running:
            return False
            
        # 检查结束对话命令
        if if_exit.ifend(self.input_text):
            self._stop_current_sound()
            self._reset_dialog_state(False)
            return False
        
        # 检查退出程序命令
        if if_exit.ifexit(self.input_text):
            config.set(command='shutdown')
            self._stop_current_sound()
            self._reset_dialog_state(False)
            return False
        
        # 检查时间和天气相关命令
        if if_time_and_weather.timedetect(self.input_text):
            self._stop_current_sound()
            self._reset_dialog_state(False)
            config.set(chat_enable=False)
            return False
        
        return True
    
    def process_command(self, command):
        """处理外部命令"""
        # 命令处理映射
        command_handlers = {
            'wake': self._handle_wake_command,
            'get_audio_complete': self._handle_audio_complete_command,
            'shutdown': self._handle_shutdown_command,
            'stop': self._handle_stop_command,
            'start': self._handle_start_command
        }
        
        # 处理空命令
        if not command:
            return False
            
        # 检查特殊配置状态
        if config.get("wakebyhw") is False and config.get("hw_started") is True:
            return self._handle_stop_command()
            
        if (snowboy_enable or porcupine_enable) and config.get("wakebyhw") is True and config.get("hw_started") is False:
            return self._handle_start_command()
        
        # 使用映射处理命令
        handler = command_handlers.get(command)
        if handler:
            return handler()
        
        # 处理文本命令
        return self._handle_text_command(command)
    
    def _handle_wake_command(self):
        """处理唤醒命令"""
        logger.info('收到唤醒命令')
        self.active_state = ChatState.WAKE_ACTIVATED
        return True
    
    def _handle_audio_complete_command(self):
        """处理手动录音完成命令"""
        logger.info('收到手动录音完成命令')
        self.manual_input_enabled = True
        self.next_enabled = False
        self.handle_hotword_trigger()
        return True
    
    def _handle_shutdown_command(self):
        """处理关闭命令"""
        self.service_active = False
        return True
    
    def _handle_stop_command(self):
        """处理停止热词检测命令"""
        try:
            if hasattr(hotword_module, 'terminate'):
                hotword_module.terminate()
            config.set(wakebyhw=False, hw_started=False)
        except Exception:
            logger.warning('停止热词检测失败')
        
        self.hotword_thread = None
        self.next_enabled = False
        return True
    
    def _handle_start_command(self):
        """处理启动热词检测命令"""
        if self.hotword_thread is None and (snowboy_enable or porcupine_enable):
            self.hotword_thread = threading.Thread(
                target=hotword_module.start, 
                args=(self.handle_hotword_trigger,)
            )
            self.hotword_thread.daemon = True
            self.hotword_thread.start()
            config.set(wakebyhw=True, hw_started=True)
        
        self.next_enabled = True
        play('Sound/hwstartsucc.wav')
        return True
    
    def _handle_text_command(self, command):
        """处理文本命令"""
        logger.info(f'收到文本命令: {command}')
        self.input_text = command
        self.text_input_enabled = True
        self.handle_hotword_trigger()
        return True
    
    #-------------------------------------------------------------------------
    # 响应生成与处理
    #-------------------------------------------------------------------------
    
    def _generate_response(self):
        """生成对话响应，返回是否成功"""
        if not self.allow_running:
            return False
            
        try:
            # 记录对话模式
            mode_str = "流式对话" if (use_deepseek and chat_or_standard) else "标准对话"
            logger.info(f"使用{mode_str}模式生成回复")
            
            # 获取对话回复
            reply = prompt_and_deal.send(self.input_text)
            logger.info(f"回复生成完成: {reply[:50]}..." if len(reply) > 50 else f"回复生成完成: {reply}")
            config.set(answer=reply)
            
            # 等待流式TTS完成（如果适用）
            if use_deepseek and chat_or_standard:
                self._wait_for_tts_task()
            
            return True
            
        except Exception as e:
            logger.error(f'对话生成错误: {e}')
            play('Sound/ding.wav')
            play('Sound/gpterror.wav')
            self.allow_running = True
            self.running = False
            return False
    
    def _wait_for_tts_task(self):
        """等待流式TTS任务完成"""
        logger.info("检查流式TTS任务状态")
        if hasattr(dialog_module, 'tts_manager') and dialog_module.tts_manager.tts_task:
            try:
                logger.info("等待流式TTS任务完成")
                dialog_module.tts_manager.tts_task.get()
                logger.info("流式TTS任务已完成")
            except Exception as e:
                logger.warning(f"等待TTS任务完成时出错: {e}")
        else:
            logger.warning("未找到流式TTS任务，可能需要手动处理TTS")
    
    def _handle_audio_response(self):
        """处理TTS和音频播放"""
        # 检查是否允许运行
        if not self.allow_running:
            return False
        
        # 流式模式下，TTS应该已经在生成响应时处理
        if use_deepseek and chat_or_standard:
            if self._check_stream_tts_executed():
                return True
        
        # 手动生成TTS
        if not self._generate_tts():
            return False
        
        # 播放TTS音频
        return self._play_tts_audio()
    
    def _check_stream_tts_executed(self):
        """检查流式TTS是否已执行，返回是否已执行"""
        logger.info("流式模式下，检查TTS状态")
        
        if hasattr(dialog_module, 'tts_manager'):
            if getattr(dialog_module.tts_manager, 'tts_executed', False):
                logger.info("TTS已执行，语音应已输出")
                return True
            else:
                logger.warning("TTS未执行，尝试手动生成语音")
        else:
            logger.error("未找到TTS管理器，尝试手动生成语音")
        
        return False
    
    def _generate_tts(self):
        """生成TTS音频，返回是否成功"""
        try:
            # 生成TTS音频
            if os.path.exists('Sound/answer.wav'):
                os.remove('Sound/answer.wav')
            
            reply = config.get("answer")
            logger.info(f"准备合成语音，文本长度: {len(reply)}")
            ssml_wav(reply, 'Sound/answer.wav')
            logger.info('TTS音频生成完成')
            return True
        except Exception as e:
            logger.warning(f"TTS生成失败: {e}")
            play('Sound/ttserror.wav')
            self.allow_running = False
            return False
    
    def _play_tts_audio(self):
        """播放TTS音频，返回是否成功"""
        logger.info("开始播放TTS音频")
        play('Sound/ding.wav')
        self.chat_sound = arcade.Sound('Sound/answer.wav')
        self.chat_player = self.chat_sound.play()
        time.sleep(0.5)
        return True
    
    #-------------------------------------------------------------------------
    # 唤醒与状态管理
    #-------------------------------------------------------------------------
    
    def handle_hotword_trigger(self):
        """处理热词唤醒事件"""
        logger.info('热词触发')
        
        # 根据当前状态决定行为
        if self.running and not self.allow_running:
            # 多次唤醒造成的错误状态
            self.active_state = ChatState.ERROR
            return False
            
        if self.running:
            # 正在运行时被唤醒
            self.active_state = ChatState.RUN_ACTIVATED
            # 如果是流式模式，停止当前TTS
            if use_deepseek and chat_or_standard:
                dialog_module.tts_manager.stop_tts()
            logger.warning('对话被中断')
        else:
            # 正常唤醒
            self.active_state = ChatState.WAKE_ACTIVATED
        
        return True
    
    def _reset_dialog_state(self, next_enabled=True):
        """重置对话状态"""
        self.next_dialog = next_enabled
        self.allow_running = True
        self.running = False
    
    #-------------------------------------------------------------------------
    # GPIO 唤醒功能
    #-------------------------------------------------------------------------
    
    def setup_gpio_wake(self):
        """设置GPIO唤醒功能"""
        if not gpio_wake_enable:
            return []
            
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)  # 按钮
        GPIO.setup(18, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) # 外设
        
        # 创建并启动按钮唤醒线程
        button_thread = self._create_gpio_wake_thread(4, "通过物理按钮唤醒")
        
        # 创建并启动外设唤醒线程
        device_thread = self._create_gpio_wake_thread(18, "通过外设唤醒")
        
        return [button_thread, device_thread]
    
    def _create_gpio_wake_thread(self, pin, wake_message):
        """创建GPIO唤醒线程"""
        def gpio_wake():
            while True:
                GPIO.wait_for_edge(pin, GPIO.RISING)
                self.handle_hotword_trigger()
                logger.info(wake_message)
                time.sleep(5)
        
        thread = threading.Thread(target=gpio_wake)
        thread.daemon = True
        thread.start()
        return thread


# 创建全局聊天服务实例
chat_service = ChatService()

#-------------------------------------------------------------------------
# 公共接口函数
#-------------------------------------------------------------------------

def hwcallback():
    """热词唤醒回调函数"""
    chat_service.handle_hotword_trigger()

def startchat():
    """初始化并启动聊天服务"""
    # 启动命令处理线程
    chat_service.start_command_processor()
    
    # 初始化对话模型
    _initialize_dialog_model()
    
    # 启动热词检测（如果启用）
    _start_hotword_detection()
    
    # 设置GPIO唤醒（如果启用）
    chat_service.setup_gpio_wake()
    
    # 播放欢迎音
    play('Sound/ding.wav')
    play('Sound/welcome.wav')
    
    # 启动监控服务
    chat_service.monitor_service()

def _initialize_dialog_model():
    """初始化对话模型"""
    if not use_deepseek:
        return
        
    if chat_or_standard:
        try:
            logger.info("初始化流式TTS模式")
            dialog_module.read()
            
            # 验证TTS管理器是否正确初始化
            if hasattr(dialog_module, 'tts_manager'):
                logger.info("流式TTS管理器初始化成功")
                # 添加一个属性用于跟踪TTS是否已执行
                if not hasattr(dialog_module.tts_manager, 'tts_executed'):
                    dialog_module.tts_manager.tts_executed = False
            else:
                logger.error("流式TTS管理器初始化失败")
                
        except Exception as e:
            logger.error(f"流式TTS模式初始化失败: {e}")
    else:
        logger.info("初始化标准对话模式")
        dialog_module.read()

def _start_hotword_detection():
    """启动热词检测"""
    if not (snowboy_enable or porcupine_enable) or not config.get("wakebyhw"):
        return
        
    hotword_thread = threading.Thread(
        target=hotword_module.start, 
        args=(hwcallback,)
    )
    hotword_thread.daemon = True
    hotword_thread.start()
    chat_service.hotword_thread = hotword_thread

# 兼容旧版本的函数
work = chat_service.process_dialog
admin = chat_service.monitor_service
inter = chat_service.start_command_processor
exwake_button = lambda: None  # 空函数，已在ChatService中实现
exwake_dev = lambda: None     # 空函数，已在ChatService中实现

# 主程序入口
if __name__ == "__main__":
    startchat()
