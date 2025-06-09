#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MQTT传感器客户端
用于管理所有传感器数据的采集、发布以及控制设备（LED、蜂鸣器等）
"""

import time
import json
import threading
import random
import RPi.GPIO as GPIO
from paho.mqtt import client as mqtt_client
from loguru import logger

# 导入硬件配置
from hardware_config import (
    PIN_LED, PIN_BUZZER, PIN_DHT11, PIN_FLAME, PIN_SMOKE, 
    MQTT_BROKER, MQTT_PORT, MQTT_TOPIC_SENSOR, MQTT_TOPIC_CONTROL,
    MQTT_USERNAME, MQTT_PASSWORD, SENSOR_INTERVAL
)

# 导入传感器模块
from dht11_sensor import get_dht11_sensor
from led_control import get_led_controller

# 配置日志
logger.add("mqtt_client_log.log", rotation="10 MB", compression="zip", level="INFO")

class MQTTSensorClient:
    """MQTT传感器客户端类"""
    
    def __init__(self):
        """初始化MQTT客户端和传感器"""
        # 初始化GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # 获取LED控制器实例
        self.led_controller = get_led_controller()
        logger.info(f"LED控制器已初始化，连接到GPIO{PIN_LED}")
        
        # 获取DHT11传感器实例
        self.dht11_sensor = get_dht11_sensor(use_pulseio=False)
        logger.info("DHT11传感器已初始化，使用bitbang模式")
        
        # 初始化蜂鸣器引脚
        GPIO.setup(PIN_BUZZER, GPIO.OUT)
        GPIO.output(PIN_BUZZER, GPIO.LOW)  # 确保蜂鸣器是关闭状态
        logger.info(f"蜂鸣器已初始化，连接到GPIO{PIN_BUZZER}")
        
        # 初始化火焰传感器引脚
        GPIO.setup(PIN_FLAME, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        logger.info(f"火焰传感器已初始化，连接到GPIO{PIN_FLAME}")
        
        # 初始化烟雾传感器引脚
        GPIO.setup(PIN_SMOKE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        logger.info(f"烟雾传感器已初始化，连接到GPIO{PIN_SMOKE}")
        
        # 创建MQTT客户端
        client_id = f'raspberry-pi-client-{random.randint(0, 1000)}'
        self.client = mqtt_client.Client(client_id)
        if MQTT_USERNAME and MQTT_PASSWORD:
            self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        
        # 设置MQTT回调函数
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # 连接状态
        self.connected = False
        
        # 运行标志
        self.running = True
        
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
            # 订阅控制主题
            client.subscribe(MQTT_TOPIC_CONTROL)
            logger.info(f"已订阅主题: {MQTT_TOPIC_CONTROL}")
        else:
            logger.error(f"MQTT连接失败，返回码: {rc}")
    
    def on_message(self, client, userdata, msg):
        """MQTT消息回调函数"""
        try:
            payload = json.loads(msg.payload.decode())
            logger.info(f"收到消息: {payload}")
            
            # 处理控制命令
            if msg.topic == MQTT_TOPIC_CONTROL:
                self.handle_control_message(payload)
        except json.JSONDecodeError:
            logger.error("无效的JSON格式")
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
    
    def handle_control_message(self, payload):
        """处理控制消息"""
        if "device" not in payload or "state" not in payload:
            logger.warning("无效的控制消息格式")
            return
        
        device = payload["device"]
        state = payload["state"]
        
        if device == "led":
            self.control_led(state, payload.get("brightness"))
        elif device == "buzzer":
            self.control_buzzer(state)
        else:
            logger.warning(f"未知设备: {device}")
    
    def control_led(self, state, brightness=None):
        """
        控制LED灯
        
        参数:
            state: 布尔值，True表示开启，False表示关闭
            brightness: 亮度百分比(0-100)，可选
        """
        try:
            if state:
                if brightness is not None:
                    self.led_controller.turn_on(brightness)
                else:
                    self.led_controller.turn_on()
            else:
                self.led_controller.turn_off()
            
            # 发布LED状态更新
            self.publish_device_state("led", state, brightness)
            logger.info(f"LED状态已设置为: {'开启' if state else '关闭'}")
        except Exception as e:
            logger.error(f"控制LED时出错: {e}")
    
    def control_buzzer(self, state):
        """控制蜂鸣器"""
        try:
            GPIO.output(PIN_BUZZER, GPIO.HIGH if state else GPIO.LOW)
            logger.info(f"蜂鸣器状态: {'开启' if state else '关闭'}")
            # 发布蜂鸣器状态更新
            self.publish_device_state("buzzer", state)
        except Exception as e:
            logger.error(f"控制蜂鸣器时出错: {e}")
    
    def read_flame_sensor(self):
        """
        读取火焰传感器状态
        
        数字火焰传感器DO输出：
        - 低电平(0): 检测到火焰
        - 高电平(1): 未检测到火焰
        
        返回:
            布尔值，True表示检测到火焰，False表示未检测到
        """
        try:
            # 读取传感器状态（低电平表示检测到火焰）
            state = not GPIO.input(PIN_FLAME)
            return state
        except Exception as e:
            logger.error(f"读取火焰传感器失败: {e}")
            return False
    
    def read_smoke_sensor(self):
        """
        读取烟雾传感器状态
        
        数字烟雾传感器DO输出：
        - 低电平(0): 检测到烟雾
        - 高电平(1): 未检测到烟雾
        
        返回:
            布尔值，True表示检测到烟雾，False表示未检测到
        """
        try:
            # 读取传感器状态（低电平表示检测到烟雾）
            state = not GPIO.input(PIN_SMOKE)
            return state
        except Exception as e:
            logger.error(f"读取烟雾传感器失败: {e}")
            return False
    
    def publish_sensor_data(self):
        """发布传感器数据"""
        if not self.connected:
            logger.warning("MQTT未连接，无法发布数据")
            return
        
        try:
            # 获取DHT11传感器数据
            dht11_data = self.dht11_sensor.get_formatted_data()
            temperature = dht11_data["temperature"]
            humidity = dht11_data["humidity"]
            
            # 获取火焰传感器数据
            flame_detected = self.read_flame_sensor()
            
            # 获取烟雾传感器数据
            smoke_detected = self.read_smoke_sensor()
            
            # 构建传感器数据消息
            sensor_data = {
                "temperature": temperature,
                "humidity": humidity,
                "flame_detected": flame_detected,
                "smoke_detected": smoke_detected,
                "timestamp": time.time()
            }
            
            # 发布传感器数据
            self.client.publish(
                MQTT_TOPIC_SENSOR,
                json.dumps(sensor_data),
                qos=0  # 使用QoS 0减少网络开销
            )
            logger.info(f"已发布传感器数据: 温度={temperature}°C, 湿度={humidity}%, 火焰={flame_detected}, 烟雾={smoke_detected}")
            
            # 单独发布火焰传感器数据
            flame_data = {
                "detected": flame_detected,
                "timestamp": time.time()
            }
            self.client.publish(
                f"{MQTT_TOPIC_SENSOR}/flame",
                json.dumps(flame_data),
                qos=0
            )
            
            # 单独发布烟雾传感器数据
            smoke_data = {
                "detected": smoke_detected,
                "timestamp": time.time()
            }
            self.client.publish(
                f"{MQTT_TOPIC_SENSOR}/smoke",
                json.dumps(smoke_data),
                qos=0
            )
            
        except Exception as e:
            logger.error(f"发布传感器数据时出错: {e}")
    
    def publish_device_state(self, device, state, brightness=None):
        """发布设备状态"""
        if not self.connected:
            return
        
        try:
            # 构建设备状态消息
            device_state = {
                "device": device,
                "state": state,
                "timestamp": time.time()
            }
            
            # 如果是LED并且指定了亮度，则添加亮度信息
            if device == "led" and brightness is not None:
                device_state["brightness"] = brightness
            
            # 发布设备状态
            self.client.publish(
                f"{MQTT_TOPIC_CONTROL}/status",
                json.dumps(device_state),
                qos=0  # 使用QoS 0减少网络开销
            )
        except Exception as e:
            logger.error(f"发布设备状态时出错: {e}")
    
    def sensor_loop(self):
        """传感器数据采集循环"""
        while self.running:
            try:
                self.publish_sensor_data()
            except Exception as e:
                logger.error(f"传感器循环出错: {e}")
            
            # 按照设定的间隔读取数据
            time.sleep(SENSOR_INTERVAL)
    
    def start(self):
        """启动MQTT客户端和传感器循环"""
        try:
            # 连接MQTT服务器
            if self.connect():
                # 启动MQTT循环
                self.client.loop_start()
                
                # 启动传感器循环
                self.sensor_loop()
            else:
                logger.error("无法启动MQTT客户端，连接失败")
        except Exception as e:
            logger.error(f"启动MQTT客户端时出错: {e}")
        finally:
            # 清理资源
            self.stop()
    
    def stop(self):
        """停止MQTT客户端和传感器循环"""
        self.running = False
        
        # 停止MQTT循环
        if self.connected:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT客户端已断开连接")
        
        # 清理DHT11传感器资源
        self.dht11_sensor.cleanup()
        logger.info("DHT11传感器资源已释放")
        
        # 清理LED控制器资源
        self.led_controller.cleanup()
        logger.info("LED控制器资源已释放")
        
        # 清理GPIO资源（关闭蜂鸣器）
        GPIO.output(PIN_BUZZER, GPIO.LOW)
        logger.info("蜂鸣器已关闭")
        
        # 不清理全部GPIO，因为可能有其他程序在使用

# 直接运行测试
if __name__ == "__main__":
    client = MQTTSensorClient()
    try:
        client.start()
    except KeyboardInterrupt:
        client.stop()
        print("程序已退出") 