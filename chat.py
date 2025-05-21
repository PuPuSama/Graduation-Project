#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
聊天服务模块
处理语音交互、对话流程和响应生成
"""

import os
import sys
import time
import threading
import arcade
from loguru import logger
from config import config
from play import play
from tts import ssml_wav

# 根据配置有条件地导入模块
from const_config import (
    snowboy_enable, porcupine_enable, gpio_wake_enable, 
    use_online_recognize, schedule_enable, 
    dev_enable, wlan_enable, use_deepseek, chat_or_standard
)

# 导入语音处理和对话模块
import speechpoint
import prompt_and_deal
import if_exit
import if_time_and_weather

# 根据配置导入热词检测模块
if snowboy_enable:
    from const_config import snowboypath
    sys.path.append(snowboypath)
    from snowboy import hotwordBymic
elif porcupine_enable:
    from const_config import porcupinepath
    sys.path.append(porcupinepath)
    from Porcupine import porcupine

# 根据配置导入其他功能模块
if gpio_wake_enable:
    import RPi.GPIO as GPIO

if use_online_recognize:
    import azure_reco

if schedule_enable:
    import schedule

if dev_enable:
    import dev_control
    import if_devControl

if wlan_enable:
    import mqtt_wlan

# 根据配置导入对话模型
if use_deepseek:
    if chat_or_standard:
        import deepseek_stream_with_tts
    else:
        import deepseek


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
        self.active_state = 0  # 0=无活动, 1=休眠激活, 2=运行时激活, 3=错误状态
        self.allow_running = True
        self.service_active = True
        
        # 文本输入相关
        self.text_input_enabled = False
        self.input_text = ''
        self.manual_input_enabled = False
        
        # 热词检测线程
        self.hotword_thread = None
    
    def handle_hotword_trigger(self):
        """处理热词唤醒事件"""
        logger.info('热词触发')
        
        # 根据当前状态决定行为
        if self.running and not self.allow_running:
            # 多次唤醒造成的错误状态
            self.active_state = 3
            return False
            
        if self.running:
            # 正在运行时被唤醒
            self.active_state = 2
            # 如果是流式模式，停止当前TTS
            if use_deepseek and chat_or_standard:
                deepseek_stream_with_tts.tts_manager.stop_tts()
            logger.warning('对话被中断')
        else:
            # 正常唤醒
            self.active_state = 1
    
    def monitor_service(self):
        """监控聊天服务状态的主循环"""
        while self.service_active:
            # 处理错误状态
            if self.active_state == 3:
                logger.error('聊天服务错误，程序即将退出')
                play('Sound/exit.wav')
                os._exit(0)
            
            # 检查音频播放状态
            is_playing = (self.chat_sound and self.chat_player and 
                          self.chat_sound.is_playing(self.chat_player))
            is_complete = (self.chat_sound and self.chat_player and 
                           self.chat_sound.is_complete(self.chat_player))
            
            # 没有声音播放且不在对话过程中时释放语音资源
            if not is_playing and not self.running:
                config.set(chat_enable=False)
            
            # 处理下一轮对话
            if (not self.running and not config.get("notify_enable") and 
                (self.active_state == 1 or 
                 (self.next_dialog and is_complete) or 
                 (self.next_dialog and use_deepseek and chat_or_standard and 
                  deepseek_stream_with_tts.tts_manager.tts_task and 
                  deepseek_stream_with_tts.tts_manager.tts_task.get()))):
                
                # 流式模式下添加延时
                if use_deepseek and chat_or_standard:
                    time.sleep(2)
                
                # 启动对话线程
                dialog_thread = threading.Thread(target=self.process_dialog)
                dialog_thread.daemon = True
                config.set(chat_enable=True)
                dialog_thread.start()
                logger.info('开始新对话')
            
            # 处理状态转换
            if self.active_state == 2:
                self.allow_running = False
                self.active_state = 1
            
            # 处理服务关闭
            if self.active_state == -1:
                self.service_active = False
            
            # 处理长时间播放的声音
            if is_playing:
                if is_complete:
                    try:
                        self.chat_sound.stop(self.chat_player)
                        self.sound_play_counter = 0
                        logger.info('通过监控函数停止声音播放')
                    except Exception:
                        logger.warning('停止声音播放失败')
                else:
                    self.sound_play_counter += 1
                    # 如果播放时间过长（约85秒），强制停止
                    if self.sound_play_counter >= 170:
                        try:
                            self.chat_sound.stop(self.chat_player)
                            logger.info('超时停止声音播放')
                        except Exception:
                            logger.warning('超时停止声音播放失败')
                        self.sound_play_counter = 0
            
            # 循环间隔
            time.sleep(0.5)
    
    def process_dialog(self):
        """处理完整的对话流程"""
        self.running = True
        self.next_dialog = True if self.next_enabled else False
        
        # 停止当前正在播放的声音
        self._stop_current_sound()
        
        # 重置激活状态
        self.active_state = 0
        
        # 录音和语音识别
        if not self._handle_voice_input():
            return
        
        # 重置输入标志
        self.manual_input_enabled = False
        self.text_input_enabled = False
        
        # 处理特殊命令
        if not self._handle_special_commands():
            return
        
        # 生成对话响应
        if not self._generate_response():
            return
        
        # 处理TTS和音频播放
        self._handle_audio_response()
        
        # 结束对话
        logger.info('对话结束')
        self.allow_running = True
        self.running = False
    
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
    
    def _handle_voice_input(self):
        """处理语音输入，返回是否成功"""
        # 如果已经有文本输入或手动输入，跳过录音
        if not self.allow_running or (self.text_input_enabled or self.manual_input_enabled):
            return True
            
        try:
            # 录音提示音
            play('Sound/ding.wav')
            logger.info('准备开始录音')
            
            # 录制语音
            speechpoint.record_file()
            
            # 录音结束提示音
            play('Sound/dong.wav')
            
        except Exception as e:
            logger.warning(f"录音出错: {e}")
            play('Sound/ding.wav')
            play('Sound/quit.wav')
            self._reset_dialog_state(False)
            return False
        
        # 语音识别
        if self.allow_running and not self.text_input_enabled:
            try:
                self.input_text = azure_reco.recognize()
                logger.info(f"识别结果: {self.input_text}")
            except Exception as e:
                logger.warning(f"语音识别失败: {e}")
                play('Sound/recoerror.wav')
                self._reset_dialog_state(False)
                return False
        
        return True
    
    def _handle_special_commands(self):
        """处理特殊命令，返回是否继续对话"""
        if not self.allow_running:
            return False
            
        # 检查是否结束对话
        if if_exit.ifend(self.input_text):
            self._reset_dialog_state(False)
            config.set(chat_enable=False)
            return False
        
        # 检查是否退出程序
        if if_exit.ifexit(self.input_text):
            # 保存对话历史
            if use_deepseek:
                if chat_or_standard:
                    deepseek_stream_with_tts.save()
                else:
                    deepseek.save()
            # 退出程序
            self._reset_dialog_state(False)
            os._exit(0)
            return False
        
        # 检查日程相关命令
        if self.allow_running and schedule_enable and schedule.if_schedule(self.input_text):
            self._reset_dialog_state(False)
            config.set(chat_enable=False)
            return False
        
        # 检查设备控制命令
        if self.allow_running and dev_enable and if_devControl.detect(self.input_text):
            self._reset_dialog_state(False)
            config.set(chat_enable=False)
            return False
        
        # 检查时间和天气相关命令
        if self.allow_running and if_time_and_weather.timedetect(self.input_text):
            self._stop_current_sound()
            self._reset_dialog_state(False)
            config.set(chat_enable=False)
            return False
        
        return True
    
    def _generate_response(self):
        """生成对话响应，返回是否成功"""
        if not self.allow_running:
            return False
            
        try:
            # 获取对话回复
            reply = prompt_and_deal.send(self.input_text)
            logger.info(f"回复: {reply}")
            config.set(answer=reply)
            
            # 处理MQTT消息
            if config.get("mqtt_message") is True:
                mqtt_wlan.wlan_client.send_message(config.get("answer"))
                config.set(mqtt_message=False)
                self._reset_dialog_state(False)
                return False
            
            # 等待流式TTS完成
            if use_deepseek and chat_or_standard and deepseek_stream_with_tts.tts_manager.tts_task:
                deepseek_stream_with_tts.tts_manager.tts_task.get()
            
            return True
            
        except Exception as e:
            logger.error(f'对话生成错误: {e}')
            play('Sound/ding.wav')
            play('Sound/gpterror.wav')
            self.allow_running = True
            self.running = False
            return False
    
    def _handle_audio_response(self):
        """处理TTS和音频播放"""
        # 跳过流式模式下的处理
        if not self.allow_running or (use_deepseek and chat_or_standard):
            return
            
        try:
            # 生成TTS音频
            if os.path.exists('Sound/answer.wav'):
                os.remove('Sound/answer.wav')
            
            reply = config.get("answer")
            ssml_wav(reply, 'Sound/answer.wav')
            logger.info('TTS生成完成')
        except Exception as e:
            logger.warning(f"TTS生成失败: {e}")
            play('Sound/ttserror.wav')
            self.allow_running = False
            return
        
        # 播放提示音和回复音频
        play('Sound/ding.wav')
        self.chat_sound = arcade.Sound('Sound/answer.wav')
        self.chat_player = self.chat_sound.play()
        time.sleep(0.5)
    
    def _reset_dialog_state(self, next_enabled=True):
        """重置对话状态"""
        self.next_dialog = next_enabled
        self.allow_running = True
        self.running = False
    
    def process_command(self, command):
        """处理外部命令"""
        if command == 'wake':
            logger.info('收到唤醒命令')
            self.active_state = 1
            return True
            
        elif command == 'get_audio_complete':
            logger.info('收到手动录音完成命令')
            self.manual_input_enabled = True
            self.next_enabled = False
            self.handle_hotword_trigger()
            return True
            
        elif command == 'shutdown':
            self.service_active = False
            return True
            
        elif command == 'stop' or (config.get("wakebyhw") is False and config.get("hw_started") is True):
            # 停止热词检测
            try:
                if snowboy_enable:
                    hotwordBymic.terminate()
                elif porcupine_enable:
                    porcupine.terminate()
                config.set(wakebyhw=False, hw_started=False)
            except Exception:
                logger.warning('停止热词检测失败')
            
            self.hotword_thread = None
            self.next_enabled = False
            return True
            
        elif (snowboy_enable or porcupine_enable) and (command == 'start' or 
              (config.get("wakebyhw") is True and config.get("hw_started") is False)):
            # 启动热词检测
            if self.hotword_thread is None:
                if snowboy_enable:
                    self.hotword_thread = threading.Thread(
                        target=hotwordBymic.start, 
                        args=(self.handle_hotword_trigger,)
                    )
                elif porcupine_enable:
                    self.hotword_thread = threading.Thread(
                        target=porcupine.start, 
                        args=(self.handle_hotword_trigger,)
                    )
                
                self.hotword_thread.daemon = True
                self.hotword_thread.start()
                config.set(wakebyhw=True, hw_started=True)
            
            self.next_enabled = True
            play('Sound/hwstartsucc.wav')
            return True
            
        elif command:
            logger.info(f'收到文本命令: {command}')
            self.input_text = command
            self.text_input_enabled = True
            self.handle_hotword_trigger()
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
    
    def setup_gpio_wake(self):
        """设置GPIO唤醒功能"""
        if not gpio_wake_enable:
            return []
            
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)  # 按钮
        GPIO.setup(18, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) # 外设
        
        # 按钮唤醒线程
        def button_wake():
            while True:
                GPIO.wait_for_edge(4, GPIO.RISING)
                self.handle_hotword_trigger()
                logger.info('通过物理按钮唤醒')
                time.sleep(5)
        
        # 外设唤醒线程
        def device_wake():
            while True:
                GPIO.wait_for_edge(18, GPIO.RISING)
                self.handle_hotword_trigger()
                logger.info('通过外设唤醒')
                time.sleep(5)
        
        # 创建并启动线程
        button_thread = threading.Thread(target=button_wake)
        button_thread.daemon = True
        button_thread.start()
        
        device_thread = threading.Thread(target=device_wake)
        device_thread.daemon = True
        device_thread.start()
        
        return [button_thread, device_thread]


# 创建全局聊天服务实例
chat_service = ChatService()

# 与之前版本兼容的接口函数
def hwcallback():
    """热词唤醒回调函数"""
    chat_service.handle_hotword_trigger()

def work():
    """处理对话流程"""
    chat_service.process_dialog()

def admin():
    """监控服务主循环"""
    chat_service.monitor_service()

def inter():
    """处理命令交互"""
    chat_service.start_command_processor()

def exwake_button():
    """按钮唤醒函数（已在ChatService中实现）"""
    pass

def exwake_dev():
    """设备唤醒函数（已在ChatService中实现）"""
    pass

def startchat():
    """初始化并启动聊天服务"""
    # 启动命令处理线程
    command_thread = chat_service.start_command_processor()
    
    # 初始化对话模型
    if use_deepseek:
        if chat_or_standard:
            deepseek_stream_with_tts.read()
        else:
            deepseek.read()
    
    # 启动热词检测（如果启用）
    if (snowboy_enable or porcupine_enable) and config.get("wakebyhw") is True:
        if snowboy_enable:
            hotword_thread = threading.Thread(
                target=hotwordBymic.start, 
                args=(hwcallback,)
            )
        elif porcupine_enable:
            hotword_thread = threading.Thread(
                target=porcupine.start, 
                args=(hwcallback,)
            )
        hotword_thread.daemon = True
        hotword_thread.start()
        chat_service.hotword_thread = hotword_thread
    
    # 设置GPIO唤醒（如果启用）
    gpio_threads = chat_service.setup_gpio_wake()
    
    # 播放欢迎音
    play('Sound/ding.wav')
    play('Sound/welcome.wav')
    
    # 启动监控服务
    admin()


if __name__ == "__main__":
    admin()
