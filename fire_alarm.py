#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
火灾预警系统
监控火焰和烟雾传感器，当检测到危险时发送邮件通知并语音播报
"""

import time
import json
import threading
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import paho.mqtt.client as mqtt_client
from loguru import logger

# 导入项目中的模块
from hardware_config import PIN_FLAME, PIN_SMOKE, MQTT_BROKER, MQTT_PORT, MQTT_TOPIC_SENSOR
from tts import ssml_save
from play import play

# 配置日志 - 提高基本日志级别，减少信息日志
logger.add("Log/fire_alarm.log", rotation="10 MB", compression="zip", level="WARNING")

# 邮件配置 - 这些应该放在配置文件中，这里为了演示直接写在代码中
EMAIL_HOST = "smtp.163.com"  # 邮件服务器，使用163邮箱
EMAIL_PORT = 25  # SMTP端口
EMAIL_USER = "pu221122@163.com"  # 发件人邮箱
EMAIL_PASSWORD = "BQfGjBUcrW3XAAKZ"  # 邮箱授权码
EMAIL_RECEIVER = "pupu5@qq.com"  # 接收通知的邮箱

# 火灾预警配置
ALARM_INTERVAL = 60  # 警报间隔（秒），防止频繁报警，从300秒改为60秒
VOICE_ALARM_TEXT = "警告！检测到火灾风险！请立即检查！"  # 语音播报文本
SENSOR_CHECK_INTERVAL = 1  # 传感器检测间隔（秒），实现近实时监控

# 语音文件配置
SOUND_DIR = "Sound"  # 语音文件目录
VOICE_CACHE = {
    "fire_alarm": {
        "text": VOICE_ALARM_TEXT,
        "file": os.path.join(SOUND_DIR, "fire_alarm.raw"),
        "generated": False
    }
}

class FireAlarmSystem:
    """火灾预警系统类"""
    
    def __init__(self):
        """初始化火灾预警系统"""
        # MQTT客户端
        self.client_id = f'fire-alarm-client-{int(time.time())}'
        self.client = mqtt_client.Client(self.client_id)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # 状态变量
        self.connected = False
        self.running = True
        self.last_alarm_time = 0  # 上次报警时间
        self.flame_detected = False  # 火焰检测状态
        self.smoke_detected = False  # 烟雾检测状态
        self.sensor_thread = None  # 传感器检测线程
        
        # GPIO设置
        self._setup_gpio()
        
        # 初始化语音文件
        self._init_voice_files()
        
        logger.info("火灾预警系统已初始化")
    
    def _setup_gpio(self):
        """设置GPIO引脚"""
        try:
            import RPi.GPIO as GPIO
            # 确保GPIO已经初始化
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # 设置火焰传感器引脚为输入模式，带上拉电阻
            if not GPIO.gpio_function(PIN_FLAME) == GPIO.IN:
                GPIO.setup(PIN_FLAME, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                
            # 设置烟雾传感器引脚为输入模式，带上拉电阻
            if not GPIO.gpio_function(PIN_SMOKE) == GPIO.IN:
                GPIO.setup(PIN_SMOKE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                
            logger.debug(f"GPIO引脚已设置: 火焰传感器={PIN_FLAME}, 烟雾传感器={PIN_SMOKE}")
        except Exception as e:
            logger.error(f"设置GPIO引脚失败: {e}")
    
    def _init_voice_files(self):
        """初始化语音文件，检查缓存是否存在，不存在则生成"""
        try:
            # 确保语音文件目录存在
            if not os.path.exists(SOUND_DIR):
                os.makedirs(SOUND_DIR)
                logger.debug(f"创建语音文件目录: {SOUND_DIR}")
            
            # 检查并生成火灾警报语音文件
            for voice_key, voice_data in VOICE_CACHE.items():
                if not os.path.exists(voice_data["file"]):
                    logger.info(f"语音文件 {voice_data['file']} 不存在，正在生成...")
                    ssml_save(voice_data["text"], voice_data["file"])
                    voice_data["generated"] = True
                    logger.info(f"语音文件 {voice_data['file']} 已生成")
                else:
                    voice_data["generated"] = True
                    logger.debug(f"使用缓存的语音文件: {voice_data['file']}")
        except Exception as e:
            logger.error(f"初始化语音文件失败: {e}")
    
    def connect(self):
        """连接到MQTT服务器"""
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT)
            logger.info(f"已连接到MQTT服务器: {MQTT_BROKER}:{MQTT_PORT}")
            self.connected = True
            return True
        except Exception as e:
            logger.error(f"连接MQTT服务器失败: {e}")
            self.connected = False
            return False
    
    def on_connect(self, client, userdata, flags, rc):
        """MQTT连接回调函数"""
        if rc == 0:
            logger.info("MQTT连接成功")
            # 订阅传感器数据主题
            client.subscribe(MQTT_TOPIC_SENSOR)
            logger.debug(f"已订阅主题: {MQTT_TOPIC_SENSOR}")
            
            # 订阅火焰和烟雾传感器特定主题
            client.subscribe(f"{MQTT_TOPIC_SENSOR}/flame")
            client.subscribe(f"{MQTT_TOPIC_SENSOR}/smoke")
            logger.debug("已订阅火焰和烟雾传感器主题")
        else:
            logger.error(f"MQTT连接失败，返回码: {rc}")
    
    def on_message(self, client, userdata, msg):
        """MQTT消息回调函数"""
        try:
            payload = json.loads(msg.payload.decode())
            logger.debug(f"收到消息: {payload}")
            
            # 处理传感器数据
            if msg.topic == f"{MQTT_TOPIC_SENSOR}/flame":
                prev_state = self.flame_detected
                self.flame_detected = payload.get("detected", False)
                # 只在状态变化或检测到火焰时记录日志
                if prev_state != self.flame_detected or self.flame_detected:
                    log_level = "WARNING" if self.flame_detected else "INFO"
                    getattr(logger, log_level.lower())(f"火焰传感器状态(MQTT): {'检测到火焰' if self.flame_detected else '正常'}")
                
            elif msg.topic == f"{MQTT_TOPIC_SENSOR}/smoke":
                prev_state = self.smoke_detected
                self.smoke_detected = payload.get("detected", False)
                # 只在状态变化或检测到烟雾时记录日志
                if prev_state != self.smoke_detected or self.smoke_detected:
                    log_level = "WARNING" if self.smoke_detected else "INFO"
                    getattr(logger, log_level.lower())(f"烟雾传感器状态(MQTT): {'检测到烟雾' if self.smoke_detected else '正常'}")
                
            # 处理综合传感器数据
            elif msg.topic == MQTT_TOPIC_SENSOR:
                # 从综合传感器数据中提取火焰和烟雾状态
                if "flame_detected" in payload:
                    prev_state = self.flame_detected
                    self.flame_detected = payload.get("flame_detected", False)
                    # 只在状态变化或检测到火焰时记录日志
                    if prev_state != self.flame_detected or self.flame_detected:
                        log_level = "WARNING" if self.flame_detected else "INFO"
                        getattr(logger, log_level.lower())(f"火焰传感器状态(综合数据): {'检测到火焰' if self.flame_detected else '正常'}")
                
                if "smoke_detected" in payload:
                    prev_state = self.smoke_detected
                    self.smoke_detected = payload.get("smoke_detected", False)
                    # 只在状态变化或检测到烟雾时记录日志
                    if prev_state != self.smoke_detected or self.smoke_detected:
                        log_level = "WARNING" if self.smoke_detected else "INFO"
                        getattr(logger, log_level.lower())(f"烟雾传感器状态(综合数据): {'检测到烟雾' if self.smoke_detected else '正常'}")
            
            # 检查是否需要触发报警
            self.check_alarm_condition()
            
        except json.JSONDecodeError:
            logger.error("无效的JSON格式")
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
    
    def read_sensors_directly(self):
        """直接从GPIO读取传感器数据"""
        try:
            import RPi.GPIO as GPIO
            
            # 读取火焰传感器
            flame_value = GPIO.input(PIN_FLAME)
            # 低电平(0)表示检测到火焰
            flame_detected = not flame_value
            
            # 读取烟雾传感器
            smoke_value = GPIO.input(PIN_SMOKE)
            # 低电平(0)表示检测到烟雾
            smoke_detected = not smoke_value
            
            # 更新状态 - 只在状态变化或检测到危险时记录日志
            if flame_detected != self.flame_detected:
                self.flame_detected = flame_detected
                log_level = "WARNING" if flame_detected else "INFO"
                getattr(logger, log_level.lower())(f"火焰传感器状态(直接读取): {'检测到火焰' if flame_detected else '正常'}")
            
            if smoke_detected != self.smoke_detected:
                self.smoke_detected = smoke_detected
                log_level = "WARNING" if smoke_detected else "INFO"
                getattr(logger, log_level.lower())(f"烟雾传感器状态(直接读取): {'检测到烟雾' if smoke_detected else '正常'}")
            
            # 如果检测到火焰或烟雾，立即检查是否需要报警
            if flame_detected or smoke_detected:
                self.check_alarm_condition()
                
            return flame_detected, smoke_detected
        except Exception as e:
            logger.error(f"直接读取传感器失败: {e}")
            return False, False
    
    def sensor_monitoring_thread(self):
        """传感器监控线程，直接从GPIO读取传感器数据"""
        logger.info("传感器监控线程已启动")
        
        while self.running:
            try:
                self.read_sensors_directly()
                # 短暂休眠，实现近实时监控
                time.sleep(SENSOR_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"传感器监控线程出错: {e}")
                time.sleep(1)  # 出错时稍微延长休眠时间
    
    def check_alarm_condition(self):
        """检查是否需要触发报警"""
        current_time = time.time()
        
        # 如果检测到火焰或烟雾，且距离上次报警已经超过设定的间隔
        if (self.flame_detected or self.smoke_detected) and (current_time - self.last_alarm_time > ALARM_INTERVAL):
            logger.warning("检测到火灾风险！触发报警...")
            
            # 更新上次报警时间
            self.last_alarm_time = current_time
            
            # 触发报警
            self.trigger_alarm()
    
    def trigger_alarm(self):
        """触发报警"""
        # 创建单独的线程处理报警，避免阻塞MQTT消息处理
        alarm_thread = threading.Thread(target=self._handle_alarm)
        alarm_thread.daemon = True
        alarm_thread.start()
    
    def _handle_alarm(self):
        """处理报警"""
        try:
            # 1. 发送邮件通知
            self.send_email_alert()
            
            # 2. 播放语音警报
            self.play_voice_alert()
            
            logger.info("报警处理完成")
        except Exception as e:
            logger.error(f"处理报警时出错: {e}")
    
    def send_email_alert(self):
        """发送邮件警报"""
        try:
            # 创建邮件内容
            msg = MIMEMultipart()
            msg['From'] = EMAIL_USER
            msg['To'] = EMAIL_RECEIVER
            msg['Subject'] = Header('火灾预警通知！', 'utf-8')
            
            # 邮件正文
            alert_type = []
            if self.flame_detected:
                alert_type.append("火焰")
            if self.smoke_detected:
                alert_type.append("烟雾")
            
            alert_text = "、".join(alert_type)
            current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            
            content = f"""
            <html>
            <body>
                <h2 style="color: red;">火灾预警通知</h2>
                <p>系统在 {current_time} 检测到以下火灾风险：</p>
                <p style="font-weight: bold; font-size: 16px;">检测到{alert_text}！</p>
                <p>请立即检查相关区域，确保安全。</p>
                <p>此邮件由系统自动发送，请勿回复。</p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(content, 'html', 'utf-8'))
            
            # 发送邮件
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.sendmail(EMAIL_USER, EMAIL_RECEIVER, msg.as_string())
            
            logger.info(f"火灾预警邮件已发送至 {EMAIL_RECEIVER}")
        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
    
    def play_voice_alert(self):
        """播放语音警报"""
        try:
            # 播放提示音
            play('Sound/ding.wav')
            
            # 检查火灾警报语音文件是否已生成
            if VOICE_CACHE["fire_alarm"]["generated"]:
                # 播放警报语音
                play(VOICE_CACHE["fire_alarm"]["file"])
                logger.info("火灾警报语音已播放")
            else:
                logger.warning("火灾警报语音文件未生成，尝试重新生成")
                # 尝试重新生成语音文件
                self._init_voice_files()
                if VOICE_CACHE["fire_alarm"]["generated"]:
                    play(VOICE_CACHE["fire_alarm"]["file"])
                    logger.info("火灾警报语音已播放")
                else:
                    logger.error("无法播放火灾警报语音")
        except Exception as e:
            logger.error(f"播放语音警报失败: {e}")
    
    def publish_sensor_data(self):
        """发布传感器数据（用于测试）"""
        if not self.connected:
            logger.warning("MQTT未连接，无法发布数据")
            return
        
        try:
            # 发布火焰传感器数据
            flame_data = {
                "detected": self.flame_detected,
                "timestamp": time.time()
            }
            self.client.publish(
                f"{MQTT_TOPIC_SENSOR}/flame",
                json.dumps(flame_data),
                qos=0
            )
            
            # 发布烟雾传感器数据
            smoke_data = {
                "detected": self.smoke_detected,
                "timestamp": time.time()
            }
            self.client.publish(
                f"{MQTT_TOPIC_SENSOR}/smoke",
                json.dumps(smoke_data),
                qos=0
            )
            
            logger.debug(f"已发布传感器数据: 火焰={self.flame_detected}, 烟雾={self.smoke_detected}")
        except Exception as e:
            logger.error(f"发布传感器数据时出错: {e}")
    
    def start(self):
        """启动火灾预警系统"""
        try:
            # 连接MQTT服务器
            if self.connect():
                # 启动MQTT循环
                self.client.loop_start()
                
                # 启动传感器监控线程
                self.sensor_thread = threading.Thread(target=self.sensor_monitoring_thread)
                self.sensor_thread.daemon = True
                self.sensor_thread.start()
                
                logger.info("火灾预警系统已启动")
                
                # 主循环
                while self.running:
                    time.sleep(1)
            else:
                logger.error("无法启动火灾预警系统，MQTT连接失败")
        except Exception as e:
            logger.error(f"启动火灾预警系统时出错: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """停止火灾预警系统"""
        self.running = False
        
        # 停止MQTT循环
        if self.connected:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT客户端已断开连接")
        
        # 等待传感器线程结束
        if self.sensor_thread and self.sensor_thread.is_alive():
            self.sensor_thread.join(timeout=2)
        
        logger.info("火灾预警系统已停止")

# 单例模式
_fire_alarm_system = None
_system_lock = threading.Lock()

def get_fire_alarm_system():
    """获取火灾预警系统实例（单例模式）"""
    global _fire_alarm_system
    
    with _system_lock:
        if _fire_alarm_system is None:
            _fire_alarm_system = FireAlarmSystem()
    
    return _fire_alarm_system

def start_fire_alarm_system():
    """启动火灾预警系统"""
    system = get_fire_alarm_system()
    
    # 创建线程运行系统
    thread = threading.Thread(target=system.start)
    thread.daemon = True
    thread.start()
    
    return system

# 测试代码
if __name__ == "__main__":
    # 启动火灾预警系统
    system = start_fire_alarm_system()
    
    try:
        # 模拟检测到火焰
        time.sleep(5)
        system.flame_detected = True
        system.publish_sensor_data()
        
        # 等待报警处理
        time.sleep(10)
        
        # 模拟检测到烟雾
        system.flame_detected = False
        system.smoke_detected = True
        system.publish_sensor_data()
        
        # 保持程序运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("程序被用户中断")
    finally:
        system.stop() 